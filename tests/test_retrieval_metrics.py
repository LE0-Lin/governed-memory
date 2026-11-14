import json
from collections import defaultdict

import pytest

from eval.cv_run import populate
from eval.metrics_cases import scaled_timelines
from eval.metrics_rescore import verify
from eval.retrieval_evidence import checksum, write_json
from eval.retrieval_metrics import paired_equivalence, summarize


@pytest.mark.parametrize("size", [1, 4])
def test_scaled_labels_match_ledger_without_deriving_gold_from_it(engine, size):
    data = scaled_timelines(size)
    assert len(data["facts"]) == 72 * size and len(data["queries"]) == 84
    ledger, token, project, candidates = populate(engine, data)
    for query in data["queries"]:
        eligible = {candidates[alias]["id"] for alias in query["eligible"]}
        actual = {
            item.candidate_id
            for item in ledger.visible(
                token, project, valid_at=query["valid_at"], known_at=query["known_at"]
            )
        }
        assert actual == eligible, query["id"]
        assert {candidates[alias]["id"] for alias in query["gold"]} <= eligible


def test_large_workload_keeps_every_query_type_and_covers_every_cohort():
    data = scaled_timelines(16)
    assert len(data["facts"]) == 1152 and len(data["queries"]) == 84
    assert len({query["id"].partition("/")[0] for query in data["queries"]}) == 16
    assert all(len(query["eligible"]) == 192 for query in data["queries"])
    for fact in data["facts"]:
        if fact.get("parent"):
            assert fact["parent"].partition("/")[0] == fact["alias"].partition("/")[0]


def test_metrics_keep_first_pass_failures_separate_from_repeat_speed():
    rows = [
        {
            "gold_ids": ["a"],
            "predicted_ids": [],
            "stale_ids": [],
            "latency_ms": 100,
            "error": "Failed",
            "repetition": 0,
            "reranker_pair_computations": 1,
        },
        {
            "gold_ids": ["a"],
            "predicted_ids": ["a"],
            "stale_ids": [],
            "latency_ms": 10,
            "error": None,
            "repetition": 1,
            "reranker_pair_computations": 0,
        },
    ]
    result = summarize(rows)
    assert result["temporal_recall"] == 0.5 and result["errors"] == 1
    assert result["first_pass_p95_ms"] == 100 and result["repeat_p95_ms"] == 10
    assert result["reranker_pair_computations"] == 1


def test_pair_gate_detects_token_or_source_changes_even_with_the_same_fact_ids():
    common = {
        "workload": "one",
        "query_id": "q",
        "repetition": 0,
        "predicted_ids": ["a"],
        "evidence_tokens": 10,
        "evidence_sha256": "source-one",
        "reason": "ok",
        "error": None,
    }
    rows = [{**common, "method": "governed_control"}, {**common, "method": "governed_score_cache"}]
    assert paired_equivalence(rows) == {"pairs": 1, "mismatches": []}
    rows[1]["evidence_sha256"] = "source-two"
    assert paired_equivalence(rows)["mismatches"] == [("one", "q", 0)]


def test_independent_rescore_checks_fixture_gold_and_keeps_all_observations(tmp_path):
    write_json(
        tmp_path / "tiny-fixture.json",
        {"queries": [{"id": "q", "gold": ["original"], "eligible": ["original"]}]},
    )
    write_json(tmp_path / "tiny-aliases.json", {"original": "candidate"})
    methods = ("session_baseline", "governed_control", "governed_score_cache")
    groups = defaultdict(list)
    rows = []
    for repetition in range(3):
        for method in methods:
            row = {
                "workload": "tiny",
                "query_id": "q",
                "repetition": repetition,
                "method": method,
                "predicted_ids": ["candidate"],
                "gold_ids": ["candidate"],
                "stale_ids": [],
                "evidence_tokens": 10,
                "evidence_sha256": "source",
                "reason": "ok",
                "latency_ms": 10.0,
                "error": None,
                "reranker_pair_computations": 1,
            }
            rows.append(row)
            groups[f"tiny/{method}"].append(row)
    stream = tmp_path / "observations.jsonl"
    stream.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    write_json(tmp_path / "summary.json", {key: summarize(group) for key, group in groups.items()})
    write_json(
        tmp_path / "manifest.json",
        {
            "datasets": {"tiny": checksum(tmp_path / "tiny-fixture.json")},
            "methods": methods,
            "cache": {"tiny": {method: {"rerank": None} for method in methods}},
            "source_unchanged": True,
        },
    )
    receipt = verify(tmp_path)
    assert receipt["observations"] == 9 and receipt["paired_comparisons"] == 3
    assert receipt["paired_mismatches"] == 0
    rows[0]["gold_ids"] = ["invented"]
    stream.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    with pytest.raises(AssertionError):
        verify(tmp_path)
