# v0.7 verification record

Verified on 2026-11-14, Asia/Shanghai. The runtime adds bounded reuse of exact
query/passage cross-encoder scores. It keeps the existing eligibility checks and
stable ranking, and does not cache credentials, text, ordering or responses.
`MEMORY_RERANK_CACHE_SIZE=0` disables reuse; the default limit is 8,192 scores.
Model, project and exact query/text hashes separate entries.

## Frozen implementation and validation

Runtime and evaluation commit: `985b10892bd4f40fb207520177e313a0183358d1`.
Selected source SHA-256:
`6a5b9b80e0b39143859877d70207fb040b5abb4bcfc78f0f1afb671f80d650ec`.
The [protocol](../eval/RETRIEVAL_METRICS_PROTOCOL.md) was committed before
implementation and measured outcomes. Its final pre-measurement SHA-256 is
`bb1f5217e6a40f00e022989f9f264c0ee53c8772b5586c358055e7e8018dde9d`.

[Runtime-source CI](https://github.com/LE0-Lin/governed-memory/actions/runs/43589872881)
passes all six jobs: core on Windows/Ubuntu, native Rust on both platforms,
actual storage/evaluation and actual local models. Local authority/cache tests
cover exact keys and LRU eviction, invalid scores, stable cutoff/ties, current
grant/source withdrawal, real OpenFGA revocation after a cache hit, updated
corroboration provenance, and withdrawal during a partial cache miss. Real
MiniLM inference verifies cached and recomputed scores across batch shapes.

The expanded timeline labels are independently generated from the unchanged
frozen CV fixtures. Tests compare every query's explicit eligible labels against
both SQLite and PostgreSQL at 1 and 4 cohorts, and verify coverage and dependency
bindings at 16 cohorts. The independent rescorer rejects a modified gold label
and checks the complete observation grid, tokens, stale labels and percentiles.

One existing small-generator quality counterexample remains an explicit expected
failure: the pinned 0.5B model does not correctly abstain on the missing-owner
probe. It is not counted as a passing no-answer test. Answer generation and the
standard profile's answer format are unchanged.

## Installed runtime

Images built from the repository Dockerfile:

- Core: `sha256:42f8a1403f3f0750bb560d058f5643519ab992ea5fe0e8163bebeac824b504d5`.
- Models: `sha256:45f2142ef90cb68953bd91f46269dd070e2d2658c87764b6420728fbbdf74492`.

Both run installed 0.7.0 as UID 10001 with a read-only root, no Linux capabilities
and temporary scratch storage. The actual MCP tests repeat the same query in one
process with the relevance gate both disabled and enabled, then withdraw its
source and check that the next request returns no eligible evidence. Core
permissions, binary PostgreSQL backup/recovery and old v0.6.0 data repair also
pass against the installed images. Model caches are mounted read-only.

The separate benchmark image adds only Git to the model image, so the evaluator
can record a clean source snapshot. It uses the installed 0.7.0 runtime, CPU
PyTorch `2.15.0+cpu`, pinned neural models and native Rust kernels. The repository
is mounted read-only; only isolated result storage is writable. Production
images do not need Git.

## Retrieval evidence

The [results report](../eval/RESULTS-v0.7.md) binds the completed paired run and
independent verification: 2,988 observations, zero execution errors or governed
stale results, and 996 exactly equivalent governed pairs. On 1,152 synthetic
historical assertions, positive temporal Recall@5 is 100% versus 85% for the
session control. Overall governed retrieval P95 falls from 627.9 to 540.4 ms; repeat
P95 falls from 623.5 to 410.6 ms. First-pass P95 is essentially unchanged and negative
queries still receive unrelated eligible evidence. The report retains all four
workloads, first-use regressions, the scope and all raw observations.

Recorded local acceptance groups cover the complete 352 configurations after
deduplicating the standard-container opt-in skips against its actual run:

| Group | Passed | Skipped | Expected quality failure |
| --- | ---: | ---: | ---: |
| Core and actual PostgreSQL/Neo4j/OPA/OpenFGA | 317 | 9 | 0 |
| Additional independent-audit regression, added after core collection | 1 | 0 | 0 |
| Actual embedding, reranking, generation and NLI models | 10 | 0 | 1 |
| Installed core/upgrade/model/standard MCP workflows | 7 | 7 | 0 |
| Total | **335** | **16** | **1** |

Five skips are the optional native extension absent from the local Windows
environment; 11 are SQLite configurations of PostgreSQL-only checks. The source
CI compiles and tests Rust on Windows and Ubuntu. The additional audit test is
reported separately rather than pretending the earlier core collection included
it. Targeted overlapping runs are not added to these totals.

OPA 1.22.2 Rego tests (10/10), the unchanged frozen governance suite (768 retrievals and
48 operation checks), the network-denied demo, Ruff and locked wheel/sdist
builds pass. Wheel SHA-256:
`0794129e2ff7ac1138ff2698e3e57e1d16954c4a207f3dfd471d4c535eb1dd62`.
The actual 1.5B standard MCP container also answers the fictional question with
resolved citations, then observes source withdrawal in the same live process.

All six owned services exited with status zero; the verified dedicated daemon
also exited cleanly. Data volumes, old/current images and model caches remain.
The original 500-question outputs and all earlier result files are unchanged.

The [machine-readable verification](../eval/results/verification-v07-2026-11-14/verification.json)
binds these counts, images and wheel to retained JUnit/log files and the canonical
experiment. It also retains the initial missing-Git provenance probe, corrected
by the benchmark-only image before any canonical inference.
