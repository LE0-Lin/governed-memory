import os

import pytest

from governed_memory.authorization import provision
from governed_memory.errors import Denied
from governed_memory.identity import revoke_access
from governed_memory.rerank_cache import RerankScoreCache
from governed_memory.retrieval import Retriever
from governed_memory.settings import Settings

from .conftest import approve, propose
from .test_relevance_cache import CountingEmbedder
from .test_source_support import add_support


class Scorer:
    def __init__(self):
        self.metadata = {"revision": "one", "test_double": True}
        self.calls = []
        self.callback = None

    async def scores(self, query, texts):
        self.calls.append((query, list(texts)))
        if self.callback:
            self.callback()
        return [2.0 for _ in texts]


async def test_keys_cover_exact_query_text_project_and_model_without_caching_text():
    model, cache = Scorer(), RerankScoreCache(8)
    result = await cache.scores(model, "one", "query", ["a", "b", "a"])
    result[0] = -1
    assert await cache.scores(model, "one", "query", ["a"]) == [2.0]
    await cache.scores(model, "one", "Query", ["a"])
    await cache.scores(model, "one", "query", ["A"])
    await cache.scores(model, "two", "query", ["a"])
    model.metadata["revision"] = "two"
    await cache.scores(model, "one", "query", ["a"])
    assert model.calls == [
        ("query", ["a", "b"]),
        ("Query", ["a"]),
        ("query", ["A"]),
        ("query", ["a"]),
        ("query", ["a"]),
    ]
    assert cache.info()["scoring_requests"] == 6


async def test_scores_are_bounded_and_lru_eviction_recomputes_only_missing_pairs():
    model, cache = Scorer(), RerankScoreCache(2)
    await cache.scores(model, "demo", "query", ["a", "b"])
    await cache.scores(model, "demo", "query", ["a"])
    await cache.scores(model, "demo", "query", ["c"])
    await cache.scores(model, "demo", "query", ["b"])
    assert cache.info() == {"entries": 2, "hits": 1, "scoring_requests": 4, "evictions": 2}
    assert model.calls == [("query", ["a", "b"]), ("query", ["c"]), ("query", ["b"])]


@pytest.mark.parametrize("bad", [[float("nan"), 1.0], [1.0], [[1.0], [2.0]], ["PRIVATE", 1.0]])
async def test_invalid_predictions_never_enter_the_cache_or_leak_values(bad):
    class Broken(Scorer):
        async def scores(self, query, texts):
            return bad

    cache = RerankScoreCache(8)
    with pytest.raises(RuntimeError, match="invalid cached scores") as error:
        await cache.scores(Broken(), "demo", "query", ["a", "b"])
    assert "PRIVATE" not in str(error.value)
    assert cache.info()["entries"] == 0


@pytest.mark.parametrize("change", ["withdraw", "grant"])
async def test_warm_scores_do_not_bypass_current_permissions_or_withdrawal(context, change):
    ledger, _, tokens = context
    candidate = approve(context, propose(context))
    model, cache = Scorer(), RerankScoreCache(8)
    retriever = Retriever(ledger, embedder=CountingEmbedder(), reranker=model, rerank_cache=cache)
    for _ in range(2):
        assert (await retriever.search(tokens["agent"], "demo", "database"))["evidence"]
    assert len(model.calls) == 1 and cache.info()["hits"] == 1
    before = cache.info()
    if change == "withdraw":
        ledger.withdraw_source(tokens["admin"], "demo", candidate["source_id"])
        assert not (await retriever.search(tokens["agent"], "demo", "database"))["evidence"]
    else:
        revoke_access(ledger.engine, tokens["admin"], "demo", "agent")
        with pytest.raises(Denied):
            await retriever.search(tokens["agent"], "demo", "database")
    assert cache.info() == before


async def test_score_hit_refreshes_provenance_instead_of_caching_the_response(context):
    ledger, _, tokens = context
    root = approve(context, propose(context))
    model, cache = Scorer(), RerankScoreCache(8)
    retriever = Retriever(ledger, embedder=CountingEmbedder(), reranker=model, rerank_cache=cache)
    before = await retriever.search(tokens["agent"], "demo", "database")
    support = add_support(context, root)
    ledger.withdraw_source(tokens["admin"], "demo", root["source_id"])
    after = await retriever.search(tokens["agent"], "demo", "database")
    assert before["evidence"][0]["source_id"] == root["source_id"]
    assert after["evidence"][0]["source_id"] == support["source_id"]
    assert len(model.calls) == 1 and cache.info()["hits"] == 1


async def test_context_change_during_partial_cache_miss_discards_withdrawn_hits(context):
    ledger, _, tokens = context
    root = approve(context, propose(context))
    model, cache = Scorer(), RerankScoreCache(8)
    retriever = Retriever(ledger, embedder=CountingEmbedder(), reranker=model, rerank_cache=cache)
    await retriever.search(tokens["agent"], "demo", "database")
    next_fact = ledger.propose(
        tokens["agent"],
        "demo",
        subject="archive",
        predicate="database",
        value="SQLite",
        valid_from="2030-01-01T00:00:00Z",
    )
    approved = approve(context, next_fact)
    model.callback = lambda: ledger.withdraw_source(tokens["admin"], "demo", root["source_id"])
    result = await retriever.search(tokens["agent"], "demo", "database")
    assert [item["candidate_id"] for item in result["evidence"]] == [approved["id"]]
    assert len(model.calls[-1][1]) == 1 and cache.info()["hits"] == 1


@pytest.mark.parametrize("capacity", [True, -1, 0, 10001, 1.5])
def test_invalid_capacity_is_rejected(capacity):
    with pytest.raises(ValueError, match="capacity"):
        RerankScoreCache(capacity)


async def test_cached_scores_preserve_cutoff_boundary_and_stable_ties(context):
    ledger, _, tokens = context
    first = approve(context, propose(context))
    second = ledger.propose(
        tokens["agent"],
        "demo",
        subject="archive",
        predicate="database",
        value="SQLite",
        valid_from="2030-01-01T00:00:00Z",
    )
    approve(context, second)
    model, cache = Scorer(), RerankScoreCache(8)
    retriever = Retriever(
        ledger,
        embedder=CountingEmbedder(),
        reranker=model,
        rerank_cache=cache,
        min_relevance_score=2.0,
    )
    responses = [await retriever.search(tokens["agent"], "demo", "database") for _ in range(2)]
    ids = [item["id"] for item in responses[0]["evidence"]]
    assert ids == sorted(ids) and len(ids) == 2
    assert {item["candidate_id"] for item in responses[0]["evidence"]} == {
        first["id"],
        second["id"],
    }
    assert responses[0]["evidence"] == responses[1]["evidence"] and len(model.calls) == 1


@pytest.mark.integration
async def test_real_openfga_revocation_blocks_an_already_warm_score_cache(context):
    endpoint = os.environ.get("GM_TEST_FGA_URL")
    if not endpoint:
        pytest.skip("set GM_TEST_FGA_URL to check warm scores against real external authorization")
    ledger, _, tokens = context
    approve(context, propose(context))
    ledger.authorizer = provision(endpoint, "demo", [("operator", "admin"), ("agent", "agent")])
    cache = RerankScoreCache(8)
    retriever = Retriever(
        ledger, embedder=CountingEmbedder(), reranker=Scorer(), rerank_cache=cache
    )
    for _ in range(2):
        assert (await retriever.search(tokens["agent"], "demo", "database"))["evidence"]
    assert cache.info()["hits"] == 1
    ledger.authorizer.grant("agent", "demo", "agent", remove=True)
    before = cache.info()
    with pytest.raises(Denied):
        await retriever.search(tokens["agent"], "demo", "database")
    assert cache.info() == before


@pytest.mark.parametrize("value", ["-1", "10001", "invalid"])
def test_bad_operator_capacity_fails_before_model_loading(context, monkeypatch, value):
    monkeypatch.setenv("MEMORY_LOCAL_RERANKER", "1")
    monkeypatch.setenv("MEMORY_RERANK_CACHE_SIZE", value)
    with pytest.raises(ValueError, match="MEMORY_RERANK_CACHE_SIZE"):
        Settings.from_env().retriever(context[0])


def test_settings_enable_score_reuse_for_local_reranker_and_allow_disabling(context, monkeypatch):
    from governed_memory import local_models

    monkeypatch.setattr(local_models, "MiniLMReranker", lambda *_: Scorer())
    monkeypatch.setenv("MEMORY_LOCAL_RERANKER", "1")
    monkeypatch.delenv("MEMORY_RERANK_CACHE_SIZE", raising=False)
    assert Settings.from_env().retriever(context[0]).rerank_cache.capacity == 8192
    monkeypatch.setenv("MEMORY_RERANK_CACHE_SIZE", "0")
    assert Settings.from_env().retriever(context[0]).rerank_cache is None
