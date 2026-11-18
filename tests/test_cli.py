import json
import os
import subprocess
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path

import governed_memory


def test_packaged_demo_and_version_ignore_unrelated_live_configuration(tmp_path):
    database = tmp_path / "must-not-be-created.db"
    environment = {
        **os.environ,
        "MEMORY_DATABASE_URL": f"sqlite:///{database.as_posix()}",
        "MEMORY_FGA_URL": "invalid-service",
        "MEMORY_ANSWER_FORMAT": "invalid-format",
        "MEMORY_GENERATION_PROFILE": "invalid-model",
    }
    demo = subprocess.run(
        [sys.executable, "-m", "governed_memory.cli", "demo"],
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=True,
    )
    rows = [json.loads(line) for line in demo.stdout.splitlines()]
    assert len(rows) == 6
    assert rows[0]["values"] == ["PostgreSQL"]
    assert rows[1]["values"] == ["SQLite"]
    assert rows[-2]["self_approval"] == "denied"
    assert rows[-1]["withdrawn_evidence_visible"] is False
    assert not database.exists()
    reported = subprocess.run(
        [sys.executable, "-m", "governed_memory.cli", "--version"],
        env=environment,
        capture_output=True,
        encoding="utf-8",
        check=True,
    )
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    expected_version = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    assert governed_memory.__version__ == expected_version
    assert version("governed-memory") == expected_version
    assert reported.stdout.strip() == f"governed-memory {expected_version}"


def test_cli_json_is_utf8_when_the_native_pipe_encoding_is_legacy(tmp_path):
    database = tmp_path / "memory.db"
    source = tmp_path / "decision.md"
    value = "数据库 🧪 São Paulo"
    source.write_text(
        '+++\nsubject="storage"\npredicate="database"\n'
        f'value="{value}"\nvalid_from="2030-01-01T00:00:00Z"\n+++\nSynthetic ADR.\n',
        encoding="utf-8",
    )
    environment = {
        **os.environ,
        "MEMORY_DATABASE_URL": f"sqlite:///{database.as_posix()}",
        "MEMORY_OPA_URL": "",
        "PYTHONIOENCODING": "cp936",
    }

    def cli(*arguments):
        result = subprocess.run(
            [sys.executable, "-m", "governed_memory.cli", *arguments],
            env=environment,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
        return json.loads(result.stdout.decode("utf-8"))

    environment["MEMORY_TOKEN"] = cli("init", "--project", "demo")["admin_token"]
    candidate = cli("ingest", "--project", "demo", str(source))[0]
    preview = cli("preview", "--project", "demo", candidate["id"])
    assert preview["value"] == value
    assert cli("upgrade", "--project", "demo") == {
        "schema": "current",
        "project": "demo",
        "dependency_repairs": 0,
    }
