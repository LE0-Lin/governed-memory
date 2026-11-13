import pytest

from governed_memory.answering import AnswerService
from governed_memory.embedding_cache import DocumentEmbeddingCache
from governed_memory.errors import Denied
from governed_memory.identity import revoke_access
from governed_memory.retrieval import Retriever
from governed_memory.settings import Settings

from .conftest import approve, propose
from .test_answering import TestGenerator


class CountingEmbedder:
    dimensions = 2

    def __init__(self):
        self.metadata = {"revision": "one"}
        self.document_calls = []

    async def create(self, text):
        return [1.0, 0.0]

    async def create_batch(self, texts):
        self.document_calls.append(list(texts))
        return [[float(len(text)), 1.0] for text in texts]


class Scorer:
    metadata = {"scores": "raw logits", "test_double": True}

    def __init__(self, score=2.0, callback=None):
        self.score, self.callback = score, callback

    async def scores(self, query, texts):
        if self.callback:
            self.callback()
        return [self.score for _ in texts]


async def test_cache_keys_include_exact_text_project_and_model_and_return_copies():
    model, cache = CountingEmbedder(), DocumentEmbeddingCache(8)
    values = await cache.embed(model, "one", ["first", "second", "first"])
    assert model.document_calls == [["first", "second"]]
    values[0][0] = -100
    assert (await cache.embed(model, "one", ["first"]))[0] == [5.0, 1.0]
    await cache.embed(model, "two", ["first"])
    model.metadata["revision"] = "two"
    await cache.embed(model, "one", ["first"])
    await cache.embed(model, "one", ["FIRST"])
    assert model.document_calls == [["first", "second"], ["first"], ["first"], ["FIRST"]]
    assert cache.info()["encoding_requests"] == 5


async def test_cache_is_bounded_and_evicts_the_least_recently_used_vector():
    model, cache = CountingEmbedder(), DocumentEmbeddingCache(2)
    await cache.embed(model, "demo", ["a", "b"])
    await cache.embed(model, "demo", ["a"])
    await cache.embed(model, "demo", ["c"])
    await cache.embed(model, "demo", ["b"])
    assert cache.info() == {"entries": 2, "hits": 1, "encoding_requests": 4, "evictions": 2}
    assert model.document_calls == [["a", "b"], ["c"], ["b"]]


@pytest.mark.parametrize(
    "bad", [[[1.0, 2.0]], [[1.0, 2.0], [float("nan"), 1.0]], [["PRIVATE", 1.0], [1.0, 2.0]]]
)
async def test_invalid_embeddings_never_enter_the_cache_or_expose_raw_values(bad):
    class Broken(CountingEmbedder):
        async def create_batch(self, texts):
            return bad

    cache = DocumentEmbeddingCache(8)
    with pytest.raises(RuntimeError, match="invalid document vectors") as error:
        await cache.embed(Broken(), "demo", ["a", "b"])
    assert "PRIVATE" not in str(error.value)
    assert cache.info()["entries"] == 0


@pytest.mark.parametrize("change", ["withdraw", "grant"])
async def test_warm_cache_never_bypasses_current_withdrawal_or_access(context, change):
    ledger, _, tokens = context
    candidate = approve(context, propose(context))
    model, cache = CountingEmbedder(), DocumentEmbeddingCache(8)
    retriever = Retriever(ledger, embedder=model, document_cache=cache)
    assert (await retriever.search(tokens["agent"], "demo", "database"))["evidence"]
    assert (await retriever.search(tokens["agent"], "demo", "database"))["evidence"]
    assert len(model.document_calls) == 1
    before = cache.info()
    if change == "withdraw":
        ledger.withdraw_source(tokens["admin"], "demo", candidate["source_id"])
        assert not (await retriever.search(tokens["agent"], "demo", "database"))["evidence"]
    else:
        revoke_access(ledger.engine, tokens["admin"], "demo", "agent")
        with pytest.raises(Denied):
            await retriever.search(tokens["agent"], "demo", "database")
    assert cache.info() == before


async def test_withdrawal_during_scoring_discards_cached_candidates(context):
    ledger, _, tokens = context
    candidate = approve(context, propose(context))
    cache, model = DocumentEmbeddingCache(8), CountingEmbedder()
    retriever = Retriever(
        ledger, embedder=model, document_cache=cache, reranker=Scorer(), min_relevance_score=1.4
    )
    assert (await retriever.search(tokens["agent"], "demo", "database"))["evidence"]
    retriever.reranker.callback = lambda: ledger.withdraw_source(
        tokens["admin"], "demo", candidate["source_id"]
    )
    response = await retriever.search(tokens["agent"], "demo", "database")
    assert not response["evidence"]
    assert len(model.document_calls) == 1


async def test_query_encoding_cannot_trigger_a_later_stale_document_request(context):
    ledger, _, tokens = context
    candidate = approve(context, propose(context))
    events = []

    class RevokingQuery(CountingEmbedder):
        async def create_batch(self, texts):
            events.append("documents")
            return await super().create_batch(texts)

        async def create(self, text):
            events.append("query")
            ledger.withdraw_source(tokens["admin"], "demo", candidate["source_id"])
            return [1.0, 0.0]

    result = await Retriever(
        ledger, embedder=RevokingQuery(), document_cache=DocumentEmbeddingCache(8)
    ).search(tokens["agent"], "demo", "database")
    assert not result["evidence"]
    assert events == ["documents", "query"]


async def test_cutoff_rejects_irrelevant_context_without_invoking_generation(context):
    ledger, _, tokens = context
    approve(context, propose(context))
    generator = TestGenerator()
    retriever = Retriever(
        ledger, embedder=CountingEmbedder(), reranker=Scorer(-3.0), min_relevance_score=1.4
    )
    result = await AnswerService(retriever, generator).answer(
        tokens["agent"], "demo", "Who owns this project?"
    )
    assert result["abstain"] and result["reason"] == "no_relevant_evidence"
    assert result["evidence"] == result["evidence_ids"] == []
    assert result["generation"] is None and generator.contexts == []


async def test_cutoff_includes_its_boundary_and_stably_orders_ties(context):
    ledger, _, tokens = context
    for attribute in ("database", "backup"):
        approve(
            context,
            ledger.propose(
                tokens["agent"],
                "demo",
                subject="storage",
                predicate=attribute,
                value="SQLite",
                valid_from="2030-01-01T00:00:00Z",
            ),
        )
    retriever = Retriever(
        ledger, embedder=CountingEmbedder(), reranker=Scorer(1.4), min_relevance_score=1.4
    )
    result = await retriever.search(tokens["agent"], "demo", "storage")
    ids = [item["id"] for item in result["evidence"]]
    assert len(ids) == 2 and ids == sorted(ids)


@pytest.mark.parametrize("bad", [[float("nan")], [1.0, 2.0], ["PRIVATE"]])
async def test_invalid_relevance_scores_fail_closed(context, bad):
    ledger, _, tokens = context
    approve(context, propose(context))

    class Broken(Scorer):
        async def scores(self, query, texts):
            return bad

    retriever = Retriever(ledger, reranker=Broken(), min_relevance_score=1.4)
    with pytest.raises(RuntimeError, match="invalid relevance scores") as error:
        await retriever.search(tokens["agent"], "demo", "database")
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize(
    "name,value",
    [
        ("MEMORY_RELEVANCE_FILTER", "maybe"),
        ("MEMORY_DOCUMENT_CACHE_SIZE", "-1"),
        ("MEMORY_DOCUMENT_CACHE_SIZE", "invalid"),
        ("MEMORY_DOCUMENT_CACHE_SIZE", "10001"),
    ],
)
def test_invalid_operator_configuration_fails_before_loading_any_model(
    context, monkeypatch, name, value
):
    monkeypatch.setenv(name, value)
    monkeypatch.setenv("MEMORY_LOCAL_RERANKER", "1")
    with pytest.raises(ValueError, match="must be"):
        Settings.from_env().retriever(context[0])


def test_settings_requires_explicit_opt_in_before_rejecting_low_relevance(context, monkeypatch):
    from governed_memory import local_models

    scorer = Scorer()
    scorer.metadata = {
        "model": local_models.RERANKING_MODEL,
        "revision": local_models.RERANKING_REVISION,
        "scores": "raw logits",
    }
    monkeypatch.setattr(local_models, "MiniLMReranker", lambda *_: scorer)
    monkeypatch.setenv("MEMORY_LOCAL_RERANKER", "1")
    monkeypatch.delenv("MEMORY_RELEVANCE_FILTER", raising=False)
    settings = Settings.from_env()
    assert settings.retriever(context[0]).min_relevance_score is None
    monkeypatch.setenv("MEMORY_RELEVANCE_FILTER", "1")
    assert settings.retriever(context[0]).min_relevance_score == 1.4
