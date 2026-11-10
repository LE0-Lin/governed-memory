"""A cutoff is tied to a scored model and development data, not a confidence percentage."""

import json
import math
from pathlib import Path


def calibrated_cutoff(reranker):
    path = Path(__file__).parent / "data/minilm-relevance-v1.json"
    policy = json.loads(path.read_text(encoding="utf-8"))
    metadata = reranker.metadata
    if (
        metadata.get("model") != policy["model"]
        or metadata.get("revision") != policy["revision"]
        or metadata.get("scores") != policy["score_type"]
    ):
        raise ValueError("the relevance calibration does not match this reranker")
    cutoff = policy["minimum_score"]
    if (
        not isinstance(cutoff, (int, float))
        or isinstance(cutoff, bool)
        or not math.isfinite(cutoff)
    ):
        raise ValueError("invalid calibrated relevance cutoff")
    return float(cutoff)
