"""Exercise the real old/new installed images, without importing host ledger code there."""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from governed_memory.graph_adapter import GraphProjection
from governed_memory.models import Candidate, FactVersion, GovernanceEvent, LineageEvent, Source

from .test_container_deployment import Container, clear_project


@pytest.mark.integration
async def test_installed_v06_upgrade_repairs_only_the_selected_project(engine):
    previous = os.environ.get("GM_TEST_PREVIOUS_IMAGE")
    current = os.environ.get("GM_TEST_CONTAINER_IMAGE")
    if not previous or not current:
        pytest.skip("configure previous v0.6.0 and current installed core images")
    if engine.dialect.name != "postgresql":
        pytest.skip("installed upgrade verification uses the real PostgreSQL/Neo4j stack")
    with engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    project = "upgrade-" + uuid4().hex
    old = Container(
        json.loads(os.environ.get("GM_TEST_DOCKER_COMMAND", '["docker"]')),
        previous,
        {
            "MEMORY_DATABASE_URL": url.render_as_string(hide_password=False),
            "MEMORY_NEO4J_URI": os.environ["GM_TEST_NEO4J_URI"],
            "MEMORY_NEO4J_PASSWORD": os.environ["GM_TEST_NEO4J_PASSWORD"],
            "MEMORY_OPA_URL": os.environ.get("GM_TEST_OPA_URL", ""),
            "GM_UPGRADE_PROJECT": project,
        },
    )
    new = Container(old.docker, current, old.environment)
    graph = GraphProjection(
        os.environ["GM_TEST_NEO4J_URI"], "neo4j", os.environ["GM_TEST_NEO4J_PASSWORD"]
    )
    try:
        fixture = Path(__file__).with_name("fixtures") / "v06_support_revocation.py"
        result = old.invoke("-", input_data=fixture.read_bytes(), entrypoint="python")
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        legacy = json.loads(result.stdout)
        target, other = legacy["projects"][project], legacy["projects"][project + "-other"]
        records, _, _ = await graph.graph.driver.execute_query(
            "MATCH ()-[e:RELATES_TO]->() WHERE e.group_id=$project RETURN count(e) AS n",
            project=project,
        )
        assert records[0]["n"] == 3  # Stale descendants plus the independent fact.
        with Session(engine) as session:
            audit_before = {
                event.id: (event.action, event.revision, event.reason)
                for event in session.scalars(select(GovernanceEvent))
            }
            lineage_before = {
                event.id: event.payload for event in session.scalars(select(LineageEvent))
            }
            sources_before = {
                source.id: source.content_hash for source in session.scalars(select(Source))
            }
        assert new.invoke("upgrade", "--project", project, token=legacy["agent"]).returncode != 0
        upgrade = new.cli("upgrade", "--project", project, token=legacy["admin"])
        assert upgrade == {"schema": "current", "project": project, "dependency_repairs": 3}
        assert (
            new.cli("upgrade", "--project", project, token=legacy["admin"])["dependency_repairs"]
            == 0
        )
        with Session(engine) as session:
            for name in ("child", "grandchild"):
                assert session.get(Candidate, target[name]).state == "revoked"
                assert session.get(Candidate, other[name]).state == "active"
            assert session.get(Candidate, target["pending"]).state == "rejected"
            assert session.get(Candidate, other["pending"]).state == "proposed"
            assert session.get(Candidate, target["unrelated"]).state == "active"
            assert all(
                (
                    session.get(GovernanceEvent, identifier).action,
                    session.get(GovernanceEvent, identifier).revision,
                    session.get(GovernanceEvent, identifier).reason,
                )
                == payload
                for identifier, payload in audit_before.items()
            )
            assert all(
                session.get(LineageEvent, identifier).payload == payload
                for identifier, payload in lineage_before.items()
            )
            assert {
                source.id: source.content_hash for source in session.scalars(select(Source))
            } == sources_before
        assert new.cli("project", "--project", project, token=legacy["admin"]) == {
            "projected": 2,
            "failed": 0,
        }
        records, _, _ = await graph.graph.driver.execute_query(
            "MATCH ()-[e:RELATES_TO]->() WHERE e.group_id=$project RETURN e.uuid AS id",
            project=project,
        )
        with Session(engine) as session:
            surviving = session.scalar(
                select(FactVersion.id).where(FactVersion.candidate_id == target["unrelated"])
            )
        assert [record["id"] for record in records] == [surviving]
        assert (
            new.cli("upgrade", "--project", project + "-other", token=legacy["admin"])[
                "dependency_repairs"
            ]
            == 3
        )
    finally:
        await clear_project(graph, project)
        await clear_project(graph, project + "-other")
        await graph.close()
