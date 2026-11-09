import copy
import json
import re
from dataclasses import asdict

from eval.longmemeval_data import chunks, retrieval_case
from eval.longmemeval_score import score


class WordTokenizer:
    def __call__(self, text, **kwargs):
        return {"offset_mapping": [match.span() for match in re.finditer(r"\S+", text)]}


def sample():
    return {
        "question_id": "example",
        "question_type": "multi-session",
        "question": "Which database is used?",
        "question_date": "2030/01/03 (Thu) 12:00",
        "answer": "LABEL-ONLY-SECRET",
        "answer_session_ids": ["history"],
        "haystack_session_ids": ["history", "future"],
        "haystack_dates": ["2030/01/01 (Tue) 12:00", "2030/01/04 (Fri) 12:00"],
        "haystack_sessions": [
            [{"role": "user", "content": "Use the PostgreSQL database.", "has_answer": True}],
            [{"role": "user", "content": "Future discussion."}],
        ],
    }


def test_score_labels_never_cross_the_retrieval_case_boundary():
    original = sample()
    modified = copy.deepcopy(original)
    modified["answer"] = "DIFFERENT-LABEL"
    modified["answer_session_ids"] = ["different-session"]
    modified["haystack_sessions"][0][0]["has_answer"] = False
    a, b = retrieval_case(original), retrieval_case(modified)
    assert a == b
    assert "LABEL-ONLY-SECRET" not in json.dumps(asdict(a))
    prepared, excluded = chunks(a, WordTokenizer(), {"chunk_wordpieces": 3, "chunk_overlap": 1})
    assert excluded == ["future"]
    assert all(chunk.session_id == "history" for chunk in prepared)
    assert {chunk.message_index for chunk in prepared} == {0}


def test_external_scoring_separates_partial_recall_and_abstention(tmp_path):
    answerable, abstention = sample(), sample()
    answerable["answer_session_ids"] = ["history", "second-evidence"]
    abstention.update(question_id="example_abs", answer_session_ids=["absent-evidence"])
    dataset, predictions = tmp_path / "dataset.json", tmp_path / "predictions.jsonl"
    dataset.write_text(json.dumps([answerable, abstention]))
    rows = [
        {
            "question_id": qid,
            "method": "bm25",
            "session_ids": ["history"],
            "chunk_ids": ["chunk"],
            "latency_ms": 1,
            "evidence_tokens": 20,
            "error": None,
        }
        for qid in ("example", "example_abs")
    ]
    predictions.write_text("".join(json.dumps(row) + "\n" for row in rows))
    _, result = score(dataset, predictions)
    assert result["bm25/all"]["session_recall"] == 0.5
    assert result["bm25/all"]["hit_any"] == 1
    assert result["bm25/all"]["hit_all"] == 0
    assert result["bm25/all"]["abstention_cases_returning_context"] == 1
