import json
import os

import numpy as np
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from governed_memory.chunking import semantic_chunks
from governed_memory.errors import Conflict, Denied
from governed_memory.generation import GeneratedText
from governed_memory.models import Candidate, EntityResolution
from governed_memory.semantic_ingest import FactExtractor, import_document
from governed_memory.semantic_review import NliDetector, SemanticReview

from .conftest import approve, propose


class TopicEmbedder:
    async def create_batch(self, texts):
        return [[0.0, 1.0] if "cat" in text else [1.0, 0.0] for text in texts]


class Extractor:
    def __init__(self, value="PostgreSQL"):
        self.value = value

    async def generate(self, messages, **kwargs):
        return GeneratedText(
            json.dumps(
                {
                    "facts": [
                        {
                            "subject": "storage",
                            "predicate": "database",
                            "value": self.value,
                        }
                    ]
                }
            ),
            10,
            10,
            "stop",
        )


async def test_semantic_boundaries_preserve_source_unicode_and_bound_oversized_sentences():
    text = "PostgreSQL stores records. " * 5 + "The cat sleeps. " * 5 + "猫😀" * 200
    chunks = await semantic_chunks(
        text, TopicEmbedder(), max_tokens=80, min_tokens=8, threshold=0.5, backend="python"
    )
    assert "".join(chunk.text for chunk in chunks) == text
    assert all(
        chunk.text == text[chunk.start : chunk.end] and chunk.tokens <= 80 for chunk in chunks
    )
    assert any(chunk.start == text.index("The cat") for chunk in chunks)


async def test_raw_ingestion_stages_quoted_spans_and_rejects_invented_provenance(context):
    ledger, _, tokens = context
    body = "Meeting😀. The storage database is PostgreSQL."
    result = await import_document(
        ledger,
        tokens["agent"],
        "demo",
        body,
        "session:one",
        "2030-01-01T00:00:00Z",
        TopicEmbedder(),
        FactExtractor(Extractor()),
    )
    assert result["candidates"][0]["state"] == "proposed"
    assert ledger.visible(tokens["reader"], "demo") == []
    record = ledger.explain(tokens["agent"], "demo", result["candidates"][0]["id"])
    _, start, end = record["source"]["fragment"].split(":")
    assert body[int(start) : int(end)] == body
    with pytest.raises(ValueError, match="copied from source"):
        await import_document(
            ledger,
            tokens["agent"],
            "demo",
            body,
            "session:invented",
            "2030-01-01T00:00:00Z",
            TopicEmbedder(),
            FactExtractor(Extractor("invented quote")),
        )
    with Session(ledger.engine) as session:
        assert len(list(session.scalars(select(Candidate)))) == 1


def test_entity_resolution_preserves_both_proposals_and_requires_separate_approval(context):
    ledger, _, tokens = context
    approve(context, propose(context))
    target = ledger.visible(tokens["admin"], "demo")[0]
    incoming = ledger.propose(
        tokens["agent"],
        "demo",
        subject="storage layer",
        predicate="database",
        value="PostgreSQL",
        valid_from="2030-01-01T00:00:00Z",
    )
    with pytest.raises(Denied):
        ledger.resolve_entity(
            tokens["agent"],
            "demo",
            incoming["id"],
            target.id,
            expected_revision=0,
            reason="same component",
        )
    result = ledger.resolve_entity(
        tokens["approver"],
        "demo",
        incoming["id"],
        target.id,
        expected_revision=0,
        reason="same component",
    )
    assert result["replacement"]["subject"] == "storage"
    assert result["replacement"]["state"] == "proposed"
    assert ledger.visible(tokens["reader"], "demo")[0].value == "SQLite"
    with Session(ledger.engine) as session:
        assert session.get(Candidate, incoming["id"]).subject == "storage layer"
        assert session.get(Candidate, incoming["id"]).state == "rejected"
        assert (
            session.get(EntityResolution, incoming["id"]).replacement_id
            == result["replacement"]["id"]
        )
    with pytest.raises(DatabaseError), ledger.engine.begin() as conn:
        conn.execute(text("DELETE FROM entity_resolutions"))
    approve(context, result["replacement"])
    assert ledger.visible(tokens["reader"], "demo")[0].value == "PostgreSQL"


async def test_semantic_review_discards_findings_when_any_input_is_withdrawn(context):
    ledger, _, tokens = context
    root = approve(context, propose(context))
    incoming = propose(context, "PostgreSQL")

    class Detector:
        metadata = {"test": True}

        async def scores(self, pairs):
            ledger.withdraw_source(tokens["admin"], "demo", root["source_id"])
            return [{"contradiction": 0.99, "entailment": 0.005, "neutral": 0.005} for _ in pairs]

    with pytest.raises(Conflict, match="context changed"):
        await SemanticReview(ledger, TopicEmbedder(), Detector()).inspect(
            tokens["admin"], "demo", incoming["id"]
        )


@pytest.mark.models
async def test_real_nli_distinguishes_contradiction_and_entailment():
    if os.environ.get("GM_TEST_REAL_NLI") != "1":
        pytest.skip("set GM_TEST_REAL_NLI=1 to exercise the pinned NLI model")
    detector = NliDetector(os.environ.get("MEMORY_MODEL_CACHE"))
    scores = await detector.scores(
        [
            ("Backups must be encrypted.", "Backups must not be encrypted."),
            ("The database is PostgreSQL.", "The database is PostgreSQL."),
        ]
    )
    assert scores[0]["contradiction"] > 0.8
    assert scores[1]["entailment"] > 0.8
    np.testing.assert_allclose([sum(score.values()) for score in scores], 1, atol=1e-5)


@pytest.mark.models
async def test_real_document_extraction_and_semantic_operator_review(context):
    if not all(
        os.environ.get(name) == "1"
        for name in (
            "GM_TEST_REAL_NLI",
            "GM_TEST_REAL_MODELS",
            "GM_TEST_REAL_GENERATION",
        )
    ):
        pytest.skip("enable the real embedding, generation and NLI model checks")
    from governed_memory.generation import TransformersGenerator
    from governed_memory.local_models import MiniLMEmbedder

    ledger, _, tokens = context
    embedder = MiniLMEmbedder(os.environ.get("MEMORY_MODEL_CACHE"))
    generator = TransformersGenerator("small", os.environ.get("MEMORY_GENERATION_CACHE"))
    document = "Atlas uses PostgreSQL for persistent storage."
    staged = await import_document(
        ledger,
        tokens["agent"],
        "demo",
        document,
        "session:real-model",
        "2030-01-01T00:00:00Z",
        embedder,
        FactExtractor(generator),
    )
    assert staged["candidates"]
    assert all(candidate["state"] == "proposed" for candidate in staged["candidates"])
    assert ledger.visible(tokens["reader"], "demo") == []
    old = ledger.propose(
        tokens["agent"],
        "demo",
        subject="backup policy",
        predicate="requirement",
        value="Backups must be encrypted.",
        valid_from="2030-01-01T00:00:00Z",
    )
    approve(context, old)
    new = ledger.propose(
        tokens["agent"],
        "demo",
        subject="backup policy",
        predicate="requirement",
        value="Backups must not be encrypted.",
        valid_from="2030-01-01T00:00:00Z",
    )
    review = await SemanticReview(
        ledger, embedder, NliDetector(os.environ.get("MEMORY_MODEL_CACHE"))
    ).inspect(tokens["admin"], "demo", new["id"])
    assert review["entity_matches"][0]["subject"] == "backup policy"
    assert any(item["contradiction"] for item in review["comparisons"])
