# v0.4 controlled temporal/governance comparison

The engineering gaps in the CV capability audit are implemented and exercised.
This controlled run verifies those paths; it does **not** establish the CV's
prewritten 83.2% recall, 26.4% stale-retrieval reduction or 1.12 s P95.

## Observed results

There were **84 unique queries**, repeated three times for each method: **504
retrieval observations**, with **0 runtime errors**. The positive denominator is
60 unique queries × three repetitions; the negative denominator is 24 × three.

| Metric | Session baseline | Governed memory |
| --- | ---: | ---: |
| Temporal recall on positive queries | 100% | 100% |
| Returned assertions | 951 | 1,008 |
| Stale assertions | 597 | 0 |
| Stale fraction of returned assertions | 62.78% | 0% |
| Negative observations returning stale assertions | 72/72 | 0/72 |
| Unrelated, eligible assertions on negative observations | 9 | 288 |
| Warm retrieval latency P50 | 0.837 s | 0.378 s |
| Warm retrieval latency P95 | 3.020 s | **1.264 s** |

The stale-rate reduction is 100% **on this controlled corpus**. There is no recall
gain over the baseline. The speed difference comes from filtering a smaller
eligible corpus before inference; both methods use the same Rust kernels, so this
is not a Rust-versus-Python speed comparison.

All 72 governed negative observations still returned four unrelated but eligible
assertions. Zero stale results therefore does not mean useful empty-result
detection or correct answers. The experiment measures retrieval, not generated
answer accuracy. Its measured P95 is higher than the CV's 1.12 s target.

## Frozen inputs and methods

The [protocol](cv-protocol.json), [fictional timelines](cv-timelines.json) and
[generator](cv_dataset.py) were committed before evaluation. Twelve named services
have database changes, a retroactive correction, a rejected injection, a withdrawn
backup policy and an invalidated derived decision. Gold aliases are explicit and
independent of ledger queries. Tests check all 84 gold eligibility sets against
both SQLite and PostgreSQL.

The baseline ranks session assertions available by `known_at`, under the same
project/source audience. It does not apply approval, valid-time, supersession,
withdrawal or dependency eligibility. The governed method applies those signals
through the authoritative ledger. Both use BM25/cosine RRF, the same pinned
embedding and cross-encoder models, native Rust ranking, `k=5`, a 1,024-token
evidence budget, and no document/query embedding-result cache. Budget packing
explains why fewer than five assertions may be returned.

Methods alternate order, with one warmup query per method. All three repetitions
are retained; none was selected for favorable results. The earlier synthetic
suite includes stronger time-aware controls and remains available separately.
These small, structured fixtures do not measure extraction accuracy, semantic
entity-resolution accuracy, general NLI accuracy or realistic long-history recall.

## Execution and reproducibility

- Source commit: `80377a9f721f43f452b510e8bf80adaf1d746d53`; selected source hash:
  `c71d808a295b9953d98fed8c41f06652c255991fd86e6132dcf649e2a75429f6`.
  The source was clean at execution. The Git commit also pins the shared baseline
  helper in `eval/run.py`.
- Dataset SHA-256, with canonical LF endings:
  `8d3b4087eee2c06381c29c886efc2be38ac226c78f4ea54c7e7a1ddca01a24b1`.
- Run: 2026-11-13, 02:52:05–02:58:16 Asia/Shanghai; UTC timestamps are in the
  manifest/summary. No observations were removed. Maximum latency was 4.979 s.
- Hardware: AMD Ryzen 9 7945HX, WSL2/Docker, 32 logical CPUs available, 7.36 GiB
  guest memory, **two inference threads**, CPU models and one sequential caller.
- Storage: isolated PostgreSQL schema. Graph retrieval was disabled for both
  methods. OpenFGA/OPA network decisions and collector delivery are outside this
  timing comparison; their behavior is verified by integration tests.
- Runtime: Python 3.12.16, CPU PyTorch 2.15.0+cpu, Sentence Transformers 5.7.0,
  Transformers 5.22.2, NumPy 2.5.4, SQLAlchemy 2.0.57.
- Embedding: `all-MiniLM-L6-v2` at
  `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; reranker:
  `ms-marco-MiniLM-L6-v2` at `233902d25c440f23af6f7d6e94d2946bac0bee0a`.

Latency includes SQL eligibility, query/document embeddings, reranking, evidence
packing and serialization. It excludes cold model loading, CLI/process startup,
transport and answer generation. P95 is the linear 95th percentile across all
252 observations per method. It is not an end-to-end production-service SLA.

Reproduce from this source with Python 3.12, a Rust toolchain and the cached models:

```sh
uv sync --frozen --extra dev --extra models --extra native
# Set MEMORY_MODEL_CACHE and GM_EVAL_DATABASE_URL for the desired PostgreSQL instance.
uv run python -m eval.cv_run --output .local/cv-reproduction
```

The runner creates/removes its own schema and refuses to overwrite results.
CPU timing will vary with hardware and load. This run used a non-root, read-only
model container with a read-only cache; the benchmark image adds Git for source
provenance only.

## Retained evidence

The [complete run directory](results/cv-v0.4-2026-11-13) contains the manifest,
candidate/alias map, all observations, summary, image/CI receipt and independent
rescoring receipt. A separate standard-library check verified all 504 unique
method/repetition/query keys, gold/stale labels, token/k limits and P95 values.
The observation SHA-256 is
`f8113a078f43df46c4ac5b69b97d92493fad8412833e0e2a9cdc654285817b85`.

The [v0.3 full 500-question QA report](RESULTS-v0.3.md) is unchanged: the highest
local judge estimate remains 169/500 (33.8%), with all validation failures and the
original timing outlier retained. That estimate and this controlled recall have
different definitions. Neither justifies the CV's original numbers or its
February–May 2025 project dates; those dates require contemporaneous evidence.
