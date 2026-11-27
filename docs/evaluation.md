# Evaluation and Scope

This page summarizes the recorded benchmark runs, their denominators, and the
conditions under which they were collected.

## Recorded measurements

| Task | Observation | Denominator and scope | Source |
| --- | --- | --- | --- |
| Temporal evidence selection | 60/60 positive queries recovered all gold evidence in each workload | 84 queries (60 positive, 24 negative); synthetic fixtures at 72 and 1,152 assertions | [Full-path v0.8.1](../eval/RESULTS-v0.8.1.md) |
| Stale evidence returned | 0/792 returned items in the largest governed case | Includes three replays of the same 84 queries (not 792 independent trials) | [Saved observations](../eval/results/system-baseline-v081-2026-11-16/observations.jsonl) |
| Stale reduction vs. session control | 498/816 -> 0/789 stale returned items | Separate v0.7 session-baseline comparison (synthetic workload) | [v0.7 study](../eval/RESULTS-v0.7.md) |
| Relevance heldout (unfiltered / default `v2`) | **47/48** positive recall (97.92%) in both; negative queries emptied: `0/32` -> **27/32 (84.4%)** (`324 -> 15` items across 3 replays) | 80 blind synthetic queries (48 positive, 32 negative) | [v0.9.1 study](../eval/RESULTS-v0.9.1.md) |
| Non-template engineering ADR + session corpus | **14/14** positive recall (100%), **0/54** stale/unsafe items, **4/6** negative queries emptied (`54 -> 9` items across 3 replays) | 16 ADR/JSONL records, 20 queries vs. session baseline (`92.9%` recall, `63/180` stale/unsafe) | [v0.9.1 study](../eval/RESULTS-v0.9.1.md) |
| Full retrieval latency | P95 0.762 s (first-pass 0.806 s, repeat 0.516 s) | Single CPU host, 2 inference threads, one caller, warmed models, PostgreSQL + Neo4j + OpenFGA + MCP stdio, k=5, 1024 tokens (`v0.8.1` unfiltered baseline) | [Protocol and hardware](../eval/RESULTS-v0.8.1.md#final-baseline-and-source-identity) |
| Optional long-conversation answers | 181/500 accepted by local judge (36.2%) | 500-question answer task graded by a local model | [v0.6 answer evaluation](../eval/RESULTS-v0.6.md) |

Last full-path performance measurement: **v0.8.1**. Subsequent packaging and
documentation releases verify installability and behavior without re-running the
retrieval benchmark.

## Interpreting the synthetic results

- **Controlled fixtures:** The temporal corpus supplies explicit approval,
  validity, withdrawal, and dependency transitions. Achieving 60/60 Recall@5
  confirms rule adherence on these fixtures; the 1,152 assertions expand known
  scenario templates across cohorts rather than 1,152 independent questions, and
  three replays measure cache/timing behavior rather than independent samples.
- **Known quality limits:** With the default decomposed `minilm-relevance-v2`
  gate (`MEMORY_RELEVANCE_FILTER=auto`), blind heldout negative queries empty
  at 27/32 (84.4%) while preserving 47/48 (97.92%) positive recall, and
  `timelines_16` empties 24/24 negative queries with 60/60 positive recall (`59/60`
  in the smaller `timelines_1` pool). Five of 32 heldout negative queries still
  return partial entity/attribute matches, and raw 200-token chat transcripts
  retain higher session recall with `MEMORY_RELEVANCE_FILTER=0` (`83.3%` vs.
  `68.7%`; see [RESULTS-v0.9.1.md](../eval/RESULTS-v0.9.1.md)). Answer
  generation correctness (181/500 local judge) remains much lower than retrieval
  recall.
- **Timing boundaries:** The 0.762 s P95 excludes process and model startup
  (4.95–5.53 s), downloads, ingestion, graph projection, and answer generation.
  Services ran on a single host with one caller; WAN latency and multi-caller
  concurrency are not measured. Earlier v0.8 latency (0.408 s) excluded Neo4j,
  OpenFGA HTTP, and MCP transport and is not directly comparable.
- **Reverted experiments:** A connection-pooling candidate regressed
  largest-case P95 by 8.8% and was reverted; its
  [negative results](../eval/results/system-transport-v1-2026-11-16/summary.json)
  remain in the repository alongside the baseline.
