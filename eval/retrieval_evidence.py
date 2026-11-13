"""Checksums and source provenance shared by the new retrieval experiments."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "eval/retrieval_quality_protocol.json"


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_protocol():
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


def load_cases(split):
    specification = load_protocol()["datasets"][split]
    path = ROOT / "eval" / specification["file"]
    if checksum(path) != specification["sha256"]:
        raise ValueError("frozen retrieval fixture checksum mismatch")
    return json.loads(path.read_text(encoding="utf-8"))


def source_snapshot():
    files = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "src").rglob("*.rego"))
    files += sorted((ROOT / "src/governed_memory/data").glob("*.json"))
    files += sorted((ROOT / "native/src").glob("*.rs")) + sorted((ROOT / "eval").glob("*.py"))
    files += [
        ROOT / name
        for name in (
            "pyproject.toml",
            "uv.lock",
            "native/Cargo.toml",
            "native/Cargo.lock",
            "native/pyproject.toml",
            "eval/retrieval_quality_protocol.json",
        )
    ]
    digest = hashlib.sha256(
        b"".join(
            path.relative_to(ROOT).as_posix().encode()
            + b"\0"
            + path.read_bytes().replace(b"\r\n", b"\n")
            for path in files
        )
    ).hexdigest()
    paths = [
        "src",
        "native",
        "eval/*.py",
        "eval/relevance-*.json",
        "eval/retrieval_quality_protocol.json",
        "pyproject.toml",
        "uv.lock",
    ]
    return {
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "dirty_source": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain", "--", *paths], cwd=ROOT, text=True
            ).strip()
        ),
        "code_sha256": digest,
        "protocol_sha256": checksum(PROTOCOL),
    }


def write_json(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
