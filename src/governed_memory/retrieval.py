import json
from dataclasses import asdict
from time import perf_counter

import numpy as np
from rank_bm25 import BM25Okapi

from governed_memory.embedding import HashEmbedder, words
from governed_memory.tokenizer import encoding


def serialize(value) -> str:
    return json.dumps(
        value,
        default=lambda obj: obj.isoformat(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


async def hybrid_rank(query: str, evidence, embedder=None):
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
    lexical = BM25Okapi(corpus).get_scores(words(query))
    query_vector = np.array(await embedder.create(query))
    # Deliberately no embedding cache: evaluation includes document and query computation.
    vectors = np.array([await embedder.create(item.text) for item in evidence])
    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query_vector)
    cosine = (vectors @ query_vector) / np.maximum(norms, 1e-12)
    lexical_order = sorted(range(len(evidence)), key=lambda i: (-lexical[i], evidence[i].id))
    vector_order = sorted(range(len(evidence)), key=lambda i: (-cosine[i], evidence[i].id))
    scores = np.zeros(len(evidence))
    for order in (lexical_order, vector_order):
        for rank, i in enumerate(order):
            scores[i] += 1 / (60 + rank + 1)
    return [
        evidence[i]
        for i in sorted(range(len(evidence)), key=lambda i: (-scores[i], evidence[i].id))
    ]


class Retriever:
    def __init__(self, ledger, graph=None):
        self.ledger, self.graph = ledger, graph
        self.encoding = encoding()

    def pack(self, ranked, budget: int, k: int) -> tuple[list[dict], int]:
        result = []
        for item in ranked:
            trial = [*result, asdict(item)]
            if len(self.encoding.encode(serialize(trial), disallowed_special=())) <= budget:
                result = trial
            if len(result) >= k:
                break
        return result, len(self.encoding.encode(serialize(result), disallowed_special=()))

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
        embedder = getattr(self.graph, "embedder", None)
        if embedder is None or isinstance(embedder, HashEmbedder):
            terms = set(words(query))
            eligible = [e for e in eligible if terms.intersection(words(e.text))]
        backend = "local-bm25+hash-rrf"
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
        )
        if fill and backend == "graphiti-hybrid-rrf":
            backend = (
                "graphiti-hybrid-rrf+ledger-fill"
                if ranked
                else "ledger-fallback:projection-missing"
            )
        ranked += fill
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
            "reason": reason,
        }
        # Force serialization into the measured interval (transport/answer generation excluded).
        serialize(response)
        response["latency_ms"] = (perf_counter() - start) * 1000
        return response
