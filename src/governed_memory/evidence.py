"""Build caller-visible provenance from currently usable, approved source records."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from governed_memory.models import Candidate, Source, SourceSupport


@dataclass(frozen=True)
class SourceReference:
    id: str
    locator: str
    content_hash: str
    fragment: str
    candidate_id: str


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
    additional_sources: tuple[SourceReference, ...] = ()
    withdrawn: bool = False


def source_reference(candidate, source):
    return SourceReference(
        source.id, source.locator, source.content_hash, candidate.fragment, candidate.id
    )


def approved_sources(session, candidate, known_at, actor=None) -> list[SourceReference]:
    return approved_source_map(session, [candidate], known_at, actor).get(candidate.id, [])


def approved_source_map(session, candidates, known_at, actor=None):
    """Fetch provenance in two queries rather than one lookup per returned fact."""
    parents = {c.id: c for c in candidates if c.state in {"active", "superseded"}}
    if not parents:
        return {}
    primary = {
        source.id: source
        for source in session.scalars(
            select(Source).where(Source.id.in_({c.source_id for c in parents.values()}))
        )
    }
    rows = [(c.id, c, primary[c.source_id]) for c in parents.values()]
    rows.extend(
        session.execute(
            select(SourceSupport.candidate_id, Candidate, Source)
            .join(
                Source,
                Source.id == Candidate.source_id,
            )
            .join(SourceSupport, SourceSupport.evidence_candidate_id == Candidate.id)
            .where(
                SourceSupport.candidate_id.in_(parents),
                SourceSupport.approved_at <= known_at,
            )
            .order_by(SourceSupport.approved_at, SourceSupport.id)
        ).all()
    )
    result = {candidate_id: [] for candidate_id in parents}
    for candidate_id, evidence_candidate, source in rows:
        if evidence_candidate.state not in {"active", "superseded"}:
            continue
        if (
            source.revoked_at
            or source.created_at > known_at
            or evidence_candidate.proposed_at > known_at
        ):
            continue
        if actor and source.audience and actor.id not in source.audience and actor.role != "admin":
            continue
        result[candidate_id].append(source_reference(evidence_candidate, source))
    return result


def make_evidence(version, candidate, sources, *, fallback=None):
    primary = sources[0] if sources else fallback
    return Evidence(
        id=version.id,
        candidate_id=candidate.id,
        fact_id=candidate.fact_id,
        project=version.project,
        text=version.text,
        source_id=primary.id,
        locator=primary.locator,
        content_hash=primary.content_hash,
        fragment=primary.fragment,
        subject=candidate.subject,
        predicate=candidate.predicate,
        value=candidate.value,
        valid_from=version.valid_from,
        valid_until=version.valid_until,
        system_from=version.system_from,
        system_until=version.system_until,
        additional_sources=tuple(sources[1:]),
        withdrawn=not bool(sources),
    )
