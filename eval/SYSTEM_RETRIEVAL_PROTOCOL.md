# Full retrieval path and OpenFGA transport protocol

Frozen before implementation/canonical measurement, 2026-11-15. Preserve every
earlier run and protocol. Report full-stack measurements separately from ledger-only timing runs.

## Hypothesis and runtime boundary

v0.8 creates and closes an HTTP client for every OpenFGA check. A Windows
loopback protocol-stub diagnostic made 20 checks in 14.75 s, including 14.35 s
of client construction. This is diagnostic setup evidence, not actual OpenFGA
or model-serving performance. Reuse one HTTP client per authorizer, close it
when its owning CLI/server exits, and retain fresh HIGHER_CONSISTENCY checks
for every existing authorization boundary. Cache no decision, role, credential,
text or response. Keep time, source, dependency and final evidence checks.

No graph/ranking/model/cache-capacity/threshold/budget/generation/schema change
is proposed. Existing embedding and score caches remain 2048/8192. Add explicit
resource cleanup without changing externally supplied ledger ownership.

## Exact installed reference

Build two core wheels: exact v0.8.0 Git commit
`ac1d6ed9bd87f1b9aed412ea65a05fd589731700` and the clean candidate. Install
each without dependencies into a separate Python target directory. Each stdio
MCP subprocess imports that target first; validate its package version and
every packaged runtime file against its source before timing. Both share the
same pinned dependency environment/native extension and read the same isolated
PostgreSQL schema, Neo4j projection, OpenFGA store and fixed query times.
Record wheel/source/protocol/dependency/model/hardware identities and startup
times. No monkeypatched production authorizer or experimental MCP tool.

## Workload and measurement

Use the unchanged known controlled timeline recipes at 1 and 16 cohorts:
72 and 1152 historical assertions, 84 queries each. These are previously seen
synthetic templates, not independent real histories or a blind accuracy set.
Freeze generated fixtures and explicit gold/eligible labels before inference.

Use actual PostgreSQL, Graphiti/Neo4j, OpenFGA backed by PostgreSQL, pinned CPU
MiniLM embedding/reranking, Rust, and the standard search_memory stdio tool.
Configure actual OPA and exercise approvals outside timing; retrieval does not
call OPA, so do not imply OPA HTTP is included in search latency. No LLM/API
extraction or answer generation. One caller, two inference threads per model
process, k=5, budget=1024, relevance cutoff disabled. Both methods are governed.

Warm models/services only with an unrelated one-fact project and unrelated
query, never measured documents/queries. Measured project caches start empty.
Start both MCP servers before timing. Three replays rotate method order by
query index plus replay, yielding 1008 observations and 504 exact-output pairs.
Time on the caller from call_tool through complete decoded response; also
retain the server-reported retrieval latency. Ingestion, graph projection,
process/model startup and generation are outside the retrieval interval.
Record startup separately; retain every first-pass cost, failure and outlier.

Graph errors/fallbacks must remain visible; any graph-unavailable result fails
the full-path claim. Record all backends and require actual graph hits in both
methods. Do not silently retry timed queries. Dedicated isolated hosted CPU
runner; no competing image builds/tests. Local WSL remains untouched.

## Gates and authority probes

Preserve complete ordered evidence/payload hashes, token counts and reasons
for all pairs, with zero retrieval errors and stale evidence. Independently
verify explicit labels, observation grid and all aggregate percentiles. Report
negative unrelated evidence; zero stale does not mean correct abstention.

After canonical timings, in both already-warm MCP processes, remove the live
OpenFGA grant and require immediate denial, restore access/downgrade it, and
withdraw a selected source while deliberately leaving its graph edge stale.
Require returned snapshots to remain a subset of the fresh eligible ledger.
Archive these probes separately from immutable fixture-scored observations.
Unit/integration checks must cover changed/invalid decisions, HTTP failures,
client disposal and externally owned ledger lifetime. Required repository CI
and installed model regressions must pass.

Promote the transport optimization only if largest-case overall AND first-pass
caller P95 improve versus the same-run installed v0.8 reference, with all
correctness gates passing. Disclose smaller/repeat regressions too. A failure
remains archived; any changed implementation needs a distinct versioned run.
Do not compare the new full-path latency to old ledger-only 0.408 s as a version
regression or speedup. Report both full-path and ledger-only scopes explicitly. This covers
same-host graph/FGA/stdio execution, not WAN/concurrent production capacity
or independent real-world corpora.
