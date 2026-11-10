"""Dependency checks shared by approval, current reads and graph projection."""

from sqlalchemy import select

from governed_memory.errors import Conflict, Denied
from governed_memory.evidence import approved_source_map, approved_sources
from governed_memory.models import Candidate, FactVersion, MemoryDependency


def dependencies(session, candidate_id):
    return list(
        session.scalars(
            select(MemoryDependency).where(MemoryDependency.candidate_id == candidate_id)
        )
    )


def available(session, candidate_id, known_at, actor=None):
    return availability(session, [candidate_id], known_at, actor)[candidate_id]


def availability(session, candidate_ids, known_at, actor=None):
    """Load by graph depth rather than issuing one query for every returned fact."""
    graph, parents, loaded = {}, {}, set()
    frontier = set(candidate_ids)
    depth = 0
    while frontier:
        depth += 1
        if depth > 32:
            return dict.fromkeys(candidate_ids, False)
        rows = session.execute(
            select(MemoryDependency, FactVersion, Candidate)
            .join(FactVersion, FactVersion.id == MemoryDependency.parent_version_id)
            .join(Candidate, Candidate.id == FactVersion.candidate_id)
            .where(MemoryDependency.candidate_id.in_(frontier))
        ).all()
        loaded.update(frontier)
        frontier = set()
        for edge, version, parent in rows:
            graph.setdefault(edge.candidate_id, []).append((edge, version, parent))
            parents[parent.id] = parent
            if parent.id not in loaded:
                frontier.add(parent.id)
    sources = approved_source_map(session, list(parents.values()), known_at, actor)
    memo = {}

    def visit(identifier, path):
        if identifier in memo:
            return memo[identifier]
        if identifier in path:
            return False
        for edge, version, parent in graph.get(identifier, []):
            if (
                parent.state not in {"active", "superseded"}
                or version.system_until is not None
                or version.system_from > known_at
                or not any(source.id == edge.source_id for source in sources.get(parent.id, []))
                or not visit(parent.id, path | {identifier})
            ):
                memo[identifier] = False
                return False
        memo[identifier] = True
        return True

    return {identifier: visit(identifier, set()) for identifier in candidate_ids}


def stage(session, candidate, parent_ids, actor, now):
    if (
        not isinstance(parent_ids, list)
        or len(parent_ids) > 32
        or len(set(parent_ids)) != len(parent_ids)
    ):
        raise ValueError("dependencies must be up to 32 distinct snapshot IDs")
    for parent_id in parent_ids:
        version = session.get(FactVersion, parent_id)
        if version is None or version.project != candidate.project:
            raise Denied("dependency not accessible")
        parent = session.get(Candidate, version.candidate_id)
        sources = approved_sources(session, parent, now, actor)
        if not sources or not available(session, parent.id, now, actor):
            raise Denied("dependency not accessible")
        if (
            parent.fact_id == candidate.fact_id
            or version.system_until is not None
            or version.valid_from > candidate.valid_from
            or (
                version.valid_until is not None
                and (candidate.valid_until is None or candidate.valid_until > version.valid_until)
            )
        ):
            raise Conflict("dependency must be a current snapshot covering the derived interval")
        # A new proposed node cannot already be an ancestor of an approved snapshot.
        session.add(
            MemoryDependency(
                candidate_id=candidate.id,
                parent_version_id=version.id,
                source_id=sources[0].id,
                parent_revision=parent.revision,
            )
        )


def check_approval(session, candidate, actor, now):
    for edge in dependencies(session, candidate.id):
        version = session.get(FactVersion, edge.parent_version_id)
        parent = session.get(Candidate, version.candidate_id)
        if parent.revision != edge.parent_revision:
            raise Conflict("dependency changed; stage a new derivation for review")
    if not available(session, candidate.id, now, actor):
        raise Conflict("dependency is no longer eligible")
