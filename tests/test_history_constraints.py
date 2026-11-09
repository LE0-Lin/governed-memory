import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from .conftest import approve, propose


@pytest.mark.parametrize(
    "query",
    [
        "UPDATE candidates SET value='unreviewed replacement'",
        "UPDATE fact_versions SET text='unreviewed replacement'",
        "UPDATE sources SET body='unreviewed replacement'",
        "DELETE FROM fact_versions",
    ],
)
def test_database_cannot_silently_rewrite_approved_history(context, query):
    ledger, _, tokens = context
    approve(context, propose(context))
    with pytest.raises(DatabaseError), ledger.engine.begin() as conn:
        conn.execute(text(query))
    assert ledger.visible(tokens["agent"], "demo")[0].value == "SQLite"
