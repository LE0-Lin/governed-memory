"""Bounded document vectors; callers must perform current eligibility checks themselves."""

import hashlib
from collections import OrderedDict
from threading import Lock

import numpy as np

from governed_memory.embedding import embed_many, embedding_profile


class DocumentEmbeddingCache:
    def __init__(self, capacity=2048):
        if (
            isinstance(capacity, bool)
            or not isinstance(capacity, int)
            or not 1 <= capacity <= 10000
        ):
            raise ValueError("document cache capacity must be 1..10000")
        self.capacity = capacity
        self._entries = OrderedDict()
        self._lock = Lock()
        self._hits = self._encoding_requests = self._evictions = 0

    async def embed(self, client, project: str, texts: list[str]):
        profile = embedding_profile(client)
        keys = [(project, profile, hashlib.sha256(text.encode()).hexdigest()) for text in texts]
        found, missing = {}, {}
        with self._lock:
            for key, text in zip(keys, texts, strict=True):
                if key in self._entries:
                    found[key] = self._entries[key]
                    self._entries.move_to_end(key)
                    self._hits += 1
                else:
                    missing[key] = text
            self._encoding_requests += len(missing)
        if missing:
            try:
                vectors = np.asarray(await embed_many(client, list(missing.values())), dtype=float)
            except (ValueError, TypeError):
                raise RuntimeError("embedder returned invalid document vectors") from None
            dimensions = getattr(client, "dimensions", None)
            if (
                vectors.ndim != 2
                or vectors.shape[0] != len(missing)
                or vectors.shape[1] == 0
                or (dimensions is not None and vectors.shape[1] != dimensions)
                or not np.isfinite(vectors).all()
            ):
                raise RuntimeError("embedder returned invalid document vectors")
            additions = {
                key: tuple(vector.tolist()) for key, vector in zip(missing, vectors, strict=True)
            }
            with self._lock:
                for key, vector in additions.items():
                    self._entries[key] = vector
                    self._entries.move_to_end(key)
                    while len(self._entries) > self.capacity:
                        self._entries.popitem(last=False)
                        self._evictions += 1
            found.update(additions)
        # Return copies: a caller must not mutate a vector held by another request.
        return [list(found[key]) for key in keys]

    def info(self):
        """Operator/test diagnostics; never expose global occupancy through an agent tool."""
        with self._lock:
            return {
                "entries": len(self._entries),
                "hits": self._hits,
                "encoding_requests": self._encoding_requests,
                "evictions": self._evictions,
            }
