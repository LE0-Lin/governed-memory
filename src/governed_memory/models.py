"""The relational ledger is authoritative; the graph is a disposable projection."""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        return value.astimezone(UTC)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


class Principal(Base):
    __tablename__ = "principals"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)


class Grant(Base):
    __tablename__ = "grants"
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), primary_key=True)
    project: Mapped[str] = mapped_column(String(100), primary_key=True)
    role: Mapped[str] = mapped_column(String(20))
    __table_args__ = (CheckConstraint("role IN ('reader','agent','approver','admin')"),)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project: Mapped[str] = mapped_column(String(100), index=True)
    locator: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    body: Mapped[str] = mapped_column(Text)
    audience: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    __table_args__ = (UniqueConstraint("project", "locator", "content_hash"),)


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fact_id: Mapped[str] = mapped_column(String(36), index=True)
    project: Mapped[str] = mapped_column(String(100), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    proposer: Mapped[str] = mapped_column(ForeignKey("principals.id"))
    subject: Mapped[str] = mapped_column(Text)
    predicate: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(Text)
    fragment: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime)
    valid_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    proposed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    state: Mapped[str] = mapped_column(String(20), default="proposed")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    protected: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        CheckConstraint("state IN ('proposed','active','rejected','superseded','revoked')"),
        CheckConstraint("valid_until IS NULL OR valid_until > valid_from"),
        CheckConstraint("revision >= 0"),
    )


class FactVersion(Base):
    __tablename__ = "fact_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    fact_id: Mapped[str] = mapped_column(String(36), index=True)
    project: Mapped[str] = mapped_column(String(100), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    text: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime)
    valid_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    system_from: Mapped[datetime] = mapped_column(UTCDateTime)
    system_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    __table_args__ = (
        CheckConstraint("valid_until IS NULL OR valid_until > valid_from"),
        CheckConstraint("system_until IS NULL OR system_until > system_from"),
    )


class FactHead(Base):
    __tablename__ = "fact_heads"
    fact_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)


class GovernanceEvent(Base):
    __tablename__ = "governance_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    actor: Mapped[str] = mapped_column(ForeignKey("principals.id"))
    action: Mapped[str] = mapped_column(String(30))
    revision: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("candidate_id", "revision"),)


class ProjectionJob(Base):
    __tablename__ = "projection_jobs"
    id: Mapped[str] = mapped_column(ForeignKey("fact_versions.id"), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    generation: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class SourceEvent(Base):
    __tablename__ = "source_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    actor: Mapped[str] = mapped_column(ForeignKey("principals.id"))
    action: Mapped[str] = mapped_column(String(30))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)


class SourceSupport(Base):
    """An operator-approved independent source for an existing assertion."""

    __tablename__ = "source_supports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    evidence_candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), unique=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    approved_at: Mapped[datetime] = mapped_column(UTCDateTime)
    target_revision: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(ForeignKey("principals.id"))
    __table_args__ = (
        UniqueConstraint("candidate_id", "source_id"),
        CheckConstraint("candidate_id <> evidence_candidate_id"),
    )


class MemoryDependency(Base):
    """A reviewed derivation uses an exact snapshot and one particular source revision."""

    __tablename__ = "memory_dependencies"
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), primary_key=True)
    parent_version_id: Mapped[str] = mapped_column(ForeignKey("fact_versions.id"), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    parent_revision: Mapped[int] = mapped_column(Integer)


class EntityResolution(Base):
    __tablename__ = "entity_resolutions"
    original_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), primary_key=True)
    replacement_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), unique=True)
    target_version_id: Mapped[str] = mapped_column(ForeignKey("fact_versions.id"))
    actor: Mapped[str] = mapped_column(ForeignKey("principals.id"))
    reason: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)


class LineageEvent(Base):
    """Immutable OpenLineage payload; delivery bookkeeping lives in a separate row."""

    __tablename__ = "lineage_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class LineageDelivery(Base):
    __tablename__ = "lineage_deliveries"
    id: Mapped[str] = mapped_column(ForeignKey("lineage_events.id"), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
