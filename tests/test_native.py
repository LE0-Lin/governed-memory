import os
from types import SimpleNamespace

import numpy as np
import pytest
from rank_bm25 import BM25Okapi

from governed_memory.embedding import words
from governed_memory.retrieval import Retriever, fusion_order, hybrid_rank

from .conftest import approve, propose


@pytest.fixture(scope="module")
def native():
    if os.environ.get("GM_TEST_NATIVE") == "1":
        import governed_memory_native

        return governed_memory_native
    return pytest.importorskip("governed_memory_native")


def test_native_bm25_vector_fusion_matches_reference_over_varied_corpora(native):
    rng = np.random.default_rng(81112)
    for size in (1, 2, 9, 40):
        corpus = [
            rng.choice(["database", "storage", "queue", "python"], size=i % 6 + 1).tolist()
            for i in range(size)
        ]
        vectors = rng.normal(size=(size, 16))
        query = rng.normal(size=16)
        ids = [f"item-{i:03}" for i in range(size)]
        lexical = BM25Okapi(corpus).get_scores(["database", "queue"])
        cosine = (
            vectors
            @ query
            / np.maximum(np.linalg.norm(vectors, axis=1) * np.linalg.norm(query), 1e-12)
        )
        assert native.hybrid_order(
            ["database", "queue"], corpus, query.tolist(), vectors.tolist(), ids
        ) == fusion_order(lexical, cosine, ids)
    with pytest.raises(ValueError):
        native.hybrid_order(["word"], [["word"]], [1.0], [[float("nan")]], ["one"])


async def test_native_pipeline_preserves_authority_and_returns_the_same_order(context, native):
    ledger, _, tokens = context
    for value in ("SQLite", "PostgreSQL"):
        approve(context, propose(context, value))
    propose(context, "database POISON")
    python = await Retriever(ledger).search(tokens["reader"], "demo", "storage database")
    rust = await Retriever(ledger, ranking_backend="rust").search(
        tokens["reader"], "demo", "storage database"
    )
    assert rust["evidence"] == python["evidence"]
    assert rust["ranking_engine"] == "rust"
    assert "POISON" not in str(rust)


async def test_native_semantic_ranking_handles_nonlexical_similarity(native):
    documents = [
        SimpleNamespace(id="one", text="durable records"),
        SimpleNamespace(id="two", text="sunny weather"),
    ]

    class Embedder:
        async def create(self, text):
            return [1.0, 0.0]

        async def create_batch(self, texts):
            return [[1.0, 0.0], [0.0, 1.0]]

    assert not set(words("persistent storage")).intersection(words(documents[0].text))
    ranked = await hybrid_rank("persistent storage", documents, Embedder(), ranking_backend="rust")
    assert ranked[0].id == "one"


async def test_native_chunking_matches_python_source_spans(native):
    from governed_memory.chunking import semantic_chunks

    class Embedder:
        async def create_batch(self, texts):
            return [[0.0, 1.0] if "猫" in text else [1.0, 0.0] for text in texts]

    text = "PostgreSQL stores records. " * 5 + "猫 sleeps beside a window. " * 7
    expected = await semantic_chunks(
        text, Embedder(), min_tokens=8, max_tokens=80, backend="python"
    )
    actual = await semantic_chunks(text, Embedder(), min_tokens=8, max_tokens=80, backend="rust")
    assert actual == expected
