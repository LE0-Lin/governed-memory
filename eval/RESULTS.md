# Recorded synthetic run — 2026-11-09

The frozen suite completed **192 queries × 4 methods = 768 retrieval calls**, plus 24 unauthorized-approval attempts and 24 legitimate-approval controls. There were no execution failures. The corpus contains 24 synthetic timelines from 8 families; variants within a family are correlated. This is a behavior demonstration, not a general memory benchmark or proof of security.

Raw outputs: [predictions](results/2026-11-09/predictions.jsonl), [operations](results/2026-11-09/operations.jsonl), [summary](results/2026-11-09/summary.json), [run provenance](results/2026-11-09/provenance.json), [scoring provenance](results/2026-11-09/scoring.json).

## Heldout retrieval/time controls

These 33 queries include 30 answerable cases with 45 required evidence items and 3 empty-gold cases. The common limit is k=3 and 1,024 evidence tokens.

| Method | Evidence Recall@3 | All required evidence found | Stale / returned evidence | P50 / P95, ms |
| --- | ---: | ---: | ---: | ---: |
| Recent structured sessions | 93.33% | 90.00% | 27 / 84 | 2.10 / 3.89 |
| BM25 + lexical hash vectors | 86.67% | 80.00% | 30 / 69 | 2.81 / 4.03 |
| Same hybrid + correct time handling | 100.00% | 100.00% | 0 / 45 | 2.11 / 2.90 |
| Complete governance | 100.00% | 100.00% | 0 / 45 | 5.12 / 7.48 |

The strong temporal baseline matches the full service on these controls. This run therefore provides no evidence of a retrieval-quality gain from approval alone in ordinary time queries. Full governance adds SQL authorization/revalidation work and is slower in this small local test.

## Heldout governance controls

Across all 96 heldout queries, 66 are answerable and 30 require abstention. The success fractions below use only the matching attack category; total unapproved/withdrawn evidence across all categories is retained separately in `summary.json`.

| Method | Unapproved retrieval successes / attempts | Withdrawal leak queries / attempts | Answerable query coverage | Correct empty-gold cases |
| --- | ---: | ---: | ---: | ---: |
| Recent structured sessions | 27 / 30 | 15 / 15 | 66 / 66 | 15 / 30 |
| Hybrid | 27 / 30 | 15 / 15 | 66 / 66 | 15 / 30 |
| Hybrid + temporal | 27 / 30 | 15 / 15 | 66 / 66 | 15 / 30 |
| Complete governance | 0 / 30 | 0 / 15 | 66 / 66 | 30 / 30 |

The governed service returned 84 heldout evidence items with 84 complete provenance records, no stale evidence, no unapproved evidence and no withdrawn evidence. Across both splits, unauthorized approvals succeeded **0 / 24** times and legitimate approvals succeeded **24 / 24** times. The source audience controls are in the dev family; all retrieval methods share the same current access filtering, so their comparison is not evidence that one scorer enforces access better than another.

The temporal-only ablation can follow a newer unapproved assertion that has a valid effective date. Approval and current withdrawal signals are deliberately absent from that ablation, so these differences demonstrate the configured policy boundary, not superior semantic retrieval. The protected-fact role distinction and concurrent approvals are covered by regression tests rather than inferred from these aggregate attack counts.

## Failure analysis and cost

- Multiple-evidence questions can lose an older necessary fact when an unfiltered method fills k with several versions of another fact. Saved `multi_evidence` predictions show these misses; hit-any and hit-all are kept separate.
- A correctly dated unapproved statement replaces an approved assertion in the temporal-only source history. Saved `protected_poisoning` queries show why time filtering alone cannot supply an approval signal.
- A source withdrawn today remains visible to receipt-time baselines, including historical questions. The governed API applies today's withdrawal restriction to those questions.
- Recent sessions can return unrelated annotations and a source received before its approval. The baseline operates on annotated records, not full transcript chunks, which limits what this comparison establishes.

Across all 96 heldout queries, governed P50/P95 was **4.78 / 7.07 ms** versus **1.91 / 2.85 ms** for hybrid + temporal. These figures include local source loading, query/document lexical hashing, ranking, packing and serialization, with one sequential caller and no embedding-result cache. They exclude ingestion, process startup, transport, answer generation and initial tokenizer loading. The run used Windows 11, Python 3.12.0 and SQLite; machine and package details are in provenance. They are **not Graphiti/Neo4j or external-model latency measurements**.

## Traceability and limits

Retrieval was run from clean source commit `83cce6f14d2718560de3af8bd7eceacce60b9107` using dataset SHA-256 `79409d2e485d8f299ffdc1a75f22e9c2ec54948ebe71d72fecf166b52a8fa772`. The first aggregate scorer counted leak queries from all categories against a narrower attack-category denominator. Commit `121c6cc` corrected that numerator and added a regression. `eval.summarize` recomputed aggregates from the original predictions; the original timing samples and retrieval outcomes remain in this report. `scoring.json` identifies that correction and hashes the raw output and scorer.

No learned embeddings, cross-encoder, answer generator, LongMemEval sample, production conversation, throughput test or significance estimate is included. Perfect governed outcomes on this small hand-authored suite establish its expected examples and regressions only. More realistic source extraction, semantic relevance, independent data and scale remain open evaluation work.
