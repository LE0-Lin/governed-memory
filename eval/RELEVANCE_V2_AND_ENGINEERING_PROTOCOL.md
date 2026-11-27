# Decomposed Relevance Gate (`v2`) and Engineering Corpus Protocol

Frozen before running the paired evaluation on `relevance-heldout.json`,
`controlled-timelines` (`72` and `1,152` assertions), `LongMemEval` archived contexts,
and `eval/engineering-corpus.json`.

## 1. Hypothesis and Design

Previously, `Settings.retriever()` defaulted `MEMORY_RELEVANCE_FILTER` to `"0"`
(unfiltered), returning up to `k` unrelated eligible assertions on negative
queries, because the single-scalar `v1` cutoff (`1.4` raw logit) lost recall on
paraphrases and long passages.

`minilm-relevance-v2` replaces the single scalar with a decomposed check
calibrated strictly on `eval/relevance-dev.json` (retaining 48/48 positive
development pairs):

1. **Passage branch** (`len(words(value)) > 32` or non-triple text): require
   `full_score >= -5.0`, preserving multi-sentence conversational chunks while
   rejecting off-topic hits (`~ -11` raw logit).
2. **Structured-triple branch** (`subject | predicate: value` with `<= 32` value
   words):
   - `full_score >= -1.2`
   - `max(score(query, subject), score(query, f"{predicate}: {value}")) >= -3.0`
     (rejects `unknown_entity` queries where neither side anchors the query)
   - when `content_words(query) - content_words(subject)` is non-empty,
     `full_score - score(query, subject) >= 0.8` (rejects `missing_attribute`
     queries where `predicate: value` contributes no relevance gain over
     `subject` alone).

Only candidates surviving the initial prefilter floor are scored for deduplicated
`subject` and `predicate: value` parts, through `RerankScoreCache` when enabled.

## 2. Workloads and Paired Methods

All runs execute sequentially on a single host with pinned CPU models
(`all-MiniLM-L6-v2` and `ms-marco-MiniLM-L6-v2`, 2 inference threads), `k=5`,
`token_budget=1024`, document cache `2048`, rerank score cache `8192`, and
three method-rotated replays per query where latency is compared:

1. **`timelines_1` (72 assertions, 84 queries)** and **`timelines_16` (1,152
   assertions, 84 queries)**: compare `unfiltered` (`MEMORY_RELEVANCE_FILTER=0`),
   `strict_v1` (`1.4`), and `default_v2` (`MEMORY_RELEVANCE_FILTER=auto`).
2. **`relevance-heldout.json` (80 queries: 48 positive, 32 negative)**: blind
   evaluation of `unfiltered`, `strict_v1`, and `default_v2` (not used during
   calibration).
3. **`engineering-corpus.json` (16 non-template ADR/session records, 20 queries:
   14 positive, 6 negative)**: compare `session_baseline` (unsafe session-only
   control without governance/temporal/withdrawal/dependency checks),
   `governed_unfiltered`, and `governed_default_v2`.
4. **Archived `LongMemEval` 500-question passage replay** (when dataset file is
   present locally): verify passage-branch recall (`-5.0`) versus `unfiltered`
   and `strict_v1` (`1.4`).

## 3. Recording Rules

- Commit implementation, corpus, and protocol before canonical execution; the
  runner rejects dirty tracked source or existing output directories.
- Retain all raw observations, manifests, failure counts, and latency
  percentiles without overwriting any historical directory under `eval/results/`.
