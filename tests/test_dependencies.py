from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from governed_memory.db import initialize, require_current_schema
from governed_memory.errors import Conflict, Denied
from governed_memory.models import (
    Candidate,
    EntityResolution,
    LineageDelivery,
    LineageEvent,
    MemoryDependency,
    ProjectionJob,
)

from .conftest import approve, propose


def derive(context, parent, subject="deployment", **kwargs):
    ledger, _, tokens = context
    parent_id = next(
        e.id for e in ledger.visible(tokens["admin"], "demo") if e.candidate_id == parent["id"]
    )
    return ledger.propose(
        tokens["admin"],
        "demo",
        subject=subject,
        predicate="decision",
        value="Use the approved database",
        valid_from="2030-01-01T00:00:00Z",
        parent_ids=[parent_id],
        **kwargs,
    )


@pytest.mark.parametrize("change", ["revoke", "supersede", "withdraw"])
def test_changes_atomically_invalidate_transitive_derivations(context, change):
    ledger, clock, tokens = context
    root = approve(context, propose(context))
    child = approve(context, derive(context, root))
    grandchild = approve(context, derive(context, child, "application"))
    staged = derive(context, grandchild, "pending-work")
    historical = clock()
    if change == "supersede":
        approve(context, propose(context, "PostgreSQL", valid_until="2035-01-01T00:00:00Z"))
    elif change == "withdraw":
        ledger.withdraw_source(tokens["admin"], "demo", root["source_id"])
    else:
        ledger.decide(
            tokens["admin"], "demo", root["id"], "revoke", root["revision"], reason="input changed"
        )
    with Session(ledger.engine) as session:
        assert session.get(Candidate, child["id"]).state == "revoked"
        assert session.get(Candidate, grandchild["id"]).state == "revoked"
        assert session.get(Candidate, staged["id"]).state == "rejected"
        revoked = [
            event.payload
            for event in session.scalars(select(LineageEvent))
            if event.payload["job"]["name"] == "memory.revoked"
        ]
        assert any(
            any(d["name"].startswith("snapshot/") for d in event["outputs"]) for event in revoked
        )
        assert all(not job.completed for job in session.scalars(select(ProjectionJob)))
    assert not {child["id"], grandchild["id"]}.intersection(
        e.candidate_id for e in ledger.visible(tokens["admin"], "demo", known_at=historical)
    )
    assert all(
        e.withdrawn
        for e, _ in ledger.pending()
        if e.candidate_id in {child["id"], grandchild["id"]}
    )


def test_source_redundancy_does_not_preserve_a_derivation_of_the_withdrawn_input(context):
    ledger, clock, tokens = context
    root = approve(context, propose(context, locator="primary"))
    child = approve(context, derive(context, root))
    support = propose(context, locator="independent")
    preview = ledger.preview(tokens["admin"], "demo", support["id"])
    clock.advance()
    ledger.approve_support(
        tokens["admin"],
        "demo",
        support["id"],
        root["id"],
        expected_revision=0,
        expected_target_revision=root["revision"],
        expected_head=preview["head_revision"],
        reason="independent corroboration",
    )
    ledger.withdraw_source(tokens["admin"], "demo", root["source_id"])
    assert [e.candidate_id for e in ledger.visible(tokens["reader"], "demo")] == [root["id"]]
    with Session(ledger.engine) as session:
        assert session.get(Candidate, child["id"]).state == "revoked"


def test_derived_public_source_never_declassifies_its_private_inputs(context):
    ledger, _, tokens = context
    root = approve(
        context,
        ledger.propose(
            tokens["admin"],
            "demo",
            subject="storage",
            predicate="database",
            value="SQLite",
            valid_from="2030-01-01T00:00:00Z",
            audience=["approver"],
        ),
    )
    child = approve(context, derive(context, root))
    assert not ledger.visible(tokens["reader"], "demo")
    assert child["id"] in {e.candidate_id for e in ledger.visible(tokens["approver"], "demo")}
    with pytest.raises(Denied):
        ledger.explain(tokens["reader"], "demo", child["id"])


def test_staging_checks_dependency_interval_and_never_allows_self_dependency(context):
    ledger, _, tokens = context
    root = approve(context, propose(context, valid_until="2031-01-01T00:00:00Z"))
    with pytest.raises(Conflict, match="covering"):
        derive(context, root)
    snapshot = ledger.visible(tokens["admin"], "demo")[0]
    with pytest.raises(Conflict):
        ledger.propose(
            tokens["agent"],
            "demo",
            subject="storage",
            predicate="database",
            value="circular",
            valid_from="2030-01-01T00:00:00Z",
            parent_ids=[snapshot.id],
        )
    with pytest.raises(Denied):
        ledger.propose(
            tokens["agent"],
            "demo",
            subject="other",
            predicate="database",
            value="missing",
            valid_from="2030-01-01T00:00:00Z",
            parent_ids=["unknown"],
        )


@pytest.mark.parametrize("table", ["memory_dependencies", "lineage_events"])
def test_dependency_and_lineage_history_is_append_only(context, table):
    ledger, _, _ = context
    root = approve(context, propose(context))
    approve(context, derive(context, root))
    with pytest.raises(DatabaseError), ledger.engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {table}"))


def test_upgrade_from_v03_tables_preserves_approved_records(context):
    ledger, _, tokens = context
    root = approve(context, propose(context))
    before = ledger.visible(tokens["admin"], "demo")
    for model in (LineageDelivery, LineageEvent, EntityResolution, MemoryDependency):
        model.__table__.drop(ledger.engine)
    with pytest.raises(RuntimeError, match="upgrade"):
        require_current_schema(ledger.engine)
    initialize(ledger.engine)
    require_current_schema(ledger.engine)
    assert ledger.visible(tokens["admin"], "demo") == before
    assert ledger.explain(tokens["admin"], "demo", root["id"])["state"] == "active"


@pytest.mark.integration
def test_postgres_dependency_approval_racing_with_withdrawal_cannot_remain_active(context):
    ledger, clock, tokens = context
    if ledger.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL transaction lock check")
    root = approve(context, propose(context))
    child = derive(context, root)
    clock.advance()
    barrier = Barrier(2)

    def decide():
        barrier.wait(timeout=10)
        try:
            ledger.decide(
                tokens["admin"],
                "demo",
                child["id"],
                "approve",
                0,
                expected_head=0,
                reason="concurrent review",
            )
        except Conflict:
            pass

    def withdraw():
        barrier.wait(timeout=10)
        ledger.withdraw_source(tokens["admin"], "demo", root["source_id"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(decide), pool.submit(withdraw)]
        for future in futures:
            future.result(timeout=20)
    assert ledger.visible(tokens["reader"], "demo") == []
    with Session(ledger.engine) as session:
        assert session.get(Candidate, child["id"]).state in {"rejected", "revoked"}
