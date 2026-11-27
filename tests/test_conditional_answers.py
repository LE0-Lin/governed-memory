import json
from types import SimpleNamespace

import pytest

from governed_memory.answering import (
    ABSTENTION,
    AnswerService,
    answer_schema,
    generate_answer,
    parse_answer,
)
from governed_memory.generation import GeneratedText
from governed_memory.settings import Settings

from .test_answer_format import accepts


@pytest.mark.parametrize(
    "reply,valid",
    [
        ({"answer": None}, True),
        ({"answer": "SQLite", "evidence_ids": ["E1"]}, True),
        ({"answer": "SQLite", "evidence_ids": []}, False),
        ({"answer": "SQLite", "evidence_ids": ["E2"]}, False),
        ({"answer": "", "evidence_ids": ["E1"]}, False),
        ({"answer": None, "evidence_ids": ["E1"]}, False),
        ({"answer": False}, False),
    ],
)
def test_conditional_schema_enforces_branch_invariants_with_the_actual_decoder(reply, valid):
    library = pytest.importorskip("lmformatenforcer")
    schema = answer_schema([{"id": "actual"}], answer_format="conditional")
    parser = library.JsonSchemaParser(schema)
    assert accepts(parser, json.dumps(reply)) is valid
    if valid:
        response = parse_answer(json.dumps(reply), [{"id": "actual"}], answer_format="conditional")
        assert response["abstain"] is (reply["answer"] is None)
        assert response["evidence_ids"] == ([] if response["abstain"] else ["actual"])
    else:
        with pytest.raises(ValueError):
            parse_answer(json.dumps(reply), [{"id": "actual"}], answer_format="conditional")


@pytest.mark.parametrize(
    "reply", [[], {"status": False}, {"status": "insufficient_evidence", "answer": "invented"}]
)
def test_conditional_parser_rejects_fields_outside_its_branch(reply):
    with pytest.raises(ValueError):
        parse_answer(json.dumps(reply), [{"id": "actual"}], answer_format="conditional")


async def test_conditional_wire_format_preserves_public_response_and_empty_context_shortcut():
    class Generator:
        metadata = {"test_double": True}
        calls = 0

        async def generate(self, messages, max_new_tokens, *, json_schema):
            self.calls += 1
            assert "anyOf" in json_schema
            return GeneratedText('{"answer":null}', 100, 10, "stop")

    generator = Generator()
    response = await generate_answer(
        generator,
        "Who is the owner?",
        [{"id": "actual", "text": "Use SQLite."}],
        answer_format="conditional",
    )
    assert response["answer"] == ABSTENTION and response["evidence_ids"] == []
    assert response["reason"] == "model_abstained" and response["abstain"]
    assert response["generation"]["format"] == "conditional"
    await generate_answer(generator, "Who is the owner?", [], answer_format="conditional")
    assert generator.calls == 1


@pytest.mark.parametrize(
    "profile,expected",
    [
        ("standard", "conditional"),
        ("small", "json_schema"),
        ("judge", "json_schema"),
        (None, "json_schema"),
    ],
)
def test_only_the_validated_profile_changes_its_service_default(profile, expected):
    generator = SimpleNamespace(metadata={"profile": profile})
    assert AnswerService(None, generator).answer_format == expected
    assert (
        AnswerService(None, generator, answer_format="json_schema").answer_format == "json_schema"
    )


def test_operator_can_restore_the_legacy_format_and_invalid_configuration_fails_early(monkeypatch):
    monkeypatch.setenv("MEMORY_ANSWER_FORMAT", "json_schema")
    assert Settings.from_env().answer_format == "json_schema"
    monkeypatch.setenv("MEMORY_ANSWER_FORMAT", "")
    assert Settings.from_env().answer_format is None
    monkeypatch.setenv("MEMORY_ANSWER_FORMAT", "invalid")
    with pytest.raises(ValueError, match="MEMORY_ANSWER_FORMAT"):
        Settings.from_env()
