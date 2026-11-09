import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from governed_memory.db import create_db, initialize
from governed_memory.identity import bootstrap, issue_credential
from governed_memory.ledger import Ledger, instant


class Clock:
    def __init__(self):
        self.time = instant("2030-01-02T00:00:00Z")

    def __call__(self):
        return self.time

    def advance(self, days=1):
        self.time += timedelta(days=days)


@pytest.fixture(params=["sqlite", "postgres"])
def engine(request):
    if request.param == "sqlite":
        db = create_db("sqlite:///:memory:")
    else:
        url = os.environ.get("GM_TEST_DATABASE_URL")
        if not url:
            pytest.skip("set GM_TEST_DATABASE_URL to exercise a real PostgreSQL ledger")
        db = create_db(url)
        schema = "gm_test_" + uuid4().hex
        with db.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))

        @event.listens_for(db, "checkout")
        def isolate(connection, *_):
            with connection.cursor() as cursor:
                cursor.execute(f'SET search_path TO "{schema}"')
            connection.commit()

    initialize(db)
    yield db
    if request.param == "postgres":
        with db.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    db.dispose()


@pytest.fixture
def context(engine):
    clock = Clock()
    ledger = Ledger(engine, clock)
    admin = bootstrap(engine, "operator", "demo")
    agent = issue_credential(engine, admin, "agent", "demo", "agent")
    approver = issue_credential(engine, admin, "approver", "demo", "approver")
    reader = issue_credential(engine, admin, "reader", "demo", "reader")
    return ledger, clock, {"admin": admin, "agent": agent, "approver": approver, "reader": reader}


def propose(context, value="SQLite", **kwargs):
    ledger, _, tokens = context
    return ledger.propose(
        tokens["agent"],
        "demo",
        subject="storage",
        predicate="database",
        value=value,
        valid_from="2030-01-01T00:00:00Z",
        **kwargs,
    )


def approve(context, candidate, protected=False):
    ledger, clock, tokens = context
    clock.advance()
    head = ledger.preview(tokens["admin"], "demo", candidate["id"])["head_revision"]
    return ledger.decide(
        tokens["admin"],
        "demo",
        candidate["id"],
        "approve",
        0,
        reason="reviewed structured fixture",
        protected=protected,
        expected_head=head,
    )
