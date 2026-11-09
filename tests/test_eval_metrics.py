import pytest

from eval.run import metrics


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
