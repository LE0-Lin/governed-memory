"""Opt-in deployment checks against a real PostgreSQL/Neo4j/OPA test stack."""

import asyncio
import json
import os
import re
import subprocess
from dataclasses import dataclass, replace
from uuid import uuid4

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy import text

from governed_memory.graph_adapter import GraphProjection

from .conftest import approve

pytestmark = pytest.mark.integration


@dataclass
class Container:
    docker: list[str]
    image: str
    environment: dict[str, str]
    mounts: tuple[str, ...] = ()

    def process_env(self, token=""):
        environment = {**os.environ, **self.environment, "MEMORY_TOKEN": token}
        if self.docker[0].lower() in {"wsl", "wsl.exe"}:
            names = [*self.environment, "MEMORY_TOKEN"]
            environment["WSLENV"] = ":".join(filter(None, [environment.get("WSLENV", ""), *names]))
        return environment

    def arguments(self, *arguments, interactive=False, entrypoint=None, image=None):
        command = [
            *self.docker,
            "run",
            "--rm",
            "--network=host",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--tmpfs=/tmp:noexec,nosuid,size=128m",
        ]
        if interactive:
            command.append("-i")
        for mount in self.mounts:
            command.extend(["--mount", mount])
        for key in [*self.environment, "MEMORY_TOKEN"]:
            command.extend(["--env", key])
        if entrypoint:
            command.extend(["--entrypoint", entrypoint])
        return [*command, image or self.image, *arguments]

    def invoke(self, *arguments, token="", input_data=None, **options):
        return subprocess.run(
            self.arguments(*arguments, interactive=input_data is not None, **options),
            env=self.process_env(token),
            input=input_data,
            capture_output=True,
            check=False,
        )

    def cli(self, *arguments, token="", **options):
        response = self.invoke(*arguments, token=token, **options)
        assert response.returncode == 0, response.stderr.decode(errors="replace")
        return json.loads(response.stdout)

    def server(self, token):
        command = self.arguments("serve", interactive=True)
        return StdioServerParameters(
            command=command[0], args=command[1:], env=self.process_env(token)
        )


async def clear_project(graph, project):
    await graph.graph.driver.execute_query(
        "MATCH (n:Entity) WHERE n.group_id=$project DETACH DELETE n", project=project
    )


async def test_container_permissions_persistence_backup_and_withdrawal(engine):
    image = os.environ.get("GM_TEST_CONTAINER_IMAGE")
    if not image:
        pytest.skip("set GM_TEST_CONTAINER_IMAGE after building the runtime image")
    if engine.dialect.name != "postgresql":
        pytest.skip("the deployment/backup check requires the real PostgreSQL test stack")
    with engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    assert re.fullmatch(r"gm_test_[0-9a-f]{32}", schema)
    url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    project = "deployment-" + uuid4().hex
    recovery_database = "gm_recovery_" + uuid4().hex
    docker = json.loads(os.environ.get("GM_TEST_DOCKER_COMMAND", '["docker"]'))
    container = Container(
        docker,
        image,
        {
            "MEMORY_DATABASE_URL": url.render_as_string(hide_password=False),
            "MEMORY_NEO4J_URI": os.environ["GM_TEST_NEO4J_URI"],
            "MEMORY_NEO4J_PASSWORD": os.environ["GM_TEST_NEO4J_PASSWORD"],
            "MEMORY_OPA_URL": os.environ.get("GM_TEST_OPA_URL", ""),
            "PGPASSWORD": url.password,
        },
    )
    graph = GraphProjection(
        os.environ["GM_TEST_NEO4J_URI"], "neo4j", os.environ["GM_TEST_NEO4J_PASSWORD"]
    )
    created_database = False
    try:
        probe = container.invoke(
            "-c",
            "import json,os,governed_memory_native; print(json.dumps({'uid':os.getuid(), "
            "'readonly':bool(os.statvfs('/').f_flag & os.ST_RDONLY)}))",
            entrypoint="python",
        )
        assert probe.returncode == 0, probe.stderr.decode(errors="replace")
        assert json.loads(probe.stdout) == {"uid": 10001, "readonly": True}
        admin = container.cli("init", "--project", project)["admin_token"]
        agent = container.cli(
            "credential",
            "--project",
            project,
            "--principal",
            "agent",
            "--role",
            "agent",
            token=admin,
        )["token"]
        async with (
            stdio_client(container.server(agent)) as streams,
            ClientSession(*streams) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "propose_memory",
                "search_memory",
                "explain_memory",
            }
            response = await session.call_tool(
                "propose_memory",
                {
                    "project": project,
                    "subject": "storage",
                    "predicate": "database",
                    "value": "SQLite",
                    "valid_from": "2020-01-01T00:00:00Z",
                },
            )
            assert not response.isError
            candidate = json.loads(response.content[0].text)
        preview = container.cli("preview", "--project", project, candidate["id"], token=admin)
        arguments = (
            "approve",
            "--project",
            project,
            candidate["id"],
            "--expected-revision",
            str(preview["revision"]),
            "--expected-head",
            str(preview["head_revision"]),
            "--reason",
            "deployment fixture",
        )
        assert container.invoke(*arguments, token=agent).returncode != 0
        container.cli(*arguments, token=admin)
        assert container.cli("project", "--project", project, token=admin)["failed"] == 0

        # Export this isolated schema only; never dump other projects in the test server.
        dump = container.invoke(
            "pg_dump",
            "--host",
            url.host,
            "--port",
            str(url.port or 5432),
            "--username",
            url.username,
            "--dbname",
            url.database,
            "--format=custom",
            "--schema",
            schema,
            image="postgres:17.6",
        )
        assert dump.returncode == 0, dump.stderr.decode(errors="replace")
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(f'CREATE DATABASE "{recovery_database}"'))
            created_database = True
        restored = container.invoke(
            "pg_restore",
            "--host",
            url.host,
            "--port",
            str(url.port or 5432),
            "--username",
            url.username,
            "--dbname",
            recovery_database,
            "--no-owner",
            "--no-acl",
            image="postgres:17.6",
            input_data=dump.stdout,
        )
        assert restored.returncode == 0, restored.stderr.decode(errors="replace")
        recovered = replace(
            container,
            environment={
                **container.environment,
                "MEMORY_DATABASE_URL": url.set(database=recovery_database).render_as_string(
                    hide_password=False
                ),
            },
        )
        await clear_project(graph, project)
        assert (
            recovered.cli("project", "--project", project, "--rebuild", token=admin)["failed"] == 0
        )
        async with (
            stdio_client(recovered.server(agent)) as streams,
            ClientSession(*streams) as session,
        ):
            await session.initialize()
            for _attempt in range(20):
                response = await session.call_tool(
                    "search_memory", {"project": project, "query": "database"}
                )
                assert not response.isError
                result = json.loads(response.content[0].text)
                if result["backend"].startswith("graphiti"):
                    break
                await asyncio.sleep(0.5)
            assert result["backend"].startswith("graphiti")
            assert result["evidence"][0]["value"] == "SQLite"
            await asyncio.to_thread(
                recovered.cli,
                "withdraw-source",
                "--project",
                project,
                candidate["source_id"],
                token=admin,
            )
            response = await session.call_tool(
                "search_memory", {"project": project, "query": "database"}
            )
            assert not json.loads(response.content[0].text)["evidence"]
    finally:
        await clear_project(graph, project)
        await graph.close()
        if created_database:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                connection.execute(text(f'DROP DATABASE "{recovery_database}"'))


async def test_model_container_filters_empty_answers_and_rechecks_a_warm_mcp_session(context):
    image = os.environ.get("GM_TEST_GENERATION_IMAGE")
    cache = os.environ.get("GM_TEST_MODEL_CACHE_MOUNT")
    if not image or not cache:
        pytest.skip("configure the model image and retrieval-model cache mount")
    ledger, _, tokens = context
    engine = ledger.engine
    if engine.dialect.name != "postgresql":
        pytest.skip("the deployed MCP process requires the PostgreSQL test stack")
    with engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    assert re.fullmatch(r"gm_test_[0-9a-f]{32}", schema)
    url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    candidate = approve(
        context,
        ledger.propose(
            tokens["agent"],
            "demo",
            subject="Berlin",
            predicate="museums",
            value="Berlin is well known for its museums.",
            valid_from="2030-01-01T00:00:00Z",
        ),
    )
    container = Container(
        json.loads(os.environ.get("GM_TEST_DOCKER_COMMAND", '["docker"]')),
        image,
        {
            "MEMORY_DATABASE_URL": url.render_as_string(hide_password=False),
            "MEMORY_LOCAL_EMBEDDING": "1",
            "MEMORY_LOCAL_RERANKER": "1",
            "MEMORY_RELEVANCE_FILTER": "1",
            "MEMORY_DOCUMENT_CACHE_SIZE": "8",
            "MEMORY_MODEL_CACHE": "/retrieval",
            "MEMORY_GENERATION_PROFILE": "small",
            "MEMORY_GENERATION_CACHE": "/intentionally-missing-generator",
            "HF_HUB_OFFLINE": "1",
            "HF_HUB_DISABLE_PROGRESS_BARS": "1",
        },
        mounts=(f"type=bind,source={cache},target=/retrieval,readonly",),
    )
    arguments = dict(
        project="demo", valid_at="2030-02-01T00:00:00Z", known_at="2030-02-01T00:00:00Z"
    )
    async with (
        stdio_client(container.server(tokens["agent"])) as streams,
        ClientSession(*streams) as session,
    ):
        await session.initialize()
        response = await session.call_tool(
            "answer_memory", {**arguments, "query": "How many people live in Berlin?"}
        )
        assert not response.isError
        empty = json.loads(response.content[0].text)
        assert empty["abstain"] and empty["reason"] == "no_relevant_evidence"
        assert empty["generation"] is None and empty["evidence"] == []
        for _ in range(2):
            response = await session.call_tool(
                "search_memory", {**arguments, "query": "What is Berlin well known for?"}
            )
            assert not response.isError
            result = json.loads(response.content[0].text)
            assert result["minimum_relevance_score"] == 1.4 and result["document_cache"]
            assert [item["candidate_id"] for item in result["evidence"]] == [candidate["id"]]
        ledger.withdraw_source(tokens["admin"], "demo", candidate["source_id"])
        response = await session.call_tool(
            "search_memory", {**arguments, "query": "What is Berlin well known for?"}
        )
        assert not response.isError
        result = json.loads(response.content[0].text)
        assert result["reason"] == "no_eligible_evidence" and result["evidence"] == []


def test_container_cli_answers_with_the_real_cpu_model_and_honors_withdrawal(engine):
    image = os.environ.get("GM_TEST_GENERATION_IMAGE")
    cache = os.environ.get("GM_TEST_GENERATION_CACHE_MOUNT")
    if not image or not cache:
        pytest.skip("set GM_TEST_GENERATION_IMAGE and GM_TEST_GENERATION_CACHE_MOUNT")
    if engine.dialect.name != "postgresql":
        pytest.skip("the container CLI requires the real PostgreSQL test stack")
    with engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    assert re.fullmatch(r"gm_test_[0-9a-f]{32}", schema)
    url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    project = "generation-" + uuid4().hex
    container = Container(
        json.loads(os.environ.get("GM_TEST_DOCKER_COMMAND", '["docker"]')),
        image,
        {
            "MEMORY_DATABASE_URL": url.render_as_string(hide_password=False),
            "MEMORY_GENERATION_PROFILE": "small",
            "MEMORY_GENERATION_CACHE": "/models",
            "HF_HUB_OFFLINE": "1",
            "HF_HUB_DISABLE_PROGRESS_BARS": "1",
        },
        mounts=(f"type=bind,source={cache},target=/models,readonly",),
    )
    runtime = container.cli(
        "-c",
        "import json,torch; print(json.dumps({'cuda': torch.version.cuda}))",
        entrypoint="python",
    )
    assert runtime["cuda"] is None
    admin = container.cli("init", "--project", project)["admin_token"]
    agent = container.cli(
        "credential", "--project", project, "--principal", "agent", "--role", "agent", token=admin
    )["token"]
    candidate = container.cli("ingest", "--project", project, "examples/decision.md", token=admin)[
        0
    ]
    preview = container.cli("preview", "--project", project, candidate["id"], token=admin)
    container.cli(
        "approve",
        "--project",
        project,
        candidate["id"],
        "--expected-revision",
        str(preview["revision"]),
        "--expected-head",
        str(preview["head_revision"]),
        "--reason",
        "synthetic deployment fixture",
        token=admin,
    )
    arguments = (
        "answer",
        "--project",
        project,
        "Which database is used for storage?",
        "--valid-at",
        "2030-11-09T00:00:00Z",
    )
    response = container.cli(*arguments, token=agent)
    assert response["reason"] == "ok"
    assert "postgresql" in response["answer"].lower()
    assert response["evidence_ids"] == [response["evidence"][0]["id"]]
    assert response["evidence"][0]["candidate_id"] == candidate["id"]
    assert response["generator"]["device"] == "cpu"
    container.cli("withdraw-source", "--project", project, candidate["source_id"], token=admin)
    withdrawn = container.cli(*arguments, token=agent)
    assert withdrawn["reason"] == "no_eligible_evidence" and withdrawn["abstain"]
    assert withdrawn["evidence"] == withdrawn["evidence_ids"] == []
    assert withdrawn["generation"] is None


def test_container_semantic_operator_workflow_preserves_approval_boundary(engine):
    image = os.environ.get("GM_TEST_GENERATION_IMAGE")
    generation_cache = os.environ.get("GM_TEST_GENERATION_CACHE_MOUNT")
    model_cache = os.environ.get("GM_TEST_MODEL_CACHE_MOUNT")
    if not image or not generation_cache or not model_cache:
        pytest.skip("configure the model image and both model-cache mounts")
    if engine.dialect.name != "postgresql":
        pytest.skip("the semantic CLI deployment check requires PostgreSQL")
    with engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    assert re.fullmatch(r"gm_test_[0-9a-f]{32}", schema)
    url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    project = "semantic-" + uuid4().hex
    container = Container(
        json.loads(os.environ.get("GM_TEST_DOCKER_COMMAND", '["docker"]')),
        image,
        {
            "MEMORY_DATABASE_URL": url.render_as_string(hide_password=False),
            "MEMORY_GENERATION_PROFILE": "small",
            "MEMORY_GENERATION_CACHE": "/generation",
            "MEMORY_LOCAL_EMBEDDING": "1",
            "MEMORY_MODEL_CACHE": "/retrieval",
            "MEMORY_RANKING_BACKEND": "rust",
            "HF_HUB_OFFLINE": "1",
            "HF_HUB_DISABLE_PROGRESS_BARS": "1",
        },
        mounts=(
            f"type=bind,source={generation_cache},target=/generation,readonly",
            f"type=bind,source={model_cache},target=/retrieval,readonly",
        ),
    )
    admin = container.cli("init", "--project", project)["admin_token"]
    agent = container.cli(
        "credential", "--project", project, "--principal", "agent", "--role", "agent", token=admin
    )["token"]
    # The source is written inside the permitted tmpfs, then consumed by the real CLI.
    program = (
        "import pathlib,subprocess,sys; "
        "pathlib.Path('/tmp/session.txt').write_text("
        "'Atlas uses PostgreSQL for persistent storage.'); "
        "sys.stdout.write(subprocess.check_output(['governed-memory','ingest-document',"
        f"'--project','{project}','/tmp/session.txt',"
        "'--valid-from','2030-01-01T00:00:00Z'],text=True))"
    )
    staged = container.cli("-c", program, entrypoint="python", token=agent)["candidates"]
    assert staged
    candidate = staged[0]
    search = ("search", "--project", project, "Atlas storage", "--valid-at", "2030-02-01T00:00:00Z")
    assert not container.cli(*search, token=agent)["evidence"]
    preview = container.cli("preview", "--project", project, candidate["id"], token=admin)
    container.cli(
        "approve",
        "--project",
        project,
        candidate["id"],
        "--expected-revision",
        "0",
        "--expected-head",
        str(preview["head_revision"]),
        "--reason",
        "synthetic source fixture",
        token=admin,
    )
    response = container.cli(*search, token=agent)
    assert response["ranking_engine"] == "rust"
    snapshot = response["evidence"][0]["id"]
    derived = container.cli(
        "derive",
        "--project",
        project,
        "--subject",
        "Atlas rollout",
        "--predicate",
        "decision",
        "--value",
        "Use the approved storage",
        "--valid-from",
        "2030-01-01T00:00:00Z",
        "--parent",
        snapshot,
        "--locator",
        "fixture:rollout",
        token=agent,
    )
    review = container.cli("review", "--project", project, derived["id"], token=admin)
    assert review["advisory"] and review["nli"]["language"] == "English"
    resolved = container.cli(
        "resolve-entity",
        "--project",
        project,
        derived["id"],
        "--target",
        snapshot,
        "--expected-revision",
        "0",
        "--reason",
        "synthetic canonical entity",
        token=admin,
    )
    assert resolved["replacement"]["state"] == "proposed"
    assert resolved["replacement"]["subject"] == candidate["subject"]
    container.cli("withdraw-source", "--project", project, candidate["source_id"], token=admin)
    assert not container.cli(*search, token=agent)["evidence"]
