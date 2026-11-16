# Measuring the full retrieval path

The v0.8 timing covers PostgreSQL authority checks and local neural/native
retrieval. It excludes Graphiti/Neo4j, OpenFGA HTTP and MCP transport. The
[baseline protocol](../eval/SYSTEM_BASELINE_PROTOCOL.md) adds a separately scoped
measurement of those paths, using the existing standard `search_memory` tool.
The original measurements remain in their original result folders.

Reproduce this historical baseline from **v0.8.1**, using its workflow/source.
The source-identity guard intentionally rejects later production changes,
including the packaged demo added in v0.9.0. Release installation verification
is a different check and does not regenerate the old performance numbers.

The [workflow](../.github/workflows/system-metrics.yml) builds the exact v0.8
core wheel from its Git commit and the candidate wheel from its clean source.
The final baseline requires identical production source in both; the package
version changes to identify the added evaluation and evidence. An earlier
[connection-pooling study](../eval/SYSTEM_RETRIEVAL_PROTOCOL.md) failed its
largest-case latency gates and was rejected, with all results retained.
They install into separate directories with the same pinned dependency/native
environment. `eval/system_runtime.py` verifies every packaged runtime file and
package version against its source, then launches a persistent stdio process
for each. Neither process can select an identity or bypass the ordinary tools.

`eval/system_metrics.py` prepares known timeline fixtures with actual OPA
approvals, PostgreSQL, a Graphiti/Neo4j projection and a separate OpenFGA store.
It starts both MCP runtimes, warms only an unrelated project, and rotates query
order across three replays. The client clock covers the complete decoded
response; server retrieval and process/model startup are recorded separately.
No approval, ingestion, projection, generation or model download runs during
the timed query loops. The installed model Docker regression follows timing.

The independent scorer reconstructs gold/eligible IDs from saved fixtures and
checks the complete observation grid, payload pairs, tokens, errors, stale
evidence and percentiles. It also verifies backend counts and rejects a
graph-unavailable fallback. After timing, both already-warm processes must
observe live OpenFGA revocation, reader downgrade and source withdrawal while
the selected Neo4j edge deliberately remains stale. These mutation probes are
separate from fixture-scored observations.

These histories are previously examined synthetic templates. The experiment
measures one caller with services on the same hosted runner; it cannot establish
independent real-world recall, WAN latency or production concurrency. OPA governs
the fixture approvals; it is not called by retrieval and is not part of search
latency. CV-versus-current values must retain these boundaries, and must be
reported separately from paired old/new gains within this run.
