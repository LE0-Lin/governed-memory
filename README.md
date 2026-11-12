# Governed Memory

Evidence memory for coding agents, with explicit approval and two time axes. A proposed architecture decision stays outside the trusted graph until an operator approves its structured facts. Retrieval checks current access, withdrawal, effective time and what was known at the requested time.

PostgreSQL holds the authoritative ledger. Graphiti 0.31.2 and Neo4j provide a rebuildable hybrid-search projection. SQLite and lexical hash embeddings support a small, network-free demonstration after installing dependencies. Optional integrations add OPA decisions, pinned local neural retrieval, cited local answers and explicitly approved corroborating sources.

## Run the example

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --frozen --extra dev
uv run python examples/demo.py
```

The synthetic example verifies SQLite → PostgreSQL, a late correction with different `known_at` results, a blocked self-approval and source withdrawal. Example output includes:

```text
current decision: PostgreSQL
earlier effective date: SQLite
late correction, before receipt: PostgreSQL
late correction, after receipt: PostgreSQL with WAL archival
unapproved injection: self-approval denied
withdrawal: withdrawn evidence hidden
```

The JSON output also includes source locators and evidence token counts. Example dates in 2030 are fictional test data.

## Use persistent storage

```sh
docker compose up -d --wait
```

Set `MEMORY_DATABASE_URL=postgresql+psycopg://memory:local-memory-only@127.0.0.1:55432/memory`, `MEMORY_NEO4J_URI=bolt://127.0.0.1:57687` and `MEMORY_NEO4J_PASSWORD=local-graph-only`. These match the local development Compose defaults. Then:

```sh
uv run governed-memory init --project demo
```

Save the issued admin token outside the repository and set it as `MEMORY_TOKEN` **in the operator's process**. Ingest stages candidates:

```sh
uv run governed-memory ingest --project demo examples/decision.md
uv run governed-memory preview --project demo CANDIDATE_ID
uv run governed-memory approve --project demo CANDIDATE_ID --expected-revision 0 --expected-head 0 --reason "Accept the database decision"
uv run governed-memory project --project demo
uv run governed-memory search --project demo "storage database" --valid-at 2030-11-09T00:00:00Z
```

Use the candidate and head revisions actually returned by `preview`; stale approvals fail. `project` processes up to 100 queued snapshots per invocation; rerun it for larger queues. `project --project demo --rebuild` requeues all historical snapshots once, for a fresh graph. Approval commits the ledger and queue together; it does not claim that graph projection has already succeeded.

Issue a separate agent credential with `credential --project demo --principal coding-agent --role agent`. The agent's stdio MCP process receives that token as `MEMORY_TOKEN` and runs `uv run governed-memory serve`. By default it exposes `propose_memory`, `search_memory` and `explain_memory`. Setting `MEMORY_GENERATION_PROFILE=small` or `standard` adds `answer_memory`; install the optional `models` dependencies first. Approval, rejection, withdrawal, credential issuance and project management stay in the operator CLI. See [configuration](docs/usage.md) and [container deployment/recovery](docs/deployment.md).

For a v0.1 ledger, back it up and run `upgrade --project demo` with its existing admin credential before starting v0.2. Rebuild an existing graph once to attach embedding-profile metadata. [Operator instructions](docs/usage.md) cover this upgrade, OPA, local models and adding a second source without replacing a fact's timeline.

## Verify and reproduce

```sh
uv run pytest -q
uv run python -m eval.run --output .local/evaluation --check
```

For real storage tests, set `GM_TEST_DATABASE_URL` to the PostgreSQL URL above, `GM_TEST_NEO4J_URI=bolt://127.0.0.1:57687`, and `GM_TEST_NEO4J_PASSWORD=local-graph-only` before running pytest. PostgreSQL tests create and remove isolated schemas. OPA tests use `GM_TEST_OPA_URL`; downloaded-model tests use `GM_TEST_REAL_MODELS=1`. Without the corresponding configuration those tests skip. CI runs Windows/Ubuntu core checks, real storage/OPA tests and a separate local-model job.

[Evaluation protocols](eval/README.md) separate the frozen synthetic governance suite from a fixed 14-question LongMemEval S retrieval comparison and the [full 500-question answer protocol](eval/FULL_PROTOCOL.md). The earlier reports measure governance and retrieval; the full protocol adds cited generation, format-failure accounting and a separate local model judge. The default offline vector channel uses deterministic lexical hashing; optional learned retrieval uses standard Sentence Transformers models. Paid external embedding providers have not been benchmarked.

In the [recorded synthetic run](eval/RESULTS.md), the governed service and the strong temporal baseline both recalled all required evidence in heldout time-query controls. The governed service additionally enforced the supplied approval/withdrawal signals, at higher local retrieval latency. The report includes the denominators, baseline failures and limits of that result.

The [v0.2 verification record](eval/RESULTS-v0.2.md) includes the unchanged frozen-suite rerun, real policy/model checks and an installed-wheel upgrade from v0.1. The [14-question external comparison](eval/LONGMEMEVAL.md) found no recall gain from reranking over BM25 and records the extra CPU cost.

## Scope

The application implements approval transitions, bitemporal corrections, source provenance, authorization, retrieval constraints, optional cited answers and the experiment harness. Answers use JSON Schema constraints and authority checks before and after generation; citations do not establish factual correctness. Graphiti supplies graph persistence and hybrid search; its extraction and entity resolution are not used on the trusted write path. Start with the [code reading guide](docs/code-guide.md), [中文验收与项目讲解](docs/acceptance.zh-CN.md), [design and trust boundaries](docs/design.md) and [third-party attribution](THIRD_PARTY.md).

This is a small experimental service: it scans authorized ledger rows before retrieval and supports one controlled projection worker. The upgrade command supports the additive v0.1 → v0.2 change; distributed deployment, general migration/rollback tooling and production security guarantees remain outside its scope. Source withdrawal preserves a fact only when another approved source is currently usable by the caller. Audit history remains stored. The permission boundary assumes that the server's database credentials, operator token and host are trusted.
