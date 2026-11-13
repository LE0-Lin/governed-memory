"""Paired real-service relevance/cache experiment under the frozen protocol."""

import argparse
import asyncio
import importlib.metadata
import os
import platform
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

import numpy as np

from eval.cv_run import database, populate, processor_name
from eval.retrieval_evidence import load_cases, load_protocol, source_snapshot, write_json
from governed_memory.budget import serialize
from governed_memory.embedding_cache import DocumentEmbeddingCache
from governed_memory.identity import bootstrap, create_project, issue_credential
from governed_memory.ledger import Ledger, instant
from governed_memory.local_models import MiniLMEmbedder, MiniLMReranker
from governed_memory.relevance import calibrated_cutoff
from governed_memory.retrieval import Retriever


class MeasuredEmbedder:
    def __init__(self, delegate):
        self.delegate = delegate
        self.metadata, self.dimensions = delegate.metadata, delegate.dimensions
        self.document_computations = 0

    async def create(self, text):
        return await self.delegate.create(text)

    async def create_batch(self, texts):
        self.document_computations += len(texts)
        return await self.delegate.create_batch(texts)


class RecordingReranker(MiniLMReranker):
    async def scores(self, query, texts):
        values = await super().scores(query, texts)
        self.last_scores = [
            dict(text=text, score=score) for text, score in zip(texts, values, strict=True)
        ]
        return values


def populate_heldout(engine, data):
    state = {"now": instant("2030-02-01T00:00:00Z")}
    ledger = Ledger(engine, lambda: state["now"])
    admin = bootstrap(engine, "operator", "quality")
    queries, aliases = [], {}
    for group in data["groups"]:
        project = group["id"]
        create_project(engine, admin, "quality", project)
        token = issue_credential(engine, admin, f"agent-{project}", project, "agent")
        for doc in group["documents"]:
            state["now"] += timedelta(seconds=1)
            candidate = ledger.propose(
                token,
                project,
                subject=doc["subject"],
                predicate=doc["predicate"],
                value=doc["value"],
                valid_from="2030-01-01T00:00:00Z",
                locator=f"fixture:{doc['id']}",
            )
            state["now"] += timedelta(seconds=1)
            aliases[doc["id"]] = ledger.decide(
                admin,
                project,
                candidate["id"],
                "approve",
                0,
                reason="frozen synthetic assertion",
                expected_head=0,
            )["id"]
        eligible = [aliases[doc["id"]] for doc in group["documents"]]
        for query in group["queries"]:
            queries.append(
                {
                    **query,
                    "project": project,
                    "token": token,
                    "gold_ids": [aliases[alias] for alias in query["gold"]],
                    "eligible_ids": eligible,
                    "valid_at": state["now"],
                    "known_at": state["now"],
                }
            )
    return ledger, queries, aliases


def metrics(rows):
    positive = [row for row in rows if row["gold_ids"]]
    negative = [row for row in rows if not row["gold_ids"]]
    return {
        "observations": len(rows),
        "errors": sum(row["error"] is not None for row in rows),
        "positive_observations": len(positive),
        "negative_observations": len(negative),
        "gold_recall": float(
            np.mean(
                [
                    len(set(row["gold_ids"]) & set(row["predicted_ids"])) / len(row["gold_ids"])
                    for row in positive
                ]
            )
        ),
        "positive_empty": sum(not row["predicted_ids"] for row in positive),
        "negative_empty": sum(not row["predicted_ids"] for row in negative),
        "negative_returned": sum(len(row["predicted_ids"]) for row in negative),
        "stale_count": sum(len(row["stale_ids"]) for row in rows),
        "document_computations": sum(row["document_computations"] for row in rows),
        "latency_ms_p50": float(np.percentile([row["latency_ms"] for row in rows], 50)),
        "latency_ms_p95": float(np.percentile([row["latency_ms"] for row in rows], 95)),
        "warm_repetitions_p95_ms": float(
            np.percentile([row["latency_ms"] for row in rows if row["repetition"] > 0], 95)
        ),
    }


async def experiment(output):
    source, protocol = source_snapshot(), load_protocol()
    if source["dirty_source"]:
        raise ValueError("commit the experiment and implementation before a canonical run")
    if output.exists():
        raise FileExistsError("preserve previous results; choose another directory")
    output.mkdir(parents=True)
    config = protocol["service"]
    embedder = MeasuredEmbedder(MiniLMEmbedder(os.environ.get("MEMORY_MODEL_CACHE")))
    reranker = RecordingReranker(os.environ.get("MEMORY_MODEL_CACHE"))
    cutoff = calibrated_cutoff(reranker)
    manifest = {
        **source,
        "protocol": protocol,
        "minimum_score": cutoff,
        "started_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "os": platform.platform(),
        "cpu": processor_name(),
        "embedding": embedder.metadata,
        "reranker": reranker.metadata,
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("torch", "transformers", "sentence-transformers", "numpy", "sqlalchemy")
        },
    }
    write_json(output / "manifest.json", manifest)
    rows, cache_info = [], {}
    with (output / "observations.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
        for workload in ("legacy_cv", "heldout"):
            with database() as engine:
                data = load_cases(workload)
                if workload == "legacy_cv":
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
                else:
                    ledger, queries, aliases = populate_heldout(engine, data)
                manifest["storage"] = engine.dialect.name
                write_json(output / f"{workload}-aliases.json", aliases)
                methods = {}
                for name in config["methods"]:
                    methods[name] = Retriever(
                        ledger,
                        embedder=embedder,
                        reranker=reranker,
                        ranking_backend=config["ranking_backend"],
                        min_relevance_score=None if name == "ungated_uncached" else cutoff,
                        document_cache=DocumentEmbeddingCache(config["cache_entries"])
                        if name == "gated_cached"
                        else None,
                    )
                    await embedder.create("A fictional warmup query.")
                    await reranker.scores("database", ["Fictional storage uses PostgreSQL."])
                for repetition in range(config["repetitions"]):
                    names = config["methods"]
                    for index, query in enumerate(queries):
                        shift = (index + repetition) % len(names)
                        for name in names[shift:] + names[:shift]:
                            retriever = methods[name]
                            before = embedder.document_computations
                            started, error = perf_counter(), None
                            reranker.last_scores = []
                            try:
                                result = await retriever.search(
                                    query["token"],
                                    query["project"],
                                    query["query"],
                                    valid_at=query["valid_at"],
                                    known_at=query["known_at"],
                                    k=config["k"],
                                    token_budget=config["token_budget"],
                                )
                            except Exception as exc:
                                error = type(exc).__name__
                                result = dict(
                                    evidence=[],
                                    evidence_tokens=0,
                                    reason="error",
                                    latency_ms=(perf_counter() - started) * 1000,
                                )
                            predicted = [item["candidate_id"] for item in result["evidence"]]
                            row = dict(
                                workload=workload,
                                method=name,
                                repetition=repetition,
                                query_id=query["id"],
                                kind=query["kind"],
                                query=query["query"],
                                gold_ids=query["gold_ids"],
                                predicted_ids=predicted,
                                stale_ids=[
                                    identifier
                                    for identifier in predicted
                                    if identifier not in query["eligible_ids"]
                                ],
                                reason=result["reason"],
                                evidence_tokens=result["evidence_tokens"],
                                latency_ms=result["latency_ms"],
                                scores=reranker.last_scores,
                                document_computations=embedder.document_computations - before,
                                error=error,
                            )
                            rows.append(row)
                            stream.write(serialize(row) + "\n")
                            stream.flush()
                    print(f"{workload}: repetition {repetition + 1} complete", flush=True)
                cache_info[workload] = methods["gated_cached"].document_cache.info()
    groups = defaultdict(list)
    for row in rows:
        groups[f"{row['workload']}/{row['method']}"].append(row)
    summary = {key: metrics(group) for key, group in sorted(groups.items())}
    final_source = source_snapshot()
    manifest.update(
        completed_at=datetime.now(UTC).isoformat(),
        source_changed_during_run=source["code_sha256"] != final_source["code_sha256"],
        cache=cache_info,
    )
    write_json(output / "manifest.json", manifest)
    write_json(output / "summary.json", summary)
    print(serialize(summary))
    if manifest["source_changed_during_run"] or any(row["error"] for row in rows):
        raise SystemExit("experiment errors retained; inspect the run")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(experiment(parser.parse_args().output))
