"""Verify and launch independently installed MCP wheels for the system study."""

import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tomllib
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REFERENCE = "5f05cc716cd649bc43378a038c998cb150480b05"


def verify_unchanged_runtime(commit):
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", REFERENCE, commit, "--", "src", "native/src"], text=True
    ).strip()
    if changed:
        raise ValueError(f"the retained-runtime baseline has changed production source: {changed}")
    return True


def verify_runtime(target, commit):
    target = target.resolve()
    paths = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", commit, "--", "src/governed_memory"],
        text=True,
    ).splitlines()
    for path in paths:
        expected = subprocess.check_output(["git", "show", f"{commit}:{path}"])
        installed = (target / path.removeprefix("src/")).read_bytes()
        if installed.replace(b"\r\n", b"\n") != expected.replace(b"\r\n", b"\n"):
            raise ValueError(f"installed runtime differs from {commit}: {path}")
    probe = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import json,governed_memory,importlib.metadata; "
            "print(json.dumps({'version':importlib.metadata.version('governed-memory'),"
            "'module':governed_memory.__file__}))",
        ],
        env={**os.environ, "PYTHONPATH": str(target)},
        text=True,
    )
    metadata = json.loads(probe)
    if not Path(metadata["module"]).resolve().is_relative_to(target):
        raise ValueError("MCP runtime would import an unintended installation")
    specification = subprocess.check_output(["git", "show", f"{commit}:pyproject.toml"])
    if metadata["version"] != tomllib.loads(specification.decode())["project"]["version"]:
        raise ValueError("installed package version differs from its frozen source")
    metadata.update(source_commit=commit, verified_runtime_files=len(paths))
    return metadata


@asynccontextmanager
async def mcp_session(target, database_url, token, authorizer, log):
    # Do not inherit unrelated model/policy/credential overrides from the caller.
    env = {key: value for key, value in os.environ.items() if not key.startswith("MEMORY_")}
    env.update(
        PYTHONPATH=str(target),
        MEMORY_DATABASE_URL=database_url,
        MEMORY_TOKEN=token,
        MEMORY_NEO4J_URI=os.environ["GM_EVAL_NEO4J_URI"],
        MEMORY_NEO4J_PASSWORD=os.environ["GM_EVAL_NEO4J_PASSWORD"],
        MEMORY_FGA_URL=authorizer.endpoint,
        MEMORY_FGA_STORE_ID=authorizer.store_id,
        MEMORY_FGA_MODEL_ID=authorizer.model_id,
        MEMORY_OPA_URL=os.environ["GM_EVAL_OPA_URL"],
        MEMORY_LOCAL_EMBEDDING="1",
        MEMORY_LOCAL_RERANKER="1",
        MEMORY_DOCUMENT_CACHE_SIZE="2048",
        MEMORY_RERANK_CACHE_SIZE="8192",
        MEMORY_RELEVANCE_FILTER="0",
        MEMORY_RANKING_BACKEND="rust",
        MEMORY_MODEL_CACHE=os.environ["MEMORY_MODEL_CACHE"],
        HF_HUB_OFFLINE="1",
        HF_HUB_DISABLE_PROGRESS_BARS="1",
        GRAPHITI_TELEMETRY_ENABLED="false",
    )
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "governed_memory.cli", "serve"], env=env
    )
    started = perf_counter()
    with log.open("w", encoding="utf-8") as errors:
        async with (
            stdio_client(params, errlog=errors) as streams,
            ClientSession(*streams) as session,
        ):
            await session.initialize()
            yield session, (perf_counter() - started) * 1000


def dependency_versions():
    return {
        name: importlib.metadata.version(name)
        for name in (
            "torch",
            "transformers",
            "sentence-transformers",
            "numpy",
            "sqlalchemy",
            "httpx",
            "mcp",
            "graphiti-core",
            "governed-memory-native",
        )
    }


def wheel_identity(directory):
    wheels = list(directory.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("require exactly one wheel per frozen runtime")
    return {"name": wheels[0].name, "sha256": hashlib.sha256(wheels[0].read_bytes()).hexdigest()}
