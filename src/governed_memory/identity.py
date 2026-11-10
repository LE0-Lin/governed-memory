import hashlib
import re
import secrets
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from governed_memory.errors import Denied as Denied
from governed_memory.models import Grant, Principal


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Identity:
    id: str
    project: str
    role: str


def authenticate(
    session: Session, token: str, project: str, roles=(), *, authorizer=None
) -> Identity:
    principal = session.scalar(select(Principal).where(Principal.token_hash == token_hash(token)))
    if principal is None or principal.disabled:
        raise Denied("invalid credential")
    grant = session.get(Grant, (principal.id, project))
    if grant is None or (roles and grant.role not in roles):
        raise Denied("project permission denied")
    identity = Identity(principal.id, project, grant.role)
    if authorizer:
        # OPA and source audience checks must see the intersected role, too.
        identity = authorizer.restrict(identity)
        if roles and identity.role not in roles:
            raise Denied("OpenFGA project permission denied")
    return identity


def bootstrap(engine, principal_id: str, project: str) -> str:
    """Local operator entry point: only an empty installation can be bootstrapped."""
    validate_project(project)
    token = secrets.token_urlsafe(32)
    with Session(engine) as s, s.begin():
        if s.scalar(select(func.count()).select_from(Principal)):
            raise Denied("already initialized; use an existing administrator credential")
        s.add(Principal(id=principal_id, token_hash=token_hash(token)))
        s.flush()
        s.add(Grant(principal_id=principal_id, project=project, role="admin"))
    return token


def validate_project(project: str):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", project):
        raise ValueError("project must be 1..64 letters, digits, hyphens or underscores")


def create_project(engine, admin_token: str, from_project: str, project: str, *, authorizer=None):
    validate_project(project)
    with Session(engine) as s, s.begin():
        actor = authenticate(s, admin_token, from_project, ("admin",), authorizer=authorizer)
        if s.scalar(select(Grant).where(Grant.project == project)):
            raise ValueError("project already exists")
        s.add(Grant(principal_id=actor.id, project=project, role="admin"))


def revoke_access(engine, admin_token: str, project: str, principal_id: str, *, authorizer=None):
    with Session(engine) as s, s.begin():
        actor = authenticate(s, admin_token, project, ("admin",), authorizer=authorizer)
        if actor.id == principal_id:
            raise Denied("use a different administrator to revoke this credential")
        grant = s.get(Grant, (principal_id, project))
        if grant is None:
            raise Denied("principal not accessible")
        s.delete(grant)


def issue_credential(
    engine, admin_token: str, principal_id: str, project: str, role: str, *, authorizer=None
) -> str:
    if role not in {"reader", "agent", "approver", "admin"}:
        raise ValueError("unknown role")
    token = secrets.token_urlsafe(32)
    with Session(engine) as s, s.begin():
        authenticate(s, admin_token, project, ("admin",), authorizer=authorizer)
        if s.get(Principal, principal_id):
            raise ValueError("principal exists; issue a distinct credential name")
        s.add(Principal(id=principal_id, token_hash=token_hash(token)))
        s.flush()
        s.add(Grant(principal_id=principal_id, project=project, role=role))
    return token
