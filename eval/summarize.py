"""Recompute aggregate metrics from saved raw predictions without rerunning retrieval."""

import argparse
import hashlib
import json
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from eval.run import ROOT, metrics
from governed_memory.retrieval import serialize


def summarize(directory, reason):
    raw = (directory / "predictions.jsonl").read_bytes()
    groups = defaultdict(list)
    for line in raw.decode().splitlines():
        row = json.loads(line)
        groups[f"{row['split']}/{row['method']}/all"].append(row)
        groups[f"{row['split']}/{row['method']}/{row['kind']}"].append(row)
    summary = {name: metrics(rows) for name, rows in sorted(groups.items())}
    (directory / "summary.json").write_text(serialize(summary) + "\n", encoding="utf-8")
    scoring = {
        "reaggregated_at": datetime.now(UTC).isoformat(),
        "reason": reason,
        "predictions_sha256": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(),
        "scorer_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "scorer_sha256": hashlib.sha256(
            (ROOT / "eval/run.py").read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
        "original_run_provenance": "provenance.json",
    }
    (directory / "scoring.json").write_text(serialize(scoring) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    summary = summarize(args.directory, args.reason)
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k.startswith("heldout/") and k.endswith("/all")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
