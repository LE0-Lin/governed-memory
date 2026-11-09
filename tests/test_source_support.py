import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from governed_memory.db import initialize, require_current_schema
from governed_memory.errors import Conflict, Denied
from governed_memory.models import SourceSupport

from .conftest import approve, propose


def add_support(context, target, *, value="SQLite", audience=None):
    ledger, clock, tokens = context
    clock.advance()
    candidate = ledger.propose(
        tokens["admin"],
        "demo",
        subject="storage",
        predicate="database",
        value=value,
        valid_from="2030-01-01T00:00:00Z",
        locator=f"second-source:{clock().isoformat()}",
        body="An independently reviewed fictional ADR",
        audience=audience,
    )
    preview = ledger.preview(tokens["admin"], "demo", target["id"])
    ledger.approve_support(
        tokens["admin"],
        "demo",
        candidate["id"],
        target["id"],
        expected_revision=0,
        expected_target_revision=preview["revision"],
        expected_head=preview["head_revision"],
        reason="corroborated by another source",
    )
    return candidate


def test_withdrawal_preserves_an_independently_supported_fact(context):
    ledger, _, tokens = context
    target = approve(context, propose(context))
    support = add_support(context, target)
    before = ledger.visible(tokens["agent"], "demo")
    assert len(before) == 1
    assert before[0].additional_sources[0].id == support["source_id"]
    ledger.withdraw_source(tokens["admin"], "demo", target["source_id"])
    after = ledger.visible(tokens["agent"], "demo")
    assert len(after) == 1
    assert after[0].id == before[0].id
    assert after[0].source_id == support["source_id"]
    ledger.withdraw_source(tokens["admin"], "demo", support["source_id"])
    assert ledger.visible(tokens["agent"], "demo") == []
    assert all(item.withdrawn for item, _ in ledger.pending())


def test_later_support_does_not_leak_into_an_earlier_known_time(context):
    ledger, clock, tokens = context
    target = approve(context, propose(context))
    known_before_support = clock()
    add_support(context, target)
    ledger.withdraw_source(tokens["admin"], "demo", target["source_id"])
    assert ledger.visible(tokens["agent"], "demo", known_at=known_before_support) == []
    assert len(ledger.visible(tokens["agent"], "demo")) == 1


def test_source_audiences_are_checked_for_each_remaining_support(context):
    ledger, _, tokens = context
    target = approve(context, propose(context))
    add_support(context, target, audience=["reader"])
    ledger.withdraw_source(tokens["admin"], "demo", target["source_id"])
    assert ledger.visible(tokens["agent"], "demo") == []
    assert len(ledger.visible(tokens["reader"], "demo")) == 1
    explanation = ledger.explain(tokens["reader"], "demo", target["id"])
    assert explanation["source_id"] != target["source_id"]
    assert [event["action"] for event in explanation["events"]] == ["support_added"]


def test_revoking_the_additional_approval_removes_its_support(context):
    ledger, _, tokens = context
    target = approve(context, propose(context))
    support = add_support(context, target)
    ledger.withdraw_source(tokens["admin"], "demo", target["source_id"])
    ledger.decide(tokens["admin"], "demo", support["id"], "revoke", 1, reason="retracted review")
    assert ledger.visible(tokens["agent"], "demo") == []


def test_an_unapproved_or_different_claim_cannot_corroborate_a_fact(context):
    ledger, _, tokens = context
    target = approve(context, propose(context))
    with pytest.raises(Conflict, match="entire structured assertion"):
        add_support(context, target, value="PostgreSQL")
    assert ledger.visible(tokens["agent"], "demo")[0].additional_sources == ()
    candidate = propose(context, "unapproved")
    with pytest.raises(Denied):
        ledger.approve_support(
            tokens["agent"],
            "demo",
            candidate["id"],
            target["id"],
            expected_revision=0,
            expected_target_revision=1,
            expected_head=1,
            reason="self declaration",
        )


def test_revoking_the_assertion_hides_all_its_sources(context):
    ledger, _, tokens = context
    target = approve(context, propose(context))
    add_support(context, target)
    current = ledger.explain(tokens["admin"], "demo", target["id"])
    ledger.decide(
        tokens["admin"],
        "demo",
        target["id"],
        "revoke",
        current["revision"],
        reason="the assertion is false regardless of its sources",
    )
    assert ledger.visible(tokens["agent"], "demo") == []


def test_additive_schema_upgrade_preserves_existing_approved_history(context):
    ledger, _, tokens = context
    target = approve(context, propose(context))
    original = ledger.visible(tokens["agent"], "demo")
    SourceSupport.__table__.drop(ledger.engine)
    with pytest.raises(RuntimeError, match="upgrade"):
        require_current_schema(ledger.engine)
    initialize(ledger.engine)
    require_current_schema(ledger.engine)
    assert ledger.visible(tokens["agent"], "demo") == original
    with Session(ledger.engine) as session:
        assert list(session.scalars(select(SourceSupport))) == []
    assert ledger.explain(tokens["admin"], "demo", target["id"])["revision"] == 1


@pytest.mark.integration
def test_concurrent_withdrawal_and_new_support_have_an_explicit_retry_path(context):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    ledger, clock, tokens = context
    if ledger.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL lock ordering check")
    target = approve(context, propose(context))
    clock.advance()
    incoming = ledger.propose(
        tokens["agent"],
        "demo",
        subject="storage",
        predicate="database",
        value="SQLite",
        valid_from="2030-01-01T00:00:00Z",
        locator="independent-concurrent-ADR",
    )
    barrier = Barrier(2)

    def withdraw():
        barrier.wait(timeout=10)
        ledger.withdraw_source(tokens["admin"], "demo", target["source_id"])

    def link():
        barrier.wait(timeout=10)
        try:
            ledger.approve_support(
                tokens["admin"],
                "demo",
                incoming["id"],
                target["id"],
                expected_revision=0,
                expected_target_revision=1,
                expected_head=1,
                reason="concurrent review",
            )
            return True
        except Conflict:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        removal = pool.submit(withdraw)
        addition = pool.submit(link)
        removal.result(timeout=20)
        applied = addition.result(timeout=20)
    if not applied:
        preview = ledger.preview(tokens["admin"], "demo", incoming["id"])
        ledger.approve_support(
            tokens["admin"],
            "demo",
            incoming["id"],
            target["id"],
            expected_revision=0,
            expected_target_revision=1,
            expected_head=preview["head_revision"],
            reason="refreshed review",
        )
    assert len(ledger.visible(tokens["agent"], "demo")) == 1


def test_provenance_loading_does_not_add_one_query_per_fact(context):
    ledger, _, tokens = context
    for index in range(12):
        candidate = ledger.propose(
            tokens["agent"],
            "demo",
            subject=f"component-{index}",
            predicate="database",
            value="SQLite",
            valid_from="2030-01-01T00:00:00Z",
        )
        approve(context, candidate)
    statements = []

    def count_query(*args):
        statements.append(args[2])

    event.listen(ledger.engine, "before_cursor_execute", count_query)
    try:
        assert len(ledger.visible(tokens["agent"], "demo")) == 12
    finally:
        event.remove(ledger.engine, "before_cursor_execute", count_query)
    assert len(statements) <= 6
