"""Paired exact-v0.7 and targeted-read retrieval, with identical model caches."""

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

from eval.controlled_run import database, processor_name
from eval.metrics_cases import scaled_timelines
from eval.reference_v07 import reference_classes
from eval.retrieval_evidence import checksum, load_cases, source_snapshot, write_json
from eval.retrieval_metrics import MeasuredReranker, prepare_queries, summarize
from eval.retrieval_quality import MeasuredEmbedder
from governed_memory.embedding_cache import DocumentEmbeddingCache
from governed_memory.local_models import MiniLMEmbedder
from governed_memory.rerank_cache import RerankScoreCache
from governed_memory.retrieval import Retriever, serialize

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "eval/AUTHORITY_REFRESH_V2_PROTOCOL.md"
METHODS = ("reference_v07", "targeted_refresh")


class ReadMeter:
    def __init__(self, ledger):
        self.reads = self.rows = 0
        self.original = ledger.visible
        ledger.visible = self.visible

    def visible(self, *args, **kwargs):
        result = self.original(*args, **kwargs)
        self.reads += 1
        self.rows += len(result)
        return result


async def experiment(output):
    source = source_snapshot()
    if source["dirty_source"]:
        raise ValueError("commit the implementation/evaluator before a canonical run")
    old_ledger, old_retriever, reference = reference_classes()
    output.mkdir(parents=True, exist_ok=False)
    datasets = {f"timelines_{size}": scaled_timelines(size) for size in (1, 4, 16)}
    datasets["heldout"] = load_cases("heldout")
    for name, data in datasets.items():
        write_json(output / f"{name}-fixture.json", data)
    manifest = {
        **source,
        "protocol": PROTOCOL.read_text(encoding="utf-8"),
        "protocol_sha256": checksum(PROTOCOL),
        "reference": reference,
        "datasets": {name: checksum(output / f"{name}-fixture.json") for name in datasets},
        "started_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "os": platform.platform(),
        "cpu": processor_name(),
        "methods": METHODS,
        "comparison": METHODS,
        "repetitions": 3,
        "document_capacity": 2048,
        "score_capacity": 8192,
        "runtime_image": os.environ.get("GM_EVAL_IMAGE_ID"),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "runner_name": os.environ.get("RUNNER_NAME"),
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
    rows, caches = [], {}
    with (output / "observations.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for workload, data in datasets.items():
            with database() as engine:
                ledger, queries, aliases = prepare_queries(engine, workload, data)
                legacy = old_ledger(engine, ledger.clock)
                meters = {"reference_v07": ReadMeter(legacy), "targeted_refresh": ReadMeter(ledger)}
                methods = {}
                for name, cls, store in (
                    ("reference_v07", old_retriever, legacy),
                    ("targeted_refresh", Retriever, ledger),
                ):
                    methods[name] = cls(
                        store,
                        embedder=embedder,
                        reranker=reranker,
                        ranking_backend="rust",
                        document_cache=DocumentEmbeddingCache(2048),
                        rerank_cache=RerankScoreCache(8192),
                    )
                manifest["storage"] = engine.dialect.name
                write_json(output / "manifest.json", manifest)
                write_json(output / f"{workload}-aliases.json", aliases)
                for repeat in range(3):
                    for index, query in enumerate(queries):
                        offset = (index + repeat) % 2
                        for name in METHODS[offset:] + METHODS[:offset]:
                            meter = meters[name]
                            previous = (meter.reads, meter.rows, reranker.pair_computations)
                            started, error = perf_counter(), None
                            try:
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
                                "repetition": repeat,
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
                                "visible_reads": meter.reads - previous[0],
                                "visible_rows": meter.rows - previous[1],
                                "reranker_pair_computations": reranker.pair_computations
                                - previous[2],
                            }
                            rows.append(row)
                            stream.write(serialize(row) + "\n")
                            stream.flush()
                    print(f"{workload}: repetition {repeat + 1}/3 completed", flush=True)
                caches[workload] = {
                    name: {
                        "document": method.document_cache.info(),
                        "rerank": method.rerank_cache.info(),
                    }
                    for name, method in methods.items()
                }
    grouped, pairs = defaultdict(list), defaultdict(dict)
    for row in rows:
        grouped[f"{row['workload']}/{row['method']}"].append(row)
        pairs[(row["workload"], row["query_id"], row["repetition"])][row["method"]] = row
    summaries = {
        name: dict(
            summarize(group),
            visible_reads=sum(row["visible_reads"] for row in group),
            visible_rows=sum(row["visible_rows"] for row in group),
        )
        for name, group in sorted(grouped.items())
    }
    mismatches = [
        key
        for key, pair in pairs.items()
        if any(
            pair[METHODS[0]][field] != pair[METHODS[1]][field]
            for field in ("predicted_ids", "evidence_tokens", "evidence_sha256", "reason", "error")
        )
    ]
    stable = (
        source["code_sha256"] == source_snapshot()["code_sha256"]
        and checksum(PROTOCOL) == manifest["protocol_sha256"]
    )
    manifest.update(
        completed_at=datetime.now(UTC).isoformat(), source_unchanged=stable, cache=caches
    )
    write_json(output / "manifest.json", manifest)
    write_json(output / "summary.json", summaries)
    write_json(output / "equivalence.json", {"pairs": len(pairs), "mismatches": mismatches})
    print(serialize(summaries))
    if not stable or mismatches or any(row["error"] or row["stale_ids"] for row in rows):
        raise SystemExit("paired run failed; all observations retained")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(experiment(parser.parse_args().output))
