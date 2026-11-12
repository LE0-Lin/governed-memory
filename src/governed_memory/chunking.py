"""Semantic boundaries over exact source spans; no model rewrites source text."""

import re
from dataclasses import dataclass

import numpy as np

from governed_memory.embedding import HashEmbedder, embed_many
from governed_memory.native import kernels
from governed_memory.tokenizer import encoding


@dataclass(frozen=True)
class Chunk:
    start: int
    end: int
    text: str
    tokens: int


def bounded_spans(text, start, end, tokenizer, limit):
    """Split oversized sentences on character offsets, preserving even multibyte text."""
    while start < end:
        if len(tokenizer.encode(text[start:end])) <= limit:
            yield start, end
            return
        low, high = start + 1, end
        while low < high:
            middle = (low + high + 1) // 2
            if len(tokenizer.encode(text[start:middle])) <= limit:
                low = middle
            else:
                high = middle - 1
        yield start, low
        start = low


def python_boundaries(vectors, counts, maximum, minimum, threshold):
    spans, start, used = [], 0, 0
    for i, count in enumerate(counts):
        drift = False
        if i > start and used >= minimum:
            norm = max(float(np.linalg.norm(vectors[i - 1]) * np.linalg.norm(vectors[i])), 1e-12)
            drift = float(np.dot(vectors[i - 1], vectors[i])) / norm < threshold
        if i > start and (used + count > maximum or drift):
            spans.append((start, i))
            start, used = i, 0
        used += count
    if start < len(counts):
        spans.append((start, len(counts)))
    return spans


async def semantic_chunks(
    text: str, embedder, *, max_tokens=180, min_tokens=40, threshold=0.45, backend="auto"
) -> list[Chunk]:
    if not isinstance(text, str) or not text.strip() or len(text) > 100_000:
        raise ValueError("document must contain 1..100000 characters")
    if not 8 <= min_tokens <= max_tokens <= 512 or not -1 <= threshold <= 1:
        raise ValueError("invalid semantic chunk limits")
    if isinstance(embedder, HashEmbedder):
        raise ValueError("semantic chunking requires a semantic embedding model")
    tokenizer = encoding()
    ends = [m.end() for m in re.finditer(r"[.!?。！？](?:\s+|$)|\n[ \t]*\n+", text)]
    if not ends or ends[-1] != len(text):
        ends.append(len(text))
    units, start = [], 0
    for end in ends:
        units.extend(bounded_spans(text, start, end, tokenizer, max_tokens))
        start = end
    vectors = np.asarray(await embed_many(embedder, [text[a:b] for a, b in units]), dtype=float)
    if (
        vectors.ndim != 2
        or len(vectors) != len(units)
        or vectors.shape[1] == 0
        or not np.isfinite(vectors).all()
    ):
        raise ValueError("embedder returned invalid sentence vectors")
    counts = [len(tokenizer.encode(text[a:b])) for a, b in units]
    native = kernels(backend)
    spans = (
        native.semantic_spans(vectors.tolist(), counts, max_tokens, min_tokens, threshold)
        if native
        else python_boundaries(vectors, counts, max_tokens, min_tokens, threshold)
    )
    chunks = []
    for first, last in spans:
        # Tokenization across a sentence boundary can differ from the sum of its parts.
        for a, b in bounded_spans(text, units[first][0], units[last - 1][1], tokenizer, max_tokens):
            chunks.append(Chunk(a, b, text[a:b], len(tokenizer.encode(text[a:b]))))
    return chunks
