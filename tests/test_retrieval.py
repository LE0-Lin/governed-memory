import pytest

from governed_memory.graph_adapter import project_pending
from governed_memory.retrieval import Retriever, serialize

from .conftest import approve, propose


class UntrustedProjection:
    def __init__(self, ids):
        self.ids = ids
        self.received = []

    async def rank(self, query, project, allowed_ids, limit):
        self.received = allowed_ids
        return self.ids


class OfflineProjection:
    async def rank(self, *args):
        raise ConnectionError("unavailable")

    async def upsert(self, item):
        raise ConnectionError("unavailable")


async def test_stale_graph_never_leaks_or_starves_valid_evidence(context):
    ledger, _, tokens = context
    old = approve(context, propose(context))
    with_ids = ledger.visible(tokens["agent"], "demo")
    old_id = with_ids[0].id
    ledger.withdraw_source(tokens["admin"], "demo", old["source_id"])
    valid = approve(context, propose(context, "PostgreSQL"))
    graph = UntrustedProjection([old_id, "foreign-project-id"])
    result = await Retriever(ledger, graph).search(tokens["agent"], "demo", "database")
    assert old_id not in graph.received
    assert [e["candidate_id"] for e in result["evidence"]] == [valid["id"]]
    assert "SQLite" not in serialize(result)


async def test_projection_outage_keeps_durable_jobs_and_serves_fallback(context):
    ledger, _, tokens = context
    approve(context, propose(context))
    graph = OfflineProjection()
    assert await project_pending(ledger, graph) == {"projected": 0, "failed": 1}
    assert len(ledger.pending()) == 1
    result = await Retriever(ledger, graph).search(tokens["agent"], "demo", "database")
    assert result["evidence"][0]["value"] == "SQLite"
    assert result["backend"] == "ledger-fallback:graph-unavailable"


async def test_token_budget_counts_complete_evidence_and_sources(context):
    ledger, _, tokens = context
    approve(context, propose(context, "数据🙂 " * 1000))
    retriever = Retriever(ledger)
    result = await retriever.search(tokens["agent"], "demo", "database", token_budget=200)
    assert result["evidence"] == []
    assert result["reason"] == "token_budget"
    result = await retriever.search(tokens["agent"], "demo", "database", token_budget=16000)
    actual = len(retriever.encoding.encode(serialize(result["evidence"])))
    assert result["evidence_tokens"] == actual <= 16000
    assert result["evidence"][0]["content_hash"]


async def test_revocation_during_graph_search_is_rechecked(context):
    ledger, _, tokens = context
    candidate = approve(context, propose(context))

    class RevokingGraph:
        async def rank(self, query, project, allowed_ids, limit):
            ledger.withdraw_source(tokens["admin"], "demo", candidate["source_id"])
            return allowed_ids

    result = await Retriever(ledger, RevokingGraph()).search(tokens["agent"], "demo", "database")
    assert result["evidence"] == []


async def test_revoked_projection_miss_never_reaches_external_fallback_embedder(context):
    ledger, _, tokens = context
    candidate = approve(context, propose(context))
    embedded = []

    class CapturingEmbedder:
        async def create(self, text):
            embedded.append(text)
            return [1.0, 0.0]

    class RevokingGraph:
        embedder = CapturingEmbedder()

        async def rank(self, query, project, allowed_ids, limit):
            ledger.withdraw_source(tokens["admin"], "demo", candidate["source_id"])
            return []

    result = await Retriever(ledger, RevokingGraph()).search(tokens["agent"], "demo", "database")
    assert result["evidence"] == []
    assert embedded == []


@pytest.mark.parametrize("budget,k", [(0, 5), (32769, 5), (100, 0), (100, 51)])
async def test_invalid_budgets(context, budget, k):
    ledger, _, tokens = context
    with pytest.raises(ValueError):
        await Retriever(ledger).search(tokens["agent"], "demo", "x", token_budget=budget, k=k)
