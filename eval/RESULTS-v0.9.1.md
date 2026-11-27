# v0.9.1 Default Decomposed Relevance Gate (`v2`) and Engineering Corpus Study

Recorded 2026-11-24 (UTC). This study evaluates two additions frozen at commit
`da3e0a0` under [RELEVANCE_V2_AND_ENGINEERING_PROTOCOL.md](RELEVANCE_V2_AND_ENGINEERING_PROTOCOL.md):

1. **Default negative-query filtering (`MEMORY_RELEVANCE_FILTER=auto`,
   `minilm-relevance-v2`):** replaces the previous unfiltered default (`0`) and
   single-scalar short-fact cutoff (`1.4` raw logit, `v1`) with a decomposed
   triple check calibrated strictly on `eval/relevance-dev.json` (`48/48`
   positive dev pairs retained), plus stopword-free lexical overlap in the
   core `HashEmbedder` fallback.
2. **Non-template engineering corpus (`eval/engineering-corpus.json`):** 16
   software-engineering ADR (`.md`) and coding-session (`.jsonl`) records across
   distinct subsystems exercising bitemporal postmortem corrections, rejected
   prompt-injection proposals, source withdrawal, corroborating second-source
   survival, transitive dependency invalidation, and negative developer queries.

Raw observations, aliases, and environment provenance are saved in
[results/relevance-v2-2026-11-24](results/relevance-v2-2026-11-24/manifest.json)
(`dirty_source: false`, zero runtime errors across all 2,412 paired service
observations). No prior `eval/results/` directory was modified.

## 1. Paired Service Results (3 Replays per Query, `k=5`, 1,024 Tokens)

| Workload / Method | Positive Recall | Stale / Returned | Negative Queries Empty | Negative Items Returned | Overall P95 (Repeat P95), ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| **Heldout (`80` blind queries: `48` pos, `32` neg)** | | | | | |
| `unfiltered` (`0`) | **97.92%** (141/144) | 0/810 | 0/96 (0.0%) | 324 | 60.5 (31.8) |
| `strict_v1` (`1.4`) | 93.75% (135/144) | 0/234 | 84/96 (87.5%) | 12 | 57.6 (29.7) |
| `default_v2` (`auto`) | **97.92%** (141/144) | 0/207 | **81/96 (84.4%)** | **15** | 85.0 (28.7) |
| **`timelines_16` (`1,152` assertions, `84` queries)** | | | | | |
| `unfiltered` (`0`) | **100.0%** (180/180) | 0/786 | 0/72 (0.0%) | 225 | 423.4 (301.9) |
| `strict_v1` (`1.4`) | **100.0%** (180/180) | 0/561 | 72/72 (100%) | 0 | 455.5 (301.6) |
| `default_v2` (`auto`) | **100.0%** (180/180) | 0/561 | **72/72 (100%)** | **0** | 595.4 (330.0) |
| **`timelines_1` (`72` assertions, `84` queries)** | | | | | |
| `unfiltered` (`0`) | **100.0%** (180/180) | 0/1008 | 0/72 (0.0%) | 288 | 92.0 (34.7) |
| `strict_v1` (`1.4`) | **100.0%** (180/180) | 0/180 | 72/72 (100%) | 0 | 86.4 (28.6) |
| `default_v2` (`auto`) | 98.33% (177/180) | 0/177 | **72/72 (100%)** | **0** | 94.2 (28.7) |
| **Engineering ADR + Session Corpus (`20` queries: `14` pos, `6` neg)** | | | | | |
| `session_baseline` (unsafe control) | 92.86% (39/42) | 63/180 (35.0%) | 0/18 (0.0%) | 54 | 255.8 (31.4) |
| `unfiltered` (`0`) | **100.0%** (42/42) | **0/180 (0.0%)** | 0/18 (0.0%) | 54 | 186.3 (42.3) |
| `strict_v1` (`1.4`) | **100.0%** (42/42) | **0/51 (0.0%)** | 15/18 (83.3%) | 3 | 174.3 (35.6) |
| `default_v2` (`auto`) | **100.0%** (42/42) | **0/54 (0.0%)** | **12/18 (66.7%)** | **9** | 215.9 (35.9) |

## 2. Archived 500-Question Passage-Branch Replay (`LongMemEval`)

| Method | Gold Session Recall | Answerable Empty (`470`) | Unanswerable Empty (`30`) | Returned Chunks |
| --- | ---: | ---: | ---: | ---: |
| `unfiltered` | **741/890 (83.26%)** | 1 | 0 | 3,990 |
| `strict_v1` (`1.4`) | 341/890 (38.31%) | 206 | 19 | 759 |
| `v2_passage_floor` (`-5.0`) | 611/890 (68.65%) | 63 | 7 | 2,140 |

## 3. Key Findings and Tradeoffs

- **Blind heldout validation:** Without retuning on heldout data, `default_v2`
  preserves the full unfiltered positive recall (**47/48 = 97.92%**, recovering
  both paraphrase queries lost by `strict_v1` at `93.75%`) while emptying
  **27/32 (84.4%)** negative queries and cutting false negative items by **95.4%**
  (`324 -> 15`).
- **Large timeline & engineering corpus:** On `timelines_16` (`1,152`
  assertions), `default_v2` retains **100%** positive recall and **0** stale
  items while eliminating **100% (`225 -> 0`)** of unrelated negative returns.
  On the non-template engineering ADR/session corpus, governed `default_v2`
  reaches **100% (`14/14`)** positive recall with **0** stale/poisoned/withdrawn
  leaks (versus `92.86%` recall and `35.0%` stale/unsafe returns in the session
  control) and cuts negative returned items from `54` to `9` (`-83.3%`).
- **Observed tradeoffs:** Scoring deduplicated `subject` and `predicate: value`
  anchors on prefilter survivors adds first-pass latency on cold caches
  (`timelines_16` overall P95 `423.4 -> 595.4 ms` on local SQLite + Python
  ranking; repeat cached P95 `301.9 -> 330.0 ms`), and one positive query in
  `timelines_1` (`59/60`) falls below the marginal-gain gate. On raw 200-token
  conversational transcripts (`LongMemEval`), the `-5.0` passage floor avoids
  `v1`'s collapse (`68.65%` vs. `38.31%`), though unfiltered ranking (`0`) still
  achieves higher recall (`83.26%`) when abstention is handled downstream.
