import hashlib
import json
from pathlib import Path

from eval.cv_run import aggregate, populate

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_controlled_gold_matches_ledger_for_every_query(engine):
    protocol = json.loads((ROOT / "eval/cv-protocol.json").read_text(encoding="utf-8"))
    raw = (ROOT / "eval/cv-timelines.json").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == protocol["dataset"]["sha256"]
    data = json.loads(raw)
    ledger, token, project, candidates = populate(engine, data)
    assert len(data["queries"]) == 84
    for query in data["queries"]:
        actual = {
            item.candidate_id
            for item in ledger.visible(
                token, project, valid_at=query["valid_at"], known_at=query["known_at"]
            )
        }
        expected = {candidates[alias]["id"] for alias in query["eligible"]}
        assert actual == expected, query["id"]
        assert {candidates[alias]["id"] for alias in query["gold"]} <= expected


def test_controlled_metrics_keep_errors_and_negative_queries_in_their_denominators():
    rows = [
        dict(
            gold_ids=["a"],
            predicted_ids=["a", "stale"],
            stale_ids=["stale"],
            latency_ms=10,
            error=None,
        ),
        dict(gold_ids=["b"], predicted_ids=[], stale_ids=[], latency_ms=20, error="Failed"),
        dict(gold_ids=[], predicted_ids=["unrelated"], stale_ids=[], latency_ms=30, error=None),
    ]
    result = aggregate(rows)
    assert result["temporal_recall"] == 0.5
    assert result["stale_rate"] == 1 / 3
    assert result["errors"] == 1
    assert result["negative_stale_failures"] == 0
    assert result["negative_unrelated_results"] == 1
    assert result["latency_ms_p95"] == 29
