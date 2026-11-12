from time import perf_counter

import numpy as np
from rank_bm25 import BM25Okapi

from governed_memory.budget import EvidenceBudget
from governed_memory.budget import serialize as serialize
from governed_memory.embedding import HashEmbedder, embed_many, words
from governed_memory.native import kernels


def fusion_order(lexical, cosine, ids):
    """Reciprocal rank fusion with stable ID tie breaking, shared with external evaluation."""
    lexical_order = sorted(range(len(ids)), key=lambda i: (-lexical[i], ids[i]))
    vector_order = sorted(range(len(ids)), key=lambda i: (-cosine[i], ids[i]))
    scores = np.zeros(len(ids))
    for order in (lexical_order, vector_order):
        for rank, i in enumerate(order):
            scores[i] += 1 / (60 + rank + 1)
    return sorted(range(len(ids)), key=lambda i: (-scores[i], ids[i]))


async def hybrid_rank(query: str, evidence, embedder=None, *, ranking_backend="python"):
    if not evidence or not query.strip():
        return []
    embedder = embedder or HashEmbedder()
    if isinstance(embedder, HashEmbedder):
        # Hash features carry lexical overlap, not semantic similarity.
        terms = set(words(query))
        evidence = [item for item in evidence if terms.intersection(words(item.text))]
        if not evidence:
            return []
    corpus = [words(item.text) or [""] for item in evidence]
    query_vector = np.array(await embedder.create(query))
    # Deliberately no embedding cache: evaluation includes document and query computation.
    vectors = np.array(await embed_many(embedder, [item.text for item in evidence]))
    native = kernels(ranking_backend)
    if native:
        indices = native.hybrid_order(
            words(query), corpus, query_vector.tolist(), vectors.tolist(), [e.id for e in evidence]
        )
        return [evidence[i] for i in indices]
    lexical = BM25Okapi(corpus).get_scores(words(query))
    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query_vector)
    cosine = (vectors @ query_vector) / np.maximum(norms, 1e-12)
    return [evidence[i] for i in fusion_order(lexical, cosine, [e.id for e in evidence])]


class Retriever:
    def __init__(
        self, ledger, graph=None, *, embedder=None, reranker=None, ranking_backend="python"
    ):
        self.ledger, self.graph = ledger, graph
        self.embedder = embedder or getattr(graph, "embedder", None) or HashEmbedder()
        self.reranker = reranker
        self.ranking_backend = "rust" if kernels(ranking_backend) else "python"
        self.budget = EvidenceBudget()
        self.encoding = self.budget.encoding

    def pack(self, ranked, budget: int, k: int) -> tuple[list[dict], int]:
        return self.budget.pack(ranked, budget, k)

    async def search(
        self,
        token: str,
        project: str,
        query: str,
        *,
        valid_at=None,
        known_at=None,
        token_budget: int = 2048,
        k: int = 5,
    ) -> dict:
        start = perf_counter()
        if not 2 <= token_budget <= 32768 or not 1 <= k <= 50:
            raise ValueError("budget must be 2..32768 tokens; k must be 1..50")
        if not query.strip() or len(query) > 10000:
            raise ValueError("query must contain 1..10000 characters")
        query_now = self.ledger.clock()
        valid_at, known_at = valid_at or query_now, known_at or query_now
        eligible = self.ledger.visible(token, project, valid_at=valid_at, known_at=known_at)
        embedder = self.embedder
        if isinstance(embedder, HashEmbedder):
            terms = set(words(query))
            eligible = [e for e in eligible if terms.intersection(words(e.text))]
        backend = (
            "local-bm25+hash-rrf"
            if isinstance(embedder, HashEmbedder)
            else "local-bm25+embedding-rrf"
        )
        ranked = []
        if self.graph and eligible:
            try:
                ids = await self.graph.rank(
                    query, project, [e.id for e in eligible], min(len(eligible), max(k * 4, 50))
                )
                lookup = {e.id: e for e in eligible}
                ranked = [lookup[item] for item in dict.fromkeys(ids) if item in lookup]
                backend = "graphiti-hybrid-rrf"
            except Exception:
                backend = "ledger-fallback:graph-unavailable"
        # Fill missing/stale projection hits from the same authoritative, authorized set.
        available = {
            e.id: e
            for e in self.ledger.visible(token, project, valid_at=valid_at, known_at=known_at)
        }
        ranked = [available[e.id] for e in ranked if e.id in available]
        present = {e.id for e in ranked}
        fill = await hybrid_rank(
            query,
            [available[e.id] for e in eligible if e.id in available and e.id not in present],
            embedder,
            ranking_backend=self.ranking_backend,
        )
        if fill and backend == "graphiti-hybrid-rrf":
            backend = (
                "graphiti-hybrid-rrf+ledger-fill"
                if ranked
                else "ledger-fallback:projection-missing"
            )
        ranked += fill
        if self.reranker and ranked:
            # Revalidate after candidate generation, before sending text to any reranker.
            current = {
                e.id: e
                for e in self.ledger.visible(token, project, valid_at=valid_at, known_at=known_at)
            }
            ranked = [current[e.id] for e in ranked if e.id in current]
            ranked = await self.reranker.rerank(query, ranked[:50])
        # Recheck current ACL/revocation after retrieval, before serializing any text.
        refreshed = {
            e.id: e
            for e in self.ledger.visible(token, project, valid_at=valid_at, known_at=known_at)
        }
        ranked = [refreshed[e.id] for e in ranked if e.id in refreshed]
        results, used = self.pack(ranked, token_budget, k)
        reason = "ok"
        if not results:
            reason = (
                "no_eligible_evidence"
                if not refreshed
                else "no_relevant_evidence"
                if not ranked
                else "token_budget"
            )
        response = {
            "evidence": results,
            "evidence_tokens": used,
            "token_budget": token_budget,
            "tokenizer": "cl100k_base",
            "backend": backend,
            "ranking_engine": self.ranking_backend,
            "reranker": self.reranker.metadata if self.reranker else None,
            "reason": reason,
        }
        # Force serialization into the measured interval (transport/answer generation excluded).
        serialize(response)
        response["latency_ms"] = (perf_counter() - start) * 1000
        return response
