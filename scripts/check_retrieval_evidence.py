"""Independently rescore the frozen v0.5 retrieval observations and external replay."""

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def checksum(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def verify_service(directory, protocol):
    rows = read_rows(directory / "observations.jsonl")
    reported = read_json(directory / "summary.json")
    manifest = read_json(directory / "manifest.json")
    assert not manifest["dirty_source"] and not manifest["source_changed_during_run"]
    assert manifest["storage"] == "postgresql"
    assert manifest["protocol_sha256"] == checksum(ROOT / "eval/retrieval_quality_protocol.json")
    fixtures, aliases = {}, {}
    for workload in ("legacy_cv", "heldout"):
        specification = protocol["datasets"][workload]
        path = ROOT / "eval" / specification["file"]
        assert checksum(path) == specification["sha256"]
        data = read_json(path)
        queries = data.get("queries") or [
            {**query, "eligible": [document["id"] for document in group["documents"]]}
            for group in data["groups"]
            for query in group["queries"]
        ]
        fixtures[workload] = {query["id"]: query for query in queries}
        aliases[workload] = read_json(directory / f"{workload}-aliases.json")
    groups, paired = defaultdict(list), defaultdict(dict)
    observed = set()
    for row in rows:
        workload, method = row["workload"], row["method"]
        query = fixtures[workload][row["query_id"]]
        assert set(row["gold_ids"]) == {aliases[workload][key] for key in query["gold"]}
        assert set(row["predicted_ids"]) <= {aliases[workload][key] for key in query["eligible"]}
        assert row["error"] is None and not row["stale_ids"]
        assert 0 < row["evidence_tokens"] <= protocol["service"]["token_budget"]
        assert len(row["predicted_ids"]) <= protocol["service"]["k"]
        assert math.isfinite(row["latency_ms"]) and row["latency_ms"] > 0
        identity = (workload, method, row["repetition"], row["query_id"])
        assert identity not in observed
        observed.add(identity)
        groups[f"{workload}/{method}"].append(row)
        paired[workload, row["repetition"], row["query_id"]][method] = row["predicted_ids"]
    expected = {
        (workload, method, repetition, query_id)
        for workload, queries in fixtures.items()
        for query_id in queries
        for method in protocol["service"]["methods"]
        for repetition in range(protocol["service"]["repetitions"])
    }
    assert observed == expected
    for methods in paired.values():
        assert methods["gated_cached"] == methods["gated_uncached"]
    assert set(groups) == set(reported)
    for name, group in groups.items():
        positive = [row for row in group if row["gold_ids"]]
        negative = [row for row in group if not row["gold_ids"]]
        expected_metrics = dict(
            observations=len(group),
            errors=0,
            positive_observations=len(positive),
            negative_observations=len(negative),
            gold_recall=sum(
                len(set(row["predicted_ids"]) & set(row["gold_ids"])) / len(row["gold_ids"])
                for row in positive
            )
            / len(positive),
            positive_empty=sum(not row["predicted_ids"] for row in positive),
            negative_empty=sum(not row["predicted_ids"] for row in negative),
            negative_returned=sum(len(row["predicted_ids"]) for row in negative),
            stale_count=0,
            document_computations=sum(row["document_computations"] for row in group),
            latency_ms_p50=percentile([row["latency_ms"] for row in group], 0.5),
            latency_ms_p95=percentile([row["latency_ms"] for row in group], 0.95),
            warm_repetitions_p95_ms=percentile(
                [row["latency_ms"] for row in group if row["repetition"] > 0], 0.95
            ),
        )
        assert expected_metrics.keys() == reported[name].keys()
        for key, value in expected_metrics.items():
            assert math.isclose(value, reported[name][key], rel_tol=1e-12, abs_tol=1e-9), (
                name,
                key,
            )
    return {"observations": len(rows), "paired_predictions_equal": True, "summary_matches": True}


def verify_replay(directory, dataset, protocol):
    import ijson

    specification = protocol["external_replay"]
    archived = ROOT / "eval" / specification["predictions"]
    assert checksum(archived) == specification["predictions_sha256"]
    originals = {
        row["question_id"]: row
        for row in read_rows(archived)
        if row["method"] == specification["method"]
    }
    provenance = read_json(directory / "provenance.json")
    assert not provenance["dirty_source"] and not provenance["source_changed_during_run"]
    assert checksum(directory / "predictions.jsonl") == provenance["predictions_sha256"]
    with dataset.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == (
            "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442"
        )
    with dataset.open("rb") as stream:
        labels = {
            record["question_id"]: set()
            if record["question_id"].endswith("_abs")
            else set(record["answer_session_ids"])
            for record in ijson.items(stream, "item")
        }
    rows = read_rows(directory / "predictions.jsonl")
    identities, groups = set(), defaultdict(list)
    for row in rows:
        identity = (row["question_id"], row["method"])
        assert identity not in identities
        identities.add(identity)
        original = originals[row["question_id"]]
        expected = original["chunk_ids"]
        if row["method"] == "frozen_cutoff":
            decisions = defaultdict(set)
            for pair in original["candidate_scores"]:
                decisions[pair["chunk_id"]].add(pair["score"] >= provenance["minimum_score"])
            assert all(len(decisions[key]) == 1 for key in expected)
            expected = [key for key in expected if True in decisions[key]]
        assert row["chunk_ids"] == expected
        groups[row["method"]].append(row)
    assert identities == {
        (key, method) for key in originals for method in ("archived_ungated", "frozen_cutoff")
    }
    reported = read_json(directory / "summary.json")
    for method, group in groups.items():
        counts = Counter(queries=len(group))
        for row in group:
            gold = labels[row["question_id"]]
            hits = len(gold & set(row["session_ids"]))
            counts["answerable" if gold else "unanswerable"] += 1
            counts["answerable_empty" if gold else "unanswerable_empty"] += not row["chunk_ids"]
            counts["gold_sessions"] += len(gold)
            counts["session_hits"] += hits
            counts["hit_any"] += bool(hits)
            counts["returned_chunks"] += len(row["chunk_ids"])
        counts["session_recall"] = counts["session_hits"] / counts["gold_sessions"]
        assert dict(counts) == reported[method]
    return {"cases": len(originals), "predictions": len(rows), "summary_matches": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    protocol = read_json(ROOT / "eval/retrieval_quality_protocol.json")
    result = {
        "service": verify_service(args.service, protocol),
        "external_replay": verify_replay(args.replay, args.dataset, protocol),
        "checker_sha256": checksum(Path(__file__)),
        "observations_sha256": checksum(args.service / "observations.jsonl"),
        "replay_predictions_sha256": checksum(args.replay / "predictions.jsonl"),
    }
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
