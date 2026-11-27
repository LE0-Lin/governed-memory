# LongMemEval S: fixed retrieval comparison

The first run contains **14 of 500 questions**, selected before inference from
the official cleaned S dataset. It measures session-evidence retrieval from the
provided histories. There is no answer generator or LLM judge, so these numbers
are not LongMemEval answer accuracy or a full-benchmark score.

## Frozen inputs and methods

[`longmemeval_manifest.json`](longmemeval_manifest.json) records dataset revision
`98d7416c24c778c2fee6e6f3006e7a073259d48f`, file SHA-256, all question IDs, model
revisions and settings. Selection takes the first two IDs in each category after
sorting by SHA-256(`governed-memory-longmemeval-v1:id`). It reads question IDs and
types only. Six question types and the `_abs` abstention group give seven groups.
No IDs, ranking settings or model versions were changed after scoring.

All methods use the full provided history, excluding only sessions dated after
the question. Dataset timestamps without a timezone are consistently interpreted
as UTC for ordering; this is a benchmark convention, not an inferred local zone.
There were 16 excluded future sessions across the selected histories. Each
message is split into 200-wordpiece windows with 40-wordpiece overlap, preserving
character offsets and adding session date/role. This is fixed windowing, not
semantic chunking. The 14 histories produced 12,714 windows from 661 eligible
sessions: 624–972 windows and 35–52 sessions per question.

| Method | Ranking |
| --- | --- |
| BM25 | `rank-bm25` on the same message windows |
| Learned hybrid | BM25 + normalized all-MiniLM-L6-v2 cosine scores, reciprocal rank fusion |
| Hybrid + cross-encoder | The same hybrid's first 50 windows, reranked by ms-marco-MiniLM-L6-v2 raw logits |

Both model revisions are pinned in the manifest. All methods share k=8, a
2,048-token evidence budget, whole-window packing and provenance fields. Budget
overhead can reduce the returned count below eight. The runner shares the
application's model wrappers, fusion function and budget implementation; it does
not invoke the SQL ledger, OPA or Neo4j. LongMemEval supplies no organization
approval or withdrawal labels, so it cannot replace the governance suite.

`longmemeval_data.py` constructs retrieval cases without `answer`,
`answer_session_ids` or `has_answer`. After predictions are finalized,
`longmemeval_score.py` opens the session labels. A session hit means at least one
window from that session was returned; it does not establish that the returned
window contains the answer. The scorer separately reports any/all required
session hits and partial session recall. Abstention cases are excluded from
recall denominators.

## Recorded result

Run directory: [`results/longmemeval-minilm-2026-11-10`](results/longmemeval-minilm-2026-11-10).
The recorded code commit is `ef7bc7cc3fa18daf6d03f03d9b15fa1e7021bdda`, with clean
source at startup and unchanged source hash across inference. There were 42
retrievals, zero errors and no inference timeout. The protocol specifies sequential
CPU inference without a timeout; zero timeouts is not a timeout-resilience test.

| Method | Required sessions recalled | Any session hit | All sessions hit | Query P50 / P95 | Mean evidence tokens |
| --- | --- | --- | --- | --- | --- |
| BM25 | 18/18 (100%) | 12/12 | 12/12 | 6.1 / 8.1 ms | 1,490.6 |
| Learned hybrid | 17/18 (94.4%) | 12/12 | 11/12 | 19.9 / 25.4 ms | 1,522.4 |
| Hybrid + cross-encoder | 18/18 (100%) | 12/12 | 12/12 | 1,515.0 / 1,802.7 ms | 1,498.6 |

The plain hybrid missed one of two required sessions for temporal-reasoning
question `gpt4_d31cdae3`. Its packed evidence contained `answer_8464304d_2` but
omitted `answer_8464304d_1`. Both BM25 and the reranked method returned both
sessions. This small subset provides **no evidence that the reranker improves
over BM25**; its additional CPU cost is substantial. The negative hybrid result
and per-window reranking scores remain in the recorded output.

All three methods returned context for both abstention questions (2/2). There is
no calibrated no-answer threshold or generated answer here. Returning context
must not be reported as correct abstention, nor as a proven wrong answer.

Measurements used Windows 11, Python 3.12.0 and an AMD Ryzen 9 7945HX CPU,
two PyTorch CPU threads, batch size 16 and one sequential caller. Model kernels
were warmed on unrelated synthetic text. Query timings include query embedding
where applicable, ranking, reranking, budget checks and serialization, with no
query-result cache. Document indexing is separate: median lexical preparation
was 228.6 ms/history and median embedding preparation was 23.72 s/history
(330.30 s total embedding work). BM25 does not require the embedding preparation.
Model downloads, process startup, ledger/graph operations and answer generation
are excluded. The sample is too small for a general quality or latency claim.

## Reproduce

Download `longmemeval_s_cleaned.json` from the
[pinned official dataset revision](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/tree/98d7416c24c778c2fee6e6f3006e7a073259d48f).
Keep it outside version control. The runner verifies its complete SHA-256 before
loading models:

```sh
uv sync --frozen --extra dev --extra models
uv run python -m eval.longmemeval_run --dataset .local/longmemeval/longmemeval_s_cleaned.json --model-cache .local/model-cache --output .local/longmemeval-new-run
```

Use a new output directory; existing predictions are never overwritten. The
first run downloads model assets. After caching both models, `HF_HUB_OFFLINE=1`
allows local inference. Avoid concurrent compute if comparing latency.

`predictions.jsonl` contains IDs, scores, timings and indexing costs without
copying conversation text. `scored.jsonl` adds session labels after retrieval.
`summary.json` gives category-level metrics; `provenance.json` records the frozen
protocol, package versions, model metadata, code hash and prediction hash. The
prediction SHA-256 is
`dd1a1e3358852eb28aca0de0f9bffd87a944a7baeaf0a6ed56c0500f231177a7`.
