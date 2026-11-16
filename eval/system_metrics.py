"""Pair installed v0.8/candidate MCP retrieval with actual graph and authorization."""

import argparse
import asyncio
import hashlib
import json
import os
import platform
from collections import Counter, defaultdict
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from eval.cv_run import aggregate, database, populate_with_operator, processor_name
from eval.metrics_cases import scaled_timelines
from eval.retrieval_evidence import checksum, source_snapshot, write_json
from eval.system_runtime import (
    REFERENCE,
    dependency_versions,
    mcp_session,
    verify_runtime,
    verify_unchanged_runtime,
    wheel_identity,
)
from governed_memory.authorization import provision
from governed_memory.graph_adapter import GraphProjection, project_pending
from governed_memory.identity import create_project
from governed_memory.local_models import MiniLMEmbedder, MiniLMReranker
from governed_memory.models import Grant
from governed_memory.policy import OpaPolicy
from governed_memory.retrieval import serialize

PROTOCOL = Path(__file__).with_name("SYSTEM_BASELINE_PROTOCOL.md")
METHODS = ("reference_v08", "governed_current")


def arguments(query):
    return {key: query[key] for key in ("project", "query", "valid_at", "known_at")} | {
        "k": 5,
        "token_budget": 1024,
    }


async def retrieve(session, query):
    started = perf_counter()
    response = await session.call_tool("search_memory", arguments(query))
    if response.isError:
        raise RuntimeError("MCP search returned an error; see retained server log")
    result = json.loads(response.content[0].text)
    elapsed = (perf_counter() - started) * 1000
    if (
        result["ranking_engine"] != "rust"
        or result["minimum_relevance_score"] is not None
        or not result["document_cache"]
        or not result["rerank_cache"]
    ):
        raise RuntimeError("MCP process is not using the frozen configuration")
    return result, elapsed


def summarize(rows):
    result = aggregate(rows)
    for phase, selected in (
        ("first_pass", [row for row in rows if row["repetition"] == 0]),
        ("repeat", [row for row in rows if row["repetition"] > 0]),
    ):
        result[f"{phase}_observations"] = len(selected)
        for percentile in (50, 95):
            result[f"{phase}_p{percentile}_ms"] = float(
                np.percentile([row["latency_ms"] for row in selected], percentile, method="linear")
            )
    result["backends"] = dict(Counter(row["backend"] for row in rows))
    result["server_p95_ms"] = float(np.percentile([row["server_latency_ms"] for row in rows], 95))
    return result


async def authority_probes(ledger, graph, authorizer, sessions, query, admin):
    authorizer.grant("agent", query["project"], "agent", remove=True)
    for session in sessions.values():
        response = await session.call_tool("search_memory", arguments(query))
        assert response.isError, "a warm MCP process retained revoked external access"
    authorizer.grant("agent", query["project"], "reader")
    for session in sessions.values():
        result, _ = await retrieve(session, query)
        assert result["evidence"]
        response = await session.call_tool(
            "propose_memory",
            {
                "project": query["project"],
                "subject": "forbidden-write",
                "predicate": "database",
                "value": "SQLite",
                "valid_from": "2030-01-01T00:00:00Z",
            },
        )
        assert response.isError, "a downgraded reader retained write access"
    authorizer.grant("agent", query["project"], "agent")
    authorizer.grant("agent", query["project"], "reader", remove=True)
    before, _ = await retrieve(next(iter(sessions.values())), query)
    selected = before["evidence"][0]
    removed = selected["source_id"]
    records, _, _ = await graph.graph.driver.execute_query(
        "MATCH ()-[e:RELATES_TO {uuid:$uuid}]->() RETURN count(e) AS n", uuid=selected["id"]
    )
    assert records[0]["n"] == 1
    ledger.withdraw_source(admin, query["project"], removed)
    # Deliberately do not project withdrawal: the actual Neo4j edge stays stale.
    eligible = {
        item.id
        for item in ledger.visible(
            query["token"], query["project"], valid_at=query["valid_at"], known_at=query["known_at"]
        )
    }
    for session in sessions.values():
        result, _ = await retrieve(session, query)
        assert {item["id"] for item in result["evidence"]} <= eligible
        assert removed not in {item["source_id"] for item in result["evidence"]}
    return {
        "external_revocation_denied": True,
        "reader_downgrade_read_only": True,
        "source_withdrawal_with_stale_graph": True,
        "methods": list(sessions),
    }


async def measure(sessions, queries, aliases, workload, stream):
    rows = []
    for repeat in range(3):
        for index, query in enumerate(queries):
            order = METHODS if (index + repeat) % 2 == 0 else METHODS[::-1]
            for method in order:
                started = perf_counter()
                try:
                    result, latency = await retrieve(sessions[method], query)
                    error = None
                except Exception as exc:
                    result, latency = {}, (perf_counter() - started) * 1000
                    error = type(exc).__name__
                evidence = result.get("evidence", [])
                predicted = [item["candidate_id"] for item in evidence]
                row = {
                    "workload": workload,
                    "query_id": query["id"],
                    "repetition": repeat,
                    "method": method,
                    "gold_ids": [aliases[x] for x in query["gold"]],
                    "predicted_ids": predicted,
                    "stale_ids": sorted(set(predicted) - {aliases[x] for x in query["eligible"]}),
                    "evidence_tokens": result.get("evidence_tokens", 0),
                    "evidence_sha256": hashlib.sha256(serialize(evidence).encode()).hexdigest(),
                    "reason": result.get("reason"),
                    "error": error,
                    "latency_ms": latency,
                    "server_latency_ms": result.get("latency_ms"),
                    "backend": result.get("backend"),
                }
                rows.append(row)
                stream.write(serialize(row) + "\n")
                stream.flush()
                if error or row["backend"] == "ledger-fallback:graph-unavailable":
                    raise RuntimeError("full-path query failed; partial evidence retained")
        print(f"{workload}: replay {repeat + 1}/3 complete", flush=True)
    return rows


async def experiment(output, targets, wheels):
    source = source_snapshot()
    if source["dirty_source"]:
        raise ValueError("commit source before a canonical system run")
    if "postgresql" not in os.environ.get("GM_EVAL_DATABASE_URL", ""):
        raise ValueError("system measurement requires actual PostgreSQL")
    output.mkdir(parents=True, exist_ok=False)
    datasets = {f"timelines_{n}": scaled_timelines(n) for n in (1, 16)}
    for name, data in datasets.items():
        write_json(output / f"{name}-fixture.json", data)
    manifest = {
        **source,
        "protocol": PROTOCOL.read_text(encoding="utf-8"),
        "protocol_sha256": checksum(PROTOCOL),
        "runtime_source_identical": verify_unchanged_runtime(source["commit"]),
        "methods": METHODS,
        "comparison": METHODS,
        "datasets": {name: checksum(output / f"{name}-fixture.json") for name in datasets},
        "started_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "os": platform.platform(),
        "cpu": processor_name(),
        "packages": dependency_versions(),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "repetitions": 3,
        "runtime": {
            name: verify_runtime(targets[name], commit)
            for name, commit in zip(METHODS, (REFERENCE, source["commit"]), strict=True)
        },
        "wheels": {name: wheel_identity(wheels[name]) for name in METHODS},
        "startup_ms": {},
        "cache": {},
        "timing": (
            "Caller-observed standard MCP stdio, actual PG/Neo4j/OpenFGA, CPU models and Rust; "
            "excludes startup/ingestion/projection/generation. OPA approvals occur before timing."
        ),
    }
    write_json(output / "manifest.json", manifest)
    embedder = MiniLMEmbedder(os.environ["MEMORY_MODEL_CACHE"])
    manifest["embedding"] = embedder.metadata
    reranker = MiniLMReranker(os.environ["MEMORY_MODEL_CACHE"])
    manifest["reranker"] = reranker.metadata
    await embedder.create("An unrelated fictional warmup query.")
    await reranker.scores("fictional warmup", ["An unrelated fictional document."])
    graph = GraphProjection(
        os.environ["GM_EVAL_NEO4J_URI"], "neo4j", os.environ["GM_EVAL_NEO4J_PASSWORD"], embedder
    )
    rows, probes = [], {}
    try:
        await graph.initialize()
        with (output / "observations.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
            for workload, data in datasets.items():
                with database() as engine:
                    ledger, token, project, candidates, admin = populate_with_operator(
                        engine, data, policy=OpaPolicy(os.environ["GM_EVAL_OPA_URL"])
                    )
                    warm = project + "-warmup"
                    create_project(engine, admin, project, warm)
                    with Session(engine) as session, session.begin():
                        session.add(Grant(principal_id="agent", project=warm, role="agent"))
                    item = ledger.propose(
                        token,
                        warm,
                        subject="fictional warmup",
                        predicate="text",
                        value="An unrelated fictional document.",
                        valid_from="2030-01-01T00:00:00Z",
                    )
                    ledger.decide(
                        admin,
                        warm,
                        item["id"],
                        "approve",
                        0,
                        expected_head=0,
                        reason="unrelated synthetic warmup fixture",
                    )
                    aliases = {alias: item["id"] for alias, item in candidates.items()}
                    write_json(output / f"{workload}-aliases.json", aliases)
                    queries = [
                        dict(query, token=token, project=project) for query in data["queries"]
                    ]
                    authorizer = provision(
                        os.environ["GM_EVAL_FGA_URL"],
                        project,
                        [("operator", "admin"), ("agent", "agent")],
                    )
                    ledger.authorizer = authorizer
                    try:
                        authorizer.grant("operator", warm, "admin")
                        authorizer.grant("agent", warm, "agent")
                        for group in (project, warm):
                            while True:
                                result = await project_pending(ledger, graph, 256, group)
                                if result["failed"]:
                                    raise RuntimeError("graph projection failed before timing")
                                if not result["projected"]:
                                    break
                        with engine.connect() as connection:
                            schema = connection.scalar(text("SELECT current_schema()"))
                        url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
                        async with AsyncExitStack() as stack:
                            sessions, startup = {}, {}
                            for method in METHODS:
                                sessions[method], startup[method] = await stack.enter_async_context(
                                    mcp_session(
                                        targets[method],
                                        url.render_as_string(hide_password=False),
                                        token,
                                        authorizer,
                                        output / f"{workload}-{method}.log",
                                    )
                                )
                                await retrieve(
                                    sessions[method],
                                    dict(
                                        project=warm,
                                        query="fictional warmup",
                                        valid_at=data["now"],
                                        known_at=data["now"],
                                    ),
                                )
                            manifest["startup_ms"][workload] = startup
                            write_json(output / "manifest.json", manifest)
                            rows.extend(await measure(sessions, queries, aliases, workload, stream))
                            probe_query = next(query for query in queries if query["gold"])
                            probes[workload] = await authority_probes(
                                ledger, graph, authorizer, sessions, probe_query, admin
                            )
                            write_json(output / "authority-probes.json", probes)
                    finally:
                        for group in (project, warm):
                            await graph.graph.driver.execute_query(
                                "MATCH (n:Entity {group_id:$group}) DETACH DELETE n", group=group
                            )
    finally:
        await graph.close()
    groups = defaultdict(list)
    for row in rows:
        groups[f"{row['workload']}/{row['method']}"].append(row)
    summaries = {name: summarize(group) for name, group in sorted(groups.items())}
    for group in summaries.values():
        if not any(
            name.startswith("graphiti") and count for name, count in group["backends"].items()
        ):
            raise RuntimeError("no actual graph hits; full-path claim rejected")
    manifest.update(
        completed_at=datetime.now(UTC).isoformat(),
        source_unchanged=source["code_sha256"] == source_snapshot()["code_sha256"]
        and checksum(PROTOCOL) == manifest["protocol_sha256"],
    )
    write_json(output / "manifest.json", manifest)
    write_json(output / "summary.json", summaries)
    print(serialize(summaries))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-target", type=Path, required=True)
    parser.add_argument("--candidate-target", type=Path, required=True)
    parser.add_argument("--reference-wheels", type=Path, required=True)
    parser.add_argument("--candidate-wheels", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(
        experiment(
            args.output,
            dict(
                zip(
                    METHODS,
                    (args.reference_target.resolve(), args.candidate_target.resolve()),
                    strict=True,
                )
            ),
            dict(zip(METHODS, (args.reference_wheels, args.candidate_wheels), strict=True)),
        )
    )
