import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from governed_memory.answering import ABSTENTION, AnswerService, generate_answer, parse_answer
from governed_memory.errors import Denied
from governed_memory.generation import GeneratedText, TransformersGenerator
from governed_memory.identity import revoke_access
from governed_memory.mcp_server import build_server
from governed_memory.models import Candidate, GovernanceEvent
from governed_memory.retrieval import Retriever
from governed_memory.settings import Settings

from .conftest import approve, propose


class TestGenerator:
    __test__ = False
    metadata = {"test_double": True}

    def __init__(self, callback=None):
        self.callback = callback
        self.contexts = []

    async def generate(self, messages, max_new_tokens, *, json_schema=None):
        context = json.loads(messages[-1]["content"])["evidence"]
        self.contexts.append(context)
        if self.callback:
            self.callback()
        reply = {"answer": "SQLite", "evidence_ids": [context[0]["id"]], "abstain": False}
        if "anyOf" in (json_schema or {}):
            reply.pop("abstain")
        return GeneratedText(
            json.dumps(reply),
            100,
            30,
            "stop",
        )


@pytest.mark.parametrize("answer_format", ["json_schema", "conditional"])
async def test_answer_receives_authorized_evidence_and_never_writes_a_fact(context, answer_format):
    ledger, _, tokens = context
    public = approve(context, propose(context))
    private = ledger.propose(
        tokens["admin"],
        "demo",
        subject="storage",
        predicate="endpoint",
        value="private-placeholder",
        valid_from="2030-01-01T00:00:00Z",
        audience=["reader"],
    )
    approve(context, private)
    with Session(ledger.engine) as session:
        before = [set(session.scalars(select(model.id))) for model in (Candidate, GovernanceEvent)]
    generator = TestGenerator()
    response = await AnswerService(
        Retriever(ledger), generator, answer_format=answer_format
    ).answer(tokens["agent"], "demo", "storage database")
    assert response["reason"] == "ok"
    assert response["answer"] == "SQLite"
    assert [item["id"] for item in generator.contexts[0]] == ["E1"]
    assert response["evidence"][0]["candidate_id"] == public["id"]
    assert "private-placeholder" not in json.dumps(response, default=str)
    assert response["evidence_ids"] == [response["evidence"][0]["id"]]
    with Session(ledger.engine) as session:
        after = [set(session.scalars(select(model.id))) for model in (Candidate, GovernanceEvent)]
    assert after == before


async def test_no_evidence_abstains_without_loading_a_model(context):
    ledger, _, tokens = context
    generator = TestGenerator()
    response = await AnswerService(Retriever(ledger), generator).answer(
        tokens["agent"], "demo", "database"
    )
    assert response["abstain"] and response["answer"] == ABSTENTION
    assert response["evidence"] == []
    assert generator.contexts == []


@pytest.mark.parametrize("answer_format", ["json_schema", "conditional"])
async def test_withdrawal_during_generation_discards_the_complete_answer(context, answer_format):
    ledger, _, tokens = context
    candidate = approve(context, propose(context))
    generator = TestGenerator(
        lambda: ledger.withdraw_source(tokens["admin"], "demo", candidate["source_id"])
    )
    response = await AnswerService(
        Retriever(ledger), generator, answer_format=answer_format
    ).answer(tokens["agent"], "demo", "database")
    assert len(generator.contexts[0]) == 1
    assert response["reason"] == "evidence_changed"
    assert response["answer"] == ABSTENTION
    assert response["evidence"] == response["evidence_ids"] == []


async def test_withdrawing_uncited_prompt_evidence_also_discards_the_answer(context):
    ledger, _, tokens = context
    approve(context, propose(context))
    other = ledger.propose(
        tokens["agent"],
        "demo",
        subject="storage",
        predicate="backup",
        value="database snapshot",
        valid_from="2030-01-01T00:00:00Z",
    )
    approve(context, other)
    generator = TestGenerator()

    def withdraw_uncited_source():
        evidence = ledger.visible(tokens["agent"], "demo")
        uncited = next(item for item in evidence if item.text == generator.contexts[0][1]["text"])
        ledger.withdraw_source(tokens["admin"], "demo", uncited.source_id)

    generator.callback = withdraw_uncited_source
    response = await AnswerService(Retriever(ledger), generator).answer(
        tokens["agent"], "demo", "storage database"
    )
    assert len(generator.contexts[0]) == 2
    assert response["reason"] == "evidence_changed"
    assert response["answer"] == ABSTENTION
    assert response["evidence"] == response["evidence_ids"] == []


async def test_access_revoked_during_generation_never_returns_generated_text(context):
    ledger, _, tokens = context
    approve(context, propose(context))
    generator = TestGenerator(
        lambda: revoke_access(ledger.engine, tokens["admin"], "demo", "agent")
    )
    with pytest.raises(Denied):
        await AnswerService(Retriever(ledger), generator).answer(
            tokens["agent"], "demo", "database"
        )


@pytest.mark.parametrize(
    "reply",
    [
        {"answer": "SQLite", "evidence_ids": ["other-project"], "abstain": False},
        {"answer": "SQLite", "evidence_ids": [], "abstain": False},
        {"answer": "unknown", "evidence_ids": ["permitted"], "abstain": True},
        {"answer": "SQLite", "evidence_ids": ["permitted"], "abstain": "false"},
    ],
)
def test_invalid_citations_and_answer_schema_fail_closed(reply):
    with pytest.raises(ValueError):
        parse_answer(json.dumps(reply), [{"id": "permitted"}])


async def test_answer_tool_is_optional_and_has_no_operator_parameters(context):
    ledger, _, tokens = context
    server = build_server(
        Settings("unused", tokens["agent"], None, "", ""), ledger=ledger, generator=TestGenerator()
    )
    tools = await server.list_tools()
    assert {tool.name for tool in tools} == {
        "propose_memory",
        "search_memory",
        "explain_memory",
        "answer_memory",
    }
    answer = next(tool for tool in tools if tool.name == "answer_memory")
    assert not {"role", "token", "principal", "protected", "approved"} & set(
        answer.inputSchema["properties"]
    )


@pytest.mark.parametrize("raises", [False, True])
async def test_model_failures_do_not_expose_raw_text_or_exception_details(raises):
    class FailedGenerator:
        metadata = {"test_double": True}

        async def generate(self, *args, **kwargs):
            if raises:
                raise RuntimeError("private-runtime-detail")
            return GeneratedText("private-malformed-output", 100, 10, "stop")

    response = await generate_answer(
        FailedGenerator(), "Which database?", [{"id": "allowed", "text": "SQLite"}]
    )
    assert response["answer"] == ABSTENTION and response["abstain"]
    assert response["evidence_ids"] == []
    assert response["reason"] == ("generation_error" if raises else "invalid_model_response")
    assert "private-" not in json.dumps(response)
    assert "raw_model_text" not in response


@pytest.mark.models
async def test_actual_small_generator_uses_the_pinned_local_model():
    import os

    if os.environ.get("GM_TEST_REAL_GENERATION") != "1":
        pytest.skip("set GM_TEST_REAL_GENERATION=1 with downloaded small-model weights")
    generator = TransformersGenerator("small", os.environ.get("MEMORY_GENERATION_CACHE"))
    reply = await generator.generate(
        [{"role": "user", "content": "Return only the word blue."}], max_new_tokens=16
    )
    assert reply.text.strip().lower() == "blue"
    assert reply.prompt_tokens > 0 and 0 < reply.completion_tokens <= 16

    evidence = [{"id": "database-source", "text": "The project uses SQLite as its database."}]
    response = await generate_answer(generator, "Which database does the project use?", evidence)
    assert response["reason"] == "ok"
    assert "sqlite" in response["answer"].lower()
    assert response["evidence_ids"] == ["database-source"]
    evidence[0]["id"] = "another-source"
    repeated = await generate_answer(generator, "Which database does the project use?", evidence)
    assert repeated["reason"] == "ok"
    assert repeated["evidence_ids"] == ["another-source"]
    conditional = await generate_answer(
        generator, "Which database does the project use?", evidence, answer_format="conditional"
    )
    assert conditional["reason"] == "ok" and "sqlite" in conditional["answer"].lower()
    assert conditional["evidence_ids"] == ["another-source"]
    missing = await generate_answer(
        generator, "Who is the owner of the project?", evidence, answer_format="conditional"
    )
    assert missing["error"] is None
    if not missing["abstain"]:
        pytest.xfail(
            "Pinned 0.5B does not abstain here; conditional default requires 1.5B validation"
        )
    assert missing["reason"] == "model_abstained" and missing["abstain"]
    assert missing["evidence_ids"] == []
