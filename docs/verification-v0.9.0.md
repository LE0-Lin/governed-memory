# v0.9.0 installation and usability verification

Verified 2026-11-16. This release packages a usable local core, adds an installed
demo and version command, and explains the project in English and Chinese.
It does not introduce a new retrieval benchmark, answer score or production SLO.

## Installed package, separate from the checkout

[Implementation CI](https://github.com/LE0-Lin/governed-memory/actions/runs/43870896889)
at `6ae9e1bab3d38be99f36022c8627a67210cd17b4` passed all six jobs. Both
Windows and Ubuntu built wheel/source archives, exported the same locked core
constraints and installed the wheel in a fresh environment outside the source
checkout. Child interpreters used `-I`; the imported module path and version
were checked against that new environment. Neither core install contained Torch.

Each installed package passed these actual CLI/stdio MCP checks:

- The packaged demo runs with external network access denied, emits all six
  scenarios and does not create the configured live database.
- The MCP server exposes only propose/search/explain tools. A proposed memory
  stays hidden; an agent's operator-only approval command fails.
- Operator approval makes the fact and its source provenance retrievable.
- A fresh server sees the persisted fact; that warm server then observes source
  withdrawal immediately and returns `no_eligible_evidence`.

Both receipts report the exact source commit and `source_dirty: false`. Their
uncompressed wheel file names and contents are identical; ZIP metadata produces
different archive hashes. The release's `SHA256SUMS` identifies the actual
published bytes. Release assets include the final build's installation receipts
and constraints; these are verification records, not a performance score.

The source-archive check rejects local environments, `.env`, live database files
and model weights. The bundled tokenizer supports the network-denied core demo;
initial installation still requires access to the release and dependency index.
Optional learned models and Rust installation use the locked source workflow
described in [getting started](getting-started.md).

## Other checks

| Implementation CI group | Passed | Skipped | Deselected | Known quality xfail |
| --- | ---: | ---: | ---: | ---: |
| Core, each Windows/Ubuntu | 191 | 146 | 35 | 0 |
| Real storage and installed core container | 326 | 46 | 0 | 0 |
| Real CPU models/generation/NLI | 32 | 14 | 0 | 1 |
| Native, each Windows/Ubuntu | 8 | 4 | 3 | 0 |

These groups overlap and must not be added into a unique-test total. Optional
environment skips and the previously documented small-model quality failure
remain explicit. Ruff, Cargo formatting/Clippy/tests, Rego, the frozen governance
evaluation and archive builds passed. Local targeted tests passed 10 with eight
PostgreSQL-dependent skips; actual service verification is the CI job above.

The PowerShell getting-started steps were executed against a new synthetic local
SQLite ledger, including import, review, separate operator/agent credentials,
approval, search and withdrawal. Relative documentation links/anchors and SVG
syntax were checked; the repository banner was rendered and visually inspected.
The packaged six-scenario demo is distinct from this persistent user workflow.

Raw implementation receipts, CI job/artifact metadata and a bounded check summary
are retained in [the verification directory](../eval/results/verification-v09-2026-11-16).
The [GitHub Release](https://github.com/LE0-Lin/governed-memory/releases/tag/v0.9.0)
is the distribution point for the final source build and its receipts.

## Measurement scope

The latest full-path performance study remains [v0.8.1](../eval/RESULTS-v0.8.1.md):
60/60 positive synthetic queries per workload, 0/792 stale returned items across
three correlated replays, and 0.762 s P95 on a single CPU host. This release
covers packaging, documentation, and isolated installation verification without
re-running retrieval or answer benchmarks; see [evaluation.md](evaluation.md)
for the complete metrics and known limits.
