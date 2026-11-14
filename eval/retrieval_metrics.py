"""Paired unfiltered service metrics, including first-pass and repeat-cache results."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import os
import platform
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np

from eval.cv_run import aggregate, database, populate, processor_name
from eval.metrics_cases import scaled_timelines
from eval.retrieval_evidence import checksum, load_cases, source_snapshot, write_json
from eval.retrieval_quality import MeasuredEmbedder, populate_heldout
from eval.run import raw_evidence
from governed_memory.embedding_cache import DocumentEmbeddingCache
from governed_memory.ledger import instant
from governed_memory.local_models import MiniLMEmbedder, MiniLMReranker
from governed_memory.rerank_cache import RerankScoreCache
from governed_memory.retrieval import Retriever, hybrid_rank, serialize

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "eval/RETRIEVAL_METRICS_PROTOCOL.md"
METHODS = ("session_baseline", "governed_control", "governed_score_cache")


class MeasuredReranker(MiniLMReranker):
    pair_computations = 0

    async def scores(self, query, texts):
        self.pair_computations += len(texts)
        return await super().scores(query, texts)


async def session_search(retriever, query):
    """The same explicit unsafe control as v0.4, now given both computation caches."""
    started = perf_counter()
    evidence = [
        item
        for item in raw_evidence(retriever.ledger, query["token"], query["project"])
        if item.system_from <= instant(query["known_at"])
    ]
    ranked = await hybrid_rank(
        query["query"],
        evidence,
        retriever.embedder,
        ranking_backend="rust",
        document_cache=retriever.document_cache,
    )
    candidates = ranked[:50]
    scores = await retriever.rerank_cache.scores(
        retriever.reranker, query["project"], query["query"], [item.text for item in candidates]
    )
    ordered = sorted(zip(candidates, scores, strict=True), key=lambda pair: (-pair[1], pair[0].id))
    packed, used = retriever.pack([item for item, _ in ordered], 1024, 5)
    result = {"evidence": packed, "evidence_tokens": used, "reason": "session_baseline"}
    serialize(result)
    result["latency_ms"] = (perf_counter() - started) * 1000
    return result


def summarize(rows):
    result = aggregate(rows)
    for label, selected in (
        ("first_pass", [row for row in rows if row["repetition"] == 0]),
        ("repeat", [row for row in rows if row["repetition"] > 0]),
    ):
        result[f"{label}_observations"] = len(selected)
        for percentile in (50, 95):
            result[f"{label}_p{percentile}_ms"] = float(
                np.percentile([row["latency_ms"] for row in selected], percentile, method="linear")
            )
    result["reranker_pair_computations"] = sum(row["reranker_pair_computations"] for row in rows)
    return result


def paired_equivalence(rows):
    pairs = defaultdict(dict)
    for row in rows:
        if row["method"] != "session_baseline":
            pairs[(row["workload"], row["query_id"], row["repetition"])][row["method"]] = row
    mismatches = []
    for key, methods in pairs.items():
        control, cached = methods["governed_control"], methods["governed_score_cache"]
        fields = ("predicted_ids", "evidence_tokens", "evidence_sha256", "reason", "error")
        if any(control[field] != cached[field] for field in fields):
            mismatches.append(key)
    return {"pairs": len(pairs), "mismatches": mismatches}


def prepare_queries(engine, workload, data):
    if workload == "heldout":
        return populate_heldout(engine, data)
    ledger, token, project, candidates = populate(engine, data)
    aliases = {alias: candidate["id"] for alias, candidate in candidates.items()}
    queries = [
        {
            **query,
            "project": project,
            "token": token,
            "gold_ids": [aliases[alias] for alias in query["gold"]],
            "eligible_ids": [aliases[alias] for alias in query["eligible"]],
        }
        for query in data["queries"]
    ]
    return ledger, queries, aliases


async def experiment(output):
    source = source_snapshot()
    if source["dirty_source"]:
        raise ValueError("commit the source before a canonical run")
    output.mkdir(parents=True, exist_ok=False)
    workloads = {f"timelines_{size}": scaled_timelines(size) for size in (1, 4, 16)}
    workloads["heldout"] = load_cases("heldout")
    for name, data in workloads.items():
        write_json(output / f"{name}-fixture.json", data)
    manifest = {
        **source,
        "protocol_sha256": checksum(PROTOCOL),
        "protocol": PROTOCOL.read_text(encoding="utf-8"),
        "datasets": {name: checksum(output / f"{name}-fixture.json") for name in workloads},
        "started_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "os": platform.platform(),
        "cpu": processor_name(),
        "repetitions": 3,
        "methods": METHODS,
        "document_capacity": 2048,
        "score_capacity": 8192,
        "runtime_image": os.environ.get("GM_EVAL_IMAGE_ID"),
    }
    write_json(output / "manifest.json", manifest)
    embedder = MeasuredEmbedder(MiniLMEmbedder(os.environ.get("MEMORY_MODEL_CACHE")))
    reranker = MeasuredReranker(os.environ.get("MEMORY_MODEL_CACHE"))
    manifest.update(
        embedding=embedder.metadata,
        reranker=reranker.metadata,
        packages={
            name: importlib.metadata.version(name)
            for name in (
                "governed-memory",
                "torch",
                "transformers",
                "sentence-transformers",
                "numpy",
                "sqlalchemy",
            )
        },
    )
    await embedder.create("An unrelated fictional warmup query.")
    await reranker.scores("fictional warmup", ["An unrelated fictional warmup document."])
    rows, cache_info = [], {}
    with (output / "observations.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for workload, data in workloads.items():
            with database() as engine:
                ledger, queries, aliases = prepare_queries(engine, workload, data)
                manifest["storage"] = engine.dialect.name
                write_json(output / "manifest.json", manifest)
                write_json(output / f"{workload}-aliases.json", aliases)
                methods = {
                    name: Retriever(
                        ledger,
                        embedder=embedder,
                        reranker=reranker,
                        ranking_backend="rust",
                        document_cache=DocumentEmbeddingCache(2048),
                        rerank_cache=None if name == "governed_control" else RerankScoreCache(8192),
                    )
                    for name in METHODS
                }
                for repetition in range(3):
                    for index, query in enumerate(queries):
                        offset = (index + repetition) % len(METHODS)
                        for name in METHODS[offset:] + METHODS[:offset]:
                            before = reranker.pair_computations
                            started, error = perf_counter(), None
                            try:
                                if name == "session_baseline":
                                    result = await session_search(methods[name], query)
                                else:
                                    result = await methods[name].search(
                                        query["token"],
                                        query["project"],
                                        query["query"],
                                        valid_at=query["valid_at"],
                                        known_at=query["known_at"],
                                        token_budget=1024,
                                        k=5,
                                    )
                            except Exception as exc:
                                error = type(exc).__name__
                                result = {
                                    "evidence": [],
                                    "evidence_tokens": 0,
                                    "reason": "retrieval_failed",
                                    "latency_ms": (perf_counter() - started) * 1000,
                                }
                            predicted = [item["candidate_id"] for item in result["evidence"]]
                            row = {
                                "workload": workload,
                                "method": name,
                                "repetition": repetition,
                                "query_id": query["id"],
                                "kind": query["kind"],
                                "query": query["query"],
                                "gold_ids": query["gold_ids"],
                                "predicted_ids": predicted,
                                "stale_ids": [
                                    item for item in predicted if item not in query["eligible_ids"]
                                ],
                                "evidence_tokens": result["evidence_tokens"],
                                "reason": result["reason"],
                                "evidence_sha256": hashlib.sha256(
                                    serialize(result["evidence"]).encode()
                                ).hexdigest(),
                                "latency_ms": result["latency_ms"],
                                "error": error,
                                "reranker_pair_computations": reranker.pair_computations - before,
                            }
                            rows.append(row)
                            stream.write(serialize(row) + "\n")
                            stream.flush()
                    print(f"{workload}: repetition {repetition + 1}/3 completed", flush=True)
                cache_info[workload] = {
                    name: {
                        "document": method.document_cache.info(),
                        "rerank": method.rerank_cache.info() if method.rerank_cache else None,
                    }
                    for name, method in methods.items()
                }
    groups = defaultdict(list)
    for row in rows:
        groups[f"{row['workload']}/{row['method']}"].append(row)
    summary = {name: summarize(group) for name, group in sorted(groups.items())}
    equivalence = paired_equivalence(rows)
    stable = (
        source["code_sha256"] == source_snapshot()["code_sha256"]
        and checksum(PROTOCOL) == manifest["protocol_sha256"]
    )
    manifest.update(
        completed_at=datetime.now(UTC).isoformat(), source_unchanged=stable, cache=cache_info
    )
    write_json(output / "manifest.json", manifest)
    write_json(output / "summary.json", summary)
    write_json(output / "equivalence.json", equivalence)
    print(serialize(summary))
    if (
        not stable
        or equivalence["mismatches"]
        or any(row["error"] for row in rows)
        or any(row["stale_ids"] for row in rows if row["method"] != "session_baseline")
    ):
        raise SystemExit("run failed; all observations are retained")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(experiment(parser.parse_args().output))
