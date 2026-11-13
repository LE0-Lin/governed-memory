# Retrieval quality and latency protocol (v1)

Frozen before calibration or new heldout results. The v0.3/v0.4 outputs stay
unchanged. The CV's prewritten numbers are not optimization or selection targets.

## Diagnosis and implementation scope

The v0.4 neural path always returns the highest ranked eligible documents, even
when every relevance score is low. It recomputes unchanged document embeddings
on every query. A diagnostic profile on the current machine measures SQL checks,
query/document encoding and reranking separately; diagnostic timings are not the
headline before/after comparison.

Add a model-specific relevance cutoff and a bounded document-vector cache.
Authentication, current source access, temporal eligibility, dependency checks and
the final authority recheck remain live. The cache stores vectors, never tokens,
source bodies, ACL decisions or serialized responses. Keys include project, model
profile and exact text hash. Query vectors are not cached.

## Calibration and independent validation

`relevance-dev.json` and `relevance-heldout.json` contain separate entities and
topics. Each split has eight four-fact groups and 80 queries (48 answerable,
32 unanswerable), including paraphrases, short keyword queries, wrong attributes,
unknown entities and unrelated questions. These are synthetic contract fixtures,
not a population sample or a claim of general QA accuracy.

The cutoff is calibrated using **only development scores**, from the pinned
`cross-encoder/ms-marco-MiniLM-L6-v2` with Identity activation (raw logits).
Choose the highest cutoff on a 0.1 grid retaining at least 95% of labeled positive
development query/document pairs. Store every calibration pair score, the
selection rule, model revision and data checksum. Freeze that artifact before
scoring heldout data. Sigmoid-transformed logits are not calibrated probabilities.
Do not reselect the cutoff using heldout, legacy CV or external outcomes.

Heldout metrics include positive gold Recall@k, answerable queries made empty,
unanswerable queries made empty, residual irrelevant context, errors and token
limits. Report raw counts and tradeoffs, including failures. A cutoff with poor
transfer must be reported as such, rather than silently adjusted.

## Paired service experiment

Run three methods against the same actual authorized ledger and neural models:

1. v0.4 behavior: no relevance cutoff, no document cache.
2. Cutoff only: the frozen cutoff, no document cache.
3. Cutoff plus bounded document cache (2,048 entries).

Use `k=5`, 1,024 evidence tokens, Rust ranking, CPU inference with two threads,
one caller and an isolated PostgreSQL schema. Replay both the unchanged 84-query
CV workload and the new 80-query heldout workload. Three measured repetitions
rotate method order. Warm each method with one unrelated synthetic query; do not
pre-encode the measured corpus. Retain first-use cache misses in the overall
results and also report later warm repetitions. Model loading, ingestion,
transport and generation are outside retrieval latency. Include serialization,
all current authorization checks, embedding work and reranking.

Report P50/P95, embedding computations, cache occupancy/eviction behavior,
positive recall and empty-result quality separately. Compare the three methods
within this run, not a new idle-machine result against the old v0.4 timing run.
The old 1.264 s result remains a historical observation.

## External evidence replay

Apply the frozen cutoff to the already archived v0.3 full-S cross-encoder outputs
for all 500 questions. Verify the original prediction checksum and the public
dataset checksum. Reconstruct chunk IDs with the original pinned tokenizer, then
retain only originally packed chunks whose archived raw score meets the cutoff.
Save the new retrieval decisions before opening `answer_session_ids` for scoring.
This is a counterfactual replay of previously examined external data, not a new
blind benchmark, new generation run or latency measurement.

Measure context rejection on 30 abstention questions, false rejection on 470
answerable questions and gold-session recall. Do not reuse old generated answers
after changing their context and do not claim improved answer accuracy without
new answer generation and scoring. Preserve the original full500 outputs.

## Required regression evidence

Tests cover cache bounds/eviction, exact text/model/project keys, mutable-input
isolation, invalid model output, cache-hit source withdrawal and grant removal,
concurrent context changes, cutoff boundary/ties, and no generator invocation
when relevant evidence is absent. Exercise actual pinned models and the installed
service/container workflow, then run the repository's required checks. Archive
raw observations, all errors, source/data/model fingerprints, calibration and
independent rescoring receipts.
