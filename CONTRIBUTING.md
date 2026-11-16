# Contributing

Small fixes, reproducible bug reports and documentation improvements are welcome.
For changes to trust boundaries, schemas or model behavior, describe the problem
and intended compatibility in an issue before a large implementation.

## Local checks

```sh
uv sync --frozen --extra dev
uv run ruff check src tests examples scripts eval
uv run ruff format --check src tests examples scripts eval
uv run pytest -q
uv run python scripts/check_offline_demo.py
```

Python 3.12 is required. Storage/model tests skip without their opt-in
configuration; [usage](docs/usage.md) and [deployment](docs/deployment.md) document
the actual service/model checks. CI covers Windows/Linux, real governance/storage,
native Rust and CPU models. Run the tests affected by a change; do not present
skipped integration tests as passing real-service checks.

## Changes worth reviewing

- Keep production code small and explicit. Preserve immutable history and the
  distinction between proposals, operator decisions and model suggestions.
- Do not cache authorization decisions or remove source/dependency rechecks to
  improve a benchmark. Cover a real user consequence and its regression.
- Keep source/credential data out of commits and issue logs. Use synthetic
  fixtures for reproduction; [security reporting](SECURITY.md) covers sensitive findings.
- Explain the resulting behavior, compatibility and actual checks in the PR.
  Do not claim a human review or manual execution that did not happen.

## Measurements and releases

Freeze a protocol and source before measurement. Retain raw observations,
failures, outliers, model/data identities and a separate rescore. Do not rewrite
earlier outputs or tune using published heldout outcomes. State sample sizes,
correlated repetitions, timing boundaries and actual hardware.

The 60/60 controlled result is not a universal accuracy target. See
[the evidence card](docs/evaluation.md). Compare code variants within a matched
run; do not combine different hardware/protocols into a speedup.

Core CI builds wheel/sdist artifacts, exports locked core constraints, installs
the wheel in a separate environment outside the checkout and exercises the
persistent CLI/MCP workflow. Release assets should come from the checked source
and include checksums and those receipts. Model weights, live databases and
operator credentials do not belong in release archives.
