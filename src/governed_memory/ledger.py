import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import or_, select, text, update
from sqlalchemy.orm import Session

from governed_memory.errors import Conflict as Conflict
from governed_memory.evidence import Evidence as Evidence
from governed_memory.evidence import (
    approved_source_map,
    approved_sources,
    make_evidence,
    source_reference,
)
from governed_memory.identity import Denied, authenticate
from governed_memory.models import (
    Candidate,
    FactHead,
    FactVersion,
    GovernanceEvent,
    ProjectionJob,
    Source,
    SourceEvent,
    SourceSupport,
)
from governed_memory.policy import BuiltinPolicy, Decision


def instant(value: str | datetime) -> datetime:
    result = (
        datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    )
    if result.tzinfo is None:
        raise ValueError("timestamps must include an explicit timezone")
    return result.astimezone(UTC)


def stable_id(*parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, json.dumps(parts, ensure_ascii=False)))


class Ledger:
    def __init__(self, engine, clock: Callable[[], datetime] | None = None, policy=None):
        self.engine = engine
        self.clock = clock or (lambda: datetime.now(UTC))
        self.policy = policy or BuiltinPolicy()

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
        return self.propose_many(
            token,
            project,
            [
                {
                    "subject": subject,
                    "predicate": predicate,
                    "value": value,
                    "valid_from": valid_from,
                    "valid_until": valid_until,
                    "locator": locator,
                    "body": body,
                    "fragment": fragment,
                    "audience": audience,
                }
            ],
        )[0]

    def propose_many(self, token: str, project: str, proposals: list[dict]) -> list[dict]:
        """Stage all proposals in one transaction; any failure rolls back the batch."""
        with Session(self.engine) as session, session.begin():
            actor = authenticate(session, token, project, ("agent", "approver", "admin"))
            return [
                self._stage_proposal(session, actor, project, **proposal) for proposal in proposals
            ]

    def _stage_proposal(
        self,
        session: Session,
        actor,
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
        if not all(
            isinstance(field, str) and field.strip()
            for field in (subject, predicate, value, locator, fragment)
        ):
            raise ValueError("fact and source fields must be nonempty text")
        if body is not None and not isinstance(body, str):
            raise ValueError("source body must be text")
        if sum(map(len, (subject, predicate, value, body or ""))) > 100_000:
            raise ValueError("proposal exceeds 100000 characters")
        payload = json.dumps([subject, predicate, value, start.isoformat(), str(end)])
        body = body if body is not None else payload
        digest = hashlib.sha256(body.encode()).hexdigest()
        source_id = stable_id(project, locator, digest)
        fact_id = stable_id(project, subject.strip().casefold(), predicate.strip().casefold())
        candidate_id = stable_id(source_id, payload, fragment)
        if audience and actor.role != "admin":
            raise Denied("only administrators may set source audience")
        source = session.get(Source, source_id)
        if source is not None:
            self._source_access(source, actor)
            if source.revoked_at:
                raise Conflict("source has been withdrawn; use a new source revision")
            if audience is not None and audience != source.audience:
                raise Conflict("idempotent import cannot change a source audience")
        else:
            session.add(
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
            session.flush()
        candidate = session.get(Candidate, candidate_id)
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
            session.add(candidate)
            session.flush()
            self._event(session, candidate, actor.id, "proposed", "staged; no trusted projection")
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
            self._lock_fact(s, c)
            self._source_access(s.get(Source, c.source_id), actor)
            if c.revision != expected_revision:
                raise Conflict("revision changed; inspect the current change set")
            target = {"approve": "active", "reject": "rejected", "revoke": "revoked"}[action]
            protected_fact = self._is_protected(s, c.fact_id)
            source = s.get(Source, c.source_id, with_for_update=True)
            self.policy.check(
                Decision(
                    actor.role,
                    action,
                    c.state,
                    protected or protected_fact,
                    source.revoked_at is not None,
                )
            )
            now = instant(self.clock())
            if action == "approve":
                self._advance_head(s, c.fact_id, expected_head)
            self._set_state(s, c, target, expected_revision, protected or protected_fact)
            self._event(s, c, actor.id, target, reason)
            if action == "approve":
                self._activate(s, c, actor, now)
            elif action == "revoke":
                targets = list(
                    s.scalars(
                        select(SourceSupport.candidate_id).where(
                            SourceSupport.evidence_candidate_id == c.id
                        )
                    )
                )
                self._queue_candidates(s, [c.id, *targets], bump_heads=True)
            return self._candidate(c)

    def approve_support(
        self,
        token: str,
        project: str,
        candidate_id: str,
        target_id: str,
        *,
        expected_revision: int,
        expected_target_revision: int,
        expected_head: int,
        reason: str,
    ) -> dict:
        """Approve a staged source as corroboration, without replacing the fact's timeline."""
        if not reason.strip():
            raise ValueError("a decision reason is required")
        with Session(self.engine) as session, session.begin():
            actor = authenticate(session, token, project, ("admin", "approver"))
            incoming = session.get(Candidate, candidate_id)
            target = session.get(Candidate, target_id)
            if (
                not incoming
                or not target
                or incoming.project != project
                or target.project != project
            ):
                raise Denied("memory not accessible")
            if incoming.fact_id != target.fact_id or incoming.id == target.id:
                raise Conflict("support must refer to the same logical fact")
            self._lock_fact(session, incoming)
            session.refresh(target)
            if (
                incoming.revision != expected_revision
                or target.revision != expected_target_revision
            ):
                raise Conflict("revision changed; inspect both candidates again")
            fields = ("subject", "predicate", "value", "valid_from", "valid_until")
            if any(getattr(incoming, field) != getattr(target, field) for field in fields):
                raise Conflict(
                    "support must match the entire structured assertion and valid interval"
                )
            if target.state not in {"active", "superseded"} or not session.scalar(
                select(FactVersion.id).where(FactVersion.candidate_id == target.id).limit(1)
            ):
                raise Conflict("support target must be an approved assertion, not another support")
            source = session.get(Source, incoming.source_id, with_for_update=True)
            self._source_access(source, actor)
            self._source_access(session.get(Source, target.source_id), actor)
            if incoming.source_id == target.source_id or session.scalar(
                select(SourceSupport.id).where(
                    SourceSupport.candidate_id == target.id,
                    SourceSupport.source_id == source.id,
                )
            ):
                raise Conflict("this source already supports the assertion")
            protected = self._is_protected(session, target.fact_id)
            self.policy.check(
                Decision(
                    actor.role,
                    "approve_support",
                    incoming.state,
                    protected,
                    source.revoked_at is not None,
                )
            )
            self._advance_head(session, target.fact_id, expected_head)
            self._set_state(session, incoming, "active", expected_revision, protected)
            target.revision += 1
            now = instant(self.clock())
            session.add(
                SourceSupport(
                    id=stable_id(target.id, source.id),
                    candidate_id=target.id,
                    evidence_candidate_id=incoming.id,
                    source_id=source.id,
                    approved_at=now,
                    target_revision=target.revision,
                    actor=actor.id,
                )
            )
            self._event(session, incoming, actor.id, "active", f"supports {target.id}: {reason}")
            self._event(session, target, actor.id, "support_added", reason)
            self._queue_candidates(session, [target.id])
            return {
                "candidate": self._candidate(incoming),
                "supports": target.id,
                "target_revision": target.revision,
            }

    def _queue_candidates(self, session, candidate_ids, *, bump_heads=False):
        versions = list(
            session.scalars(select(FactVersion).where(FactVersion.candidate_id.in_(candidate_ids)))
        )
        if bump_heads and versions:
            session.execute(
                update(FactHead)
                .where(
                    FactHead.fact_id.in_(
                        {version.fact_id for version in versions},
                    )
                )
                .values(revision=FactHead.revision + 1)
            )
        # Reviews also lock the fact head before the outbox. Keep that order on withdrawal.
        for version in versions:
            self._queue(session, version)

    def _lock_fact(self, session, candidate):
        """Serialize reviews of different candidates for the same logical fact."""
        if self.engine.dialect.name == "postgresql":
            key = int.from_bytes(
                hashlib.sha256(candidate.fact_id.encode()).digest()[:8], "big", signed=True
            )
            session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
            session.refresh(candidate)

    @staticmethod
    def _is_protected(session, fact_id):
        return (
            session.scalar(
                select(Candidate.id).where(
                    Candidate.fact_id == fact_id, Candidate.protected.is_(True)
                )
            )
            is not None
        )

    @staticmethod
    def _advance_head(session, fact_id, expected_head):
        head = session.get(FactHead, fact_id)
        if expected_head != (head.revision if head else 0):
            raise Conflict("fact head changed or missing; preview the change set again")
        if head:
            head.revision += 1
        else:
            session.add(FactHead(fact_id=fact_id, revision=1))

    @staticmethod
    def _set_state(session, candidate, target, expected_revision, protected):
        changed = session.execute(
            update(Candidate)
            .where(
                Candidate.id == candidate.id,
                Candidate.revision == expected_revision,
                Candidate.state == candidate.state,
            )
            .values(
                state=target,
                revision=expected_revision + 1,
                protected=candidate.protected or protected,
            )
        )
        if changed.rowcount != 1:
            raise Conflict("concurrent decision; reload the candidate")
        session.refresh(candidate)

    def _activate(self, session, candidate, actor, now):
        """Replace overlapping valid-time intervals while retaining prior system-time beliefs."""
        current = list(
            session.scalars(
                select(FactVersion).where(
                    FactVersion.fact_id == candidate.fact_id,
                    FactVersion.system_until.is_(None),
                    or_(
                        FactVersion.valid_until.is_(None),
                        FactVersion.valid_until > candidate.valid_from,
                    ),
                    *(
                        [FactVersion.valid_from < candidate.valid_until]
                        if candidate.valid_until
                        else []
                    ),
                )
            )
        )
        for old in current:
            if now <= old.system_from:
                raise Conflict("approval time must advance beyond previous fact version")
            prior = session.get(Candidate, old.candidate_id)
            self._source_access(session.get(Source, old.source_id), actor)
            old.system_until = now
            self._queue(session, old)
            if old.valid_from < candidate.valid_from:
                self._insert_version(
                    session, prior, old.valid_from, candidate.valid_from, now, original=old
                )
            if candidate.valid_until is not None and (
                old.valid_until is None or candidate.valid_until < old.valid_until
            ):
                self._insert_version(
                    session, prior, candidate.valid_until, old.valid_until, now, original=old
                )
            if prior.state == "active":
                prior.state = "superseded"
                prior.revision += 1
                self._event(session, prior, actor.id, "superseded", f"replaced by {candidate.id}")
        self._insert_version(session, candidate, candidate.valid_from, candidate.valid_until, now)

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
                )
            )
            rows = rows.all()
            source_map = approved_source_map(s, [c for _, c, _ in rows], known, actor)
            result = []
            for version, candidate, _ in rows:
                sources = source_map.get(candidate.id, [])
                if not sources:
                    continue
                item = make_evidence(version, candidate, sources)
                if item.system_until is not None and item.system_until > known:
                    item = replace(item, system_until=None)
                result.append(item)
            return result

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
            if c.state in {"proposed", "rejected"}:
                self._source_access(source, actor)
                sources = [] if source.revoked_at else [source_reference(c, source)]
            else:
                sources = approved_sources(s, c, instant(self.clock()), actor)
            if not sources:
                raise Denied("memory withdrawn or no supporting source is accessible")
            primary = sources[0]
            result = self._candidate(c)
            result["source_id"] = primary.id
            result["source"] = {
                "id": primary.id,
                "locator": primary.locator,
                "sha256": primary.content_hash,
                "fragment": primary.fragment,
            }
            result["additional_sources"] = [asdict(ref) for ref in sources[1:]]
            visible_support_revisions = set(
                s.scalars(
                    select(SourceSupport.target_revision).where(
                        SourceSupport.candidate_id == c.id,
                        SourceSupport.source_id.in_([ref.id for ref in sources]),
                    )
                )
            )
            primary_visible = any(ref.id == c.source_id for ref in sources)
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
                if (primary_visible and e.action != "support_added")
                or e.revision in visible_support_revisions
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
            self.policy.check(
                Decision(
                    actor.role,
                    "withdraw_source",
                    "",
                    bool(protected),
                    source.revoked_at is not None,
                )
            )
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
                targets = list(
                    s.scalars(select(Candidate.id).where(Candidate.source_id == source_id))
                )
                targets += list(
                    s.scalars(
                        select(SourceSupport.candidate_id).where(
                            SourceSupport.source_id == source_id
                        )
                    )
                )
                self._queue_candidates(s, targets, bump_heads=True)

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
            rows = rows.all()
            source_map = approved_source_map(s, [c for _, c, _, _ in rows], instant(self.clock()))
            return [
                (
                    make_evidence(
                        v,
                        c,
                        source_map.get(c.id, []),
                        fallback=source_reference(c, source),
                    ),
                    generation,
                )
                for v, c, source, generation in rows
            ]

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
