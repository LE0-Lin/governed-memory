"""Frozen controlled comparison with actual neural models and native ranking kernels."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import numpy as np
from sqlalchemy import event, text

from eval.run import raw_evidence
from governed_memory.db import create_db, initialize
from governed_memory.identity import bootstrap, issue_credential
from governed_memory.ledger import Ledger, instant
from governed_memory.local_models import MiniLMEmbedder, MiniLMReranker
from governed_memory.retrieval import Retriever, hybrid_rank, serialize

ROOT = Path(__file__).resolve().parents[1]


def processor_name():
    name = platform.processor()
    if not name and Path("/proc/cpuinfo").exists():
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.partition(":")[2].strip()
    return name


def snapshot():
    files = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "native/src").glob("*.rs"))
    files += sorted((ROOT / "eval").glob("cv*"))
    files += [
        ROOT / name
        for name in (
            "pyproject.toml",
            "uv.lock",
            "native/Cargo.toml",
            "native/pyproject.toml",
            "native/Cargo.lock",
        )
    ]
    return {
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "dirty_source": bool(
            subprocess.check_output(
                [
                    "git",
                    "status",
                    "--porcelain",
                    "--",
                    "src",
                    "native",
                    "eval/cv*",
                    "pyproject.toml",
                    "uv.lock",
                ],
                cwd=ROOT,
                text=True,
            ).strip()
        ),
        "code_sha256": hashlib.sha256(
            b"".join(
                p.relative_to(ROOT).as_posix().encode()
                + b"\0"
                + p.read_bytes().replace(b"\r\n", b"\n")
                for p in files
                if p.is_file()
            )
        ).hexdigest(),
    }


@contextmanager
def database():
    url = os.environ.get("GM_EVAL_DATABASE_URL", "sqlite:///:memory:")
    engine = create_db(url)
    schema = "gm_cv_" + uuid4().hex
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))

        @event.listens_for(engine, "checkout")
        def isolate(connection, *_):
            with connection.cursor() as cursor:
                cursor.execute(f'SET search_path TO "{schema}"')
            connection.commit()

    try:
        initialize(engine)
        yield engine
    finally:
        if engine.dialect.name == "postgresql":
            with engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def populate(engine, data):
    state = {"now": instant("2030-01-01T00:00:00Z")}
    ledger = Ledger(engine, lambda: state["now"])
    project = "cv-controlled-v1"
    admin = bootstrap(engine, "operator", project)
    agent = issue_credential(engine, admin, "agent", project, "agent")
    candidates, operations = {}, []
    for fact in data["facts"]:
        for field, action in (
            ("arrives", "propose"),
            ("approves", "approve"),
            ("rejects", "reject"),
            ("withdrawn", "withdraw"),
        ):
            if fact.get(field):
                operations.append((fact[field], action, fact))
    for timestamp, action, fact in sorted(
        operations, key=lambda op: (op[0], op[1], op[2]["alias"])
    ):
        state["now"] = instant(timestamp)
        if action == "propose":
            parent_ids = []
            if fact.get("parent"):
                parent = candidates[fact["parent"]]
                parent_ids = [
                    next(
                        item.id
                        for item in ledger.visible(admin, project)
                        if item.candidate_id == parent["id"]
                    )
                ]
            candidates[fact["alias"]] = ledger.propose(
                agent,
                project,
                subject=fact["subject"],
                predicate=fact["predicate"],
                value=fact["value"],
                valid_from=fact["valid_from"],
                locator=f"synthetic:{fact['alias']}",
                parent_ids=parent_ids,
            )
        else:
            candidate = candidates[fact["alias"]]
            if action == "withdraw":
                ledger.withdraw_source(admin, project, candidate["source_id"])
            else:
                head = ledger.preview(admin, project, candidate["id"])["head_revision"]
                ledger.decide(
                    admin,
                    project,
                    candidate["id"],
                    action,
                    0,
                    expected_head=head,
                    reason="frozen synthetic lifecycle label",
                )
    state["now"] = instant(data["now"])
    return ledger, agent, project, candidates


async def session_baseline(ledger, token, project, query, retriever, config):
    start = perf_counter()
    evidence = [
        item
        for item in raw_evidence(ledger, token, project)
        if item.system_from <= instant(query["known_at"])
    ]
    ranked = await hybrid_rank(query["query"], evidence, retriever.embedder, ranking_backend="rust")
    ranked = await retriever.reranker.rerank(query["query"], ranked[:50])
    packed, used = retriever.pack(ranked, config["token_budget"], config["k"])
    result = {"evidence": packed, "evidence_tokens": used, "ranking_engine": "rust"}
    serialize(result)
    result["latency_ms"] = (perf_counter() - start) * 1000
    return result


def aggregate(rows):
    positive = [row for row in rows if row["gold_ids"]]
    negative = [row for row in rows if not row["gold_ids"]]
    returned = sum(len(row["predicted_ids"]) for row in rows)
    stale = sum(len(row["stale_ids"]) for row in rows)
    return {
        "observations": len(rows),
        "positive_observations": len(positive),
        "negative_observations": len(negative),
        "errors": sum(row["error"] is not None for row in rows),
        "temporal_recall": float(
            np.mean(
                [
                    len(set(row["predicted_ids"]) & set(row["gold_ids"])) / len(row["gold_ids"])
                    for row in positive
                ]
            )
        ),
        "returned": returned,
        "stale_count": stale,
        "stale_rate": stale / returned if returned else 0.0,
        "negative_stale_failures": sum(bool(row["stale_ids"]) for row in negative),
        "negative_unrelated_results": sum(
            len(row["predicted_ids"]) - len(row["stale_ids"]) for row in negative
        ),
        "latency_ms_p50": float(
            np.percentile([row["latency_ms"] for row in rows], 50, method="linear")
        ),
        "latency_ms_p95": float(
            np.percentile([row["latency_ms"] for row in rows], 95, method="linear")
        ),
    }


async def run(args):
    protocol = json.loads((ROOT / "eval/cv-protocol.json").read_text(encoding="utf-8"))
    raw = (ROOT / "eval" / protocol["dataset"]["file"]).read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(raw).hexdigest() != protocol["dataset"]["sha256"]:
        raise ValueError("frozen CV dataset checksum mismatch")
    data, config = json.loads(raw), protocol["retrieval"]
    source = snapshot()
    if source["dirty_source"]:
        raise ValueError("commit the implementation before recording a canonical CV evaluation")
    if args.output.exists():
        raise ValueError("output already exists; previous results must not be overwritten")
    args.output.mkdir(parents=True)
    embedder = MiniLMEmbedder(os.environ.get("MEMORY_MODEL_CACHE"))
    reranker = MiniLMReranker(os.environ.get("MEMORY_MODEL_CACHE"))
    with database() as engine:
        ledger, token, project, candidates = populate(engine, data)
        (args.output / "candidate-ids.json").write_text(
            json.dumps(
                {
                    alias: {key: candidate[key] for key in ("id", "source_id", "fact_id")}
                    for alias, candidate in candidates.items()
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        retriever = Retriever(ledger, embedder=embedder, reranker=reranker, ranking_backend="rust")
        methods = ("session_baseline", "governed")

        async def retrieve(method, query):
            if method == "session_baseline":
                return await session_baseline(ledger, token, project, query, retriever, config)
            return await retriever.search(
                token,
                project,
                query["query"],
                valid_at=query["valid_at"],
                known_at=query["known_at"],
                token_budget=config["token_budget"],
                k=config["k"],
            )

        manifest = {
            **source,
            "started_at": datetime.now(UTC).isoformat(),
            "protocol": protocol,
            "python": platform.python_version(),
            "os": platform.platform(),
            "cpu": processor_name(),
            "logical_cpus": os.cpu_count(),
            "storage": engine.dialect.name,
            "embedding": embedder.metadata,
            "reranker": reranker.metadata,
            "packages": {
                name: importlib.metadata.version(name)
                for name in (
                    "torch",
                    "sentence-transformers",
                    "transformers",
                    "numpy",
                    "sqlalchemy",
                    "rank-bm25",
                )
            },
        }
        (args.output / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        for method in methods:
            await retrieve(method, data["queries"][0])
        rows = []
        with (args.output / "observations.jsonl").open(
            "x", encoding="utf-8", newline="\n"
        ) as stream:
            for repetition in range(protocol["execution"]["measured_repetitions"]):
                for index, query in enumerate(data["queries"]):
                    order = methods if (index + repetition) % 2 == 0 else methods[::-1]
                    for method in order:
                        start, error = perf_counter(), None
                        try:
                            response = await retrieve(method, query)
                        except Exception as exc:
                            error = type(exc).__name__
                            response = {
                                "evidence": [],
                                "evidence_tokens": 0,
                                "latency_ms": (perf_counter() - start) * 1000,
                            }
                        predicted = [item["candidate_id"] for item in response["evidence"]]
                        eligible = {candidates[alias]["id"] for alias in query["eligible"]}
                        row = {
                            "query_id": query["id"],
                            "kind": query["kind"],
                            "method": method,
                            "repetition": repetition,
                            "valid_at": query["valid_at"],
                            "known_at": query["known_at"],
                            "gold_ids": [candidates[alias]["id"] for alias in query["gold"]],
                            "predicted_ids": predicted,
                            "stale_ids": [
                                identifier for identifier in predicted if identifier not in eligible
                            ],
                            "evidence_tokens": response["evidence_tokens"],
                            "latency_ms": response["latency_ms"],
                            "error": error,
                        }
                        stream.write(json.dumps(row) + "\n")
                        stream.flush()
                        rows.append(row)
        grouped = defaultdict(list)
        for row in rows:
            grouped[row["method"]].append(row)
        summary = {method: aggregate(group) for method, group in grouped.items()}
        base = summary["session_baseline"]["stale_rate"]
        summary["stale_rate_reduction"] = (
            1 - summary["governed"]["stale_rate"] / base if base else None
        )
        summary["completed_at"] = datetime.now(UTC).isoformat()
        (args.output / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
