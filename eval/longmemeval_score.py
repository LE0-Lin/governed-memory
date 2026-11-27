"""Score saved retrieval IDs only, after inference has finished. Never imports a model."""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from eval.longmemeval_data import category, records


def score(dataset: Path, predictions: Path):
    rows = [json.loads(line) for line in predictions.read_text(encoding="utf-8").splitlines()]
    requested = {row["question_id"] for row in rows}
    labels = {}
    for record in records(dataset):
        if record["question_id"] in requested:
            labels[record["question_id"]] = {
                "gold": set(record["answer_session_ids"]),
                "category": category(record),
            }
    if requested != labels.keys():
        raise ValueError("missing score labels")
    groups = defaultdict(list)
    for row in rows:
        label = labels[row["question_id"]]
        gold = label["gold"] if label["category"] != "abstention" else set()
        predicted = set(row["session_ids"])
        row.update(
            gold_session_ids=sorted(gold),
            evidence_hits=len(gold & predicted),
            gold_count=len(gold),
            hit_any=bool(gold & predicted),
            hit_all=bool(gold) and gold <= predicted,
            abstention_case=label["category"] == "abstention",
        )
        groups[row["method"] + "/all"].append(row)
        groups[row["method"] + "/" + label["category"]].append(row)
    summary = {}
    for name, group in sorted(groups.items()):
        answerable = [row for row in group if row["gold_count"]]
        required = sum(row["gold_count"] for row in answerable)
        summary[name] = {
            "queries": len(group),
            "answerable": len(answerable),
            "gold_sessions": required,
            "session_recall": sum(row["evidence_hits"] for row in answerable) / required
            if required
            else None,
            "hit_any": sum(row["hit_any"] for row in answerable) / len(answerable)
            if answerable
            else None,
            "hit_all": sum(row["hit_all"] for row in answerable) / len(answerable)
            if answerable
            else None,
            "abstention_cases": sum(row["abstention_case"] for row in group),
            "abstention_cases_returning_context": sum(
                row["abstention_case"] and bool(row["chunk_ids"]) for row in group
            ),
            "latency_ms_p50": float(np.percentile([r["latency_ms"] for r in group], 50)),
            "latency_ms_p95": float(np.percentile([r["latency_ms"] for r in group], 95)),
            "mean_evidence_tokens": float(np.mean([r["evidence_tokens"] for r in group])),
            "failures": sum(bool(r.get("error")) for r in group),
        }
    return rows, summary
