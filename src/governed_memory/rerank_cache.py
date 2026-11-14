"""Bounded reranker computations; every caller must still check current eligibility."""

import hashlib
import json
from collections import OrderedDict
from threading import Lock

import numpy as np


class RerankScoreCache:
    def __init__(self, capacity=8192):
        if (
            isinstance(capacity, bool)
            or not isinstance(capacity, int)
            or not 1 <= capacity <= 10000
        ):
            raise ValueError("rerank cache capacity must be 1..10000")
        self.capacity = capacity
        self._entries = OrderedDict()
        self._lock = Lock()
        self._hits = self._scoring_requests = self._evictions = 0

    async def scores(self, client, project: str, query: str, texts: list[str]):
        profile = hashlib.sha256(
            json.dumps(
                {
                    "client": f"{type(client).__module__}.{type(client).__qualname__}",
                    "metadata": client.metadata,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        query_hash = hashlib.sha256(query.encode()).hexdigest()
        keys = [
            (project, profile, query_hash, hashlib.sha256(text.encode()).hexdigest())
            for text in texts
        ]
        found, missing = {}, {}
        with self._lock:
            for key, text in zip(keys, texts, strict=True):
                if key in self._entries:
                    found[key] = self._entries[key]
                    self._entries.move_to_end(key)
                    self._hits += 1
                else:
                    missing[key] = text
            self._scoring_requests += len(missing)
        if missing:
            try:
                values = np.asarray(await client.scores(query, list(missing.values())), dtype=float)
            except (ValueError, TypeError):
                raise RuntimeError("reranker returned invalid cached scores") from None
            if values.shape != (len(missing),) or not np.isfinite(values).all():
                raise RuntimeError("reranker returned invalid cached scores")
            additions = dict(zip(missing, values.tolist(), strict=True))
            with self._lock:
                for key, value in additions.items():
                    self._entries[key] = value
                    self._entries.move_to_end(key)
                    while len(self._entries) > self.capacity:
                        self._entries.popitem(last=False)
                        self._evictions += 1
            found.update(additions)
        return [found[key] for key in keys]

    def info(self):
        """Operator diagnostics; do not expose global usage through an agent tool."""
        with self._lock:
            return {
                "entries": len(self._entries),
                "hits": self._hits,
                "scoring_requests": self._scoring_requests,
                "evictions": self._evictions,
            }
