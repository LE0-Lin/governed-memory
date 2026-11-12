"""Transactional OpenLineage outbox. Network failures never roll back approved memory."""

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from governed_memory.models import (
    FactVersion,
    LineageDelivery,
    LineageEvent,
    MemoryDependency,
)

PRODUCER = "https://github.com/LE0-Lin/governed-memory/tree/v0.4.0"
SCHEMA = "https://openlineage.io/spec/2-0-2/OpenLineage.json#/$defs/RunEvent"
LIFECYCLE_SCHEMA = (
    "https://openlineage.io/spec/facets/1-0-1/LifecycleStateChangeDatasetFacet.json"
    "#/$defs/LifecycleStateChangeDatasetFacet"
)


def dataset(project, kind, identifier, *, action=None):
    result = {"namespace": f"governed-memory://{project}", "name": f"{kind}/{identifier}"}
    if action:
        result["facets"] = {
            "lifecycleStateChange": {
                "_producer": PRODUCER,
                "_schemaURL": LIFECYCLE_SCHEMA,
                "lifecycleStateChange": action,
            }
        }
    return result


def record(session, candidate, action, event_id, now, *, version=None, extra_inputs=()):
    inputs = [dataset(candidate.project, "source", candidate.source_id)]
    inputs.extend(
        dataset(candidate.project, "snapshot", edge.parent_version_id)
        for edge in session.scalars(
            select(MemoryDependency).where(MemoryDependency.candidate_id == candidate.id)
        )
    )
    inputs.extend(extra_inputs)
    lifecycle = "CREATE" if version else "ALTER"
    if action in {"revoked", "rejected", "snapshot_superseded"}:
        lifecycle = "DROP"
    output = dataset(
        candidate.project,
        "snapshot" if version else "candidate",
        version.id if version else candidate.id,
        action=lifecycle,
    )
    outputs = [output]
    if action == "revoked":
        outputs.extend(
            dataset(candidate.project, "snapshot", identifier, action="DROP")
            for identifier in session.scalars(
                select(FactVersion.id).where(FactVersion.candidate_id == candidate.id)
            )
        )
    payload = {
        "eventType": "COMPLETE",
        "eventTime": now.isoformat(),
        "producer": PRODUCER,
        "schemaURL": SCHEMA,
        "run": {"runId": event_id},
        "job": {"namespace": f"governed-memory://{candidate.project}", "name": f"memory.{action}"},
        "inputs": inputs,
        "outputs": outputs,
    }
    session.add(LineageEvent(id=event_id, project=candidate.project, payload=payload))
    session.flush()
    session.add(LineageDelivery(id=event_id, completed=False, attempts=0))


def record_source_withdrawal(session, source, event_id, now):
    # A source lifecycle event is separate from candidate invalidations in the same transaction.
    session.add(
        LineageEvent(
            id=event_id,
            project=source.project,
            payload={
                "eventType": "COMPLETE",
                "eventTime": now.isoformat(),
                "producer": PRODUCER,
                "schemaURL": SCHEMA,
                "run": {"runId": event_id},
                "job": {
                    "namespace": f"governed-memory://{source.project}",
                    "name": "memory.withdraw_source",
                },
                "inputs": [],
                "outputs": [dataset(source.project, "source", source.id, action="DROP")],
            },
        )
    )
    session.flush()
    session.add(LineageDelivery(id=event_id, completed=False, attempts=0))


def drain(engine, project, endpoint, *, api_key=None, limit=100):
    """Send a bounded batch; a crash after HTTP success may repeat the same runId."""
    if not 1 <= limit <= 1000:
        raise ValueError("lineage batch size must be 1..1000")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    counts = {"completed": 0, "failed": 0}
    with httpx.Client(timeout=10, follow_redirects=False, headers=headers) as client:
        with Session(engine) as session:
            ids = list(
                session.scalars(
                    select(LineageEvent.id)
                    .join(LineageDelivery)
                    .where(LineageEvent.project == project, LineageDelivery.completed.is_(False))
                    .order_by(LineageEvent.id)
                    .limit(limit)
                )
            )
        for identifier in ids:
            # Holding only this outbox row allows concurrent workers to skip completed jobs.
            with Session(engine) as session, session.begin():
                delivery = session.get(LineageDelivery, identifier, with_for_update=True)
                if delivery.completed:
                    continue
                event = session.get(LineageEvent, identifier)
                delivery.attempts += 1
                try:
                    client.post(endpoint, json=event.payload).raise_for_status()
                except httpx.HTTPError:
                    # Collector errors may contain credentials or source details: do not store them.
                    delivery.error = "collector delivery failed"
                    counts["failed"] += 1
                else:
                    delivery.completed, delivery.error = True, None
                    counts["completed"] += 1
    return counts
