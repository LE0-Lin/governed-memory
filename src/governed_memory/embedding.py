"""Deterministic lexical features for offline checks, not semantic model embeddings."""

import hashlib
import json
import math
import re

from graphiti_core.embedder.client import EmbedderClient


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


async def embed_many(client, texts: list[str]):
    """Use batch inference when supported; preserve the single-text client interface."""
    batch = getattr(client, "create_batch", None)
    if batch:
        try:
            return await batch(texts)
        except NotImplementedError:
            pass
    return [await client.create(text) for text in texts]


def embedding_profile(client) -> str:
    """Bind a graph edge to its embedding configuration, without storing credentials."""
    config = getattr(client, "config", None)
    identity = {
        "client": type(client).__name__,
        "metadata": getattr(client, "metadata", {}),
        "model": getattr(config, "embedding_model", None),
        "dimensions": getattr(config, "embedding_dim", getattr(client, "dimensions", 1024)),
        "endpoint": getattr(config, "base_url", None),
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


class HashEmbedder(EmbedderClient):
    dimensions = 1024

    async def create(self, input_data) -> list[float]:
        text = input_data if isinstance(input_data, str) else " ".join(input_data)
        vector = [0.0] * self.dimensions
        for word in words(text):
            digest = hashlib.sha256(word.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1 if digest[4] % 2 else -1
        norm = math.sqrt(sum(x * x for x in vector)) or 1
        return [x / norm for x in vector]

    async def create_batch(self, input_data_list):
        return [await self.create(item) for item in input_data_list]
