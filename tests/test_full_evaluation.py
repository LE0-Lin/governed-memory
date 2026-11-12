import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from eval.full_run import MANIFEST, STRUCTURED_MANIFEST, read_json, write_json
from eval.full_score import judge_label, lexical_scores, summarize, verify_prediction_ids
from eval.longmemeval_data import retrieval_case
from eval.longmemeval_run import retrieve_case
from governed_memory.budget import EvidenceBudget
from governed_memory.generation import GeneratedText


def test_full_manifest_keeps_all_questions_and_the_original_subset():
    full = json.loads(MANIFEST.read_text())
    original = json.loads(Path("eval/longmemeval_manifest.json").read_text())
    ids = {case["id"] for case in full["cases"]}
    assert len(full["cases"]) == len(ids) == 500
    assert {case["id"] for case in original["cases"]} <= ids
    assert len(original["cases"]) == 14
    assert full["sha256"] == original["sha256"]
    assert full["k"] == original["k"] and full["token_budget"] == original["token_budget"]


def test_structured_protocol_changes_decoding_without_changing_the_questions_or_models():
    original = read_json(MANIFEST)
    structured = read_json(STRUCTURED_MANIFEST)
    changes = {"protocol", "answer_format", "format_enforcer_revision"}
    original_settings = {key: value for key, value in original.items() if key not in changes}
    structured_settings = {key: value for key, value in structured.items() if key not in changes}
    assert structured_settings == original_settings
    assert structured["answer_format"] == "json_schema"


def test_checkpoint_json_round_trips_unicode_text(tmp_path):
    path = tmp_path / "answer.json"
    value = {"answer": "数据库 🧪 São Paulo"}
    write_json(path, value)
    assert read_json(path) == value
    assert not path.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize(
    "text,expected",
    [("yes", True), ("Yes.", True), ("no!", False), ("yesterday", None), ("not yes", None)],
)
def test_judge_requires_an_unambiguous_label(text, expected):
    assert judge_label(text) is expected


def test_lexical_metrics_handle_articles_punctuation_and_repeated_tokens():
    assert lexical_scores("The BLUE.", "blue") == (1.0, 1.0)
    assert lexical_scores("red red blue", "red blue") == (0.0, 0.8)
    assert lexical_scores("", "blue") == (0.0, 0.0)


def test_missing_or_duplicate_prediction_rows_cannot_be_scored_as_a_complete_run():
    config = {"cases": [{"id": "one"}, {"id": "two"}], "methods": ["bm25", "hybrid"]}
    rows = [
        {"question_id": case["id"], "method": method}
        for case in config["cases"]
        for method in config["methods"]
    ]
    verify_prediction_ids(rows, config)
    with pytest.raises(ValueError):
        verify_prediction_ids(rows[:-1], config)
    with pytest.raises(ValueError):
        verify_prediction_ids([*rows, rows[0]], config)


def test_invalid_answers_and_judgments_remain_in_the_accuracy_denominator():
    rows = []
    for decision in [True, False, None]:
        rows.append(
            {
                "method": "bm25",
                "category": "knowledge-update",
                "judge_label": decision,
                "lexical_eligible": True,
                "exact_match": float(decision is True),
                "token_f1": float(decision is True),
                "abstain": False,
                "answer_error": "InvalidAnswer" if decision is False else None,
                "answer_latency_ms": 1.0,
            }
        )
    summary = summarize(rows)["bm25/all"]
    assert summary["questions"] == 3
    assert summary["local_judge_accuracy"] == pytest.approx(1 / 3)
    assert summary["answer_errors"] == summary["judge_invalid_or_failed"] == 1


async def test_labels_never_enter_the_generation_prompt():
    record = {
        "question_id": "example",
        "question_type": "single-session-user",
        "question": "Which database?",
        "question_date": "2023/01/02 00:00",
        "answer": "forbidden-reference-label",
        "answer_session_ids": ["forbidden-session-label"],
        "haystack_session_ids": ["session"],
        "haystack_dates": ["2023/01/01 00:00"],
        "haystack_sessions": [[{"role": "user", "content": "Use SQLite.", "has_answer": True}]],
    }

    class Embedder:
        model = SimpleNamespace(
            tokenizer=lambda text, **kwargs: {"offset_mapping": [(0, len(text))]}
        )

        async def create_batch(self, texts):
            return [[1.0, 0.0] for _ in texts]

    prompts = []

    class Generator:
        metadata = {"test_double": True}

        async def generate(self, messages, max_new_tokens, *, json_schema=None):
            prompts.append(json.dumps(messages))
            source = json.loads(messages[-1]["content"])["evidence"][0]["id"]
            return GeneratedText(
                json.dumps({"answer": "SQLite", "evidence_ids": [source], "abstain": False}),
                100,
                30,
                "stop",
            )

    config = {
        "methods": ["bm25"],
        "chunk_wordpieces": 200,
        "chunk_overlap": 40,
        "k": 8,
        "token_budget": 2048,
        "generation_max_tokens": 384,
    }
    rows = await retrieve_case(
        retrieval_case(record), config, Embedder(), None, EvidenceBudget(), Generator()
    )
    assert rows[0]["response"]["answer"] == "SQLite"
    assert json.loads(rows[0]["response"]["raw_model_text"])["evidence_ids"] == ["E1"]
    assert all("forbidden-" not in prompt and "has_answer" not in prompt for prompt in prompts)
