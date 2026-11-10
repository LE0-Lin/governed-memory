"""Advisory entity matches and NLI findings over caller-visible approved snapshots."""

import asyncio
import unicodedata

import numpy as np

from governed_memory.embedding import HashEmbedder, embed_many
from governed_memory.errors import Conflict

NLI_MODEL = "cross-encoder/nli-deberta-v3-small"
NLI_REVISION = "fa2804872c3b4bd748f38c0185cc85775361e735"


class NliDetector:
    def __init__(self, cache_dir=None, device="cpu"):
        from governed_memory.local_models import runtime

        torch, library = runtime()
        self.model = library.CrossEncoder(
            NLI_MODEL,
            revision=NLI_REVISION,
            device=device,
            max_length=512,
            cache_folder=str(cache_dir) if cache_dir else None,
            token=False,
            trust_remote_code=False,
            activation_fn=torch.nn.Softmax(dim=-1),
            model_kwargs={"use_safetensors": True},
        )
        labels = {
            int(key): value.lower() for key, value in self.model.model.config.id2label.items()
        }
        if labels != {0: "contradiction", 1: "entailment", 2: "neutral"}:
            raise RuntimeError("unexpected NLI label mapping")
        self.metadata = {
            "model": NLI_MODEL,
            "revision": NLI_REVISION,
            "device": device,
            "max_tokens": 512,
            "language": "English",
            "scores": "softmax probabilities",
        }

    async def scores(self, pairs):
        if not pairs:
            return []
        values = np.asarray(
            await asyncio.to_thread(
                self.model.predict,
                pairs,
                batch_size=16,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
        )
        if values.shape != (len(pairs), 3) or not np.isfinite(values).all():
            raise RuntimeError("invalid NLI scores")
        return [
            dict(zip(("contradiction", "entailment", "neutral"), row.tolist(), strict=True))
            for row in values
        ]


def normalized(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def assertion(item):
    if isinstance(item, dict):
        return f"{item['subject']} {item['predicate']}: {item['value']}"
    return f"{item.subject} {item.predicate}: {item.value}"


class SemanticReview:
    def __init__(self, ledger, embedder, detector):
        if isinstance(embedder, HashEmbedder):
            raise ValueError("semantic entity review requires a semantic embedding model")
        self.ledger, self.embedder, self.detector = ledger, embedder, detector

    async def inspect(self, token, project, candidate_id):
        candidate, evidence = self.ledger.review_context(token, project, candidate_id)
        subjects = sorted({item.subject for item in evidence})
        vectors = np.asarray(await embed_many(self.embedder, [candidate["subject"], *subjects]))
        if vectors.ndim != 2 or len(vectors) != len(subjects) + 1 or not np.isfinite(vectors).all():
            raise ValueError("invalid entity embeddings")
        query = vectors[0]
        similarities = {}
        for subject, vector in zip(subjects, vectors[1:], strict=True):
            similarity = float(vector @ query) / max(
                float(np.linalg.norm(vector) * np.linalg.norm(query)), 1e-12
            )
            similarities[subject] = (
                1.0 if normalized(subject) == normalized(candidate["subject"]) else similarity
            )
        related = sorted(
            (item for item in evidence if similarities[item.subject] >= 0.55),
            key=lambda item: (-similarities[item.subject], item.id),
        )[:20]
        scores = await self.detector.scores(
            [(assertion(item), assertion(candidate)) for item in related]
        )
        # Re-read the entire supplied context: even an uncited private input must remain authorized.
        current, refreshed = self.ledger.review_context(token, project, candidate_id)
        if current != candidate or {item.id: item for item in evidence} != {
            item.id: item for item in refreshed
        }:
            raise Conflict("review context changed; discard findings and review again")
        return {
            "candidate_id": candidate_id,
            "advisory": True,
            "nli": self.detector.metadata,
            "entity_matches": [
                {
                    "subject": subject,
                    "similarity": similarities[subject],
                    "snapshot_id": next(item.id for item in evidence if item.subject == subject),
                }
                for subject in sorted(subjects, key=lambda s: (-similarities[s], s))[:5]
                if similarities[subject] >= 0.55
            ],
            "comparisons": [
                {
                    "snapshot_id": item.id,
                    "scores": score,
                    "contradiction": score["contradiction"] >= 0.8,
                }
                for item, score in zip(related, scores, strict=True)
            ],
        }
