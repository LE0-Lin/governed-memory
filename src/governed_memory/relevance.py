"""Relevance policies are tied to a pinned scored model and frozen development split."""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from governed_memory.embedding import content_words, words


def _finite_number(value, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f"invalid calibrated {label}")
    return float(value)


def _matches_reranker(reranker, policy: dict) -> bool:
    metadata = getattr(reranker, "metadata", None) or {}
    return (
        metadata.get("model") == policy["model"]
        and metadata.get("revision") == policy["revision"]
        and metadata.get("scores") == policy["score_type"]
    )


@dataclass(frozen=True)
class RelevanceGate:
    version: str
    minimum_score: float
    minimum_anchor_score: float
    minimum_gain: float
    passage_word_limit: int
    minimum_passage_score: float

    def is_structured_fact(self, item) -> bool:
        subject = getattr(item, "subject", None)
        predicate = getattr(item, "predicate", None)
        value = getattr(item, "value", None)
        if not all(isinstance(part, str) and part for part in (subject, predicate, value)):
            return False
        if getattr(item, "text", None) != f"{subject} | {predicate}: {value}":
            return False
        return len(words(value)) <= self.passage_word_limit

    def prefilter_floor(self, item) -> float:
        return self.minimum_score if self.is_structured_fact(item) else self.minimum_passage_score

    def accepts(
        self,
        query: str,
        item,
        full_score: float,
        *,
        subject_score: float | None = None,
        pv_score: float | None = None,
    ) -> bool:
        if not self.is_structured_fact(item):
            return full_score >= self.minimum_passage_score
        if full_score < self.minimum_score:
            return False
        if subject_score is None or pv_score is None:
            raise ValueError("structured relevance check requires subject and predicate scores")
        if max(subject_score, pv_score) < self.minimum_anchor_score:
            return False
        extra_terms = set(content_words(query)) - set(content_words(item.subject))
        if extra_terms and (full_score - subject_score) < self.minimum_gain:
            return False
        return True


def calibrated_cutoff(reranker) -> float:
    path = Path(__file__).parent / "data/minilm-relevance-v1.json"
    policy = json.loads(path.read_text(encoding="utf-8"))
    if not _matches_reranker(reranker, policy):
        raise ValueError("the relevance calibration does not match this reranker")
    return _finite_number(policy["minimum_score"], "relevance cutoff")


def calibrated_policy(reranker, *, strict: bool = True) -> RelevanceGate | None:
    path = Path(__file__).parent / "data/minilm-relevance-v2.json"
    policy = json.loads(path.read_text(encoding="utf-8"))
    if not _matches_reranker(reranker, policy):
        if strict:
            raise ValueError("the relevance calibration does not match this reranker")
        return None
    limit = policy["passage_word_limit"]
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("invalid calibrated passage word limit")
    return RelevanceGate(
        version=str(policy["version"]),
        minimum_score=_finite_number(policy["minimum_score"], "minimum score"),
        minimum_anchor_score=_finite_number(policy["minimum_anchor_score"], "anchor score"),
        minimum_gain=_finite_number(policy["minimum_gain"], "relevance gain"),
        passage_word_limit=limit,
        minimum_passage_score=_finite_number(policy["minimum_passage_score"], "passage score"),
    )
