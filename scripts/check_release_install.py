"""Install a built core wheel and verify its real CLI/MCP user journey."""

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from email.parser import BytesParser
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


def run(command, *, cwd, env, expected_success=True):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, encoding="utf-8")
    if expected_success and result.returncode:
        raise RuntimeError(f"release command failed ({result.returncode}): {result.stderr}")
    if not expected_success and result.returncode == 0:
        raise AssertionError("an agent unexpectedly completed an operator-only command")
    return result.stdout


async def persistent_journey(python, cwd, env):
    def cli(*arguments, token=None, expected_success=True):
        output = run(
            [str(python), "-I", "-m", "governed_memory.cli", *arguments],
            cwd=cwd,
            env={**env, "MEMORY_TOKEN": token or ""},
            expected_success=expected_success,
        )
        return json.loads(output) if expected_success else None

    async def call(session, tool, arguments):
        response = await session.call_tool(tool, arguments)
        assert not response.isError, f"installed MCP tool failed: {tool}"
        return json.loads(response.content[0].text)

    admin = cli("init", "--project", "demo")["admin_token"]
    agent = cli(
        "credential",
        "--project",
        "demo",
        "--principal",
        "coding-agent",
        "--role",
        "agent",
        token=admin,
    )["token"]
    params = StdioServerParameters(
        command=str(python),
        args=["-I", "-m", "governed_memory.cli", "serve"],
        env={**env, "MEMORY_TOKEN": agent},
        cwd=str(cwd),
    )
    query = {"project": "demo", "query": "storage database"}
    async with stdio_client(params) as streams, ClientSession(*streams) as session:
        await session.initialize()
        tools = await session.list_tools()
        assert {tool.name for tool in tools.tools} == {
            "propose_memory",
            "search_memory",
            "explain_memory",
        }
        candidate = await call(
            session,
            "propose_memory",
            {
                "project": "demo",
                "subject": "storage",
                "predicate": "database",
                "value": "PostgreSQL",
                "valid_from": "2020-01-01T00:00:00Z",
            },
        )
        assert not (await call(session, "search_memory", query))["evidence"]
        preview = cli("preview", "--project", "demo", candidate["id"], token=admin)
        approval = (
            "approve",
            "--project",
            "demo",
            candidate["id"],
            "--expected-revision",
            str(preview["revision"]),
            "--expected-head",
            str(preview["head_revision"]),
            "--reason",
            "release fixture review",
        )
        cli(*approval, token=agent, expected_success=False)
        assert not (await call(session, "search_memory", query))["evidence"]
        cli(*approval, token=admin)
        result = await call(session, "search_memory", query)
        assert [item["value"] for item in result["evidence"]] == ["PostgreSQL"]
        assert result["evidence"][0]["locator"] and result["evidence"][0]["content_hash"]
    # A fresh server proves persistence; withdrawal is then observed by that warm server.
    async with stdio_client(params) as streams, ClientSession(*streams) as session:
        await session.initialize()
        result = await call(session, "search_memory", query)
        assert [item["candidate_id"] for item in result["evidence"]] == [candidate["id"]]
        cli("withdraw-source", "--project", "demo", candidate["source_id"], token=admin)
        result = await call(session, "search_memory", query)
        assert result["evidence"] == [] and result["reason"] == "no_eligible_evidence"
    return [
        "unapproved proposal hidden",
        "agent self-approval denied",
        "operator approval visible",
        "source provenance",
        "fresh-process persistence",
        "warm-process source withdrawal",
    ]


def verify(args):
    wheels = list(args.dist.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("release verification requires exactly one built core wheel")
    wheel = wheels[0].resolve()
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "governed_memory/demo.py" in names
        assert "governed_memory/data/cl100k_base.tiktoken" in names
        metadata = next(name for name in names if name.endswith(".dist-info/METADATA"))
        expected_version = BytesParser().parsebytes(archive.read(metadata))["Version"]
    sources = list(args.dist.glob("*.tar.gz"))
    if len(sources) != 1:
        raise ValueError("release verification requires one source distribution")
    with tarfile.open(sources[0]) as archive:
        source_names = archive.getnames()
        for name in source_names:
            parts = Path(name).parts
            assert not {".local", ".venv", ".env", "__pycache__"}.intersection(parts), name
            assert not name.endswith((".db", ".safetensors", ".gguf")), name
    # Only this freshly created, explicitly checked temp directory is removed.
    temp_parent = Path(tempfile.gettempdir()).resolve()
    with tempfile.TemporaryDirectory(prefix="gm-release-") as temporary:
        work = Path(temporary).resolve()
        assert work.parent == temp_parent and work.name.startswith("gm-release-")
        assert not work.is_relative_to(ROOT)
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("MEMORY_", "GM_", "PYTHONPATH"))
        }
        environment.update(
            MEMORY_DATABASE_URL="sqlite:///" + (work / "memory.db").as_posix(),
            GRAPHITI_TELEMETRY_ENABLED="false",
            HF_HUB_OFFLINE="1",
        )
        run(
            ["uv", "venv", "--python", sys.executable, str(work / "env")], cwd=work, env=environment
        )
        python = work / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        install = [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--constraints",
            str(args.constraints.resolve()),
            str(wheel),
        ]
        if args.offline:
            install.append("--offline")
        run(install, cwd=work, env=environment)
        probe = json.loads(
            run(
                [
                    str(python),
                    "-I",
                    "-c",
                    "import json,importlib.util,importlib.metadata,governed_memory; "
                    "print(json.dumps({'version':importlib.metadata.version('governed-memory'),"
                    "'module':governed_memory.__file__,"
                    "'torch':importlib.util.find_spec('torch') is not None}))",
                ],
                cwd=work,
                env=environment,
            )
        )
        assert probe["version"] == expected_version and not probe["torch"]
        assert Path(probe["module"]).resolve().is_relative_to(work / "env")
        reported = run(
            [str(python), "-I", "-m", "governed_memory.cli", "--version"], cwd=work, env=environment
        )
        assert reported.strip() == f"governed-memory {expected_version}"
        demo = run(
            [str(python), "-I", str(ROOT / "scripts/check_offline_demo.py")],
            cwd=work,
            env=environment,
        )
        lines = demo.splitlines()
        assert lines[-1] == "Offline example passed with external network access denied."
        examples = [json.loads(line) for line in lines[:-1]]
        assert len(examples) == 6 and examples[-1]["withdrawn_evidence_visible"] is False
        assert not (work / "memory.db").exists()
        checks = asyncio.run(persistent_journey(python, work, environment))
    return {
        "version": expected_version,
        "python": sys.version,
        "platform": sys.platform,
        "wheel": wheel.name,
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "constraints_sha256": hashlib.sha256(args.constraints.read_bytes()).hexdigest(),
        "outside_checkout": True,
        "isolated_interpreter": True,
        "core_has_torch": False,
        "source_archive_excludes_private_state": True,
        "offline_packaged_demo": True,
        "demo_did_not_create_live_database": True,
        "persistent_mcp_checks": checks,
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--constraints", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    receipt = verify(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt, indent=2))
