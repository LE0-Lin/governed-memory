# Retained runtime full-path baseline

Frozen before this measurement on 2026-11-16. The earlier transport-pooling
study at source 5b32311 and CI43823918983 is retained in full. On the largest
case it regressed overall P95 537.0 -> 584.3 ms (+8.8%) and first-pass
577.1 -> 644.8 ms (+11.7%); repeats improved 406.4 -> 395.3 ms (-2.7%).
It fails its prespecified promotion gate and will not ship as an optimization.
The smallest case improved overall 10.4%/first 15.0%/repeat 22.3%; preserve both.
Windows stub setup costs did not establish hosted Linux full-path gains.

Restore the production runtime to exact v0.8 source ac1d6ed. The patch release
adds evaluation/evidence only; no new transport cache or authority behavior.
Validate that every src/native runtime file is byte-identical to the reference.
The two installed wheels differ in package version, not runtime Python/Rust.
Do not interpret their latency differences as a code speedup or regression.

Use the same full retrieval path, source/wheel verification, fixed known
72/1152-assertion recipes, explicit labels, neural models, 2 threads, Rust,
2048/8192 caches, no relevance cutoff, k=5/budget=1024 and three rotating replays
from SYSTEM_RETRIEVAL_PROTOCOL.md. Expected 1008 observations, 504 pairs, four
summary groups. Record actual hardware; no cross-run timing subtraction.
Warm only an unrelated one-fact project; measured caches start empty. Record
all first/repeat caller and server costs, including errors/outliers. No retries.

Measure actual standard MCP stdio with PostgreSQL, Graphiti/Neo4j and OpenFGA
HTTP. OPA approves synthetic fixture transactions before timing; search does
not call OPA. Startup, projection, ingestion and generation remain outside the
retrieval interval. After timing, verify live grant revocation, downgrade and
source withdrawal with the graph deliberately stale in both installed runtimes.
Independently audit fixture labels, complete grid, exact payload pairs, tokens,
backend counts and percentiles. Require actual graph hits, no graph-unavailable
fallbacks, zero retrieval errors/stale results and unchanged source. Final
required CI and actual installed model regressions must pass.

Publish all results. There is no performance-promotion gate because no runtime
optimization is being promoted. This is an explicit full-path baseline with a
retained negative experiment, not another attempt to obtain a favorable pooling
score. No labels/fixtures/models/ranking are tuned. No independent real histories,
WAN/concurrent production capacity, general answerability, historical 2025 dates
or new 500-question answer score is established. Every round must compare CV
83.2%/26.4%/1.12 s to the correctly scoped current values, separately from any
same-run code gains. Preserve the old ledger-only 0.408 s observation unchanged.
