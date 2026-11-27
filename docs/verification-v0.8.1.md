# v0.8.1 verification

Verified 2026-11-16, Asia/Shanghai. This release adds full-path evaluation and
evidence. Production `src` and `native/src` are identical to v0.8 commit
`ac1d6ed9bd87f1b9aed412ea65a05fd589731700`; the candidate pooling and resource
lifecycle changes were completely reverted after their performance gate failed.
Only package version, evaluation, tests, workflow and documentation change.

## Frozen runtime and deployed evidence

Source/evaluation commit: `eb6e50f88b5309893638286180c4c06152844f75`.
Selected source SHA:
`80afc91602fca0ccf4b3da6102f95ec04aca84241dcc74b76c5425d0785a2516`.
Protocol SHA:
`836960fd3137923e7993689971ca0b4bc6d72614b7b8a46c686accb692d307ae`.

The full-path workflow verifies every installed source file against its exact
Git commit, checks actual imported package path/version, and uses independently
installed 0.8.0/0.8.1 wheels with identical shared dependencies/native kernels.
Measured current wheel SHA:
`e83c1f743b1dda6f41e20240e87fbc9a368b0b9e0800096e89cc359b6f7d03c2`.
The runtime-source identity gate rejects any new production code change.

[Source CI43826351086](https://github.com/LE0-Lin/governed-memory/actions/runs/43826351086)
passes six jobs. [System CI43826351173](https://github.com/LE0-Lin/governed-memory/actions/runs/43826351173)
passes full retrieval, independent rescoring, live-authority mutations and the
subsequent installed model container check. Image building and tests run after
all canonical timing, with no competing task on that benchmark runner.

The actual model image is
`sha256:0669421728577562fd3ce2ab4b261580b4c25e53858b2f405357a6c992a8b56e`.
Persistent installed MCP tests cover 52 facts, both relevance modes, repeated
cache hits and immediate source withdrawal as UID 10001 with a read-only root
and model cache. Both PostgreSQL modes pass; two SQLite configurations skip.
Standard storage CI separately verifies installed core backup/restore and
actual PostgreSQL/Neo4j/OPA/OpenFGA integration.

The final source collects 372 test configurations. Groups below overlap and
must not be summed into a unique-test count.

| CI group | Passed | Skipped | Deselected | Known quality xfail |
| --- | ---: | ---: | ---: | ---: |
| Core, each Windows/Ubuntu | 190 | 147 | 35 | 0 |
| Real storage and installed core | 326 | 46 | 0 | 0 |
| Real CPU models/generation/NLI | 32 | 14 | 0 | 1 |
| Native, each Windows/Ubuntu | 8 | 4 | 3 | 0 |
| Installed model MCP | 2 | 2 | 0 | 0 |

Optional environment/SQLite skips remain explicit. The small generator's
missing-owner abstention remains an expected quality failure, not a passing
no-answer check. Ruff, Cargo formatting/Clippy/tests, Rego, network-denied core
demo, wheel/sdist builds and the unchanged frozen governance evaluation pass.
The new independent-audit configuration covers caller/server timing and graph
backend accounting; old scorer formats still work. Final local targeted checks
pass 9 with 3 PostgreSQL-dependent skips. Final real-service acceptance is CI.

## Experiments and negative results

[Results](../eval/RESULTS-v0.8.1.md) retain both complete 1008-observation runs.
The rejected source 5b32311 had zero errors/stale/payload mismatches but largest
overall/first P95 regressions of 8.8%/11.7%, so it did not ship. Smaller gains
and actual model checks were retained too. The final unchanged-runtime baseline
has 504 identical pairs, zero errors/stale evidence and real graph hits, with
current large-case full-path P95 761.6 ms, first 806.0 ms, repeats 515.7 ms.

All query fixtures/aliases, observations, backend counts, source/model/wheel
identities and independent rescores remain. After timing, both warm MCP processes
observe live OpenFGA revocation/downgrade and source withdrawal with an actual
selected graph edge deliberately left stale. There is no new session-control
run, semantic quality gain, 500-question generation or changed old evaluation.

The [machine-readable receipt](../eval/results/verification-v081-2026-11-16/verification.json)
binds final/rejected CI metadata, image IDs, JUnit/log files and exact hashes.
It retains the Windows setup diagnostic, initial local keepalive assertion and
the observed intermediary `Connection: close` responses; the candidate test was
corrected to respect that header while still requiring one client and fresh
decisions. Those dropped candidate tests are not current feature acceptance.

## Scope and environment notes

All full-path services and timing measurements in this release ran in CI on a
single host with one caller. Real-world histories, WAN latency, and
multi-caller production throughput remain outside the scope of this baseline.
