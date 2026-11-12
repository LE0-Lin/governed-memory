# v0.3 full cleaned-S answer evaluation

All 500 pinned LongMemEval cleaned-S questions were evaluated with three retrieval
methods in two runs: unconstrained JSON (v1) and schema-constrained JSON (v2).
Each run retains all 1,500 outputs, including failures. Both runs completed with
zero retrieval/generation runtime errors and unchanged inference source hashes.

The constrained run's best **local judge estimate is 169/500 (33.8%)**, from
hybrid retrieval with the cross-encoder. This is a modest prototype result,
not the official GPT-graded LongMemEval score or a human assessment. The earlier
14-question retrieval result remains a separate measurement.

## Protocol and integrity

- Dataset: cleaned-S revision `98d7416c24c778c2fee6e6f3006e7a073259d48f`, SHA-256
  `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
- All 500 IDs, all supplied histories except future sessions; k=8, 2,048 evidence
  tokens, 200-wordpiece windows/40 overlap and rerank pool 50.
- Generator: pinned Qwen2.5-1.5B-Instruct, greedy decoding, 384 output tokens and
  a 4,096-token complete prompt. Reference answers and answer-session labels do
  not enter retrieval or generation.
- v1 inference commit `54b2593`; v2 inference/scoring commit `bdb3112`. The v2
  protocol was frozen after inspecting JSON shape failures, before reading
  reference answers or semantic scores. IDs, models, prompts and retrieval
  settings stayed fixed; only JSON token constraints were added.
- One sequential caller on an RTX 4080 Laptop 12 GB, PyTorch 2.8.0+cu128,
  Transformers 5.22.2 and bfloat16 generation. Exact revisions and package
  exports are in [the protocol](FULL_PROTOCOL.md) and
  [GPU environment](GPU_ENVIRONMENT.md).
- All 1,500 retrieval contexts match between v1 and v2. Independent saved-ID
  retrieval rescoring reproduces both summaries. Question/method pairs have no
  duplicates or omissions; answer-accuracy counts were independently checked
  against the complete 500-question denominators.

Later release fixes select actual CPU wheels for the optional CPU installation
and make CLI JSON UTF-8 on legacy Windows pipes. They do not alter these saved
GPU runs. Use their recorded commits/environments when reproducing predictions.

## Answer results

The separate pinned Qwen3-4B-Instruct-2507 judge uses the frozen category rules.
Both scoring stages passed 20/20 simple synthetic calibration items and produced
zero invalid/failed judgments. These checks do not establish grading reliability
on complex questions. Invalid answers count as non-passing, including fallback
abstention text; every method's accuracy denominator is 500.

| Retrieval | v1 local judge | v2 local judge | Answer validation failures, v1 → v2 | v2 exact match | v2 mean token F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 | 22/500 (4.4%) | 132/500 (26.4%) | 419 → 160 | 13.4% | 0.220 |
| Learned hybrid | 13/500 (2.6%) | 151/500 (30.2%) | 431 → 130 | 16.1% | 0.248 |
| Hybrid + cross-encoder | 14/500 (2.8%) | 169/500 (33.8%) | 448 → 108 | 17.7% | 0.272 |

Exact match and token F1 use 440 answerable, non-preference questions, retaining
answer failures as zero. Preference rubrics and the 30 abstention questions are
excluded from those lexical metrics. The judge uses all 500 questions.

The improvement includes fewer output-validation failures. It does not isolate
better semantic reasoning. Both generator and judge are small Qwen models, and
their errors may be correlated. No human review, training-data independence,
statistical significance or generalization to unseen data is claimed.

### Constrained results by category

| Category | Questions | BM25 correct | Hybrid correct | Hybrid + cross-encoder correct |
| --- | ---: | ---: | ---: | ---: |
| abstention | 30 | 14 | 16 | 15 |
| knowledge-update | 72 | 28 | 34 | 38 |
| multi-session | 121 | 10 | 7 | 19 |
| single-session-assistant | 56 | 31 | 37 | 36 |
| single-session-preference | 30 | 3 | 10 | 10 |
| single-session-user | 64 | 32 | 30 | 30 |
| temporal-reasoning | 127 | 14 | 17 | 21 |

## Format failures remain observable

There were 1,497 actual model outputs per run; three no-evidence outputs used
the fixed abstention without a model call. Parseable JSON
(including the parser's accepted JSON fences) increased from **405/1,497 (27.1%)
to 1,470/1,497 (98.2%)**. Passing JSON syntax does not imply valid citations or
correct content.

- v1: 1,298 outputs failed validation. Failures included malformed JSON,
  wrong field types and answers without required text/citations.
- v2: 398 failed validation: 356 lacked required text/citations, 15 abstentions
  cited evidence, and 27 JSON strings were unfinished. Twenty-six outputs hit
  the token limit; one unfinished string ended with an EOS token. Every failed
  output remains in the archive and the accuracy denominator.
- The parser accepted 78 cited model answers in v1 and 925 in v2. It accepted
  121 and 174 model abstentions respectively. These are structural counts,
  not counts of factually correct answers or correctly identified abstentions.

The application keeps the final parser and authorization checks after schema
decoding. Malformed text fails closed; generated answers never become facts.
Citation entailment was not scored in this experiment.

## Retrieval results

The following counts are identical in both runs. Session recall uses 890 target
sessions across 470 answerable questions; hit-all uses those 470 questions.

| Method | Target sessions recalled | Hit-all | Query p50 / p95, v2 | Mean evidence tokens |
| --- | ---: | ---: | ---: | ---: |
| BM25 | 672/890 (75.5%) | 329/470 (70.0%) | 6.1 / 9.8 ms | 1570 |
| Learned hybrid | 716/890 (80.4%) | 356/470 (75.7%) | 15.0 / 19.8 ms | 1611 |
| Hybrid + cross-encoder | 741/890 (83.3%) | 372/470 (79.1%) | 54.4 / 69.8 ms | 1596 |

All three methods returned context for all 30 unanswerable questions. Retrieval
alone therefore does not establish correct abstention. Full-set learned
retrieval has higher observed recall than BM25 here; the earlier 14-question
CPU run showed no reranking gain. They have different scopes and both records
are retained.

## Latency, tokens and the interrupted host

| Method | v1 retrieval + answer p50 | v2 retrieval + answer p50 | v2 p95 |
| --- | ---: | ---: | ---: |
| BM25 | 1.634 s | 1.917 s | 10.908 s |
| Learned hybrid | 1.672 s | 1.998 s | 14.672 s |
| Hybrid + cross-encoder | 1.712 s | 2.059 s | 14.073 s |

Per-history indexing is separate: v2 median lexical index 0.222 s and embedding index 0.712 s. Warmup used unrelated synthetic text; there was no query/answer cache.
These are laptop measurements, not serving-throughput or production-scale claims.
Response lengths and validation outcomes differ between runs, so the latency
change does not isolate the overhead of the format library.

**A long host/monitoring interruption occurred during v2.** Case `4d6b87c8`
logged 18,432.5 seconds overall; its cross-encoder answer timer recorded
18,427,368.1668 ms. The cause was not established. The process survived and
continued; the original outlier is included in all raw timings/summaries.
See [the interruption receipt](results/longmemeval-full-2026-11-12/timing-interruption.json).
Total v2 wall-clock time must not be presented as continuous GPU work, and these
timings do not establish an isolated performance comparison.

- v1: 2,340,130 prompt tokens, 56,184 completion tokens.
- v2: 2,340,130 prompt tokens, 84,268 completion tokens.

The two judge stages took 50.7 and 168.7 seconds respectively, including their
calibration and model loading. Calls were local; hardware time is not priced.
Exact UTC receipts are retained.

## Evidence and reproduction

The [archive](results/longmemeval-full-2026-11-12/README.md) contains complete
predictions, raw model text, retrieval labels/summaries, judgments, calibration,
official-format hypothesis exports and code/data/environment provenance.
[Checksums](results/longmemeval-full-2026-11-12/checksums.json) use canonical LF
line endings. Independent graders must keep `response_error` rows non-passing
to reproduce this protocol; an unmodified grader may accept fallback abstention
on an unanswerable question instead.

The benchmark does not exercise organization approvals, PostgreSQL or Neo4j.
Those paths have separate application/container tests. Follow
[FULL_PROTOCOL.md](FULL_PROTOCOL.md) for commands and scope. The public-data
history excerpts retain the upstream [MIT attribution](../THIRD_PARTY.md).

The [release verification](../docs/verification-v0.3.md) also records 171 passing
tests/5 SQLite skips and the unchanged frozen synthetic rerun: 768 retrieval
calls plus 48 operation checks, no failures, at clean commit `fcb9775`.
