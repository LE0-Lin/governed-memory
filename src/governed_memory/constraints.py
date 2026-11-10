"""Database checks supplement the service's authorization and transition checks."""

from sqlalchemy import text


def protect_history(conn, dialect):
    columns = {
        "candidates": [
            "id",
            "fact_id",
            "project",
            "source_id",
            "proposer",
            "subject",
            "predicate",
            "value",
            "fragment",
            "valid_from",
            "valid_until",
            "proposed_at",
        ],
        "fact_versions": [
            "id",
            "candidate_id",
            "fact_id",
            "project",
            "source_id",
            "text",
            "valid_from",
            "valid_until",
            "system_from",
        ],
        "sources": ["id", "project", "locator", "content_hash", "body", "created_at"],
    }
    operator = "IS NOT" if dialect == "sqlite" else "IS DISTINCT FROM"
    for table, fields in columns.items():
        changes = " OR ".join(f"OLD.{field} {operator} NEW.{field}" for field in fields)
        if table == "fact_versions":
            changes += (
                " OR (OLD.system_until IS NOT NULL AND "
                f"OLD.system_until {operator} NEW.system_until)"
            )
        if table == "candidates":
            changes += " OR (OLD.protected AND NOT NEW.protected)"
            changes += " OR (OLD.state <> NEW.state AND NEW.revision <> OLD.revision + 1)"
        if table == "sources":
            changes += (
                f" OR (OLD.revoked_at IS NOT NULL AND OLD.revoked_at {operator} NEW.revoked_at)"
            )
        if dialect == "sqlite":
            conn.execute(
                text(f"""
                CREATE TRIGGER IF NOT EXISTS preserve_{table} BEFORE UPDATE ON {table}
                WHEN {changes}
                BEGIN SELECT RAISE(ABORT, 'immutable ledger history'); END
            """)
            )
            conn.execute(
                text(f"""
                CREATE TRIGGER IF NOT EXISTS preserve_{table}_delete BEFORE DELETE ON {table}
                BEGIN SELECT RAISE(ABORT, 'immutable ledger history'); END
            """)
            )
        else:
            conn.execute(
                text(f"""
                CREATE OR REPLACE FUNCTION preserve_{table}() RETURNS trigger AS $$
                BEGIN
                    IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'immutable ledger history'; END IF;
                    IF {changes} THEN RAISE EXCEPTION 'immutable ledger history'; END IF;
                    RETURN NEW;
                END; $$ LANGUAGE plpgsql
            """)
            )
            conn.execute(text(f"DROP TRIGGER IF EXISTS preserve_{table} ON {table}"))
            conn.execute(
                text(f"""
                CREATE TRIGGER preserve_{table} BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION preserve_{table}()
            """)
            )
