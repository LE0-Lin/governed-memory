import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from eval.longmemeval_data import Chunk
from eval.relevance_calibrate import choose_cutoff
from eval.relevance_replay import contexts, score_predictions
from eval.retrieval_evidence import load_cases
from governed_memory.budget import EvidenceBudget
from governed_memory.relevance import calibrated_cutoff

ROOT = Path(__file__).resolve().parents[1]


def test_relevance_splits_are_frozen_disjoint_and_have_valid_gold():
    subjects = {}
    for split in ("dev", "heldout"):
        data = load_cases(split)
        assert len(data["groups"]) == 8
        queries = [q for group in data["groups"] for q in group["queries"]]
        assert len(queries) == 80 and sum(bool(q["gold"]) for q in queries) == 48
        subjects[split] = {doc["subject"] for group in data["groups"] for doc in group["documents"]}
        for group in data["groups"]:
            ids = {doc["id"] for doc in group["documents"]}
            assert all(set(query["gold"]) <= ids for query in group["queries"])
    assert subjects["dev"].isdisjoint(subjects["heldout"])


def test_shipped_cutoff_matches_frozen_development_scores_and_model():
    directory = ROOT / "eval/results/relevance-calibration-v1-2026-11-13"
    pairs = json.loads((directory / "pair-scores.json").read_text())
    policy = json.loads((directory / "policy.json").read_text())
    expected = choose_cutoff([pair["score"] for pair in pairs if pair["positive"]])
    assert expected == policy["minimum_score"]
    reranker = SimpleNamespace(
        metadata={"model": policy["model"], "revision": policy["revision"], "scores": "raw logits"}
    )
    assert calibrated_cutoff(reranker) == expected
    reranker.metadata["revision"] = "different-weights"
    with pytest.raises(ValueError, match="does not match"):
        calibrated_cutoff(reranker)


def test_cutoff_grid_handles_negative_scores_and_retention_boundaries():
    assert choose_cutoff([-2.12, -1.0, 3.0], retention=1) == -2.2
    assert choose_cutoff(list(range(20)), retention=0.95) == 1.0
    with pytest.raises(ValueError):
        choose_cutoff([float("nan")])


def test_replay_reproduces_original_pool_before_filtering_and_rejects_bad_ids():
    documents = [
        Chunk("a", "s1", "2030", 0, 0, 5, "Database is PostgreSQL."),
        Chunk("b", "s2", "2030", 0, 0, 5, "A cat is sleeping."),
    ]
    budget, config = EvidenceBudget(), {"k": 8, "token_budget": 2048}
    original, tokens = budget.pack(documents, 2048, 8)
    row = dict(
        candidate_scores=[dict(chunk_id="b", score=-4.0), dict(chunk_id="a", score=3.0)],
        chunk_ids=[item["id"] for item in original],
        evidence_tokens=tokens,
    )
    result = contexts(row, documents, budget, config, 1.4)
    assert [item["id"] for item in result[0][1]] == ["a", "b"]
    assert [item["id"] for item in result[1][1]] == ["a"]
    row["candidate_scores"][0]["chunk_id"] = "unreconstructable"
    with pytest.raises(ValueError, match="cannot be reconstructed"):
        contexts(row, documents, budget, config, 1.4)


def test_external_summary_distinguishes_empty_answers_from_gold_session_recall():
    rows = [
        dict(question_id="positive", method="gated", chunk_ids=["a"], session_ids=["s1"]),
        dict(question_id="negative", method="gated", chunk_ids=[], session_ids=[]),
    ]
    summary = score_predictions(rows, {"positive": {"s1", "s2"}, "negative": set()})["gated"]
    assert summary["session_recall"] == 0.5
    assert summary["unanswerable_empty"] == 1 and summary["answerable_empty"] == 0
