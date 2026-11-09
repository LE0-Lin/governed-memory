"""Import annotated session JSONL or Markdown ADRs; no implicit approval or extraction."""

import json
import tomllib
from pathlib import Path


def import_file(ledger, token: str, project: str, path: str | Path) -> list[dict]:
    path = Path(path)
    body = path.read_text(encoding="utf-8")
    records = []
    if path.suffix == ".jsonl":
        for number, line in enumerate(body.splitlines(), 1):
            if not line.strip():
                continue
            message = json.loads(line)
            if "memory" in message:
                record = dict(message["memory"])
                records.append((record, f"line:{number}"))
    elif path.suffix in {".md", ".markdown"}:
        if not body.startswith("+++\n"):
            raise ValueError("ADR must start with +++ TOML metadata +++")
        header, separator, _ = body[4:].partition("\n+++\n")
        if not separator:
            raise ValueError("unterminated ADR metadata")
        records.append((tomllib.loads(header), "frontmatter:memory"))
    else:
        raise ValueError("supported formats: annotated .jsonl and TOML-frontmatter .md")
    allowed = {"subject", "predicate", "value", "valid_from", "valid_until"}
    result = []
    # Validate the entire file before writing anything.
    from governed_memory.ledger import instant

    for record, _ in records:
        if set(record) - allowed or not allowed.difference({"valid_until"}) <= set(record):
            raise ValueError("memory requires subject, predicate, value, valid_from")
        start = instant(record["valid_from"])
        if record.get("valid_until") and instant(record["valid_until"]) <= start:
            raise ValueError("invalid time interval")
    for record, fragment in records:
        result.append(
            ledger.propose(
                token, project, **record, body=body, locator=path.name, fragment=fragment
            )
        )
    return result
