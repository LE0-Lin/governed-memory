"""Corroboration is scoped to one assertion, even when sources contain several facts."""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from governed_memory.errors import Denied
from governed_memory.ingest import import_file
from governed_memory.models import Candidate, GovernanceEvent, LineageEvent, ProjectionJob, Source

from .conftest import approve, propose
from .test_dependencies import derive
from .test_source_support import add_support


def revoke_support(context, support):
    ledger, clock, tokens = context
    clock.advance()
    ledger.decide(
        tokens["admin"], "demo", support["id"], "revoke", 1, reason="corroborating claim retracted"
    )


def complete_projections(ledger):
    for item, generation in ledger.pending():
        ledger.mark_projection(item.id, generation, None)


def test_revoked_support_invalidates_bound_descendants_and_requeues_projection(context):
    ledger, clock, tokens = context
    root = approve(context, propose(context))
    support = add_support(context, root)
    ledger.withdraw_source(tokens["admin"], "demo", root["source_id"])
    child = approve(context, derive(context, root), protected=True)
    grandchild = approve(context, derive(context, child, "application"))
    pending = derive(context, grandchild, "pending-work")
    historical = clock()
    complete_projections(ledger)

    revoke_support(context, support)

    expected = {child["id"]: "revoked", grandchild["id"]: "revoked", pending["id"]: "rejected"}
    with Session(ledger.engine) as session:
        assert {
            identifier: session.get(Candidate, identifier).state for identifier in expected
        } == expected
        for identifier, state in expected.items():
            events = list(
                session.scalars(
                    select(GovernanceEvent).where(
                        GovernanceEvent.candidate_id == identifier, GovernanceEvent.action == state
                    )
                )
            )
            assert len(events) == 1
            lineage = session.get(LineageEvent, events[0].id).payload
            assert lineage["job"]["name"] == f"memory.{state}"
            assert any(output["name"] == f"candidate/{identifier}" for output in lineage["outputs"])
    assert ledger.visible(tokens["reader"], "demo", known_at=historical) == []
    queued = {item.candidate_id: item for item, _ in ledger.pending()}
    assert all(queued[identifier].withdrawn for identifier in (child["id"], grandchild["id"]))


def test_revoking_unused_support_preserves_derivations_bound_to_the_primary(context):
    ledger, _, tokens = context
    root = approve(context, propose(context))
    support = add_support(context, root)
    child = approve(context, derive(context, root))
    complete_projections(ledger)

    revoke_support(context, support)

    assert {item.candidate_id for item in ledger.visible(tokens["reader"], "demo")} == {
        root["id"],
        child["id"],
    }
    assert child["id"] not in {item.candidate_id for item, _ in ledger.pending()}
    with Session(ledger.engine) as session:
        assert session.get(Candidate, child["id"]).state == "active"


def test_revoking_one_claim_does_not_withdraw_other_claims_in_the_same_file(context, tmp_path):
    ledger, _, tokens = context
    roots = []
    records = []
    for subject in ("storage", "archive"):
        proposal = ledger.propose(
            tokens["agent"],
            "demo",
            subject=subject,
            predicate="database",
            value="SQLite",
            valid_from="2030-01-01T00:00:00Z",
            locator=f"primary:{subject}",
        )
        roots.append(approve(context, proposal))
        records.append(
            {
                "memory": {
                    "subject": subject,
                    "predicate": "database",
                    "value": "SQLite",
                    "valid_from": "2030-01-01T00:00:00Z",
                }
            }
        )
    source = tmp_path / "session.jsonl"
    source.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
    supports = import_file(ledger, tokens["admin"], "demo", source)
    assert supports[0]["source_id"] == supports[1]["source_id"]
    children = []
    for root, support in zip(roots, supports, strict=True):
        preview = ledger.preview(tokens["admin"], "demo", root["id"])
        ledger.approve_support(
            tokens["admin"],
            "demo",
            support["id"],
            root["id"],
            expected_revision=0,
            expected_target_revision=preview["revision"],
            expected_head=preview["head_revision"],
            reason="independent source for this particular assertion",
        )
        ledger.withdraw_source(tokens["admin"], "demo", root["source_id"])
        children.append(approve(context, derive(context, root, f"deploy-{root['subject']}")))
    complete_projections(ledger)

    revoke_support(context, supports[0])

    assert {item.candidate_id for item in ledger.visible(tokens["reader"], "demo")} == {
        roots[1]["id"],
        children[1]["id"],
    }
    with Session(ledger.engine) as session:
        assert session.get(Candidate, children[0]["id"]).state == "revoked"
        assert session.get(Candidate, children[1]["id"]).state == "active"
        assert session.get(Candidate, supports[1]["id"]).state == "active"
        assert session.get(Source, supports[0]["source_id"]).revoked_at is None
    assert children[1]["id"] not in {item.candidate_id for item, _ in ledger.pending()}


def test_repair_is_admin_only_and_idempotent_for_legacy_revocations(context, monkeypatch):
    ledger, _, tokens = context
    root = approve(context, propose(context))
    support = add_support(context, root)
    ledger.withdraw_source(tokens["admin"], "demo", root["source_id"])
    child = approve(context, derive(context, root))
    pending = derive(context, child, "pending-work")
    complete_projections(ledger)
    # Reproduce the old transaction without editing append-only history.
    with monkeypatch.context() as patch:
        patch.setattr(ledger, "_invalidate_dependents", lambda *args, **kwargs: None)
        revoke_support(context, support)
    with pytest.raises(Denied):
        ledger.reconcile_support_dependencies(tokens["agent"], "demo")
    assert ledger.reconcile_support_dependencies(tokens["admin"], "demo") == 2
    with Session(ledger.engine) as session:
        assert session.get(Candidate, child["id"]).state == "revoked"
        assert session.get(Candidate, pending["id"]).state == "rejected"
        event_count = len(list(session.scalars(select(GovernanceEvent))))
    assert ledger.reconcile_support_dependencies(tokens["admin"], "demo") == 0
    with Session(ledger.engine) as session:
        assert len(list(session.scalars(select(GovernanceEvent)))) == event_count
    assert next(item for item, _ in ledger.pending() if item.candidate_id == child["id"]).withdrawn


def test_failed_cascade_rolls_back_the_revocation_and_both_outboxes(context, monkeypatch):
    ledger, _, tokens = context
    root = approve(context, propose(context))
    support = add_support(context, root)
    ledger.withdraw_source(tokens["admin"], "demo", root["source_id"])
    child = approve(context, derive(context, root))
    complete_projections(ledger)
    original = ledger._queue_candidates

    def fail_child_projection(session, candidate_ids, **kwargs):
        if child["id"] in candidate_ids:
            raise RuntimeError("injected projection outbox failure")
        return original(session, candidate_ids, **kwargs)

    monkeypatch.setattr(ledger, "_queue_candidates", fail_child_projection)
    with Session(ledger.engine) as session:
        events_before = set(session.scalars(select(LineageEvent.id)))
    with pytest.raises(RuntimeError, match="injected"):
        revoke_support(context, support)
    with Session(ledger.engine) as session:
        assert session.get(Candidate, support["id"]).state == "active"
        assert session.get(Candidate, child["id"]).state == "active"
        assert all(job.completed for job in session.scalars(select(ProjectionJob)))
        assert set(session.scalars(select(LineageEvent.id))) == events_before
    assert child["id"] in {item.candidate_id for item in ledger.visible(tokens["reader"], "demo")}
