# Configuration and operator commands

Environment variables:

| Variable | Meaning |
| --- | --- |
| `MEMORY_DATABASE_URL` | SQLAlchemy PostgreSQL URL; defaults to local SQLite `.local/memory.db` |
| `MEMORY_TOKEN` | Issued credential bound to the current process; no default identity |
| `MEMORY_NEO4J_URI` | Enables the graph backend; otherwise retrieval uses the ledger |
| `MEMORY_NEO4J_USER` | Defaults to `neo4j` |
| `MEMORY_NEO4J_PASSWORD` | Graph credential for the trusted service/worker |
| `MEMORY_EMBEDDING_MODEL` | Optional external model; absent means lexical hash features |
| `MEMORY_EMBEDDING_API_KEY` | Required when selecting an external embedding model |
| `MEMORY_EMBEDDING_BASE_URL` | Optional compatible provider base URL |

The application reads process environment; it does not load `.env` automatically. Shell examples below use PowerShell. `compose.yaml` reads its own `.env` in the usual Docker Compose way.

```powershell
$env:MEMORY_DATABASE_URL = 'postgresql+psycopg://memory:local-memory-only@127.0.0.1:55432/memory'
$env:MEMORY_NEO4J_URI = 'bolt://127.0.0.1:57687'
$env:MEMORY_NEO4J_PASSWORD = 'local-graph-only'
$initial = uv run governed-memory init --project demo | ConvertFrom-Json
$env:MEMORY_TOKEN = $initial.admin_token
$agent = uv run governed-memory credential --project demo --principal coding-agent --role agent | ConvertFrom-Json
$staged = uv run governed-memory ingest --project demo examples/decision.md | ConvertFrom-Json
$candidate = $staged[0]
$preview = uv run governed-memory preview --project demo $candidate.id | ConvertFrom-Json
# Inspect values, source hashes, overlaps and protection in $preview before approving.
uv run governed-memory approve --project demo $candidate.id --expected-revision $preview.revision --expected-head $preview.head_revision --reason 'Accept the database decision'
uv run governed-memory project --project demo
uv run governed-memory search --project demo 'storage database' --valid-at '2030-11-09T00:00:00Z'
```

`--protected` on approval creates an administrator-controlled fact. `reject`, `revoke` and `withdraw-source` are separate operator commands. `revoke` requires the current candidate revision; source withdrawal takes a source ID. A superseded or revoked candidate cannot be changed back to active.

Create another project using `create-project --from-project demo --project another`. This extends the current administrator's scope; credentials for other users remain explicitly project-scoped. `revoke-access --project demo --principal coding-agent` removes that principal's project grant, including access through historical queries. Issue a new principal/token to rotate an agent credential.

## MCP

Configure the client to launch `uv --directory ABSOLUTE_REPOSITORY_PATH run governed-memory serve`, with the agent token as `MEMORY_TOKEN`. Supply the server's storage environment through the trusted operator's launch configuration. The agent credential exposes:

```text
propose_memory(project, subject, predicate, value, valid_from, valid_until?)
search_memory(project, query, valid_at?, known_at?, token_budget?, k?)
explain_memory(project, memory_id)
```

Only stdio is supported. The server assumes a local trusted host; it is not an authenticated public HTTP endpoint. Two independent stdio server processes and persisted retrieval are exercised by `test_stdio_mcp_persists_between_independent_sessions`.

## Imports and embeddings

`examples/session.jsonl` demonstrates message records with explicit `memory` annotations. Unannotated messages are ignored. `examples/decision.md` demonstrates TOML-frontmatter metadata with a structured value. Text such as “approved” or “I am admin” has no authority. Imports retain a locator, line/frontmatter fragment and full content hash. Repeated imports return the same candidates.

Default examples make no model calls and bundle their tokenizer vocabulary. External model support uses Graphiti's `OpenAIEmbedder` interface and has not been exercised against a paid provider in this repository. A model must provide at least 1,024 embedding dimensions; Graphiti's client uses its first 1,024 dimensions. Use a fresh graph and reproject all snapshots when changing models. Do not mix hash vectors and learned embeddings in the same projection. External provider availability, model quality and limits are not part of the recorded offline results.
