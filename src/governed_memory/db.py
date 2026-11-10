from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.pool import StaticPool

from governed_memory.constraints import protect_history
from governed_memory.models import Base


def create_db(url: str):
    options = {}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            options["poolclass"] = StaticPool
    engine = create_engine(url, **options)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def sqlite_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


TRANSITIONS = """
    (OLD.state = 'proposed' AND NEW.state IN ('active', 'rejected')) OR
    (OLD.state = 'active' AND NEW.state IN ('superseded', 'revoked')) OR
    (OLD.state = 'superseded' AND NEW.state = 'revoked')
"""

AUDIT_TABLES = (
    "governance_events",
    "source_events",
    "source_supports",
    "memory_dependencies",
    "entity_resolutions",
    "lineage_events",
)


def require_current_schema(engine):
    if not {
        "source_supports",
        "memory_dependencies",
        "entity_resolutions",
        "lineage_events",
        "lineage_deliveries",
    }.issubset(inspect(engine).get_table_names()):
        raise RuntimeError(
            "initialize an empty ledger with init, or run operator upgrade for existing data"
        )


def initialize(engine):
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        protect_history(conn, engine.dialect.name)
        if engine.dialect.name == "sqlite":
            conn.execute(
                text(f"""
                CREATE TRIGGER IF NOT EXISTS legal_candidate_transition
                BEFORE UPDATE OF state ON candidates
                WHEN NEW.state <> OLD.state AND NOT ({TRANSITIONS})
                BEGIN SELECT RAISE(ABORT, 'illegal lifecycle transition'); END
            """)
            )
            for table in AUDIT_TABLES:
                for operation in ("UPDATE", "DELETE"):
                    conn.execute(
                        text(f"""
                        CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT, 'append-only audit log'); END
                    """)
                    )
        elif engine.dialect.name == "postgresql":
            conn.execute(
                text(f"""
                CREATE OR REPLACE FUNCTION check_candidate_transition() RETURNS trigger AS $$
                BEGIN
                    IF NEW.state <> OLD.state AND NOT ({TRANSITIONS}) THEN
                        RAISE EXCEPTION 'illegal lifecycle transition';
                    END IF;
                    RETURN NEW;
                END; $$ LANGUAGE plpgsql
            """)
            )
            conn.execute(text("DROP TRIGGER IF EXISTS legal_candidate_transition ON candidates"))
            conn.execute(
                text("""
                CREATE TRIGGER legal_candidate_transition BEFORE UPDATE ON candidates
                FOR EACH ROW EXECUTE FUNCTION check_candidate_transition()
            """)
            )
            conn.execute(
                text("""
                CREATE OR REPLACE FUNCTION immutable_audit() RETURNS trigger AS $$
                BEGIN RAISE EXCEPTION 'append-only audit log'; END; $$ LANGUAGE plpgsql
            """)
            )
            for table in AUDIT_TABLES:
                conn.execute(text(f"DROP TRIGGER IF EXISTS immutable_audit ON {table}"))
                conn.execute(
                    text(f"""
                    CREATE TRIGGER immutable_audit BEFORE UPDATE OR DELETE ON {table}
                    FOR EACH ROW EXECUTE FUNCTION immutable_audit()
                """)
                )
