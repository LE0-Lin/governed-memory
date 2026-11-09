import pytest

from eval.run import future_metadata_count, metrics


def test_evidence_recall_distinguishes_any_all_and_empty_gold():
    common = {
        "kind": "quality",
        "stale_count": 0,
        "unapproved_count": 0,
        "withdrawn_count": 0,
        "source_complete_count": 0,
        "evidence_tokens": 10,
        "latency_ms": 1,
    }
    rows = [
        {**common, "gold_ids": ["a", "b"], "predicted_ids": ["a"], "source_complete_count": 1},
        {**common, "gold_ids": ["c"], "predicted_ids": []},
        {**common, "gold_ids": [], "predicted_ids": []},
    ]
    result = metrics(rows)
    assert result["evidence_recall_at_k"] == pytest.approx(1 / 3)
    assert result["hit_any"] == 0.5
    assert result["hit_all"] == 0
    assert result["empty_gold_correct"] == result["empty_gold_total"] == 1


def test_attack_numerators_and_denominators_use_the_same_query_category():
    common = {
        "gold_ids": ["a"],
        "predicted_ids": ["a"],
        "stale_count": 0,
        "unapproved_count": 1,
        "withdrawn_count": 1,
        "source_complete_count": 1,
        "evidence_tokens": 10,
        "latency_ms": 1,
    }
    result = metrics([{**common, "kind": kind} for kind in ("quality", "poisoning", "withdrawal")])
    assert result["unapproved_query_successes"] == result["unapproved_query_attacks"] == 1
    assert result["withdrawal_query_successes"] == result["withdrawal_query_attacks"] == 1
    assert result["unapproved_query_leaks_all_categories"] == 3
    assert result["withdrawn_query_leaks_all_categories"] == 3


def test_future_metadata_diagnostic_flags_a_later_snapshot_closure():
    row = {
        "known_at": "2030-01-03T00:00:00Z",
        "predictions": [
            {"system_from": "2030-01-01T00:00:00Z", "system_until": "2030-01-05T00:00:00Z"},
            {"system_from": "2030-01-01T00:00:00Z", "system_until": None},
        ],
    }
    assert future_metadata_count(row) == 1
