"""Compare retrieval behavior. No answer generator, hidden labels, or external model calls."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from governed_memory.db import create_db, initialize
from governed_memory.identity import Denied, bootstrap, issue_credential
from governed_memory.ledger import Evidence, Ledger, instant
from governed_memory.models import Candidate, Source
from governed_memory.retrieval import Retriever, hybrid_rank, serialize

ROOT = Path(__file__).resolve().parents[1]


def raw_evidence(ledger, token, project):
    from governed_memory.identity import authenticate

    with Session(ledger.engine) as session:
        actor = authenticate(session, token, project)
        result = []
        for c, source in session.execute(
            select(Candidate, Source)
            .join(Source, Source.id == Candidate.source_id)
            .where(Candidate.project == project)
        ):
            if source.audience and actor.id not in source.audience:
                continue
            result.append(
                Evidence(
                    c.id,
                    c.id,
                    c.fact_id,
                    project,
                    f"{c.subject} | {c.predicate}: {c.value}",
                    source.id,
                    source.locator,
                    source.content_hash,
                    c.fragment,
                    c.subject,
                    c.predicate,
                    c.value,
                    c.valid_from,
                    c.valid_until,
                    c.proposed_at,
                    None,
                )
            )
        return result


async def baseline(name, ledger, token, project, query, config, retriever):
    start = perf_counter()
    known, valid = instant(query["known_at"]), instant(query["valid_at"])
    # All methods start with exactly the same currently accessible source corpus.
    rows = [e for e in raw_evidence(ledger, token, project) if e.system_from <= known]
    if name == "recent_sessions":
        ranked = sorted(rows, key=lambda e: (e.system_from, e.id), reverse=True)
    else:
        if name == "hybrid_temporal":
            by_fact = {}
            for e in rows:
                if e.valid_from <= valid and (e.valid_until is None or valid < e.valid_until):
                    previous = by_fact.get(e.fact_id)
                    if previous is None or e.system_from > previous.system_from:
                        by_fact[e.fact_id] = e
            rows = list(by_fact.values())
        ranked = await hybrid_rank(query["query"], rows)
    output, used = retriever.pack(ranked, config["token_budget"], config["k"])
    response = {"evidence": output, "evidence_tokens": used}
    serialize(response)
    response["latency_ms"] = (perf_counter() - start) * 1000
    return response


def future_metadata_count(row):
    known = instant(row["known_at"])
    return sum(
        any(e.get(field) and instant(e[field]) > known for field in ("system_from", "system_until"))
        for e in row.get("predictions", [])
    )


def metrics(rows):
    answerable = [row for row in rows if row["gold_ids"]]
    empty = [row for row in rows if not row["gold_ids"]]
    returned = sum(len(row["predicted_ids"]) for row in rows)
    gold_count = sum(len(row["gold_ids"]) for row in answerable)
    hits = sum(len(set(row["gold_ids"]) & set(row["predicted_ids"])) for row in answerable)
    return {
        "queries": len(rows),
        "failures": sum(bool(r.get("error")) for r in rows),
        "future_metadata_count": sum(future_metadata_count(r) for r in rows if "known_at" in r),
        "answerable_queries": len(answerable),
        "evidence_recall_at_k": hits / gold_count if gold_count else None,
        "hit_any": sum(bool(set(r["gold_ids"]) & set(r["predicted_ids"])) for r in answerable)
        / len(answerable)
        if answerable
        else None,
        "hit_all": sum(set(r["gold_ids"]) <= set(r["predicted_ids"]) for r in answerable)
        / len(answerable)
        if answerable
        else None,
        "coverage": sum(bool(r["predicted_ids"]) for r in answerable) / len(answerable)
        if answerable
        else None,
        "empty_gold_correct": sum(not r["predicted_ids"] for r in empty),
        "empty_gold_total": len(empty),
        "returned_evidence": returned,
        "stale_count": sum(r["stale_count"] for r in rows),
        "stale_fraction": sum(r["stale_count"] for r in rows) / returned if returned else 0,
        "unapproved_count": sum(r["unapproved_count"] for r in rows),
        "unapproved_query_successes": sum(
            r["unapproved_count"] > 0 and r["kind"] in {"poisoning", "approval_lag"} for r in rows
        ),
        "unapproved_query_leaks_all_categories": sum(r["unapproved_count"] > 0 for r in rows),
        "unapproved_query_attacks": sum(r["kind"] in {"poisoning", "approval_lag"} for r in rows),
        "withdrawn_count": sum(r["withdrawn_count"] for r in rows),
        "withdrawal_query_successes": sum(
            r["withdrawn_count"] > 0 and r["kind"] == "withdrawal" for r in rows
        ),
        "withdrawn_query_leaks_all_categories": sum(r["withdrawn_count"] > 0 for r in rows),
        "withdrawal_query_attacks": sum(r["kind"] == "withdrawal" for r in rows),
        "source_complete_count": sum(r["source_complete_count"] for r in rows),
        "source_complete_fraction": sum(r["source_complete_count"] for r in rows) / returned
        if returned
        else None,
        "evidence_tokens_mean": float(np.mean([r["evidence_tokens"] for r in rows])),
        "latency_ms_p50": float(np.percentile([r["latency_ms"] for r in rows], 50)),
        "latency_ms_p95": float(np.percentile([r["latency_ms"] for r in rows], 95)),
    }


async def evaluate(scenario, config):
    engine = create_db("sqlite:///:memory:")
    initialize(engine)
    now = instant(scenario["facts"][0]["arrives"])
    ledger = Ledger(engine, lambda: now)
    project = scenario["id"]
    admin = bootstrap(engine, "operator", project)
    agent = issue_credential(engine, admin, "agent", project, "agent")
    candidates = {}
    events = []
    for f in scenario["facts"]:
        events.append((f["arrives"], 0, "propose", f))
        if f["approves"]:
            events.append((f["approves"], 1, "approve", f))
        if f["withdrawn"]:
            events.append((f["withdrawn"], 2, "withdraw", f))
    for timestamp, _, action, fact in sorted(events, key=lambda e: (e[0], e[1], e[3]["alias"])):
        now = instant(timestamp)
        if action == "propose":
            candidates[fact["alias"]] = ledger.propose(
                admin if fact["audience"] else agent,
                project,
                subject=fact["subject"],
                predicate=fact["predicate"],
                value=fact["value"],
                valid_from=fact["valid_from"],
                valid_until=fact["valid_until"],
                locator=f"synthetic:{project}/{fact['alias']}",
                audience=fact["audience"],
            )
        elif action == "approve":
            c = candidates[fact["alias"]]
            head = ledger.preview(admin, project, c["id"])["head_revision"]
            ledger.decide(
                admin,
                project,
                c["id"],
                "approve",
                0,
                reason="synthetic approval label",
                protected=fact["protected"],
                expected_head=head,
            )
        else:
            ledger.withdraw_source(admin, project, candidates[fact["alias"]]["source_id"])
    now = instant(scenario["now"])
    retriever = Retriever(ledger)
    by_id = {candidates[f["alias"]]["id"]: f for f in scenario["facts"]}
    records = []
    for query in scenario["queries"]:
        gold = [candidates[alias]["id"] for alias in query["gold"]]
        eligible = {
            e.candidate_id
            for e in ledger.visible(
                agent, project, valid_at=query["valid_at"], known_at=query["known_at"]
            )
        }
        for method in ("recent_sessions", "hybrid", "hybrid_temporal", "governed"):
            started, error = perf_counter(), None
            try:
                if method == "governed":
                    response = await retriever.search(
                        agent,
                        project,
                        query["query"],
                        valid_at=query["valid_at"],
                        known_at=query["known_at"],
                        token_budget=config["token_budget"],
                        k=config["k"],
                    )
                else:
                    response = await baseline(
                        method, ledger, agent, project, query, config, retriever
                    )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                response = {
                    "evidence": [],
                    "evidence_tokens": 1,
                    "latency_ms": (perf_counter() - started) * 1000,
                }
            predictions = [e["candidate_id"] for e in response["evidence"]]
            stale, unapproved, withdrawn = 0, 0, 0
            for candidate_id in predictions:
                f = by_id[candidate_id]
                if f["withdrawn"]:
                    withdrawn += 1
                elif not f["approves"] or instant(f["approves"]) > instant(query["known_at"]):
                    unapproved += 1
                elif candidate_id not in eligible:
                    stale += 1
            records.append(
                {
                    "project": project,
                    "template": scenario["template"],
                    "split": scenario["split"],
                    "query_id": query["id"],
                    "kind": query["kind"],
                    "query": query["query"],
                    "valid_at": query["valid_at"],
                    "known_at": query["known_at"],
                    "method": method,
                    "error": error,
                    "gold_ids": gold,
                    "predicted_ids": predictions,
                    "predictions": response["evidence"],
                    "stale_count": stale,
                    "unapproved_count": unapproved,
                    "withdrawn_count": withdrawn,
                    "source_complete_count": sum(
                        all(e.get(k) for k in ("source_id", "locator", "fragment", "content_hash"))
                        for e in response["evidence"]
                    ),
                    "evidence_tokens": response["evidence_tokens"],
                    "latency_ms": response["latency_ms"],
                    "config": {"k": config["k"], "token_budget": config["token_budget"]},
                }
            )
    operation_records = []
    try:
        ledger.decide(
            agent,
            project,
            candidates["attack"]["id"],
            "approve",
            0,
            reason="self-declared administrator",
            expected_head=0,
        )
        blocked = False
    except Denied:
        blocked = True
    operation_records.append(
        {
            "project": project,
            "operation": "unauthorized_approval",
            "success": not blocked,
            "expected_success": False,
        }
    )
    legal = ledger.propose(
        agent, project, subject="logging", predicate="retention", value="seven days", valid_from=now
    )
    ledger.decide(
        admin, project, legal["id"], "approve", 0, reason="legitimate operation", expected_head=0
    )
    operation_records.append(
        {
            "project": project,
            "operation": "legitimate_approval",
            "success": legal["id"] in {e.candidate_id for e in ledger.visible(agent, project)},
            "expected_success": True,
        }
    )
    engine.dispose()
    return records, operation_records


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "eval/results/local")
    parser.add_argument("--split", choices=["dev", "heldout", "all"], default="all")
    parser.add_argument("--check", action="store_true", help="fail on incorrect governed evidence")
    args = parser.parse_args()
    config = json.loads((ROOT / "eval/manifest.json").read_text())
    data = (ROOT / "eval/timelines.jsonl").read_bytes()
    if hashlib.sha256(data).hexdigest() != config["sha256"]:
        raise ValueError("dataset changed after freeze")
    rows, operations = [], []
    for line in data.decode().splitlines():
        scenario = json.loads(line)
        if args.split != "all" and scenario["split"] != args.split:
            continue
        r, o = await evaluate(scenario, config)
        rows.extend(r)
        operations.extend(o)
    grouped = defaultdict(list)
    for row in rows:
        grouped[f"{row['split']}/{row['method']}/all"].append(row)
        grouped[f"{row['split']}/{row['method']}/{row['kind']}"].append(row)
    summary = {name: metrics(group) for name, group in sorted(grouped.items())}
    code_files = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "eval").glob("*.py"))
    code_hash = hashlib.sha256(
        b"".join(
            p.relative_to(ROOT).as_posix().encode() + b"\0" + p.read_bytes().replace(b"\r\n", b"\n")
            for p in code_files
        )
    ).hexdigest()
    provenance = {
        "ran_at": datetime.now(UTC).isoformat(),
        "dataset": config,
        "split": args.split,
        "code_sha256": code_hash,
        "python": platform.python_version(),
        "os": platform.platform(),
        "processor": platform.processor(),
        "concurrency": 1,
        "caching": "no query/document embedding cache",
        "warm_state": "tokenizer loaded before timing; fresh ledger per project",
        "backend": "SQLite + rank-bm25 + lexical hash vectors; Graphiti tested separately",
        "query_count": len(rows),
        "operation_count": len(operations),
        "failures": sum(bool(r["error"]) for r in rows),
        "timeouts": 0,
        "timeout_policy": "none; sequential local run",
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("governed-memory", "graphiti-core", "rank-bm25", "numpy", "tiktoken")
        },
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "uncommitted_changes": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain", "--", "src", "eval/*.py"], cwd=ROOT, text=True
            ).strip()
        ),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    for filename, records in (("predictions.jsonl", rows), ("operations.jsonl", operations)):
        (args.output / filename).write_text(
            "".join(serialize(r) + "\n" for r in records), encoding="utf-8"
        )
    (args.output / "summary.json").write_text(serialize(summary) + "\n", encoding="utf-8")
    (args.output / "provenance.json").write_text(serialize(provenance) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "queries": len(rows),
                "operation_checks": len(operations),
                "heldout": {
                    k: v
                    for k, v in summary.items()
                    if k.startswith("heldout/") and k.endswith("/all")
                },
            },
            indent=2,
        )
    )
    if args.check and (
        any(r["error"] for r in rows)
        or any(future_metadata_count(r) for r in rows if r["method"] == "governed")
        or any(
            set(r["predicted_ids"]) != set(r["gold_ids"]) for r in rows if r["method"] == "governed"
        )
        or any(o["success"] != o["expected_success"] for o in operations)
    ):
        raise SystemExit(
            "governed behavior differs from frozen expected evidence; inspect predictions"
        )


if __name__ == "__main__":
    asyncio.run(main())
