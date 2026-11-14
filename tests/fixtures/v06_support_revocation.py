"""Build legacy inconsistencies using only the installed v0.6.0 public API."""

import asyncio
import json
import os
from importlib.metadata import version

from sqlalchemy.orm import Session

from governed_memory.db import create_db
from governed_memory.graph_adapter import GraphProjection, project_pending
from governed_memory.identity import bootstrap, create_project, issue_credential
from governed_memory.ledger import Ledger
from governed_memory.models import Candidate

assert version("governed-memory") == "0.6.0"
engine = create_db(os.environ["MEMORY_DATABASE_URL"])
ledger = Ledger(engine)
project = os.environ["GM_UPGRADE_PROJECT"]
admin = bootstrap(engine, "operator", project)
create_project(engine, admin, project, project + "-other")
agent = issue_credential(engine, admin, "agent", project, "agent")


def propose(project, subject, locator, parents=None):
    return ledger.propose(
        admin,
        project,
        subject=subject,
        predicate="database",
        value="SQLite",
        valid_from="2020-01-01T00:00:00Z",
        locator=locator,
        parent_ids=parents,
    )


def approve(project, candidate):
    preview = ledger.preview(admin, project, candidate["id"])
    return ledger.decide(
        admin,
        project,
        candidate["id"],
        "approve",
        0,
        expected_head=preview["head_revision"],
        reason="fictional upgrade fixture",
    )


def derive(project, parent, subject):
    snapshot = next(
        item.id for item in ledger.visible(admin, project) if item.candidate_id == parent["id"]
    )
    return propose(project, subject, f"derived:{subject}", [snapshot])


projects = {}
for name in (project, project + "-other"):
    root = approve(name, propose(name, "storage", "primary"))
    support = propose(name, "storage", "corroboration")
    preview = ledger.preview(admin, name, root["id"])
    ledger.approve_support(
        admin,
        name,
        support["id"],
        root["id"],
        expected_revision=0,
        expected_target_revision=preview["revision"],
        expected_head=preview["head_revision"],
        reason="independent corroboration",
    )
    ledger.withdraw_source(admin, name, root["source_id"])
    child = approve(name, derive(name, root, "deployment"))
    grandchild = approve(name, derive(name, child, "application"))
    pending = derive(name, grandchild, "pending-work")
    unrelated = approve(name, propose(name, "independent", "independent-primary"))
    projects[name] = {
        "root": root["id"],
        "support": support["id"],
        "child": child["id"],
        "grandchild": grandchild["id"],
        "pending": pending["id"],
        "unrelated": unrelated["id"],
    }


async def project_all(expected):
    graph = GraphProjection(
        os.environ["MEMORY_NEO4J_URI"], "neo4j", os.environ["MEMORY_NEO4J_PASSWORD"]
    )
    try:
        await graph.initialize()
        assert (await project_pending(ledger, graph)) == {"projected": expected, "failed": 0}
    finally:
        await graph.close()


asyncio.run(project_all(8))
for name, candidates in projects.items():
    ledger.decide(admin, name, candidates["support"], "revoke", 1, reason="legacy retraction")
    with Session(engine) as session:
        assert session.get(Candidate, candidates["child"]).state == "active"
        assert session.get(Candidate, candidates["pending"]).state == "proposed"
asyncio.run(project_all(2))
print(json.dumps({"admin": admin, "agent": agent, "projects": projects}))
