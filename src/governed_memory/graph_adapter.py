"""Project approved ledger rows through Graphiti's direct node/edge APIs.

No add_episode/add_triplet: both may resolve or rewrite facts using an LLM.
"""

import os

from graphiti_core import Graphiti
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.edges import EntityEdge
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.nodes import EntityNode
from graphiti_core.search.search_config_recipes import EDGE_HYBRID_SEARCH_RRF
from graphiti_core.search.search_filters import SearchFilters

from governed_memory.embedding import HashEmbedder
from governed_memory.ledger import Evidence, stable_id


class ExtractionDisabled(LLMClient):
    def __init__(self):
        super().__init__(None)

    async def _generate_response(self, *args, **kwargs):
        raise RuntimeError("unreviewed LLM extraction is disabled in the trusted projection")


class NeuralRerankingDisabled(CrossEncoderClient):
    async def rank(self, query, passages):
        raise RuntimeError("this adapter uses reciprocal rank fusion, not a cross-encoder")


class GraphProjection:
    def __init__(self, uri: str, user: str, password: str, embedder=None):
        os.environ.setdefault("GRAPHITI_TELEMETRY_ENABLED", "false")
        self.embedder = embedder or HashEmbedder()
        self.graph = Graphiti(
            uri,
            user,
            password,
            embedder=self.embedder,
            llm_client=ExtractionDisabled(),
            cross_encoder=NeuralRerankingDisabled(),
        )

    async def initialize(self):
        await self.graph.build_indices_and_constraints()

    async def close(self):
        await self.graph.close()

    async def upsert(self, item: Evidence):
        subject_id = stable_id(item.project, "subject", item.subject)
        # One target per snapshot prevents summaries from merging unrelated evidence.
        target_id = stable_id(item.id, "value")
        for node_id, name in ((subject_id, item.subject), (target_id, item.value)):
            await EntityNode(
                uuid=node_id,
                group_id=item.project,
                name=name,
                name_embedding=await self.embedder.create(name),
                labels=["Entity"],
                summary="",
                created_at=item.system_from,
            ).save(self.graph.driver)
        edge = EntityEdge(
            uuid=item.id,
            group_id=item.project,
            source_node_uuid=subject_id,
            target_node_uuid=target_id,
            name="APPROVED_FACT",
            fact=item.text,
            fact_embedding=await self.embedder.create(item.text),
            episodes=[],
            valid_at=item.valid_from,
            invalid_at=item.valid_until,
            created_at=item.system_from,
            expired_at=item.system_until,
            attributes={
                "source_id": item.source_id,
                "candidate_id": item.candidate_id,
                "content_hash": item.content_hash,
                "locator": item.locator,
            },
        )
        await edge.save(self.graph.driver)

    async def rank(self, query: str, project: str, allowed_ids: list[str], limit: int) -> list[str]:
        if not allowed_ids:
            return []
        # Push down authority-derived permissions AND bitemporal eligibility before retrieval.
        config = EDGE_HYBRID_SEARCH_RRF.model_copy(deep=True)
        config.limit = limit
        result = await self.graph.search_(
            query,
            config=config,
            group_ids=[project],
            search_filter=SearchFilters(edge_uuids=allowed_ids),
        )
        return [edge.uuid for edge in result.edges]


async def project_pending(ledger, graph, limit: int = 100, project: str | None = None) -> dict:
    successes, failures = 0, 0
    for item, generation in ledger.pending(limit, project):
        try:
            await graph.upsert(item)
        except Exception as exc:
            ledger.mark_projection(item.id, generation, f"{type(exc).__name__}: projection failed")
            failures += 1
        else:
            ledger.mark_projection(item.id, generation, None)
            successes += 1
    return {"projected": successes, "failed": failures}
