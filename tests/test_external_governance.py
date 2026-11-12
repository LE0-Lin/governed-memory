import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from sqlalchemy import select
from sqlalchemy.orm import Session

from governed_memory.authorization import OpenFgaAuthorizer, provision
from governed_memory.errors import Denied
from governed_memory.identity import Identity, issue_credential
from governed_memory.lineage import drain
from governed_memory.models import LineageDelivery, LineageEvent
from governed_memory.settings import Settings

from .conftest import approve, propose


@pytest.mark.integration
def test_real_openfga_restricts_local_roles_and_withdraws_access_immediately(context):
    endpoint = os.environ.get("GM_TEST_FGA_URL")
    if not endpoint:
        pytest.skip("set GM_TEST_FGA_URL to exercise a real OpenFGA server")
    ledger, _, tokens = context
    root = approve(context, propose(context))
    authorizer = provision(
        endpoint, "demo", [("operator", "admin"), ("agent", "agent"), ("reader", "reader")]
    )
    ledger.authorizer = authorizer
    assert ledger.visible(tokens["agent"], "demo")[0].candidate_id == root["id"]
    authorizer.grant("agent", "demo", "agent", remove=True)
    with pytest.raises(Denied):
        ledger.visible(tokens["agent"], "demo")
    authorizer.grant("agent", "demo", "reader")
    assert ledger.visible(tokens["agent"], "demo")
    with pytest.raises(Denied):
        propose(context, "No external write permission")
    # An external admin tuple cannot grant a locally read-only credential write access.
    authorizer.grant("reader", "demo", "admin")
    with pytest.raises(Denied):
        ledger.propose(
            tokens["reader"],
            "demo",
            subject="storage",
            predicate="database",
            value="forged",
            valid_from="2030-01-01T00:00:00Z",
        )
    # OPA and audience checks receive the effective role, so local admin cannot bypass FGA.
    authorizer.grant("operator", "demo", "approver")
    authorizer.grant("operator", "demo", "admin", remove=True)
    with pytest.raises(Denied):
        issue_credential(
            ledger.engine, tokens["admin"], "forged-admin", "demo", "admin", authorizer=authorizer
        )
    with pytest.raises(Denied):
        ledger.propose(
            tokens["admin"],
            "demo",
            subject="secret",
            predicate="policy",
            value="private",
            valid_from="2030-01-01T00:00:00Z",
            audience=["operator"],
        )
    incoming = ledger.propose(
        tokens["admin"],
        "demo",
        subject="storage",
        predicate="database",
        value="PostgreSQL",
        valid_from="2030-01-01T00:00:00Z",
    )
    head = ledger.preview(tokens["admin"], "demo", incoming["id"])["head_revision"]
    with pytest.raises(Denied):
        ledger.decide(
            tokens["admin"],
            "demo",
            incoming["id"],
            "approve",
            0,
            expected_head=head,
            protected=True,
            reason="external role is only approver",
        )


@pytest.mark.parametrize("payload", [{}, {"allowed": "true"}, [], {"allowed": 1}])
def test_malformed_fga_decisions_fail_closed(monkeypatch, payload):
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *a, **kw: httpx.Response(
            200, json=payload, request=httpx.Request("POST", "http://localhost/check")
        ),
    )
    authorizer = OpenFgaAuthorizer(
        "http://localhost:8080", "01ARZ3NDEKTSV4RRFFQ69G5FAV", "01ARZ3NDEKTSV4RRFFQ69G5FAW"
    )
    with pytest.raises(Denied):
        authorizer.check(Identity("operator", "demo", "admin"), "admin")


def test_incomplete_fga_configuration_is_never_silently_disabled(monkeypatch):
    for name in (
        "MEMORY_FGA_URL",
        "MEMORY_FGA_STORE_ID",
        "MEMORY_FGA_MODEL_ID",
        "MEMORY_FGA_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MEMORY_FGA_URL", "http://localhost:8080")
    with pytest.raises(ValueError, match="together"):
        Settings.from_env().authorizer()


@pytest.fixture
def collector():
    received, fail = [], [True]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(503 if fail[0] else 200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/api/v1/lineage", received, fail
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def validate_event(event):
    directory = Path(__file__).parent / "schemas"
    schemas = [json.loads(path.read_text(encoding="utf-8")) for path in directory.glob("*.json")]
    registry = Registry().with_resources(
        [(schema["$id"], Resource.from_contents(schema)) for schema in schemas]
    )
    validator = Draft202012Validator(
        {"$ref": event["schemaURL"]}, registry=registry, format_checker=FormatChecker()
    )
    validator.validate(event)
    for dataset in event["outputs"]:
        for facet in dataset.get("facets", {}).values():
            Draft202012Validator(
                {"$ref": facet["_schemaURL"]}, registry=registry, format_checker=FormatChecker()
            ).validate(facet)


def test_openlineage_real_http_retry_retains_ids_and_validates_offline(context, collector):
    ledger, _, tokens = context
    candidate = approve(context, propose(context, "PRIVATE-TEXT-MUST-NOT-LEAVE-LEDGER"))
    ledger.withdraw_source(tokens["admin"], "demo", candidate["source_id"])
    endpoint, received, fail = collector
    with Session(ledger.engine) as session:
        total = len(list(session.scalars(select(LineageEvent))))
    result = drain(ledger.engine, "demo", endpoint)
    assert result == {"completed": 0, "failed": total}
    first_ids = [item["run"]["runId"] for item in received]
    fail[0] = False
    assert drain(ledger.engine, "demo", endpoint) == {"completed": total, "failed": 0}
    assert [item["run"]["runId"] for item in received[total:]] == first_ids
    assert drain(ledger.engine, "demo", endpoint) == {"completed": 0, "failed": 0}
    assert "PRIVATE-TEXT" not in json.dumps(received)
    for event in received:
        validate_event(event)
    with Session(ledger.engine) as session:
        assert all(
            row.completed and row.attempts == 2 for row in session.scalars(select(LineageDelivery))
        )
