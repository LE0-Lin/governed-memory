import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import or_, select, text, update
from sqlalchemy.orm import Session

from governed_memory.identity import Denied, authenticate
from governed_memory.models import (
    Candidate,
    FactHead,
    FactVersion,
    GovernanceEvent,
    ProjectionJob,
    Source,
    SourceEvent,
)


class Conflict(ValueError):
    pass


def instant(value: str | datetime) -> datetime:
    result = (
        datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    )
    if result.tzinfo is None:
        raise ValueError("timestamps must include an explicit timezone")
    return result.astimezone(UTC)


def stable_id(*parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, json.dumps(parts, ensure_ascii=False)))


@dataclass(frozen=True)
class Evidence:
    id: str
    candidate_id: str
    fact_id: str
    project: str
    text: str
    source_id: str
    locator: str
    content_hash: str
    fragment: str
    subject: str
    predicate: str
    value: str
    valid_from: datetime
    valid_until: datetime | None
    system_from: datetime
    system_until: datetime | None


def evidence(version, candidate, source) -> Evidence:
    return Evidence(
        version.id,
        candidate.id,
        candidate.fact_id,
        version.project,
        version.text,
        source.id,
        source.locator,
        source.content_hash,
        candidate.fragment,
        candidate.subject,
        candidate.predicate,
        candidate.value,
        version.valid_from,
        version.valid_until,
        version.system_from,
        version.system_until,
    )


class Ledger:
    def __init__(self, engine, clock: Callable[[], datetime] | None = None):
        self.engine = engine
        self.clock = clock or (lambda: datetime.now(UTC))

    def propose(
        self,
        token: str,
        project: str,
        *,
        subject: str,
        predicate: str,
        value: str,
        valid_from: str | datetime,
        valid_until: str | datetime | None = None,
        locator: str = "mcp:proposal",
        body: str | None = None,
        fragment: str = "proposal",
        audience: list[str] | None = None,
    ) -> dict:
        start = instant(valid_from)
        end = instant(valid_until) if valid_until else None
        if end is not None and end <= start:
            raise ValueError("valid interval must be nonempty and left closed, right open")
        if not all(x.strip() for x in (subject, predicate, value, locator, fragment)):
            raise ValueError("fact and source fields cannot be empty")
        if sum(map(len, (subject, predicate, value, body or ""))) > 100_000:
            raise ValueError("proposal exceeds 100000 characters")
        payload = json.dumps([subject, predicate, value, start.isoformat(), str(end)])
        body = body if body is not None else payload
        digest = hashlib.sha256(body.encode()).hexdigest()
        source_id = stable_id(project, locator, digest)
        fact_id = stable_id(project, subject.strip().casefold(), predicate.strip().casefold())
        candidate_id = stable_id(source_id, payload, fragment)
        with Session(self.engine) as s, s.begin():
            actor = authenticate(s, token, project, ("agent", "approver", "admin"))
            if audience and actor.role != "admin":
                raise Denied("only administrators may set source audience")
            source = s.get(Source, source_id)
            if source is not None:
                self._source_access(source, actor)
                if source.revoked_at:
                    raise Conflict("source has been withdrawn; use a new source revision")
                if audience is not None and audience != source.audience:
                    raise Conflict("idempotent import cannot change a source audience")
            else:
                s.add(
                    Source(
                        id=source_id,
                        project=project,
                        locator=locator,
                        content_hash=digest,
                        body=body,
                        audience=audience or [],
                        created_at=instant(self.clock()),
                    )
                )
                s.flush()
            candidate = s.get(Candidate, candidate_id)
            if candidate is None:
                candidate = Candidate(
                    id=candidate_id,
                    fact_id=fact_id,
                    project=project,
                    source_id=source_id,
                    proposer=actor.id,
                    subject=subject.strip(),
                    predicate=predicate.strip(),
                    value=value.strip(),
                    fragment=fragment,
                    valid_from=start,
                    valid_until=end,
                    proposed_at=instant(self.clock()),
                    state="proposed",
                    revision=0,
                    protected=False,
                )
                s.add(candidate)
                s.flush()
                self._event(s, candidate, actor.id, "proposed", "staged; no trusted projection")
            return self._candidate(candidate)

    @staticmethod
    def _source_access(source, actor):
        if source.audience and actor.id not in source.audience and actor.role != "admin":
            raise Denied("source is not accessible")

    @staticmethod
    def _candidate(c):
        return {
            key: getattr(c, key)
            for key in (
                "id",
                "fact_id",
                "project",
                "source_id",
                "subject",
                "predicate",
                "value",
                "valid_from",
                "valid_until",
                "state",
                "revision",
                "protected",
            )
        }

    def _event(self, s, candidate, actor, action, reason):
        s.add(
            GovernanceEvent(
                id=str(uuid4()),
                candidate_id=candidate.id,
                actor=actor,
                action=action,
                revision=candidate.revision,
                occurred_at=instant(self.clock()),
                reason=reason,
            )
        )

    @staticmethod
    def _queue(s, version):
        s.flush()
        job = s.get(ProjectionJob, version.id)
        if job:
            job.completed = False
            job.generation += 1
        else:
            s.add(ProjectionJob(id=version.id, completed=False, attempts=0, generation=0))

    def _insert_version(self, s, c, start, end, now, *, original=None):
        v = FactVersion(
            id=str(uuid4()),
            candidate_id=c.id,
            fact_id=c.fact_id,
            project=c.project,
            source_id=c.source_id,
            text=(original.text if original else f"{c.subject} | {c.predicate}: {c.value}"),
            valid_from=start,
            valid_until=end,
            system_from=now,
            system_until=None,
        )
        s.add(v)
        self._queue(s, v)
        return v

    def decide(
        self,
        token: str,
        project: str,
        candidate_id: str,
        action: str,
        expected_revision: int,
        *,
        reason: str,
        protected: bool = False,
        expected_head: int | None = None,
    ) -> dict:
        if action not in {"approve", "reject", "revoke"}:
            raise ValueError("unknown decision")
        if not reason.strip():
            raise ValueError("a decision reason is required")
        with Session(self.engine) as s, s.begin():
            actor = authenticate(s, token, project, ("approver", "admin"))
            c = s.get(Candidate, candidate_id)
            if c is None or c.project != project:
                raise Denied("memory not accessible")
            # Serialize changes to one fact, including approvals of different candidates.
            if self.engine.dialect.name == "postgresql":
                lock = int.from_bytes(
                    hashlib.sha256(c.fact_id.encode()).digest()[:8], "big", signed=True
                )
                s.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
                s.refresh(c)
            self._source_access(s.get(Source, c.source_id), actor)
            if c.revision != expected_revision:
                raise Conflict("revision changed; inspect the current change set")
            target = {"approve": "active", "reject": "rejected", "revoke": "revoked"}[action]
            allowed = {
                "proposed": {"active", "rejected"},
                "active": {"revoked"},
                "superseded": {"revoked"},
            }
            if target not in allowed.get(c.state, set()):
                raise Conflict(f"cannot transition {c.state} to {target}")
            protected_fact = s.scalar(
                select(Candidate.id).where(
                    Candidate.fact_id == c.fact_id, Candidate.protected.is_(True)
                )
            )
            if (protected or protected_fact) and actor.role != "admin":
                raise Denied("protected facts require an administrator")
            now = instant(self.clock())
            source = s.get(Source, c.source_id, with_for_update=True)
            if action == "approve" and source.revoked_at:
                raise Conflict("cannot approve a withdrawn source")
            if action == "approve":
                head = s.get(FactHead, c.fact_id)
                if expected_head != (head.revision if head else 0):
                    raise Conflict("fact head changed or missing; preview the change set again")
                if head:
                    head.revision += 1
                else:
                    s.add(FactHead(fact_id=c.fact_id, revision=1))
            old_state = c.state
            changed = s.execute(
                update(Candidate)
                .where(
                    Candidate.id == c.id,
                    Candidate.revision == expected_revision,
                    Candidate.state == old_state,
                )
                .values(
                    state=target,
                    revision=expected_revision + 1,
                    protected=c.protected or protected or bool(protected_fact),
                )
            )
            if changed.rowcount != 1:
                raise Conflict("concurrent decision; reload the candidate")
            s.refresh(c)
            self._event(s, c, actor.id, target, reason)
            if action == "approve":
                current = list(
                    s.scalars(
                        select(FactVersion).where(
                            FactVersion.fact_id == c.fact_id,
                            FactVersion.system_until.is_(None),
                            or_(
                                FactVersion.valid_until.is_(None),
                                FactVersion.valid_until > c.valid_from,
                            ),
                            *([FactVersion.valid_from < c.valid_until] if c.valid_until else []),
                        )
                    )
                )
                for old in current:
                    if now <= old.system_from:
                        raise Conflict("approval time must advance beyond previous fact version")
                    prior = s.get(Candidate, old.candidate_id)
                    self._source_access(s.get(Source, old.source_id), actor)
                    old.system_until = now
                    self._queue(s, old)
                    if old.valid_from < c.valid_from:
                        self._insert_version(
                            s, prior, old.valid_from, c.valid_from, now, original=old
                        )
                    if c.valid_until is not None and (
                        old.valid_until is None or c.valid_until < old.valid_until
                    ):
                        self._insert_version(
                            s, prior, c.valid_until, old.valid_until, now, original=old
                        )
                    if prior.state == "active":
                        prior.state = "superseded"
                        prior.revision += 1
                        self._event(s, prior, actor.id, "superseded", f"replaced by {c.id}")
                self._insert_version(s, c, c.valid_from, c.valid_until, now)
            return self._candidate(c)

    def visible(self, token: str, project: str, *, valid_at=None, known_at=None) -> list[Evidence]:
        now = instant(self.clock())
        valid, known = (
            instant(valid_at) if valid_at else now,
            instant(known_at) if known_at else now,
        )
        with Session(self.engine) as s:
            actor = authenticate(s, token, project)
            rows = s.execute(
                select(FactVersion, Candidate, Source)
                .join(
                    Candidate,
                    Candidate.id == FactVersion.candidate_id,
                )
                .join(Source, Source.id == FactVersion.source_id)
                .where(
                    FactVersion.project == project,
                    FactVersion.valid_from <= valid,
                    or_(FactVersion.valid_until.is_(None), FactVersion.valid_until > valid),
                    FactVersion.system_from <= known,
                    or_(FactVersion.system_until.is_(None), FactVersion.system_until > known),
                    Candidate.state.in_(("active", "superseded")),
                    Candidate.proposed_at <= known,
                    Source.created_at <= known,
                    Source.revoked_at.is_(None),
                )
            )
            return [
                evidence(v, c, source)
                for v, c, source in rows
                if not source.audience or actor.id in source.audience or actor.role == "admin"
            ]

    def explain(self, token: str, project: str, memory_id: str) -> dict:
        with Session(self.engine) as s:
            actor = authenticate(s, token, project)
            c = s.get(Candidate, memory_id)
            if c is None:
                version = s.get(FactVersion, memory_id)
                c = s.get(Candidate, version.candidate_id) if version else None
            if c is None or c.project != project:
                raise Denied("memory not accessible")
            source = s.get(Source, c.source_id)
            self._source_access(source, actor)
            if source.revoked_at or c.state == "revoked":
                raise Denied("memory withdrawn")
            if (
                c.state in {"proposed", "rejected"}
                and c.proposer != actor.id
                and actor.role
                not in {
                    "approver",
                    "admin",
                }
            ):
                raise Denied("staged memory is not accessible")
            result = self._candidate(c)
            result["source"] = {
                "id": source.id,
                "locator": source.locator,
                "sha256": source.content_hash,
                "fragment": c.fragment,
            }
            result["events"] = [
                {
                    "actor": e.actor,
                    "action": e.action,
                    "at": e.occurred_at,
                    "revision": e.revision,
                    "reason": e.reason,
                }
                for e in s.scalars(
                    select(GovernanceEvent)
                    .where(
                        GovernanceEvent.candidate_id == c.id,
                    )
                    .order_by(GovernanceEvent.revision)
                )
            ]
            return result

    def withdraw_source(self, token: str, project: str, source_id: str):
        with Session(self.engine) as s, s.begin():
            actor = authenticate(s, token, project, ("admin", "approver"))
            source = s.get(Source, source_id, with_for_update=True)
            if source is None or source.project != project:
                raise Denied("source not accessible")
            self._source_access(source, actor)
            protected = s.scalar(
                select(Candidate.id).where(
                    Candidate.source_id == source_id, Candidate.protected.is_(True)
                )
            )
            if protected and actor.role != "admin":
                raise Denied("protected sources require an administrator")
            if source.revoked_at is None:
                source.revoked_at = instant(self.clock())
                s.add(
                    SourceEvent(
                        id=str(uuid4()),
                        source_id=source_id,
                        actor=actor.id,
                        action="withdrawn",
                        occurred_at=source.revoked_at,
                    )
                )

    def pending(self, limit: int = 100, project: str | None = None):
        with Session(self.engine) as s:
            rows = s.execute(
                select(FactVersion, Candidate, Source, ProjectionJob.generation)
                .join(
                    ProjectionJob,
                    ProjectionJob.id == FactVersion.id,
                )
                .join(Candidate, Candidate.id == FactVersion.candidate_id)
                .join(
                    Source,
                    Source.id == FactVersion.source_id,
                )
                .where(ProjectionJob.completed.is_(False))
                .where(*([FactVersion.project == project] if project else []))
                .order_by(FactVersion.id)
                .limit(limit)
            )
            return [(evidence(v, c, source), generation) for v, c, source, generation in rows]

    def mark_projection(self, version_id: str, generation: int, error: str | None):
        with Session(self.engine) as s, s.begin():
            job = s.get(ProjectionJob, version_id, with_for_update=True)
            job.attempts += 1
            job.completed = error is None and job.generation == generation
            job.error = error

    def requeue(self, token: str, project: str):
        with Session(self.engine) as s, s.begin():
            authenticate(s, token, project, ("admin",))
            for version in s.scalars(select(FactVersion).where(FactVersion.project == project)):
                self._queue(s, version)

    def preview(self, token: str, project: str, candidate_id: str):
        result = self.explain(token, project, candidate_id)
        with Session(self.engine) as s:
            actor = authenticate(s, token, project, ("admin", "approver"))
            head = s.get(FactHead, result["fact_id"])
            result["head_revision"] = head.revision if head else 0
            rows = s.execute(
                select(FactVersion, Candidate, Source)
                .join(
                    Candidate,
                    Candidate.id == FactVersion.candidate_id,
                )
                .join(Source, Source.id == FactVersion.source_id)
                .where(
                    FactVersion.fact_id == result["fact_id"],
                    FactVersion.system_until.is_(None),
                    or_(
                        FactVersion.valid_until.is_(None),
                        FactVersion.valid_until > result["valid_from"],
                    ),
                    *(
                        [FactVersion.valid_from < result["valid_until"]]
                        if result["valid_until"]
                        else []
                    ),
                )
            )
            changes = []
            for version, prior, source in rows:
                self._source_access(source, actor)
                changes.append(
                    {
                        "candidate_id": prior.id,
                        "value": prior.value,
                        "valid_from": version.valid_from,
                        "valid_until": version.valid_until,
                        "source_locator": source.locator,
                        "protected": prior.protected,
                    }
                )
            result["overlapping_versions"] = changes
        return result
