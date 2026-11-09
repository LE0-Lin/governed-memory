import pytest

from governed_memory.identity import Denied, create_project, issue_credential, revoke_access

from .conftest import approve, propose


def test_project_admin_can_create_an_isolated_second_project(context):
    ledger, _, tokens = context
    create_project(ledger.engine, tokens["admin"], "demo", "second")
    second = issue_credential(ledger.engine, tokens["admin"], "second-agent", "second", "agent")
    approve(context, propose(context))
    assert ledger.visible(second, "second") == []
    with pytest.raises(Denied):
        ledger.visible(second, "demo")
    with pytest.raises(Denied):
        create_project(ledger.engine, tokens["agent"], "demo", "third")


def test_revoked_project_access_blocks_historical_lookup(context):
    ledger, _, tokens = context
    approve(context, propose(context))
    revoke_access(ledger.engine, tokens["admin"], "demo", "agent")
    with pytest.raises(Denied):
        ledger.visible(tokens["agent"], "demo", known_at="2030-01-03T00:00:00Z")
