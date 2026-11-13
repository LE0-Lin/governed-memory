"""Counterfactual cutoff replay of all 500 archived cross-encoder retrieval outputs."""

import argparse
import json
import math
import os
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from eval.longmemeval_data import (
    EMBEDDING_MODEL,
    EMBEDDING_REVISION,
    chunks,
    records,
    retrieval_case,
    verify_dataset,
)
from eval.retrieval_evidence import ROOT, checksum, load_protocol, source_snapshot, write_json
from governed_memory.budget import EvidenceBudget, serialize
from governed_memory.relevance import calibrated_cutoff


def contexts(row, documents, budget, config, cutoff):
    lookup = {}
    for document in documents:
        if document.id in lookup and document != lookup[document.id]:
            raise ValueError("ambiguous reconstructed chunk ID")
        lookup[document.id] = document
    scores = row["candidate_scores"]
    if not all(math.isfinite(item["score"]) for item in scores):
        raise ValueError("invalid archived candidate scores")
    counts = Counter(item["chunk_id"] for item in scores)
    if not counts.keys() <= lookup.keys():
        raise ValueError("archived chunks cannot be reconstructed")
    if counts - Counter(document.id for document in documents):
        raise ValueError("archived chunk multiplicity exceeds the reconstructed corpus")
    # Some public histories repeat an identical session. Preserve its archived
    # occurrences and individual logits rather than silently deduplicating them.
    ordered = sorted(scores, key=lambda item: (-item["score"], item["chunk_id"]))
    ranked = [lookup[item["chunk_id"]] for item in ordered]
    original, tokens = budget.pack(ranked, config["token_budget"], config["k"])
    if [item["id"] for item in original] != row["chunk_ids"]:
        raise ValueError("archived context packing could not be reproduced")
    if ranked and tokens != row["evidence_tokens"]:
        raise ValueError("archived context token count changed")
    filtered, filtered_tokens = budget.pack(
        [lookup[item["chunk_id"]] for item in ordered if item["score"] >= cutoff],
        config["token_budget"],
        config["k"],
    )
    if not {item["id"] for item in filtered} <= set(row["chunk_ids"]):
        raise ValueError("a monotone cutoff unexpectedly introduced a new context chunk")
    return [("archived_ungated", original, tokens), ("frozen_cutoff", filtered, filtered_tokens)]


def score_predictions(predictions, labels):
    groups = defaultdict(list)
    for row in predictions:
        gold = labels[row["question_id"]]
        groups[row["method"]].append((row, gold))
    summary = {}
    for method, group in groups.items():
        positive = [(row, gold) for row, gold in group if gold]
        negative = [row for row, gold in group if not gold]
        required = sum(len(gold) for _, gold in positive)
        summary[method] = {
            "queries": len(group),
            "answerable": len(positive),
            "unanswerable": len(negative),
            "answerable_empty": sum(not row["chunk_ids"] for row, _ in positive),
            "unanswerable_empty": sum(not row["chunk_ids"] for row in negative),
            "gold_sessions": required,
            "session_hits": sum(len(set(row["session_ids"]) & gold) for row, gold in positive),
            "session_recall": sum(len(set(row["session_ids"]) & gold) for row, gold in positive)
            / required,
            "hit_any": sum(bool(set(row["session_ids"]) & gold) for row, gold in positive),
            "returned_chunks": sum(len(row["chunk_ids"]) for row, _ in group),
        }
    return summary


def replay(dataset, output):
    source, protocol = source_snapshot(), load_protocol()
    if source["dirty_source"]:
        raise ValueError("commit source before recording an external replay")
    if output.exists():
        raise FileExistsError("preserve previous replay outputs")
    specification = protocol["external_replay"]
    archived = ROOT / "eval" / specification["predictions"]
    if checksum(archived) != specification["predictions_sha256"]:
        raise ValueError("archived predictions checksum mismatch")
    verify_dataset(dataset)
    previous = json.loads(archived.with_name("provenance.json").read_text(encoding="utf-8"))
    cutoff = calibrated_cutoff(SimpleNamespace(metadata=previous["reranker"]))
    rows = [json.loads(line) for line in archived.read_text(encoding="utf-8").splitlines()]
    originals = {
        row["question_id"]: row for row in rows if row["method"] == specification["method"]
    }
    if len(originals) != specification["cases"] or any(row["error"] for row in originals.values()):
        raise ValueError("expected 500 successful archived retrieval records")
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
    output.mkdir(parents=True)
    predictions, found = [], set()
    with (output / "predictions.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for record in records(dataset):
            case = retrieval_case(
                record
            )  # Deliberately no answer/session labels cross this boundary.
            original = originals[case.id]
            documents, _ = chunks(case, tokenizer, config)
            for method, evidence, tokens in contexts(original, documents, budget, config, cutoff):
                row = dict(
                    question_id=case.id,
                    method=method,
                    chunk_ids=[item["id"] for item in evidence],
                    session_ids=list(dict.fromkeys(item["session_id"] for item in evidence)),
                    evidence_tokens=tokens,
                    archived_evidence_tokens=original["evidence_tokens"],
                )
                predictions.append(row)
                stream.write(serialize(row) + "\n")
            found.add(case.id)
            if len(found) % 50 == 0:
                stream.flush()
                print(f"Reconstructed {len(found)}/500 archived contexts", flush=True)
    if found != originals.keys():
        raise ValueError("external case IDs differ from the archived experiment")
    # Predictions are closed before labels are opened for scoring.
    labels = {
        record["question_id"]: set()
        if record["question_id"].endswith("_abs")
        else set(record["answer_session_ids"])
        for record in records(dataset)
    }
    summary = score_predictions(predictions, labels)
    final = source_snapshot()
    duplicates = {}
    for identifier, row in originals.items():
        counts = Counter(item["chunk_id"] for item in row["candidate_scores"])
        repeated = {key: count for key, count in counts.items() if count > 1}
        if repeated:
            duplicates[identifier] = repeated
    write_json(output / "summary.json", summary)
    write_json(
        output / "provenance.json",
        {
            **source,
            "source_changed_during_run": source["code_sha256"] != final["code_sha256"],
            "completed_at": datetime.now(UTC).isoformat(),
            "minimum_score": cutoff,
            "archived_predictions_sha256": checksum(archived),
            "predictions_sha256": checksum(output / "predictions.jsonl"),
            "tokenizer": {"model": EMBEDDING_MODEL, "revision": EMBEDDING_REVISION},
            "archived_reranker": previous["reranker"],
            "new_generation": False,
            "new_latency_measurement": False,
            "external_data_previously_evaluated": True,
            "repeated_candidate_ids": duplicates,
        },
    )
    print(serialize(summary))
    if source["code_sha256"] != final["code_sha256"]:
        raise SystemExit("source changed during replay; outputs retained")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    replay(args.dataset, args.output)
