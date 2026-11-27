"""Paired evaluation of decomposed relevance filtering (v2) and the engineering corpus."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np

from eval.controlled_run import database, populate, processor_name
from eval.longmemeval_data import (
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    chunks,
    records,
    retrieval_case,
    verify_dataset,
)
from eval.metrics_cases import scaled_timelines
from eval.relevance_replay import contexts, score_predictions
from eval.retrieval_evidence import checksum, load_cases, write_json
from eval.retrieval_quality import populate_heldout
from eval.run import raw_evidence
from governed_memory.budget import EvidenceBudget, serialize
from governed_memory.embedding_cache import DocumentEmbeddingCache
from governed_memory.identity import bootstrap, issue_credential
from governed_memory.ingest import import_file
from governed_memory.ledger import Ledger, instant
from governed_memory.local_models import MiniLMEmbedder, MiniLMReranker
from governed_memory.relevance import calibrated_cutoff, calibrated_policy
from governed_memory.rerank_cache import RerankScoreCache
from governed_memory.retrieval import Retriever, hybrid_rank

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "eval/RELEVANCE_V2_AND_ENGINEERING_PROTOCOL.md"
ENGINEERING = ROOT / "eval/engineering-corpus.json"


def study_snapshot() -> dict:
    tracked = sorted((ROOT / "src").rglob("*.py")) + sorted(
        (ROOT / "src/governed_memory/data").glob("*.json")
    )
    tracked += [
        PROTOCOL,
        ENGINEERING,
        ROOT / "eval/relevance_v2_study.py",
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
    ]
    dirty = subprocess.check_output(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            "src",
            "eval/RELEVANCE_V2_AND_ENGINEERING_PROTOCOL.md",
            "eval/engineering-corpus.json",
            "eval/relevance_v2_study.py",
            "pyproject.toml",
            "uv.lock",
        ],
        cwd=ROOT,
        text=True,
    ).strip()
    digest = hashlib.sha256(
        b"".join(
            p.relative_to(ROOT).as_posix().encode() + b"\0" + p.read_bytes().replace(b"\r\n", b"\n")
            for p in tracked
            if p.is_file()
        )
    ).hexdigest()
    return {
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "dirty_source": bool(dirty),
        "code_sha256": digest,
        "protocol_sha256": checksum(PROTOCOL),
        "engineering_corpus_sha256": checksum(ENGINEERING),
    }


def populate_engineering(engine, data: dict):
    state = {"now": instant("2026-01-01T00:00:00Z")}
    ledger = Ledger(engine, lambda: state["now"])
    project = "engineering-decisions"
    admin = bootstrap(engine, "operator", project)
    agent = issue_credential(engine, admin, "coding-agent", project, "agent")
    candidates = {}
    events = []
    for rec in data["records"]:
        for field, order, action in (
            ("arrives", 0, "propose"),
            ("approves", 1, "approve"),
            ("rejects", 1, "reject"),
            ("withdrawn", 2, "withdraw"),
        ):
            if rec.get(field):
                events.append((rec[field], order, action, rec))
    with tempfile.TemporaryDirectory() as staging_dir:
        staging = Path(staging_dir)
        for index, (timestamp, _, action, rec) in enumerate(
            sorted(events, key=lambda item: (item[0], item[1], item[3]["alias"]))
        ):
            state["now"] = instant(timestamp)
            if action == "propose":
                if rec.get("parent"):
                    parent = candidates[rec["parent"]]
                    parent_version_id = next(
                        item.id
                        for item in ledger.visible(admin, project)
                        if item.candidate_id == parent["id"]
                    )
                    candidates[rec["alias"]] = ledger.propose(
                        agent,
                        project,
                        subject=rec["subject"],
                        predicate=rec["predicate"],
                        value=rec["value"],
                        valid_from=rec["valid_from"],
                        valid_until=rec["valid_until"],
                        locator=rec["locator"],
                        fragment=rec["fragment"],
                        parent_ids=[parent_version_id],
                    )
                elif rec["kind"] == "adr":
                    until_line = (
                        f'\nvalid_until = "{rec["valid_until"]}"' if rec["valid_until"] else ""
                    )
                    adr_path = staging / f"{index:02d}-{Path(rec['locator']).stem}.md"
                    adr_path.write_text(
                        "+++\n"
                        f"subject = {json.dumps(rec['subject'])}\n"
                        f"predicate = {json.dumps(rec['predicate'])}\n"
                        f"value = {json.dumps(rec['value'])}\n"
                        f"valid_from = {json.dumps(rec['valid_from'])}"
                        f"{until_line}\n+++\n{rec['fragment']}\n",
                        encoding="utf-8",
                    )
                    candidates[rec["alias"]] = import_file(ledger, agent, project, adr_path)[0]
                else:
                    jsonl_path = staging / f"{index:02d}-session.jsonl"
                    memory = {
                        "subject": rec["subject"],
                        "predicate": rec["predicate"],
                        "value": rec["value"],
                        "valid_from": rec["valid_from"],
                    }
                    if rec["valid_until"]:
                        memory["valid_until"] = rec["valid_until"]
                    jsonl_path.write_text(
                        json.dumps(
                            {"role": "assistant", "content": rec["fragment"], "memory": memory}
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    candidates[rec["alias"]] = import_file(ledger, agent, project, jsonl_path)[0]
            elif action == "approve" and rec.get("supports"):
                staged = candidates[rec["alias"]]
                target_cand = candidates[rec["supports"]]
                target_preview = ledger.preview(admin, project, target_cand["id"])
                ledger.approve_support(
                    admin,
                    project,
                    staged["id"],
                    target_cand["id"],
                    expected_revision=0,
                    expected_target_revision=target_preview["revision"],
                    expected_head=target_preview["head_revision"],
                    reason="corroborating ADR record",
                )
            elif action in {"approve", "reject"}:
                staged = candidates[rec["alias"]]
                head = ledger.preview(admin, project, staged["id"])["head_revision"]
                ledger.decide(
                    admin,
                    project,
                    staged["id"],
                    action,
                    0,
                    expected_head=head if action == "approve" else None,
                    reason="engineering governance decision",
                )
            elif action == "withdraw":
                staged = candidates[rec["alias"]]
                ledger.withdraw_source(admin, project, staged["source_id"])
    state["now"] = instant(data["now"])
    aliases = {alias: cand["id"] for alias, cand in candidates.items()}
    queries = []
    for q in data["queries"]:
        eligible = [
            item.candidate_id
            for item in ledger.visible(
                agent, project, valid_at=q["valid_at"], known_at=q["known_at"]
            )
        ]
        queries.append(
            {
                **q,
                "project": project,
                "token": agent,
                "gold_ids": [aliases[a] for a in q["gold"]],
                "eligible_ids": eligible,
            }
        )
    return ledger, queries, aliases


async def session_control_search(retriever: Retriever, query: dict, ranking_backend: str) -> dict:
    started = perf_counter()
    evidence = [
        item
        for item in raw_evidence(retriever.ledger, query["token"], query["project"])
        if item.system_from <= instant(query["known_at"])
    ]
    ranked = await hybrid_rank(
        query["query"],
        evidence,
        retriever.embedder,
        ranking_backend=ranking_backend,
        document_cache=retriever.document_cache,
    )
    candidates = ranked[:50]
    scores = await retriever.rerank_cache.scores(
        retriever.reranker, query["project"], query["query"], [item.text for item in candidates]
    )
    ordered = sorted(zip(candidates, scores, strict=True), key=lambda pair: (-pair[1], pair[0].id))
    packed, used = retriever.pack([item for item, _ in ordered], 1024, 5)
    result = {"evidence": packed, "evidence_tokens": used, "reason": "session_baseline"}
    serialize(result)
    result["latency_ms"] = (perf_counter() - started) * 1000
    return result


def summarize_group(rows: list[dict]) -> dict:
    positive = [r for r in rows if r["gold_ids"]]
    negative = [r for r in rows if not r["gold_ids"]]
    returned = sum(len(r["predicted_ids"]) for r in rows)
    stale = sum(len(r["stale_ids"]) for r in rows)
    first_pass = [r["latency_ms"] for r in rows if r["repetition"] == 0]
    repeats = [r["latency_ms"] for r in rows if r["repetition"] > 0]
    return {
        "observations": len(rows),
        "errors": sum(r["error"] is not None for r in rows),
        "positive_observations": len(positive),
        "negative_observations": len(negative),
        "positive_recall": float(
            np.mean(
                [
                    len(set(r["gold_ids"]) & set(r["predicted_ids"])) / len(r["gold_ids"])
                    for r in positive
                ]
            )
        )
        if positive
        else None,
        "positive_hit_all": sum(set(r["gold_ids"]) <= set(r["predicted_ids"]) for r in positive),
        "positive_empty": sum(not r["predicted_ids"] for r in positive),
        "negative_empty": sum(not r["predicted_ids"] for r in negative),
        "negative_empty_rate": (
            sum(not r["predicted_ids"] for r in negative) / len(negative) if negative else None
        ),
        "negative_returned_items": sum(len(r["predicted_ids"]) for r in negative),
        "returned_items": returned,
        "stale_items": stale,
        "stale_fraction": stale / returned if returned else 0.0,
        "overall_p50_ms": float(np.percentile([r["latency_ms"] for r in rows], 50)),
        "overall_p95_ms": float(np.percentile([r["latency_ms"] for r in rows], 95)),
        "first_pass_p95_ms": float(np.percentile(first_pass, 95)) if first_pass else None,
        "repeat_p95_ms": float(np.percentile(repeats, 95)) if repeats else None,
    }


def run_passage_replay(dataset_path: Path, passage_floor: float, strict_cutoff: float) -> dict:
    archived = ROOT / "eval/results/longmemeval-full-2026-11-12/v2/predictions.jsonl"
    verify_dataset(dataset_path)
    previous = json.loads(archived.with_name("provenance.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in archived.read_text(encoding="utf-8").splitlines()]
    originals = {
        row["question_id"]: row for row in rows if row["method"] == "learned_hybrid_cross_encoder"
    }
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        EMBEDDING_MODEL,
        revision=EMBEDDING_REVISION,
        cache_dir=os.environ.get("MEMORY_MODEL_CACHE"),
        token=False,
        trust_remote_code=False,
    )
    config = previous["manifest"]
    budget = EvidenceBudget()
    predictions = []
    for record in records(dataset_path):
        case = retrieval_case(record)
        original = originals[case.id]
        documents, _ = chunks(case, tokenizer, config)
        ungated, strict = contexts(original, documents, budget, config, strict_cutoff)
        _, passage_gated = contexts(original, documents, budget, config, passage_floor)
        for name, (_, evidence, tokens) in (
            ("unfiltered", ungated),
            ("strict_v1_1.4", strict),
            ("v2_passage_floor", passage_gated),
        ):
            predictions.append(
                {
                    "question_id": case.id,
                    "method": name,
                    "chunk_ids": [item["id"] for item in evidence],
                    "session_ids": list(dict.fromkeys(item["session_id"] for item in evidence)),
                    "evidence_tokens": tokens,
                }
            )
    labels = {
        record["question_id"]: set()
        if record["question_id"].endswith("_abs")
        else set(record["answer_session_ids"])
        for record in records(dataset_path)
    }
    return score_predictions(predictions, labels)


async def run_study(output: Path, dataset: Path | None, allow_dirty: bool = False):
    source = study_snapshot()
    if source["dirty_source"] and not allow_dirty:
        raise ValueError("commit source, protocol, and corpus before canonical execution")
    if output.exists():
        raise FileExistsError("preserve previous results; choose a new output directory")
    output.mkdir(parents=True)

    cache_dir = os.environ.get("MEMORY_MODEL_CACHE")
    embedder = MiniLMEmbedder(cache_dir)
    reranker = MiniLMReranker(cache_dir)
    strict_cutoff = calibrated_cutoff(reranker)
    v2_policy = calibrated_policy(reranker, strict=True)
    probe_retriever = Retriever(None, embedder=embedder, ranking_backend="auto")
    ranking_backend = probe_retriever.ranking_backend

    manifest = {
        **source,
        "started_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "os": platform.platform(),
        "cpu": processor_name(),
        "ranking_backend": ranking_backend,
        "embedding": embedder.metadata,
        "reranker": reranker.metadata,
        "strict_v1_cutoff": strict_cutoff,
        "v2_policy": {
            "version": v2_policy.version,
            "minimum_score": v2_policy.minimum_score,
            "minimum_anchor_score": v2_policy.minimum_anchor_score,
            "minimum_gain": v2_policy.minimum_gain,
            "passage_word_limit": v2_policy.passage_word_limit,
            "minimum_passage_score": v2_policy.minimum_passage_score,
        },
        "packages": {
            name: importlib.metadata.version(name)
            for name in (
                "governed-memory",
                "torch",
                "transformers",
                "sentence-transformers",
                "numpy",
                "sqlalchemy",
            )
        },
    }
    write_json(output / "manifest.json", manifest)

    rows = []
    workloads = ("timelines_1", "timelines_16", "heldout", "engineering")
    with (output / "observations.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for workload in workloads:
            with database() as engine:
                manifest["storage"] = engine.dialect.name
                if workload in {"timelines_1", "timelines_16"}:
                    cohorts = 1 if workload == "timelines_1" else 16
                    data = scaled_timelines(cohorts)
                    ledger, token, project, candidates = populate(engine, data)
                    aliases = {alias: cand["id"] for alias, cand in candidates.items()}
                    queries = [
                        {
                            **q,
                            "project": project,
                            "token": token,
                            "gold_ids": [aliases[a] for a in q["gold"]],
                            "eligible_ids": [aliases[a] for a in q["eligible"]],
                        }
                        for q in data["queries"]
                    ]
                    method_names = ("unfiltered", "strict_v1", "default_v2")
                elif workload == "heldout":
                    data = load_cases("heldout")
                    ledger, queries, aliases = populate_heldout(engine, data)
                    method_names = ("unfiltered", "strict_v1", "default_v2")
                else:
                    data = json.loads(ENGINEERING.read_text(encoding="utf-8"))
                    ledger, queries, aliases = populate_engineering(engine, data)
                    method_names = ("session_baseline", "unfiltered", "strict_v1", "default_v2")

                write_json(output / f"{workload}-aliases.json", aliases)
                retrievers = {}
                for name in method_names:
                    retrievers[name] = Retriever(
                        ledger,
                        embedder=embedder,
                        reranker=reranker,
                        ranking_backend="auto",
                        document_cache=DocumentEmbeddingCache(2048),
                        rerank_cache=RerankScoreCache(8192),
                        min_relevance_score=strict_cutoff if name == "strict_v1" else None,
                        relevance_policy=v2_policy if name == "default_v2" else None,
                    )
                await embedder.create("Synthetic warmup sentence.")
                await reranker.scores("warmup", ["Synthetic warmup fact."])

                for repetition in range(3):
                    for index, query in enumerate(queries):
                        shift = (index + repetition) % len(method_names)
                        rotated = method_names[shift:] + method_names[:shift]
                        for name in rotated:
                            retriever = retrievers[name]
                            started, error = perf_counter(), None
                            try:
                                if name == "session_baseline":
                                    result = await session_control_search(
                                        retriever, query, ranking_backend
                                    )
                                else:
                                    result = await retriever.search(
                                        query["token"],
                                        query["project"],
                                        query["query"],
                                        valid_at=query["valid_at"],
                                        known_at=query["known_at"],
                                        k=5,
                                        token_budget=1024,
                                    )
                            except Exception as exc:
                                error = type(exc).__name__
                                result = {
                                    "evidence": [],
                                    "evidence_tokens": 0,
                                    "reason": "error",
                                    "latency_ms": (perf_counter() - started) * 1000,
                                }
                            predicted = [item["candidate_id"] for item in result["evidence"]]
                            row = {
                                "workload": workload,
                                "method": name,
                                "repetition": repetition,
                                "query_id": query["id"],
                                "kind": query["kind"],
                                "query": query["query"],
                                "gold_ids": query["gold_ids"],
                                "predicted_ids": predicted,
                                "stale_ids": [
                                    cid for cid in predicted if cid not in query["eligible_ids"]
                                ],
                                "reason": result["reason"],
                                "evidence_tokens": result["evidence_tokens"],
                                "latency_ms": result["latency_ms"],
                                "error": error,
                            }
                            rows.append(row)
                            stream.write(serialize(row) + "\n")
                    stream.flush()
                    print(f"{workload}: repetition {repetition + 1}/3 complete", flush=True)

    groups = defaultdict(list)
    for row in rows:
        groups[f"{row['workload']}/{row['method']}"].append(row)
    summary = {key: summarize_group(group) for key, group in sorted(groups.items())}

    if dataset and dataset.exists():
        print("Running LongMemEval 500-question passage-branch replay...", flush=True)
        summary["longmemeval_passage_replay"] = run_passage_replay(
            dataset, v2_policy.minimum_passage_score, strict_cutoff
        )

    final_source = study_snapshot()
    manifest.update(
        completed_at=datetime.now(UTC).isoformat(),
        source_changed_during_run=source["code_sha256"] != final_source["code_sha256"],
        observations_sha256=checksum(output / "observations.jsonl"),
        reason_counts=dict(Counter(f"{r['workload']}/{r['method']}:{r['reason']}" for r in rows)),
    )
    write_json(output / "manifest.json", manifest)
    write_json(output / "summary.json", summary)
    print(serialize(summary))
    if manifest["source_changed_during_run"] or any(r["error"] for r in rows):
        raise SystemExit("study recorded errors or source change; inspect output")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / ".local/longmemeval/longmemeval_s_cleaned.json",
    )
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args()
    asyncio.run(run_study(args.output, args.dataset, allow_dirty=args.allow_dirty))
