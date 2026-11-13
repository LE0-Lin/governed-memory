# v0.5: relevance rejection, vector reuse and transfer evidence

Recorded on 2026-11-14, Asia/Shanghai. The main improvement that is enabled by
default is bounded reuse of learned document vectors. Relevance rejection is
**opt-in**: it helps these short-fact fixtures but transfers poorly to the
archived long-conversation benchmark. All previous v0.3/v0.4 outputs remain
unchanged. No new answer generation or answer-accuracy claim is made here.

## Frozen inputs and execution

The [protocol](RETRIEVAL_QUALITY_PROTOCOL.md), machine-readable
[configuration](retrieval_quality_protocol.json), separate development/heldout
fixtures and calibration rule were committed before calibration or validation.
The development-only artifact was then frozen before either validation run.
The selected cutoff is **1.4 raw logit**, retaining 46/48 positive development
pairs; it also empties 24/32 development negative queries. It is tied to the
pinned MiniLM cross-encoder revision, not a universal probability threshold.
The cutoff was not reselected after seeing any validation result.

The [service run](results/retrieval-quality-v05-2026-11-14/manifest.json) uses
isolated PostgreSQL schemas, actual CPU MiniLM embedding/reranking, two inference
threads, Rust ranking, one caller, `k=5` and 1,024 evidence tokens. Three methods
alternate by query and repetition. Loading and ingestion are excluded from
timing; all live ledger checks, embedding, reranking, evidence packing and
serialization are included. Transport and generation are excluded. Warmup uses
unrelated synthetic text, with no measured-corpus pre-encoding. First-use misses
remain in the overall latency distribution.

The frozen implementation commit is `41df31c1a08eab38156fc70c8476ff68339f4797`;
selected source SHA-256 is
`9a6b2db838035416816e88186d9b2c275b10986c8714a230078b9c9c00299db3`.
It runs from a read-only source mount in the existing CPU benchmark image, with
its unchanged native 0.4 extension. The manifest identifies the actual dependency
versions and model revisions. Installed v0.5 runtime images are validated
separately; this was not an HTTP load test or a cold CLI measurement.

## Paired service results

All **1,476 observations** completed without runtime errors or stale evidence.
Each unique query is repeated three times; repetitions are not independent new
questions. Positive recall measures the fraction of labeled required fact IDs
returned per positive query, averaged over queries. Empty negative retrieval
does not establish factual answer accuracy.

| Workload / configuration | Positive gold recall | Positive empty | Negative empty | P50 / P95, ms | Document encodings |
| --- | ---: | ---: | ---: | ---: | ---: |
| Legacy CV, no cutoff or cache | 100% | 0/180 | 0/72 | 162.8 / 195.1 | 3,024 |
| Legacy CV, cutoff | 100% | 0/180 | 72/72 | 158.3 / 191.9 | 3,024 |
| Legacy CV, cutoff + cache | 100% | 0/180 | 72/72 | 121.1 / 149.3 | 36 |
| New heldout, no cutoff or cache | 97.92% | 0/144 | 0/96 | 131.5 / 168.0 | 960 |
| New heldout, cutoff | 93.75% | 9/144 | 84/96 | 130.1 / 164.8 | 960 |
| New heldout, cutoff + cache | 93.75% | 9/144 | 84/96 | 105.8 / 141.8 | 32 |

Within the same filtered configuration, caching reduces P95 by **22.2%** on
legacy CV and **14.0%** on heldout. All paired cached/uncached retrieved ID lists
are identical. Document computations fall by 98.8% and 96.7%, respectively.
Cache occupancy is 36 and 32 entries, with no eviction in these small workloads;
bounded eviction is exercised by regression tests. Later-repetition P95 values
are retained in the raw summary, rather than substituting them for overall P95.

On unique heldout queries the cutoff empties **28/32 negative queries** (87.5%)
and **3/48 positive queries** (6.25%). The three false empty results are all
paraphrases: redistribution terms for Orchid library (Apache 2.0), the invoice
interval for Finch subscription (quarterly), and the recording container for
Vesta (FLAC). Their gold scores are below the frozen cutoff. The unfiltered
baseline also misses one gold fact without producing an empty result. Filtering
reduces irrelevant negative-context items from 312 to 12 across repetitions,
but does not solve answerability. These failures were not removed or retuned.

The old v0.4 P95 of 1.264 s was observed under different host conditions. An
unchanged-v0.4 diagnostic before this implementation was already much faster on
the current host. Therefore **1.264 s versus 0.149 s is not an attributable
optimization speedup**. Only the paired measurements above support that claim.
These small synthetic catalogs establish neither general latency nor production
capacity. The frozen three-way experiment measures cache effects with filtering
enabled; it does not measure the default unfiltered-plus-cache combination.

## All500 archived external replay

The [completed replay](results/relevance-replay-v05-2026-11-14-v2/provenance.json)
verifies the original full500 prediction checksum and the pinned public dataset.
It reconstructs contexts with the original tokenizer, verifies original packed
IDs/token counts, and applies the frozen cutoff to archived candidate logits.
New decisions are saved before opening gold session labels. This is a
counterfactual replay of previously examined data, **not a new blind benchmark**.

| Metric | Archived unfiltered | Frozen cutoff |
| --- | ---: | ---: |
| Answerable questions | 470 | 470 |
| Answerable questions with empty context | 1 | 206 |
| Unanswerable questions with empty context | 0/30 | 19/30 |
| Required gold sessions retrieved | 741/890 (83.26%) | 341/890 (38.31%) |
| Positive questions with any gold session | 446/470 | 262/470 |
| Returned chunks | 3,990 | 759 |

Rejecting 19 negative contexts comes with a substantial false-rejection cost.
That rules out enabling this synthetic-development cutoff globally. Operators
can explicitly enable it for a validated short-fact workload; the default keeps
unfiltered ranking. The old full500 answer outputs and best local judge estimate
of 169/500 (33.8%) remain historical, unchanged results. Old answers are not
rescored against a changed context, and this replay makes no new latency claim.

Three incomplete attempts and their failure records are retained. Public
histories can reuse a session ID at different dates; the original chunk ID omits
the date. The initial replay incorrectly assumed unique IDs, and the first fix
also rejected unused ambiguous corpus chunks. The completed runner preserves
archived occurrences, checks corpus multiplicity, and rejects ambiguity if
packing consumes that candidate. Both repeated candidate IDs were outside the
original packed prefix and below the cutoff. All 500 original packed contexts
were reproduced. This repair changes replay bookkeeping, not the frozen cutoff
or any original benchmark output.

## Reproduction and independent checks

Raw [service observations](results/retrieval-quality-v05-2026-11-14/observations.jsonl),
[summary](results/retrieval-quality-v05-2026-11-14/summary.json),
[external decisions](results/relevance-replay-v05-2026-11-14-v2/predictions.jsonl)
and [external summary](results/relevance-replay-v05-2026-11-14-v2/summary.json)
are committed. The [independent receipt](results/retrieval-quality-v05-2026-11-14/independent-verification.json)
checks frozen fixture labels/aliases, complete case coverage, current eligible
IDs, error/token limits, cache prediction equality, all metric counts and P95.
It separately verifies every external filtering decision and session metric
without importing either runner's scoring functions.

Canonical LF SHA-256 values:

- Service observations: `6101ac52814b28be4e209ec7da22248ba2a004ff58f84e21ff74353ebb6cc516`.
- Replay decisions: `8eb5c15e558e355a2085ea190544577d15db7ac8d2f5f0b67e2ac6f2ab0f5266`.
- Original full500 predictions: `6f2d609e91d6791b839b49c89e9d530491ec9e2c0918cfec5aa02008b21985f6`.

With the locked model dependencies and pinned weights cached:

```sh
GM_EVAL_DATABASE_URL=postgresql+psycopg://... MEMORY_MODEL_CACHE=... \
  uv run python -m eval.retrieval_quality --output .local/new-quality-run
MEMORY_MODEL_CACHE=... uv run python -m eval.relevance_replay \
  --dataset PATH/longmemeval_s_cleaned.json --output .local/new-replay
uv run python scripts/check_retrieval_evidence.py \
  --service eval/results/retrieval-quality-v05-2026-11-14 \
  --replay eval/results/relevance-replay-v05-2026-11-14-v2 \
  --dataset PATH/longmemeval_s_cleaned.json --output .local/new-independent-receipt.json
```

The service run requires the optional native extension; the environment must
match the frozen protocol for a comparable timing run. Output paths must be
fresh. [Runtime behavior](../docs/usage.md#relevance-filtering-and-vector-reuse)
describes cache lifetime, current withdrawal checks and the opt-in filter.
