# v0.7 retrieval metrics

Recorded 2026-11-14, Asia/Shanghai. Bounded cross-encoder score reuse improves
repeated-query latency without changing evidence, tokens or eligibility. The
default unfiltered retriever is evaluated; no relevance threshold was adjusted.

The largest controlled history contains **1,152 synthetic assertions**. Positive
temporal Recall@5 is **100%**, versus **85%** for the session-retrieval control.
Stale evidence falls from **498/816** returned assertions to **0/789**. Overall
governed retrieval P95 is **540.4 ms**, versus **627.9 ms** with score reuse
disabled in the same run (13.9% lower). Repeat-query P95 is **410.6 ms**, versus
623.5 ms (34.1% lower). These are scoped controlled results, not general answer
accuracy, a production capacity result, or an official external benchmark score.

## Protocol and execution

The [protocol](RETRIEVAL_METRICS_PROTOCOL.md) was first committed as `3be594f`,
before implementation and canonical measurement. Runtime/evaluation source was
then frozen at `985b10892bd4f40fb207520177e313a0183358d1`, selected source SHA-256
`6a5b9b80e0b39143859877d70207fb040b5abb4bcfc78f0f1afb671f80d650ec`.
Final pre-measurement protocol SHA-256 is
`bb1f5217e6a40f00e022989f9f264c0ee53c8772b5586c358055e7e8018dde9d`.
The source was clean and unchanged throughout the run.

Actual PostgreSQL schemas, pinned CPU MiniLM embedding/cross-encoder models,
two inference threads and native Rust ranking run on an AMD Ryzen 9 7945HX under
WSL2. The installed package is 0.7.0 with CPU PyTorch 2.15.0+cpu. One caller
executes three repetitions, rotating method order for every query/repetition.
Only unrelated text warms the models; measured caches start empty. Every method
uses k=5 and 1,024 evidence tokens. The session control receives the same vector
and score-cache opportunities, but deliberately lacks approval, effective-time,
supersession, source-withdrawal and dependency filtering. It is an unsafe
experimental control. The two governed methods differ only in score-cache use.

The unchanged 84-query CV timelines are expanded deterministically into 1, 4
and 16 cohorts, containing 72, 288 and 1,152 historical assertions. Each size
retains all original query types and distributes targets across cohorts; source
and parent bindings remain separate. The published 80-query relevance heldout
set supplies a fourth workload. These previously examined synthetic templates
are not independent new real-world samples or blind validation. All fixtures,
explicit labels, source/model identities and raw observations are retained.

The complete run has **2,988 observations**: three methods times three replays
of (84 + 84 + 84 + 80) workload/query instances. All complete without runtime
errors. All **996 governed comparisons** have identical ordered IDs, evidence
payload hashes, token counts and reason codes. No governed result is stale.
The [independent rescore](results/retrieval-metrics-v07-2026-11-14/independent-verification.json)
reconstructs labels from fixtures/aliases and verifies all 12 summary groups.
It confirms the complete observation grid, error denominators and percentiles.

## Recall and stale evidence

Each temporal workload has 60 positive and 24 negative unique query instances;
heldout has 48 positive and 32 negative instances. Counts below include three
replays, which are not independent questions. Recall is positive macro gold-ID
recall, not answer correctness. Both governed variants have the same results.

| Workload | Session recall | Governed recall | Session stale / returned | Governed stale / returned |
| --- | ---: | ---: | ---: | ---: |
| 72 historical assertions | 100% | 100% | 600/960 | 0/1,008 |
| 288 historical assertions | 76.67% | 100% | 498/804 | 0/780 |
| 1,152 historical assertions | 85% | 100% | 498/816 | 0/789 |
| Published relevance heldout | 97.92% | 97.92% | 0/810 | 0/810 |

The controlled temporal stale-rate reduction is 100% where the session
denominator is nonzero; it is undefined for heldout, whose baseline has no
stale evidence. These results demonstrate the specified governance/timeline
rules on these fixtures, not a universal 100% recall or stale-prevention rate.
The original v0.4/v0.5/v0.6 observations remain unchanged.

Negative queries still receive unrelated eligible evidence: 288, 219, 225 and
324 items across replays for the four workloads, respectively. Cache reuse
preserves this limitation. Zero stale evidence does not establish answerability,
correct abstention, or factual answer accuracy. No new answer generation or
500-question scoring was performed.

## Paired latency

All timings include live SQL checks, embeddings, ranking, evidence packing and
serialization. They exclude model loading, ingestion, transport and generation.
Graph retrieval and external authorization HTTP calls are disabled to isolate
the same authoritative path as the original controlled CV protocol. Their
correctness is tested separately; these numbers do not establish their latency.

| Workload | Overall P95, control / cache, ms | First-pass P95, control / cache, ms | Repeat P95, control / cache, ms | Repeat reduction |
| --- | ---: | ---: | ---: | ---: |
| 72 historical assertions | 121.2 / 111.7 | 119.8 / 121.7 | 122.9 / 70.8 | 42.4% |
| 288 historical assertions | 323.7 / 309.5 | 330.0 / 329.6 | 317.6 / 101.0 | 68.2% |
| 1,152 historical assertions | 627.9 / 540.4 | 630.0 / 623.6 | 623.5 / 410.6 | 34.1% |
| Published relevance heldout | 89.0 / 81.2 | 90.2 / 88.0 | 87.3 / 61.9 | 29.0% |

Overall P95 reductions are 7.9%, 4.4%, 13.9% and 8.7%. The gain primarily
comes from repeats; there is no established first-use improvement. In the
smallest workload first-pass P95 increases from 119.8 to 121.7 ms. All first-use
misses and outliers remain in the raw data: for example, the 288-assertion
candidate's first-pass maximum is 541.3 ms versus 404.9 ms for its control.
Do not substitute the repeat-only number for overall or first-pass P95.

The governed cross-encoder pair computations fall from 3,024/12,096/12,600/960
to 1,008/4,032/4,200/320: a two-thirds reduction over three exact replays.
All working sets fit the 8,192-score cache and no eviction occurs in this run.
LRU eviction is exercised by tests, not by these headline timings. Changing
queries, text, model profiles or projects causes misses; a one-shot CLI process
does not retain a cache across invocations. The bounds do not prove performance
under larger working sets, concurrent callers or production traffic.

## Reproduction and usable CV scope

With the pinned native/model dependencies, actual PostgreSQL and a clean source
checkout configured, run:

```powershell
uv run python -m eval.retrieval_metrics --output .local/my-metrics-run
uv run python -m eval.metrics_rescore --results .local/my-metrics-run
```

Set `GM_EVAL_DATABASE_URL` and `MEMORY_MODEL_CACHE` for the chosen test stack.
The [manifest](results/retrieval-metrics-v07-2026-11-14/manifest.json) identifies
the actual environment. The benchmark image adds only Git to the installed
model image for source provenance; [its build recipe](Dockerfile.metrics-v07)
is retained. Production images remain unchanged by this extra tool.

A supported project statement is: “On a controlled 1,152-assertion timeline
workload, achieved 100% temporal Recall@5 and zero stale evidence, with 540 ms
overall retrieval P95; bounded score reuse reduced repeat-query P95 by 34.1%.”
Retain the controlled/synthetic and retrieval scope. The figures do not establish
the CV's original benchmark definitions or historical project dates. Deployment,
regressions and artifact identities are in the [verification record](../docs/verification-v0.7.md).
