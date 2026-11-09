# Governed Memory

Evidence memory for coding agents, with explicit approval and two time axes. A proposed architecture decision stays outside the trusted graph until an operator approves its structured facts. Retrieval checks current access, withdrawal, effective time and what was known at the requested time.

PostgreSQL holds the authoritative ledger. Graphiti 0.31.2 and Neo4j provide a rebuildable hybrid-search projection. SQLite and lexical hash embeddings support a small, network-free demonstration after installing dependencies.

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

Issue a separate agent credential with `credential --project demo --principal coding-agent --role agent`. The agent's stdio MCP process receives that token as `MEMORY_TOKEN` and runs `uv run governed-memory serve`. It exposes only `propose_memory`, `search_memory` and `explain_memory`. Approval, rejection, withdrawal, credential issuance and project management stay in the operator CLI. See [configuration](docs/usage.md).

## Verify and reproduce

```sh
uv run pytest -q
uv run python -m eval.run --output .local/evaluation --check
```

For real storage tests, set `GM_TEST_DATABASE_URL` to the PostgreSQL URL above, `GM_TEST_NEO4J_URI=bolt://127.0.0.1:57687`, and `GM_TEST_NEO4J_PASSWORD=local-graph-only` before running pytest. PostgreSQL tests create and remove isolated schemas. Without those variables the corresponding tests skip. The CI workflow is configured to run deterministic checks and real storage tests.

[Evaluation protocol and recorded results](eval/README.md) include a frozen synthetic corpus, four methods, equal evidence budgets, raw predictions and run provenance. These measure retrieval and governance behavior; they do not measure generated-answer accuracy or performance on real conversations. The offline vector channel uses deterministic lexical hashing, **not a learned semantic model**. External embedding configuration is separate and has not been benchmarked here.

## Scope

The application implements approval transitions, bitemporal corrections, source provenance, authorization, retrieval constraints and the experiment harness. Graphiti supplies graph persistence and hybrid search; its extraction and entity resolution are not used on the trusted write path. See [design and trust boundaries](docs/design.md) and [third-party attribution](THIRD_PARTY.md).

This is a small experimental service: it scans authorized ledger rows before retrieval, supports one controlled projection worker, and has no distributed deployment, schema upgrade tooling, OPA policy, neural reranker or production security guarantee. Withdrawal hides evidence from normal APIs while retaining audit history. The permission boundary assumes that the server's database credentials, operator token and host are trusted.
