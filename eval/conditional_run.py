"""Evaluate one conditional-answer candidate without changing retrieved contexts."""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from eval.full_run import hardware, versions
from eval.longmemeval_data import (
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    chunks,
    records,
    retrieval_case,
    verify_dataset,
)
from eval.relevance_replay import contexts
from eval.retrieval_evidence import (
    ROOT,
    checksum,
    load_cases,
    load_protocol,
    source_snapshot,
    write_json,
)
from governed_memory.answering import generate_answer
from governed_memory.budget import EvidenceBudget, serialize
from governed_memory.generation import TransformersGenerator

MANIFEST = ROOT / "eval/conditional_v2_manifest.json"
PROTOCOL = ROOT / "eval/CONDITIONAL_ANSWER_V2_PROTOCOL.md"


def archived_contexts(dataset, model_cache):
    from transformers import AutoTokenizer

    specification = load_protocol()["external_replay"]
    path = ROOT / "eval" / specification["predictions"]
    if checksum(path) != specification["predictions_sha256"]:
        raise ValueError("archived prediction checksum mismatch")
    verify_dataset(dataset)
    previous = json.loads(path.with_name("provenance.json").read_text(encoding="utf-8"))
    originals = {
        row["question_id"]: row
        for row in map(json.loads, path.read_text(encoding="utf-8").splitlines())
        if row["method"] == specification["method"]
    }
    if len(originals) != 500 or any(row["error"] for row in originals.values()):
        raise ValueError("expected all 500 successful archived retrievals")
    tokenizer = AutoTokenizer.from_pretrained(
        EMBEDDING_MODEL,
        revision=EMBEDDING_REVISION,
        cache_dir=model_cache,
        token=False,
        trust_remote_code=False,
    )
    budget = EvidenceBudget()
    for record in records(dataset):
        case = retrieval_case(record)
        documents, _ = chunks(case, tokenizer, previous["manifest"])
        evidence = contexts(
            originals[case.id], documents, budget, previous["manifest"], -float("inf")
        )[0][1]
        yield dict(
            question_id=case.id,
            question=case.question,
            question_date=case.question_date,
            category=case.category,
            evidence=evidence,
        )


def development_contexts():
    for group in load_cases("dev")["groups"]:
        evidence = [
            {"id": doc["id"], "text": f"{doc['subject']} | {doc['predicate']}: {doc['value']}"}
            for doc in group["documents"]
        ]
        for query in group["queries"]:
            yield dict(question_id=query["id"], question=query["query"], evidence=evidence)


def development_metrics(rows):
    labels = {}
    for group in load_cases("dev")["groups"]:
        values = {doc["id"]: doc["value"].casefold() for doc in group["documents"]}
        for query in group["queries"]:
            labels[query["id"]] = [values[key] for key in query["gold"]]
    summary = {}
    for method in ("json_schema", "conditional"):
        selected = [row for row in rows if row["method"] == method]
        positive = [row for row in selected if labels[row["question_id"]]]
        negative = [row for row in selected if not labels[row["question_id"]]]
        summary[method] = {
            "queries": len(selected),
            "answer_errors": sum(bool(row["response"]["error"]) for row in selected),
            "negative_queries": len(negative),
            "valid_negative_abstentions": sum(
                row["response"]["abstain"] and not row["response"]["error"] for row in negative
            ),
            "positive_queries": len(positive),
            "positive_gold_included": sum(
                not row["response"]["error"]
                and not row["response"]["abstain"]
                and all(
                    value in row["response"]["answer"].casefold()
                    for value in labels[row["question_id"]]
                )
                for row in positive
            ),
        }
    return summary


async def run(args):
    source = source_snapshot()
    if source["dirty_source"]:
        raise ValueError("commit the candidate and protocol before inference")
    config = json.loads(MANIFEST.read_text(encoding="utf-8"))
    bindings = {
        **source,
        "manifest_sha256": checksum(MANIFEST),
        "conditional_protocol_sha256": checksum(PROTOCOL),
        "stage": args.stage,
        "versions": versions(),
        "hardware": hardware(args.device),
    }
    if args.output.exists():
        if not args.resume:
            raise FileExistsError("use a fresh output or resume unchanged inputs")
        start = json.loads((args.output / "start.json").read_text(encoding="utf-8"))
        if any(start[key] != value for key, value in bindings.items()):
            raise ValueError("resume requires identical source, protocol and runtime")
    else:
        args.output.mkdir(parents=True)
        write_json(
            args.output / "start.json", {**bindings, "started_at": datetime.now(UTC).isoformat()}
        )
    folder = args.output / "cases"
    folder.mkdir(exist_ok=True)
    generator = TransformersGenerator("standard", args.generation_cache, args.device)
    for mode in ("json_schema", "conditional"):
        await generate_answer(
            generator,
            "Which database?",
            [{"id": "warmup", "text": "Use SQLite."}],
            answer_format=mode,
        )
    cases = (
        development_contexts()
        if args.stage == "dev"
        else archived_contexts(args.dataset, args.model_cache)
    )
    rows, found = [], set()
    for number, case in enumerate(cases, 1):
        identifier = case["question_id"]
        context_hash = hashlib.sha256(serialize(case["evidence"]).encode()).hexdigest()
        path = folder / f"{identifier}.json"
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if any(
                row["context_sha256"] != context_hash or row["question_id"] != identifier
                for row in saved
            ):
                raise ValueError("saved case does not match its context")
        else:
            saved = []
            modes = ("json_schema", "conditional") if args.stage == "dev" else ("conditional",)
            for mode in modes:
                started = perf_counter()
                response = await generate_answer(
                    generator,
                    case["question"],
                    case["evidence"],
                    case.get("question_date"),
                    max_new_tokens=config["generation_max_tokens"],
                    retain_raw=True,
                    answer_format=mode,
                )
                elapsed = (perf_counter() - started) * 1000
                saved.append(
                    dict(
                        question_id=identifier,
                        category=case.get("category", "development"),
                        method=mode,
                        chunk_ids=[item["id"] for item in case["evidence"]],
                        context_sha256=context_hash,
                        response=response,
                        error=None,
                        latency_ms=elapsed,
                        answer_latency_ms=elapsed,
                    )
                )
            write_json(path, saved)
        rows.extend(saved)
        if identifier in found:
            raise ValueError("duplicate question ID")
        found.add(identifier)
        if number % 10 == 0:
            print(f"{args.stage}: completed {number} cases", flush=True)
    expected = 80 if args.stage == "dev" else 500
    if len(found) != expected:
        raise ValueError("incomplete experiment")
    predictions = args.output / "predictions.jsonl"
    with predictions.open("x", encoding="utf-8", newline="\n") as stream:
        stream.writelines(serialize(row) + "\n" for row in rows)
    final = source_snapshot()
    changed = (
        source["code_sha256"] != final["code_sha256"]
        or bindings["manifest_sha256"] != checksum(MANIFEST)
        or bindings["conditional_protocol_sha256"] != checksum(PROTOCOL)
    )
    write_json(
        args.output / "provenance.json",
        {
            **bindings,
            "completed_at": datetime.now(UTC).isoformat(),
            "generator": generator.metadata,
            "predictions_sha256": checksum(predictions),
            "rows": len(rows),
            "source_changed_during_run": changed,
            "retrieval_contexts_unchanged": True,
            "runtime_errors": sum(row["response"]["reason"] == "generation_error" for row in rows),
            "answer_errors": sum(bool(row["response"]["error"]) for row in rows),
        },
    )
    if args.stage == "dev":
        summary = development_metrics(rows)  # Labels opened after predictions are closed.
        write_json(args.output / "summary.json", summary)
        print(serialize(summary), flush=True)
    if changed:
        raise SystemExit("source changed during inference; outputs retained")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("dev", "external"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--model-cache", type=Path)
    parser.add_argument("--generation-cache", type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.stage == "external" and args.dataset is None:
        parser.error("--dataset is required for external inference")
    asyncio.run(run(args))
