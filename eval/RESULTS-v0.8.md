# v0.8 authority read metrics

Recorded 2026-11-15, Asia/Shanghai. The promoted change restricts only the final
live visibility lookup after reranking has narrowed the candidate pool. Every
existing authority check remains, and a full fresh fallback preserves reason
codes when selected hits disappear. The original source materialization stays.

**This round improves the largest tested candidate pool; smaller pools show
little benefit and some first-pass regressions.** In the final same-run
comparison, overall P95 falls **521.9 -> 408.3 ms (21.8%)**, first-pass P95
**602.9 -> 558.3 ms (7.4%)**, and repeat P95 **400.6 -> 378.9 ms (5.4%)**.
Positive temporal Recall@5 remains 100%, with zero stale results. This is a
controlled synthetic retrieval result, not production/general answer accuracy.

## Preserved rejected attempt

The [v1 protocol](AUTHORITY_REFRESH_PROTOCOL.md) combined two changes: dropping
unused Source ORM columns and restricting the final read. Its
[complete run](results/authority-v08-v1-2026-11-15/manifest.json) at source
`63eec49ae9cca8df876b50bff3d9178440d41f64` preserved all 996 paired outputs and
had zero errors/stale results, but its largest-case overall P95 increased
371.6 -> 488.0 ms (+31.3%) and first-pass P95 454.4 -> 528.5 ms (+16.3%).
Repeat P95 improved 369.8 -> 340.0 ms (-8.0%). It was rejected as an overall
performance promotion; the complete observations and independent rescore remain.

The [v2 protocol](AUTHORITY_REFRESH_V2_PROTOCOL.md) was frozen before the second
measurement and restored the original Source columns. Its prespecified gate
rejects promotion if largest-case overall OR first-pass P95 regresses, even if
repeats improve. The final revision passes both. The runners differ, so the
results do not establish that the removed columns caused v1's regression; do
not compute a speedup by subtracting v1's candidate from v2's candidate.

## Exact reference and environment

Final runtime/evaluation source: `20057750b410eaa278b42fcd7045fa1ed2eb70c4`.
Selected source SHA-256:
`074194f66412f70b1be40aa7131eaa7ce9b9989b1f6ebf0b9105ae3c2be37bb3`.
Final pre-measurement protocol SHA-256:
`73e98137c3007bed654c8f6a312eb69220f3d65b0f999e5c73c10bcc4c382717`.
Source is clean and unchanged during the run.

The reference Ledger and Retriever are compiled from the exact Git blobs at
v0.7.0 commit `df8349b7abfcdd8485868225e6bb74589f397edb`. The evaluator hashes
and verifies every other runtime/native reference file unchanged. Both versions
read the same PostgreSQL schemas and fixed clock, share pinned neural models,
and have separate identical document/score caches (2048/8192), k=5 and 1024 tokens.
No model, ranking, threshold, budget or answer-generation change is introduced.

The canonical run uses one isolated GitHub-hosted Ubuntu CPU runner, AMD EPYC
9V45, Python 3.12.14, PyTorch 2.15.0+cpu, pinned MiniLM models with two inference
threads, native Rust kernels and actual PostgreSQL 17.6. One caller executes
three replays with method order rotating by query index and replay. Models warm
only on unrelated text; measured caches start empty. Model loading, ingestion,
graph search, external-policy HTTP, transport and generation are outside latency.

The local C: volume ran critically low during a model-image build and Ubuntu
reported I/O errors before the candidate benchmark started. The final experiment
and installed-model verification therefore ran in isolated CI. Local partial
PostgreSQL test failures and build errors are retained as infrastructure failures,
not counted as passes. Model/data/old image files were not deleted. This report
does not claim a recovered local WSL environment or a clean local shutdown.

## Results and exact-output gate

The four recipes are unchanged known synthetic fixtures: 72/288/1152 historical
assertions with 84 queries each, plus the previously examined 80-query relevance
heldout set. Expanded cohorts and repeated queries are correlated templates,
not independent real-world or new blind validation. Labels are explicit and
checked independently of ledger output. Counts below include three replays.

| Workload | Positive recall, both versions | Stale / returned, both | Overall P95 old / new, ms | First-pass P95 old / new, ms | Repeat P95 old / new, ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| 72 assertions | 100% | 0/1008 | 78.4 / 77.9 | 84.9 / 88.9 | 35.7 / 35.8 |
| 288 assertions | 100% | 0/777 | 251.1 / 248.3 | 270.7 / 266.7 | 54.2 / 53.5 |
| 1152 assertions | 100% | 0/795 | 521.9 / 408.3 | 602.9 / 558.3 | 400.6 / 378.9 |
| Relevance heldout | 97.92% | 0/780 | 50.7 / 50.7 | 55.9 / 58.7 | 27.2 / 26.6 |

Smallest-case first-pass P95 worsens 4.7%, and heldout first-pass P95 worsens 5.0%.
Those two cases do not narrow the final pool, and the evidence does not establish
a benefit there. Do not describe this as universal first-use acceleration.
The large-case improvement is relative to the v0.7 implementation measured in
the same run. The old Ryzen/WSL 540.4 ms observation is a separate experiment.

All **1992 observations** complete without retrieval errors; all **996 pairs**
match ordered fact IDs, full evidence payload hashes, tokens and reasons. No
stale evidence appears in either governed version. The
[independent verification](results/authority-v08-v2-2026-11-15/independent-verification.json)
checks all eight groups, explicit labels, complete observation grid, token
limits, percentiles and visibility-read counts. Downloaded artifacts were also
rescored locally. Raw observations SHA-256:
`36e826fc6b13a6a7aaae4087a1ff59043f6deac09f7413d5bb68738a9dc8c2ac`.

In the largest case both versions still execute 1008 visibility reads across
252 observations: four per query. Returned visibility rows fall 193536 -> 157752
(18.5%), because only the final read narrows 192 eligible snapshots to 50 selected
ones. The first three reads remain full so that concurrent withdrawal before
reranking can still admit lower-ranked valid survivors. Empty final subsets
perform a full fresh fallback to retain the original reason semantics.

Negative queries still receive unrelated eligible evidence, and heldout positive
recall remains 97.92%. This round improves read cost, not semantic ranking or
abstention. Zero stale results must not be described as correct answers. No new
500-question answers or scores were generated; previous outputs stay unchanged.

## Verification and scope

[Regular source CI](https://github.com/LE0-Lin/governed-memory/actions/runs/43717801551)
passes all six jobs. The separate
[paired/deployed-model workflow](https://github.com/LE0-Lin/governed-memory/actions/runs/43717801550)
passes both jobs, including an installed model container in both relevance modes,
more than 50 eligible facts, repeated MCP queries, and source withdrawal.
Regression tests cover historical/private/foreign snapshots, empty filter
authentication, updated support provenance, grant removal, vanished selected
hits, exact reason codes and valid survivors beyond the first 50 withdrawn hits.
The [verification record](../docs/verification-v0.8.md) links test counts,
installed-image identity, retained local failures and checksummed receipts.

On 1,152 synthetic historical assertions, this revision preserves 100% positive
temporal Recall@5 and zero stale evidence while reducing same-run ledger-path
retrieval P95 from 521.9 to 408.3 ms (21.8%), with first-pass P95 improving 7.4%.
Do not combine this percentage with v0.7's score-cache gain or interpret it as
an unqualified WAN/production speedup.
