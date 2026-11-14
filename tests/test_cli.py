import json
import os
import subprocess
import sys


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
