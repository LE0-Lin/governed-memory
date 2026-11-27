# Authority read comparison v1

Frozen before implementation and canonical measurement, 2026-11-15. Every completed round reports same-run paired changes alongside explicit scope boundaries. Prior results stay unchanged.

## Diagnosis and scope

A diagnostic of installed v0.7.0 with 1,152 synthetic historical assertions and
warm model caches observes mean retrieval 208.4 ms: the four authority reads take
45.6/33.2/45.8/33.4 ms, together about 76%. Packing takes 19.1 ms. This diagnostic
is not a before/after speedup; host conditions differ from previous runs.

Optimize only two related read costs. Do not materialize the unused primary
Source ORM object in the main visibility query (retain its join and all source
checks). Add an optional exact-snapshot filter to the existing visibility query.
After reranking has narrowed the pool, use it for the final live lookup. Keep
all existing authentication, time, source/audience, dependency and provenance
checks. Preserve empty-result reason codes by falling back to a full fresh read
when the selected subset disappears. Do not narrow the pre-reranker check,
which must still allow lower-ranked survivors after a concurrent withdrawal.

No eligibility cache or authorization bypass is permitted. Do not change model
revisions, inference resources, caches, ranking, token packing, cutoffs or answer
generation. Only ledger.py and retrieval.py may differ from the reference among
runtime source files. Require the same exact ordered evidence payload, token
count and reason as v0.7.0 for every paired observation, zero stale results,
and passing permissions/time/dependency/concurrency regressions.

## Actual reference and paired workloads

Load the exact reference Ledger and Retriever source blobs from commit
df8349b7abfcdd8485868225e6bb74589f397edb (v0.7.0). Validate that every other
reference runtime/native file is unchanged before loading it. Both classes use
the same authoritative database, fixed clock, models, kernels and independent
caches. Retain reference file hashes and the reference commit. Do not estimate
a version speedup by subtracting an old run's latency from a new one.

Use all four unchanged v0.7 workload recipes: 72/288/1,152 synthetic historical
assertions with 84 query instances per size, and the known 80-query relevance
heldout set. Materialize and hash their fixtures before inference. They reuse
previously examined templates and labels, and are not independent real-world or
blind data. This cache/read optimization does not learn from their labels.

Two methods, reference_v07 and targeted_refresh, both with document capacity 2048,
score capacity 8192, no cutoff, native Rust, k=5, token budget 1024, actual isolated
PostgreSQL and pinned CPU MiniLM models with two inference threads. Share loaded
models, retain separate caches, and warm only unrelated text. Run three replays
with method order rotating by query index plus repetition, one caller.
Expected observations: (84*3+80)*2*3=1,992, with 996 exact paired comparisons.

Record every query's explicit gold/eligible IDs, predicted IDs, evidence payload
hash, tokens, errors, reason, latency and repetition. Report per workload positive
macro gold recall, stale counts/rates, negative unrelated evidence, and overall,
first-pass and repeat P50/P95. Preserve all errors, outliers and failed attempts.
Do not pool correlated repetitions as independent questions. Cache misses and
first-pass costs stay in overall metrics. No speedup threshold is used to hide
negative outcomes; first-pass and repeated gains must be distinguished.

Timing includes live SQL, embeddings, ranking, packing and serialization;
excludes model loading, ingestion, graph retrieval, external authorization HTTP,
transport and answer generation, as in v0.7. Compare within this run only.

## Verification and reporting

Independently reconstruct gold/eligibility from saved fixtures and alias maps;
verify the complete observation grid, all summary groups and pairwise equality.
Archive source/protocol/data/model/hardware/package fingerprints and all raw
observations. Freeze source before the canonical run; verify no source changes
through completion. Subsequent implementation changes require another preserved
versioned run. Run required CI and actual installed MCP/authority checks.

The completion report must state whether this round met its promotion gate, give
reference-to-candidate numbers and relative changes, and state remaining scope
boundaries (such as full graph/remote-policy transport and multi-caller load).
No new 500-question answer-generation run is in this scope.

Execution-environment note, frozen before canonical measurement: the local C:\ volume exhausted space and Ubuntu reported I/O errors before a candidate benchmark could start. The canonical comparison therefore runs on one isolated GitHub-hosted Ubuntu CPU runner with PostgreSQL. Both versions share that runner and all resources. Record its hardware and run ID; do not compare its absolute latency to the earlier Ryzen/WSL run. Existing local model/data/image files are retained, and local deployment is not claimed after this fault.
