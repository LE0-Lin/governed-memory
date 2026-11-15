import pytest

from governed_memory.errors import Denied
from governed_memory.identity import create_project, revoke_access
from governed_memory.retrieval import Retriever

from .conftest import approve, propose
from .test_relevance_cache import CountingEmbedder
from .test_source_support import add_support


def second_fact(context, subject="archive"):
    ledger, _, tokens = context
    return approve(
        context,
        ledger.propose(
            tokens["agent"],
            "demo",
            subject=subject,
            predicate="database",
            value="SQLite",
            valid_from="2030-01-01T00:00:00Z",
        ),
    )


def test_snapshot_filter_preserves_historical_payloads_and_empty_means_empty(context):
    ledger, clock, tokens = context
    approve(context, propose(context))
    historical = clock()
    before = ledger.visible(tokens["agent"], "demo", valid_at="2030-03-01T00:00:00Z")
    approve(
        context,
        ledger.propose(
            tokens["agent"],
            "demo",
            subject="storage",
            predicate="database",
            value="PostgreSQL",
            valid_from="2030-02-01T00:00:00Z",
        ),
    )
    assert (
        ledger.visible(
            tokens["agent"],
            "demo",
            known_at=historical,
            valid_at="2030-03-01T00:00:00Z",
            memory_ids=[before[0].id],
        )
        == before
    )
    assert ledger.visible(tokens["agent"], "demo", memory_ids=[]) == []
    assert ledger.visible(tokens["agent"], "demo", memory_ids=["unknown"]) == []


def test_filtered_reads_check_credentials_project_audience_and_new_provenance(context):
    ledger, _, tokens = context
    root = approve(context, propose(context))
    snapshot = ledger.visible(tokens["agent"], "demo")[0]
    support = add_support(context, root)
    ledger.withdraw_source(tokens["admin"], "demo", root["source_id"])
    actual = ledger.visible(tokens["agent"], "demo", memory_ids=[snapshot.id])
    assert actual == ledger.visible(tokens["agent"], "demo")
    assert actual[0].source_id == support["source_id"]
    private = ledger.propose(
        tokens["admin"],
        "demo",
        subject="private",
        predicate="database",
        value="secret",
        valid_from="2030-01-01T00:00:00Z",
        audience=["reader"],
    )
    approve(context, private)
    secret_id = next(
        item.id
        for item in ledger.visible(tokens["admin"], "demo")
        if item.candidate_id == private["id"]
    )
    assert ledger.visible(tokens["agent"], "demo", memory_ids=[secret_id]) == []
    assert len(ledger.visible(tokens["reader"], "demo", memory_ids=[secret_id])) == 1
    create_project(ledger.engine, tokens["admin"], "demo", "other")
    assert ledger.visible(tokens["admin"], "other", memory_ids=[snapshot.id]) == []
    with pytest.raises(Denied):
        ledger.visible(tokens["agent"], "other", memory_ids=[])
    with pytest.raises(Denied):
        ledger.visible("bad-token", "demo", memory_ids=[])
    revoke_access(ledger.engine, tokens["admin"], "demo", "agent")
    with pytest.raises(Denied):
        ledger.visible(tokens["agent"], "demo", memory_ids=[snapshot.id])


@pytest.mark.parametrize("change", ["none", "selected", "all", "grant", "budget"])
async def test_final_read_is_narrowed_but_reasons_and_current_access_stay_live(context, change):
    ledger, _, tokens = context
    root = approve(context, propose(context))
    other = second_fact(context)
    selected = next(
        item for item in ledger.visible(tokens["agent"], "demo") if item.candidate_id == root["id"]
    )

    class OneHit:
        metadata = {"test_double": True}

        async def rerank(self, query, documents):
            if change in {"selected", "all"}:
                ledger.withdraw_source(tokens["admin"], "demo", root["source_id"])
            if change == "all":
                ledger.withdraw_source(tokens["admin"], "demo", other["source_id"])
            if change == "grant":
                revoke_access(ledger.engine, tokens["admin"], "demo", "agent")
            return [selected]

    reads, original = [], ledger.visible

    def visible(*args, **kwargs):
        result = original(*args, **kwargs)
        reads.append((kwargs.get("memory_ids"), len(result)))
        return result

    ledger.visible = visible
    retriever = Retriever(ledger, embedder=CountingEmbedder(), reranker=OneHit())
    if change == "grant":
        with pytest.raises(Denied):
            await retriever.search(tokens["agent"], "demo", "database")
        return
    result = await retriever.search(
        tokens["agent"], "demo", "database", token_budget=2 if change == "budget" else 1024
    )
    assert all(ids is None for ids, _ in reads[:3])
    assert reads[3][0] == [selected.id]
    expected = {
        "none": "ok",
        "selected": "no_relevant_evidence",
        "all": "no_eligible_evidence",
        "budget": "token_budget",
    }
    assert result["reason"] == expected[change]
    if change == "none":
        assert reads[3][1] == 1 and len(reads) == 4
        assert [item["candidate_id"] for item in result["evidence"]] == [root["id"]]
    else:
        assert not result["evidence"]


async def test_pre_reranker_refresh_still_fills_from_beyond_fifty_withdrawn_hits(context):
    ledger, _, tokens = context
    for index in range(52):
        second_fact(context, f"service-{index:02}")
    snapshots = sorted(ledger.visible(tokens["agent"], "demo"), key=lambda item: item.id)

    class WithdrawTopFifty(CountingEmbedder):
        async def create(self, text):
            for item in snapshots[:50]:
                ledger.withdraw_source(tokens["admin"], "demo", item.source_id)
            return await super().create(text)

    class Reranker:
        metadata = {"test_double": True}

        async def rerank(self, query, documents):
            assert {item.id for item in documents} == {item.id for item in snapshots[50:]}
            return documents

    result = await Retriever(ledger, embedder=WithdrawTopFifty(), reranker=Reranker()).search(
        tokens["agent"], "demo", "database"
    )
    assert {item["id"] for item in result["evidence"]} == {item.id for item in snapshots[50:]}
