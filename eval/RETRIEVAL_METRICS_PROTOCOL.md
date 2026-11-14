# Retrieval metrics protocol v2

Frozen before implementation and canonical measurement, 2026-11-14. The user
authorized pursuing stronger measured recall, stale filtering and latency. The
original CV numbers are aspirations, not labels, calibration targets or reasons
to discard runs. All prior protocols and results remain unchanged.

## Proposed change and gates

A diagnostic of v0.6.1's default unfiltered, document-cached service found mean
authority work of 46.3 ms, reranking of 42.7 ms and query encoding of 10.1 ms.
These are diagnostic timings, not a controlled version-to-version speedup.

Add a bounded LRU of deterministic query/passage reranker scores. Keys include
project, model class/profile, and SHA-256 of exact query and passage. Cache no
text, credentials, eligibility, ordering or responses. Keep all existing live
authority checks. Default capacity is 8,192 scalar scores (range 0..10,000);
zero disables it. Document-vector capacity stays 2,048. Relevance rejection
stays disabled by default. Do not change ranking, thresholds, models or budgets.

Promotion requires identical ordered evidence IDs and token counts to the
governed score-uncached control for every successful paired observation, no
stale result, and passing authority/cache regressions. Report all failures and
regressions. A gain on repeat hits alone must be described as such; unique or
first-use P95 cannot be replaced by warm P95. Do not tune on the measured data.

## Workloads and labels

Use the unchanged 80-question published relevance heldout set and the unchanged
84-query CV timelines at 1, 4 and 16 replicated cohorts: 72, 288 and 1,152
historical assertions, respectively. `metrics_cases.py` generates these expanded
fixtures deterministically. It prefixes entity names and source aliases with a
cohort name, preserves every original lifecycle and dependency, and assigns
query i to cohort i modulo the cohort count. Each size retains all 84 original
query types; its eligible labels span all cohorts and gold refers to the queried
cohort. Retain generated fixtures and their checksums before model inference.

This is a scalability stress test derived from previously examined synthetic
templates, not new independent data, realistic production history or blind
external accuracy. Explicit labels remain independent of ledger visibility.
The 80-question heldout data were also previously evaluated. No label-based
selection is needed for a computation cache. Do not rerun the 500-question
answer generator or treat old answer outputs as new scores.

## Paired experiment

Use real isolated PostgreSQL schemas, the existing pinned CPU MiniLM models,
two inference threads, native Rust ranking, k=5 and 1,024 evidence tokens. One
caller executes three repetitions, rotating method order by query index plus
repetition. Share the loaded inference models; keep separate caches per method
and workload. Warm only one unrelated query/passage before measurement, without
pre-encoding measured documents or queries. Retain all first-use misses.

Three methods:

1. Session-retrieval control: assertions received by known_at and current
   project/source audience, without fact approval, validity, supersession,
   withdrawal or dependency filtering. Give it both vector and score caches,
   too; it is an unsafe experimental control, not a deployable configuration.
2. Governed control: current v0.6.1 behavior, document cache enabled, no score
   cache, no relevance cutoff.
3. Governed candidate: same eligibility, ranking and document cache, plus the
   score cache, no relevance cutoff.

Time retrieval from the initial ledger lookup through serialization, including
all live checks, embeddings, reranking and evidence packing. Exclude ingestion,
model loading, transport and answer generation. Compare within this run only.
Graph retrieval and external authorization HTTP calls are disabled here, as in
the original controlled CV protocol; they remain covered by integration tests.
These timings do not establish full graph/remote-policy or concurrent capacity.
Record per-observation IDs, explicit gold/eligible IDs, tokens, errors, latency,
reranker pair computations, cache counters and repetition. No silent retries.

Report per workload/method: positive macro gold recall; returned and stale
counts/rates; relative stale-rate reduction when baseline rate is nonzero;
negative unrelated evidence; overall, first-repetition and repeat P50/P95;
pair computation counts and cache hits/evictions. Never pool the fixture sizes
or repeats as independent questions. Also report pairwise output equivalence.

Archive source/data/model/package/hardware identities, raw observations, all
failed attempts, independent aggregate/hash checks, installed runtime and MCP
cache-hit revocation checks, and required repository CI. Freeze source before
the canonical run; verify it has not changed afterwards. Any implementation
change following measured outcomes requires a new versioned run and preserves
the old attempt. The final CV wording must retain workload and timing scope.
