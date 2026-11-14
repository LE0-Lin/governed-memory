"""Recompute the frozen retrieval metrics from fixtures and raw observations."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from eval.retrieval_evidence import checksum, write_json


def verify(directory):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    summaries = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    expected = {}
    for workload, digest in manifest["datasets"].items():
        path = directory / f"{workload}-fixture.json"
        assert checksum(path) == digest, workload
        data = json.loads(path.read_text(encoding="utf-8"))
        aliases = json.loads((directory / f"{workload}-aliases.json").read_text(encoding="utf-8"))
        if workload == "heldout":
            queries = [
                dict(query, eligible=[doc["id"] for doc in group["documents"]])
                for group in data["groups"]
                for query in group["queries"]
            ]
        else:
            queries = data["queries"]
        for query in queries:
            expected[(workload, query["id"])] = (
                {aliases[identifier] for identifier in query["gold"]},
                {aliases[identifier] for identifier in query["eligible"]},
            )
    rows = [
        json.loads(line)
        for line in (directory / "observations.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    keys = [(row["workload"], row["query_id"], row["repetition"], row["method"]) for row in rows]
    required = {
        (workload, query_id, repeat, method)
        for workload, query_id in expected
        for repeat in range(3)
        for method in manifest["methods"]
    }
    assert len(keys) == len(set(keys)) and set(keys) == required
    groups, pairs = defaultdict(list), defaultdict(dict)
    for row in rows:
        gold, eligible = expected[(row["workload"], row["query_id"])]
        assert set(row["gold_ids"]) == gold
        assert set(row["stale_ids"]) == set(row["predicted_ids"]) - eligible
        assert row["evidence_tokens"] <= 1024 and len(row["predicted_ids"]) <= 5
        groups[f"{row['workload']}/{row['method']}"].append(row)
        if row["method"] != "session_baseline":
            pairs[(row["workload"], row["query_id"], row["repetition"])][row["method"]] = row
    for name, selected in groups.items():
        published = summaries[name]
        positive = [row for row in selected if row["gold_ids"]]
        negative = [row for row in selected if not row["gold_ids"]]
        returned = sum(len(row["predicted_ids"]) for row in selected)
        stale = sum(len(row["stale_ids"]) for row in selected)
        calculated = {
            "observations": len(selected),
            "positive_observations": len(positive),
            "negative_observations": len(negative),
            "errors": sum(row["error"] is not None for row in selected),
            "temporal_recall": float(
                np.mean(
                    [
                        len(set(row["predicted_ids"]) & set(row["gold_ids"])) / len(row["gold_ids"])
                        for row in positive
                    ]
                )
            ),
            "returned": returned,
            "stale_count": stale,
            "stale_rate": stale / returned if returned else 0.0,
            "negative_stale_failures": sum(bool(row["stale_ids"]) for row in negative),
            "negative_unrelated_results": sum(
                len(row["predicted_ids"]) - len(row["stale_ids"]) for row in negative
            ),
            "reranker_pair_computations": sum(
                row["reranker_pair_computations"] for row in selected
            ),
        }
        for key, value in calculated.items():
            assert published[key] == value, (name, key)
        for phase, subset in (
            ("", selected),
            ("first_pass_", [row for row in selected if row["repetition"] == 0]),
            ("repeat_", [row for row in selected if row["repetition"] > 0]),
        ):
            for percentile in (50, 95):
                key = f"{phase}p{percentile}_ms" if phase else f"latency_ms_p{percentile}"
                assert published[key] == float(
                    np.percentile(
                        [row["latency_ms"] for row in subset], percentile, method="linear"
                    )
                )
        workload, method = name.split("/")
        cache = manifest["cache"][workload][method]["rerank"]
        if cache:
            assert cache["scoring_requests"] == calculated["reranker_pair_computations"]
    mismatches = 0
    for methods in pairs.values():
        before, after = methods["governed_control"], methods["governed_score_cache"]
        mismatches += any(
            before[key] != after[key]
            for key in ("predicted_ids", "evidence_tokens", "evidence_sha256", "reason", "error")
        )
    return {
        "observations": len(rows),
        "unique_workload_queries": len(expected),
        "summary_groups": len(groups),
        "paired_comparisons": len(pairs),
        "paired_mismatches": mismatches,
        "execution_errors": sum(row["error"] is not None for row in rows),
        "governed_stale_results": sum(
            len(row["stale_ids"]) for row in rows if row["method"] != "session_baseline"
        ),
        "observations_sha256": checksum(directory / "observations.jsonl"),
        "source_unchanged_during_run": manifest["source_unchanged"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = verify(args.results)
    if args.output:
        if args.output.exists():
            raise FileExistsError("retain previous verification receipts")
        write_json(args.output, receipt)
    print(json.dumps(receipt, indent=2))
    if (
        receipt["execution_errors"]
        or receipt["governed_stale_results"]
        or receipt["paired_mismatches"]
        or not receipt["source_unchanged_during_run"]
    ):
        raise SystemExit("verification failed; observations retained")
