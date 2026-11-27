# v0.8.1 full retrieval evidence

Recorded 2026-11-16, Asia/Shanghai. This release adds a reproducible full-path
baseline and preserves a rejected optimization. **Production Python/Rust source
is identical to v0.8; no new runtime speedup is claimed.** The new timing includes
actual PostgreSQL, Graphiti/Neo4j, OpenFGA HTTP and standard MCP stdio transport.

## Summary across benchmark scopes

| Metric | Paired session control (`v0.7`) | Ledger-only path (`v0.8`) | Full MCP stack (`v0.8.1`) |
| --- | --- | --- | --- |
| Positive temporal Recall@5 | 100% (vs. 85% session baseline) | 100% | **100%** (60/60 per replay) |
| Stale assertions / returned | **0/789** (vs. **498/816** session baseline) | 0/795 | **0/792** |
| Retrieval latency P95 (1,152 assertions) | 540.4 ms | 408.3 ms | **761.6 ms** (first-pass 806.0 ms, repeat 515.7 ms) |

The session-baseline stale reduction comes from the preserved
[v0.7 same-run session comparison](RESULTS-v0.7.md) (`498/816` stale returned
assertions reduced to `0/789`). This release does not rerun that unguarded session
control; it directly measures the complete governed stack through PostgreSQL,
Graphiti/Neo4j, OpenFGA HTTP, and stdio MCP.

The [v0.8 ledger-path P95 of 0.408 s](RESULTS-v0.8.md) excludes graph search,
remote authorization HTTP, and stdio MCP transport, and ran on different hardware;
do not subtract it from 0.762 s to infer a version regression. Process and model
startup is separately recorded at 4.95–5.53 s outside retrieval timing.

## Rejected pooling study

The [original protocol](SYSTEM_RETRIEVAL_PROTOCOL.md) proposed reusing an OpenFGA
HTTP client while keeping all fresh `HIGHER_CONSISTENCY` decisions. A Windows
loopback diagnostic showed large construction cost, but was not actual OpenFGA
performance. The canonical study ran installed wheels on an isolated Intel Xeon
6975P-C host, actual services and CPU models. Its full
[manifest and observations](results/system-transport-v1-2026-11-16/manifest.json)
are retained, including exact output equivalence, zero errors/stale results and
passing live-authority/model-container checks.

| Case | Overall P95 reference / pooling, ms | First-pass, ms | Repeat, ms |
| --- | ---: | ---: | ---: |
| 72 assertions | 175.6 / 157.2 | 222.7 / 189.2 | 138.5 / 107.6 |
| 1152 assertions | 537.0 / 584.3 | 577.1 / 644.8 | 406.4 / 395.3 |

The largest overall and first-pass costs worsened **8.8% and 11.7%**, failing
the prespecified promotion gate. Smaller-case gains and repeat improvements
cannot compensate. All proposed pooling/lifecycle runtime changes were reverted;
the final product has no new authorizer client API or configuration knob. This
one experiment does not prove pooling is universally slower or establish why
the large-case tails changed. No attempts or outliers were discarded.

Rejected source `5b32311e2b735c9c45552b36177637a500478375`, selected source SHA
`808c3a1598762fd455672ed501f193b52e0a483a3c726ecd9617b693578cdc15`.
The separate [baseline protocol](SYSTEM_BASELINE_PROTOCOL.md) was frozen before
measuring the restored runtime. This second experiment establishes its full-path
baseline; it is not a repeat pooling attempt seeking a better score.

## Final baseline and source identity

Frozen source: `eb6e50f88b5309893638286180c4c06152844f75`.
Selected source SHA-256:
`80afc91602fca0ccf4b3da6102f95ec04aca84241dcc74b76c5425d0785a2516`.
Baseline protocol SHA-256:
`836960fd3137923e7993689971ca0b4bc6d72614b7b8a46c686accb692d307ae`.

The runner rejects any production source difference from exact v0.8 commit
`ac1d6ed9bd87f1b9aed412ea65a05fd589731700`. It verifies 36 runtime files in
each separately installed wheel, plus imported package path/version. Both use
the same PostgreSQL schemas, graph, OpenFGA store, model/dependency environment
and fixed query times, with independent equally sized caches (2048/8192), k=5,
1024 tokens and no relevance cutoff. Source and protocol stay unchanged.

The final host is AMD EPYC 9V74, CPU PyTorch 2.15.0+cpu, pinned MiniLM models
with two inference threads per process, native Rust and one caller. Actual OPA
approves synthetic fixture transactions before timing; retrieval does not call
OPA. There is no paid API, unreviewed LLM extraction or answer generation.

| Case / installed wheel | Positive recall | Stale / returned | Caller overall P95, ms | First-pass, ms | Repeat, ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| 72 / v0.8 reference | 100% | 0/1008 | 211.5 | 252.6 | 169.3 |
| 72 / current v0.8.1 | 100% | 0/1008 | 212.1 | 248.5 | 163.0 |
| 1152 / v0.8 reference | 100% | 0/792 | 719.8 | 805.4 | 524.6 |
| 1152 / current v0.8.1 | 100% | 0/792 | **761.6** | **806.0** | **515.7** |

These two wheels have identical runtime source. Their observed differences are
not an optimization effect. Do not select a smaller reference number as the
current measurement or compare the Intel and AMD experiments as a speedup.
All 252 large-case queries per version use real graph hits plus ledger fill;
no graph-unavailable fallback occurs. Small cases have 177 graph-only and 75
graph-plus-fill observations per version. Server-only P95 is 757.3 ms in the
current largest case; the primary figure remains caller-observed 761.6 ms.

The [independent verification](results/system-baseline-v081-2026-11-16/independent-verification.json)
confirms **1008 observations**, **504 exact payload/order/token/reason pairs**,
four summary groups and zero retrieval errors/stale results. Raw observation
SHA-256: `359b7c864d5673236cbcbdeee396b13d63818321c436717588adab276a3ef500`.
The downloaded files were also independently rescored locally. Both already-warm
MCP processes immediately deny removed external grants, allow only reads after
downgrade, and hide a withdrawn source while its verified Neo4j edge is left
stale. These [mutation probes](results/system-baseline-v081-2026-11-16/authority-probes.json)
are separate from the immutable fixture-scored query observations.

## Scope, validation and remaining distance

The unchanged recipes contain 72/1152 synthetic historical assertions and 84
queries each, replayed three times. Cohorts/replays are correlated templates
previously examined; this is not a new blind or independent real-history set.
Positive recall is evidence-ID recall, not answer correctness. Negative queries
still receive 288/225 unrelated eligible items in the small/large current cases.
This round establishes neither better abstention nor a new 500-question score.

Timing covers decoded standard MCP responses, live PostgreSQL checks, actual
graph/authorization requests, local models, ranking and evidence serialization.
All services are on one hosted runner. Ingestion, graph projection, process/model
startup, downloads and generation are outside it. WAN/remote MCP deployment and
concurrency/production capacity remain unmeasured. Same-host full-stack retrieval is covered here; multi-tenant WAN concurrency remains outside scope.

[Source CI](https://github.com/LE0-Lin/governed-memory/actions/runs/43826351086)
passes all six jobs; [system/model CI](https://github.com/LE0-Lin/governed-memory/actions/runs/43826351173)
passes its full-path audit and subsequent installed model-image regressions.
See [verification](../docs/verification-v0.8.1.md) for exact test counts, image
identity, retained failures and checksummed source-bound artifacts. All prior experimental observations and checksummed artifacts remain preserved.
