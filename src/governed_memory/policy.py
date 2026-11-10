"""Operator decision rules. Inputs are built from authenticated ledger records."""

from dataclasses import asdict, dataclass

import httpx

from governed_memory.errors import Conflict, Denied, PolicyUnavailable

TRANSITIONS = {
    "approve": {"proposed"},
    "reject": {"proposed"},
    "revoke": {"active", "superseded"},
    "approve_support": {"proposed"},
}


@dataclass(frozen=True)
class Decision:
    role: str
    action: str
    state: str
    protected: bool
    source_revoked: bool


class BuiltinPolicy:
    def check(self, decision: Decision):
        if decision.role not in {"admin", "approver"}:
            raise Denied("an operator credential is required")
        if decision.protected and decision.role != "admin":
            raise Denied("protected facts require an administrator")
        if decision.action == "withdraw_source":
            return
        if decision.action not in TRANSITIONS:
            raise ValueError("unknown decision")
        if decision.state not in TRANSITIONS[decision.action]:
            raise Conflict(f"cannot {decision.action} a {decision.state} candidate")
        if decision.source_revoked and decision.action in {"approve", "approve_support"}:
            raise Conflict("cannot approve a withdrawn source")


class OpaPolicy(BuiltinPolicy):
    """OPA may further restrict decisions; it cannot relax the built-in safety rules."""

    def __init__(self, url: str, timeout: float = 2.0):
        self.url = url.rstrip("/") + "/v1/data/governed_memory/allow"
        self.timeout = timeout

    def check(self, decision: Decision):
        super().check(decision)
        try:
            response = httpx.post(self.url, json={"input": asdict(decision)}, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PolicyUnavailable("OPA is unavailable; the decision was not applied") from exc
        if not isinstance(result, dict) or result.get("result") is not True:
            raise Denied("OPA did not allow this decision")
