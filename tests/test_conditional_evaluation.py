import json

from eval.conditional_run import MANIFEST, development_contexts, development_metrics
from eval.full_run import STRUCTURED_MANIFEST


def test_conditional_manifest_preserves_all_original_context_and_model_settings():
    old = json.loads(STRUCTURED_MANIFEST.read_text())
    new = json.loads(MANIFEST.read_text())
    for key in (
        "cases",
        "generation",
        "generation_max_tokens",
        "judge",
        "judge_max_tokens",
        "sha256",
        "max_input_tokens",
        "k",
        "token_budget",
        "chunk_wordpieces",
        "chunk_overlap",
    ):
        assert new[key] == old[key]
    assert new["methods"] == ["conditional"]


def test_development_generation_inputs_exclude_query_labels_and_keep_every_fact():
    cases = list(development_contexts())
    assert len(cases) == len({case["question_id"] for case in cases}) == 80
    for case in cases:
        assert set(case) == {"question_id", "question", "evidence"}
        assert len(case["evidence"]) == 4
        assert all(set(item) == {"id", "text"} for item in case["evidence"])


def test_development_errors_do_not_count_as_successful_abstentions():
    cases = list(development_contexts())
    rows = [
        dict(
            question_id=case["question_id"],
            method=method,
            response=dict(abstain=True, error="InvalidAnswer", answer=""),
        )
        for case in cases
        for method in ("json_schema", "conditional")
    ]
    for value in development_metrics(rows).values():
        assert value["queries"] == value["answer_errors"] == 80
        assert value["positive_queries"] == 48 and value["negative_queries"] == 32
        assert value["valid_negative_abstentions"] == value["positive_gold_included"] == 0
