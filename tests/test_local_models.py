import os

import numpy as np
import pytest

from governed_memory.local_models import MiniLMEmbedder, MiniLMReranker
from governed_memory.retrieval import Retriever, serialize

from .conftest import approve


@pytest.fixture(scope="module")
def local_models():
    if os.environ.get("GM_TEST_REAL_MODELS") != "1":
        pytest.skip("set GM_TEST_REAL_MODELS=1 to download and exercise the pinned neural models")
    cache = os.environ.get("MEMORY_MODEL_CACHE")
    return MiniLMEmbedder(cache), MiniLMReranker(cache)


@pytest.mark.models
async def test_real_embeddings_preserve_batch_padding_and_semantic_similarity(local_models):
    embedder, _ = local_models
    texts = [
        "The developer changed the database to PostgreSQL.",
        "The engineer migrated persistent storage to Postgres.",
        "A cat sleeps beside a sunny window.",
    ]
    vectors = np.array(await embedder.create_batch(texts))
    assert vectors.shape == (3, 1024)
    assert np.all(vectors[:, 384:] == 0)
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
    assert vectors[0] @ vectors[1] > vectors[0] @ vectors[2]
    alone = np.array(await embedder.create(texts[0]))
    np.testing.assert_allclose(vectors[0], alone, atol=1e-5)


@pytest.mark.models
async def test_real_cross_encoder_matches_the_published_reference_example(local_models):
    _, reranker = local_models
    scores = await reranker.scores(
        "How many people live in Berlin?",
        [
            "Berlin had a population of 3,520,031 registered inhabitants "
            "in an area of 891.82 square kilometers.",
            "Berlin is well known for its museums.",
        ],
    )
    # Model-card reference logits, not expected scores produced by this implementation.
    np.testing.assert_allclose(scores, [8.607138, -4.320078], atol=0.05)


@pytest.mark.models
async def test_real_models_work_through_the_authorized_service_pipeline(context, local_models):
    ledger, _, tokens = context
    embedder, reranker = local_models
    for subject, predicate, value, audience in (
        ("storage", "database", "PostgreSQL stores durable application records", []),
        ("build", "language", "Python 3.12", []),
        ("storage", "private endpoint", "PRIVATE-PLACEHOLDER", ["reader"]),
    ):
        candidate = ledger.propose(
            tokens["admin"],
            "demo",
            subject=subject,
            predicate=predicate,
            value=value,
            valid_from="2030-01-01T00:00:00Z",
            audience=audience,
        )
        approve(context, candidate)
    result = await Retriever(ledger, embedder=embedder, reranker=reranker).search(
        tokens["agent"], "demo", "Which database stores the application's data?", k=1
    )
    assert result["evidence"][0]["subject"] == "storage"
    assert result["backend"] == "local-bm25+embedding-rrf"
    assert result["reranker"] == reranker.metadata
    assert "PRIVATE-PLACEHOLDER" not in serialize(result)
