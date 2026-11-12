# Evaluation protocols

The synthetic suite below tests governance and two-time behavior. The separate
[LongMemEval protocol and results](LONGMEMEVAL.md) test learned retrieval on a
small frozen public subset. The [full cleaned-S protocol](FULL_PROTOCOL.md)
extends this to all 500 questions with cited generation and a separate pinned
local model judge. Each report retains its original scope and raw failures.

## Synthetic governance suite

This is a small behavior suite for governance and temporal retrieval, not a conversational-memory benchmark or an LLM answer-accuracy evaluation. It contains 24 fictional project timelines from **8 template families**, with 192 evidence queries and 48 operation checks. Three variants of a family are correlated; counts are not independent scientific samples and no significance claim is made.

`manifest.json` freezes the corpus SHA-256, k=3 and a 1,024-token evidence budget. `timelines.jsonl` contains sources, operator decisions, explicit query times and gold evidence aliases. Version 2 corrected a dev audience fixture to use a distinct fact key **before any evaluation was run**; the original version mistakenly made its restricted endpoint replace the public database fact. The heldout families were not changed. Dev and heldout splits are separated by complete template family:

| Dev | Heldout |
| --- | --- |
| Migration | Scheduled change |
| Late correction | Source withdrawal |
| Bounded correction | Protected poisoning |
| Source audience | Multiple required evidence items |

## Methods and fairness

All methods receive the same current project/source access restrictions and source records received by `known_at`. All pack whole evidence items, including provenance, using the same tokenizer, k and evidence token budget.

1. **Recent sessions:** annotated message/decision records, newest receipt first, without relevance or time filtering. This is a structured-record session baseline, not full transcript truncation.
2. **Hybrid:** actual BM25 plus cosine lexical hash vectors, combined by RRF, without approval or effective-time filtering.
3. **Hybrid + temporal:** the same scorer with effective-time intervals and a receipt-time history: for each fact key, take the latest received assertion that contains `valid_at`, using only assertions received by `known_at`. This handles delayed/bounded changes; it does not receive operator approval or withdrawal decisions.
4. **Governed:** the application ledger with approval-time system history, both time intervals, current permissions/withdrawal and authoritative rechecks, then the same offline hybrid scorer.

This is **not** a Graphiti-versus-application comparison. Graphiti's temporal capabilities are not disabled to create a weaker upstream baseline. Real Graphiti/Neo4j persistence and filtered hybrid search are tested separately. These measurements use SQLite plus `rank-bm25` and 1,024-dimensional SHA-256 lexical features. They do not establish semantic retrieval quality or model inference cost.

The `quality` category contains retrieval/time controls. Poisoning, approval lag, withdrawal and access controls are reported separately. Governance methods intentionally receive approval/withdrawal signals that the corresponding ablations omit; differences in those categories measure enforcement of those signals, not a better learned retriever. Gold aliases are used only for scoring, never by retrieval. A gold evidence ID is the stable approved candidate ID; returned snapshot IDs are also preserved so that temporal slices can be inspected.

## Reproduce

```sh
uv sync --frozen --extra dev
uv run python -m eval.run --split dev --output .local/eval-dev --check
uv run python -m eval.run --output .local/eval-all --check
```

Do not regenerate or tune the corpus against heldout outcomes. `python -m eval.make_dataset` is the explicit maintenance command; normal evaluation verifies the frozen hash. `--check` fails if any method errors, governed evidence differs from the frozen gold set, or an operation violates its expected result. Failures and imperfect baseline outcomes remain in the output.

Each run writes:

- `predictions.jsonl`: every method/query, gold and predicted IDs, complete evidence, timing, category, token usage and errors.
- `operations.jsonl`: unauthorized approval and legitimate approval outcomes, with expected outcomes.
- `summary.json`: results by split, method and category, including raw denominators.
- `provenance.json`: data/code hashes, commit, dirty-source status, versions, machine, concurrency and timing conditions.

Metrics distinguish evidence Recall@k, hit-any and hit-all. Empty-gold cases are scored as abstention controls and excluded from recall denominators. Stale evidence is judged against the specified valid/known times; historical facts are valid in historical questions. Unapproved and withdrawn evidence are counted separately. Normal-query coverage and legitimate-operation success accompany attack counts so that rejecting everything cannot appear successful. A diagnostic added after an as-of metadata bug was found also checks for system-time fields later than `known_at`; its discovery and both runs are documented in the report.

Latency includes source loading/filtering, query and document hashing/embedding, ranking, tokenization and response serialization. It excludes ingestion, process startup, answer generation, transport and initial tokenizer loading. There is one sequential caller and no embedding-result cache. UUIDs and latency vary between runs; evidence outcomes are reproducible. This suite uses lexical hash vectors, without a neural reranker or paid embedding provider. The separate LongMemEval run measures the optional local models; neither is a production workload.

See [the original run and error analysis](RESULTS.md) and the [v0.2 regression run](RESULTS-v0.2.md). Their raw predictions and original run provenance are retained. A category-denominator aggregation correction is documented with separate scoring provenance. To reaggregate a saved run without retrieving again:

```sh
uv run python -m eval.summarize .local/eval-all --reason "Recompute using the current metric definitions"
```
