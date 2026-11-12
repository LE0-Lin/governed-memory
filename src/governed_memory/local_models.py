"""Optional, pinned CPU models using the standard Sentence Transformers interfaces."""

import asyncio
from pathlib import Path
from typing import Protocol, TypeVar

import numpy as np
from graphiti_core.embedder.client import EmbedderClient

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
RERANKING_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
RERANKING_REVISION = "233902d25c440f23af6f7d6e94d2946bac0bee0a"
CPU_THREADS = 2
BATCH_SIZE = 16


class Document(Protocol):
    id: str
    text: str


D = TypeVar("D", bound=Document)


def runtime():
    try:
        import sentence_transformers
        import torch
    except ImportError as exc:
        raise RuntimeError("install optional models with: uv sync --extra models") from exc
    torch.set_num_threads(CPU_THREADS)
    return torch, sentence_transformers


class MiniLMEmbedder(EmbedderClient):
    dimensions = 1024
    native_dimensions = 384

    def __init__(self, cache_dir: str | Path | None = None, device="cpu"):
        _, library = runtime()
        self.model = library.SentenceTransformer(
            EMBEDDING_MODEL,
            revision=EMBEDDING_REVISION,
            device=device,
            cache_folder=str(cache_dir) if cache_dir else None,
            token=False,
            trust_remote_code=False,
            model_kwargs={"use_safetensors": True},
        )
        self.model.max_seq_length = 256
        self.metadata = {
            "model": EMBEDDING_MODEL,
            "revision": EMBEDDING_REVISION,
            "device": device,
            "threads": CPU_THREADS,
            "max_tokens": 256,
            "native_dimensions": 384,
            "projection_dimensions": 1024,
        }

    async def create(self, input_data):
        if not isinstance(input_data, str):
            if len(input_data) != 1:
                raise ValueError("create accepts one text; use create_batch for multiple texts")
            input_data = input_data[0]
        return (await self.create_batch([input_data]))[0]

    async def create_batch(self, input_data_list):
        if not input_data_list:
            return []
        vectors = await asyncio.to_thread(
            self.model.encode,
            input_data_list,
            batch_size=BATCH_SIZE,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        if vectors.shape != (len(input_data_list), self.native_dimensions):
            raise RuntimeError("embedding model returned unexpected dimensions")
        # Zero padding preserves cosine similarity while using the existing graph index width.
        return np.pad(vectors, ((0, 0), (0, self.dimensions - self.native_dimensions))).tolist()


class MiniLMReranker:
    def __init__(self, cache_dir: str | Path | None = None, device="cpu"):
        torch, library = runtime()
        self.model = library.CrossEncoder(
            RERANKING_MODEL,
            revision=RERANKING_REVISION,
            device=device,
            max_length=512,
            cache_folder=str(cache_dir) if cache_dir else None,
            token=False,
            trust_remote_code=False,
            activation_fn=torch.nn.Identity(),
            model_kwargs={"use_safetensors": True},
        )
        self.metadata = {
            "model": RERANKING_MODEL,
            "revision": RERANKING_REVISION,
            "device": device,
            "threads": CPU_THREADS,
            "max_tokens": 512,
            "scores": "raw logits",
        }

    async def scores(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        scores = await asyncio.to_thread(
            self.model.predict,
            [(query, passage) for passage in passages],
            batch_size=BATCH_SIZE,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        values = np.asarray(scores).reshape(-1)
        if len(values) != len(passages) or not np.isfinite(values).all():
            raise RuntimeError("reranker returned invalid scores")
        return values.tolist()

    async def rerank(self, query: str, documents: list[D]) -> list[D]:
        scores = await self.scores(query, [document.text for document in documents])
        ranked = sorted(
            zip(documents, scores, strict=True), key=lambda pair: (-pair[1], pair[0].id)
        )
        return [document for document, _ in ranked]
