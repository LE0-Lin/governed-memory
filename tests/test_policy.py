import itertools
import os
from dataclasses import asdict

import httpx
import pytest

from governed_memory.errors import Conflict, Denied, PolicyUnavailable
from governed_memory.policy import BuiltinPolicy, Decision, OpaPolicy

from .conftest import approve, propose


@pytest.mark.parametrize("failure", ["unavailable", "deny", "invalid_boolean"])
def test_policy_failure_does_not_apply_any_part_of_an_approval(context, monkeypatch, failure):
    ledger, _, tokens = context
    candidate = propose(context)
    ledger.policy = OpaPolicy("http://policy.invalid")

    def response(*args, **kwargs):
        if failure == "unavailable":
            raise httpx.ConnectError("offline")
        return httpx.Response(
            200,
            json={"result": "true" if failure == "invalid_boolean" else False},
            request=httpx.Request("POST", "http://policy.invalid"),
        )

    monkeypatch.setattr(httpx, "post", response)
    with pytest.raises((Denied, PolicyUnavailable)):
        approve(context, candidate)
    current = ledger.explain(tokens["admin"], "demo", candidate["id"])
    assert current["state"] == "proposed" and current["revision"] == 0
    assert [event["action"] for event in current["events"]] == ["proposed"]
    assert ledger.visible(tokens["agent"], "demo") == []
    assert ledger.pending() == []


@pytest.mark.integration
def test_rego_and_builtin_decisions_agree_for_the_full_permission_matrix():
    url = os.environ.get("GM_TEST_OPA_URL")
    if not url:
        pytest.skip("set GM_TEST_OPA_URL for real OPA policy parity")
    policy = BuiltinPolicy()
    endpoint = url.rstrip("/") + "/v1/data/governed_memory/allow"
    cases = itertools.product(
        ("reader", "agent", "approver", "admin"),
        ("approve", "reject", "revoke", "approve_support", "withdraw_source"),
        ("proposed", "active", "rejected", "superseded", "revoked"),
        (False, True),
        (False, True),
    )
    with httpx.Client(timeout=5) as client:
        for values in cases:
            decision = Decision(*values)
            try:
                policy.check(decision)
                expected = True
            except (Denied, Conflict):
                expected = False
            response = client.post(endpoint, json={"input": asdict(decision)})
            response.raise_for_status()
            assert response.json().get("result") is expected, decision


@pytest.mark.integration
def test_real_opa_allows_a_legitimate_ledger_approval(context):
    url = os.environ.get("GM_TEST_OPA_URL")
    if not url:
        pytest.skip("set GM_TEST_OPA_URL for real OPA ledger integration")
    ledger, _, tokens = context
    ledger.policy = OpaPolicy(url)
    approve(context, propose(context))
    assert ledger.visible(tokens["agent"], "demo")[0].value == "SQLite"
