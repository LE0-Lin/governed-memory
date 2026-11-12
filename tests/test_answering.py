import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from governed_memory.answering import ABSTENTION, AnswerService, parse_answer
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

    async def generate(self, messages, max_new_tokens):
        context = json.loads(messages[-1]["content"])["evidence"]
        self.contexts.append(context)
        if self.callback:
            self.callback()
        return GeneratedText(
            json.dumps({"answer": "SQLite", "evidence_ids": [context[0]["id"]], "abstain": False}),
            100,
            30,
            "stop",
        )


async def test_answer_receives_authorized_evidence_and_never_writes_a_fact(context):
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
    response = await AnswerService(Retriever(ledger), generator).answer(
        tokens["agent"], "demo", "storage database"
    )
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


async def test_withdrawal_during_generation_discards_the_complete_answer(context):
    ledger, _, tokens = context
    candidate = approve(context, propose(context))
    generator = TestGenerator(
        lambda: ledger.withdraw_source(tokens["admin"], "demo", candidate["source_id"])
    )
    response = await AnswerService(Retriever(ledger), generator).answer(
        tokens["agent"], "demo", "database"
    )
    assert len(generator.contexts[0]) == 1
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
