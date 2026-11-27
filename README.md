<p align="center"><img src="docs/assets/hero.svg" alt="Governed Memory — remember what was approved" width="1120"></p>

# Governed Memory

[![Checks](https://github.com/LE0-Lin/governed-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/LE0-Lin/governed-memory/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/LE0-Lin/governed-memory)](https://github.com/LE0-Lin/governed-memory/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB)](pyproject.toml)
[![License](https://img.shields.io/github/license/LE0-Lin/governed-memory)](LICENSE)

**Persistent evidence memory for coding agents, with operator approval and two time axes.**

[中文](README.zh-CN.md) · [Get started](docs/getting-started.md) · [Connect MCP](docs/getting-started.md#connect-an-mcp-client) · [Measurements](docs/evaluation.md) · [Releases](https://github.com/LE0-Lin/governed-memory/releases)

An agent proposes “use PostgreSQL.” An operator reviews it. Later, a correction
arrives: you can query both **what was effective then** and **what was known then**.
Every response rechecks access and source withdrawal, including when the graph
projection or model-computation cache is stale.

## Try it locally

Requires **Python 3.12** and [uv](https://docs.astral.sh/uv/). Windows and Linux
are tested. The core demo needs no Docker, API keys, model downloads or services
after installation.

```sh
git clone https://github.com/LE0-Lin/governed-memory.git
cd governed-memory
uv sync --frozen
uv run governed-memory demo
```

The installed package includes the demo; a source checkout is optional when
using the [release wheel](https://github.com/LE0-Lin/governed-memory/releases/latest).
See [install without a checkout](docs/getting-started.md#install-a-release-wheel).

The demo verifies current/historical decisions, a late correction, denied
self-approval and withdrawal. Its JSON output includes:

```json
{"scenario":"unapproved injection","self_approval":"denied"}
{"scenario":"withdrawal","withdrawn_evidence_visible":false}
```

Source locators and token counts come from the actual run. The demo uses an
isolated in-memory SQLite database and ignores live storage credentials.
Its hash-vector channel is lexical; learned semantic retrieval is an optional
[model configuration](docs/usage.md#imports-and-embeddings).

## Use your own persistent memory

1. [Initialize a local ledger](docs/getting-started.md#keep-a-real-local-ledger) and keep its operator credential separate from the agent.
2. Import an ADR or JSONL session. Imports stage proposals; they do not approve themselves.
3. Review the candidate and approve its actual revisions through the CLI.
4. Bind a separate agent token to the MCP server. Query it across coding sessions.

The [walkthrough](docs/getting-started.md) includes PowerShell/POSIX setup,
an example valid today, client configuration and expected results.
For PostgreSQL/Neo4j, read [deployment and recovery](docs/deployment.md).

## What it provides

| Capability | Behavior |
| --- | --- |
| Approval-gated memory | Proposed text remains outside trusted retrieval until operator approval. Agent tools expose no approval or identity override. |
| Bitemporal history | Query effective time (`valid_at`) and recorded knowledge (`known_at`); retain immutable snapshots and provenance. |
| Hybrid retrieval | BM25/vector fusion, optional Rust kernels and pinned local cross-encoder; whole-item token budgets. |
| Live authority | Local grants, source audiences, withdrawal and exact dependency checks; optional OpenFGA intersection and OPA governance. |
| Rebuildable graph | PostgreSQL is authoritative; Graphiti/Neo4j returns candidate IDs that are rechecked against the ledger. |
| Controlled ingestion | JSONL/ADR imports, optional semantic chunking/entity/NLI review; model suggestions do not grant approval. |
| Lifecycle propagation | Exact-snapshot dependency invalidation, reviewed corroborating sources and OpenLineage delivery outbox. |
| Optional cited answers | Local generation with constrained output and evidence rechecks. Citations alone do not establish correctness. |

```mermaid
flowchart LR
    A[Agent proposal] --> P[Untrusted candidate]
    O[Operator review] -->|approve| L[Authoritative ledger]
    P --> O
    L --> G[Graph projection]
    Q[MCP query] --> R[Hybrid retrieval]
    G -->|IDs| R
    R --> C[Live ledger and access checks]
    L --> C
    C --> E[Budgeted source evidence]
```

SQLite supports the local core workflow. PostgreSQL, Neo4j and the optional
governance/model integrations support the fuller self-hosted configuration.
See [configuration](docs/usage.md), [design](docs/design.md) and the
[code reading guide](docs/code-guide.md).

## Benchmarks and scope

Measured on **v0.8.1** (full local stack: PostgreSQL, Neo4j/Graphiti, OpenFGA, and stdio MCP on a single CPU host with warmed models, `k=5`, 1024-token budget):

| Workload | Result | Notes |
| --- | --- | --- |
| Controlled temporal retrieval | **60/60** positive queries (100% Recall@5) | 84 synthetic queries (60 positive, 24 negative) across 72 and 1,152 historical assertions |
| Stale retrieval vs. session baseline | **0/789** vs. **498/816** baseline (`v0.7`); **0/792** full-stack (`v0.8.1`) | Paired 1,152-assertion session control ([v0.7](eval/RESULTS-v0.7.md)) and full MCP stack ([v0.8.1](eval/RESULTS-v0.8.1.md)) across 3 replays |
| Full-path retrieval P95 (`v0.8.1`) | **0.762 s** (first-pass 0.806 s, repeat 0.516 s) | Single caller, CPU inference; excludes process/model startup (4.95–5.53 s) and answer generation |
| Relevance heldout (default `v2` gate) | **47/48** positive recall (97.92%), **27/32** negative queries emptied | Blind 80-query set; cuts unrelated negative items `324 -> 15` across 3 replays ([v0.9.1](eval/RESULTS-v0.9.1.md)) |
| Engineering ADR + session corpus | **14/14** positive recall, **0/54** stale/unsafe items | Non-template 16-record ADR/JSONL corpus vs. session baseline (`63/180` stale/unsafe; [v0.9.1](eval/RESULTS-v0.9.1.md)) |
| Optional 500-question answers | **181/500** (36.2%) | Long-conversation QA scored by a local model judge |

These numbers reflect bounded local-model runs rather than general accuracy or a production SLO. With `MEMORY_LOCAL_RERANKER=1`, the default `minilm-relevance-v2` gate (`MEMORY_RELEVANCE_FILTER=auto`) filters most negative queries on structured assertions while keeping `0` available for raw long-transcript workloads. Full protocols, hardware details, and raw outputs—including reverted experiments—are in [docs/evaluation.md](docs/evaluation.md) and [eval/README.md](eval/README.md).

## Develop and contribute

```sh
uv sync --frozen --extra dev
uv run pytest -q
uv run python scripts/check_offline_demo.py
```

CI also exercises actual storage/policy services, installed containers, local
models and native Rust on Windows/Linux. Optional tests skip when their services
or models are absent; [contribution instructions](CONTRIBUTING.md) explain how
to enable them. Release checks install the built wheel into a separate environment
and exercise persisted MCP proposal, approval, restart and withdrawal.

**Status:** standalone `v0.9.x` open-source package and reproducible benchmark suite (evolved from an earlier 2025 architectural prototype) for local stdio MCP and controlled self-hosting. One projection worker, additive upgrades and retained audit
history; distributed failover, public HTTP hosting and production capacity are
not established. Use [backup/recovery instructions](docs/deployment.md) for stored
data. [Report a bug](https://github.com/LE0-Lin/governed-memory/issues/new/choose)
or read [security guidance](SECURITY.md).

MIT licensed. See [third-party attribution](THIRD_PARTY.md) for libraries, models
and evaluation data.
