"""Fit one raw-logit cutoff on the frozen development split only."""

import argparse
import asyncio
import math
import os
from datetime import UTC, datetime
from pathlib import Path

from eval.retrieval_evidence import load_cases, load_protocol, source_snapshot, write_json
from governed_memory.local_models import MiniLMReranker


def choose_cutoff(positive_scores, retention=0.95, grid=0.1):
    if not positive_scores or not all(math.isfinite(value) for value in positive_scores):
        raise ValueError("calibration needs finite positive-pair scores")
    if not 0 < retention <= 1 or not math.isfinite(grid) or grid <= 0:
        raise ValueError("invalid calibration rule")
    ordered = sorted(positive_scores)
    maximum_misses = math.floor((1 - retention) * len(ordered) + 1e-10)
    return round(math.floor(ordered[maximum_misses] / grid) * grid, 6)


async def calibrate(output):
    protocol, source = load_protocol(), source_snapshot()
    if source["dirty_source"]:
        raise ValueError("commit source and frozen fixtures before calibration")
    if output.exists():
        raise FileExistsError("preserve the previous calibration; choose a new directory")
    data = load_cases("dev")
    output.mkdir(parents=True)
    reranker = MiniLMReranker(os.environ.get("MEMORY_MODEL_CACHE"))
    pairs = []
    for group in data["groups"]:
        documents = group["documents"]
        texts = [f"{doc['subject']} | {doc['predicate']}: {doc['value']}" for doc in documents]
        for query in group["queries"]:
            scores = await reranker.scores(query["query"], texts)
            pairs.extend(
                {
                    "query_id": query["id"],
                    "document_id": doc["id"],
                    "score": score,
                    "positive": doc["id"] in query["gold"],
                }
                for doc, score in zip(documents, scores, strict=True)
            )
    rule = protocol["calibration"]
    positive = [pair["score"] for pair in pairs if pair["positive"]]
    cutoff = choose_cutoff(positive, rule["positive_pair_retention"], rule["score_grid"])
    policy = {
        "version": "minilm-relevance-v1",
        "model": reranker.metadata["model"],
        "revision": reranker.metadata["revision"],
        "score_type": "raw logits",
        "minimum_score": cutoff,
        "calibration_data_sha256": protocol["datasets"]["dev"]["sha256"],
        "selection": rule,
        "positive_pairs": len(positive),
        "positive_pairs_retained": sum(value >= cutoff for value in positive),
    }
    write_json(output / "policy.json", policy)
    write_json(output / "pair-scores.json", pairs)
    write_json(
        output / "provenance.json",
        {
            **source,
            "model": reranker.metadata,
            "calibrated_at": datetime.now(UTC).isoformat(),
            "heldout_used": False,
        },
    )
    print(policy)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(calibrate(parser.parse_args().output))
