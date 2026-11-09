import pytest
from sqlalchemy.orm import Session

from governed_memory.ledger import Conflict
from governed_memory.models import ProjectionJob

from .conftest import approve, propose


def test_old_worker_completion_does_not_lose_new_projection_generation(context):
    ledger, _, _ = context
    approve(context, propose(context))
    item, generation = ledger.pending()[0]
    approve(context, propose(context, "PostgreSQL"))
    ledger.mark_projection(item.id, generation, None)
    with Session(ledger.engine) as s:
        job = s.get(ProjectionJob, item.id)
        assert job.generation > generation
        assert not job.completed


def test_preview_contains_overlapping_approved_change_set(context):
    ledger, _, tokens = context
    first = approve(context, propose(context))
    second = propose(context, "PostgreSQL")
    preview = ledger.preview(tokens["admin"], "demo", second["id"])
    assert preview["overlapping_versions"][0]["candidate_id"] == first["id"]
    assert preview["overlapping_versions"][0]["value"] == "SQLite"


def test_approval_cannot_apply_a_change_set_after_another_fact_approval(context):
    ledger, _, tokens = context
    first = propose(context)
    stale = propose(context, "PostgreSQL")
    preview = ledger.preview(tokens["admin"], "demo", stale["id"])
    approve(context, first)
    with pytest.raises(Conflict, match="fact head"):
        ledger.decide(
            tokens["admin"],
            "demo",
            stale["id"],
            "approve",
            0,
            reason="old preview",
            expected_head=preview["head_revision"],
        )
