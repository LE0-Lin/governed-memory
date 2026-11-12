# Configuration and operator commands

Environment variables:

| Variable | Meaning |
| --- | --- |
| `MEMORY_DATABASE_URL` | SQLAlchemy PostgreSQL URL; defaults to local SQLite `.local/memory.db` |
| `MEMORY_TOKEN` | Issued credential bound to the current process; no default identity |
| `MEMORY_NEO4J_URI` | Enables the graph backend; otherwise retrieval uses the ledger |
| `MEMORY_NEO4J_USER` | Defaults to `neo4j` |
| `MEMORY_NEO4J_PASSWORD` | Graph credential for the trusted service/worker |
| `MEMORY_OPA_URL` | Optional OPA base URL, e.g. `http://127.0.0.1:58181`; decisions then require OPA to allow them |
| `MEMORY_LOCAL_EMBEDDING` | `1` selects the pinned local MiniLM embedder |
| `MEMORY_LOCAL_RERANKER` | `1` selects the pinned local MiniLM cross-encoder |
| `MEMORY_MODEL_CACHE` | Optional directory for downloaded model weights/tokenizers |
| `MEMORY_GENERATION_PROFILE` | Enables cited answers: `small` (0.5B) or `standard` (1.5B); unset disables generation |
| `MEMORY_GENERATION_CACHE` | Optional directory for downloaded generator weights/tokenizers |
| `MEMORY_GENERATION_DEVICE` | `cpu` (default) or `cuda`, with a compatible PyTorch installation |
| `MEMORY_EMBEDDING_MODEL` | Optional external model; mutually exclusive with local embeddings |
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

## Add and withdraw a supporting source

After the preceding example, import a second source for the same structured assertion:

```powershell
$support = (uv run governed-memory ingest --project demo examples/corroboration.md | ConvertFrom-Json)[0]
$target = uv run governed-memory preview --project demo $candidate.id | ConvertFrom-Json
$incoming = uv run governed-memory preview --project demo $support.id | ConvertFrom-Json
# Inspect both sources and the matching assertion before approving the link.
uv run governed-memory approve-support --project demo $support.id --target $candidate.id --expected-revision $incoming.revision --expected-target-revision $target.revision --expected-head $target.head_revision --reason 'Accept the corroborating source'
uv run governed-memory withdraw-source --project demo $candidate.source_id
uv run governed-memory project --project demo
uv run governed-memory search --project demo 'storage database' --valid-at '2030-11-09T00:00:00Z'
```

The search still returns PostgreSQL with the remaining source's provenance. Withdraw `$support.source_id` to suppress the last support as well. Revoking the original assertion instead suppresses the entire claim. Source withdrawal is current authorization: an earlier `known_at` cannot undo it. A newly approved support cannot appear at an earlier `known_at`. This command requires exact matching values and valid intervals; it does not merge similar prose or verify source independence.

Create another project using `create-project --from-project demo --project another`. This extends the current administrator's scope; credentials for other users remain explicitly project-scoped. `revoke-access --project demo --principal coding-agent` removes that principal's project grant, including access through historical queries. Issue a new principal/token to rotate an agent credential.

## Upgrade a v0.1 installation

Stop the MCP process and projection worker, back up the ledger, and retain its existing admin token. With that credential and the existing storage configuration:

```powershell
uv sync --frozen --extra dev
uv run governed-memory upgrade --project demo
uv run governed-memory project --project demo --rebuild
```

`upgrade` adds the support table and audit triggers; it preserves existing facts and tokens. `--rebuild` queues all snapshots and processes up to 100 per invocation. Repeat `project --project demo` while pending jobs remain. Old graph edges without embedding-profile metadata use ledger fallback until rebuilt. This is the supported additive v0.1 → v0.2 upgrade, not a general migration/rollback system.

## Optional OPA

```powershell
docker compose --profile policy up -d --wait
$env:MEMORY_OPA_URL = 'http://127.0.0.1:58181'
docker compose run --rm --no-deps opa test --fail-on-empty /policies /policy-tests -v
```

The bundled Rego rules cover operator roles, legal lifecycle changes, protected facts and withdrawn sources. OPA is consulted inside operator decision transactions. If it is unreachable, malformed or denies a decision, the transaction rolls back. Built-in rules remain mandatory. After changing Rego, test it and restart the OPA service to reload the mounted policy.

## MCP

Configure the client to launch `uv --directory ABSOLUTE_REPOSITORY_PATH run governed-memory serve`, with the agent token as `MEMORY_TOKEN`. Supply the server's storage environment through the trusted operator's launch configuration. The agent credential exposes:

```text
propose_memory(project, subject, predicate, value, valid_from, valid_until?)
search_memory(project, query, valid_at?, known_at?, token_budget?, k?)
explain_memory(project, memory_id)
```

Only stdio is supported. The server assumes a local trusted host; it is not an authenticated public HTTP endpoint. Two independent stdio server processes and persisted retrieval are exercised by `test_stdio_mcp_persists_between_independent_sessions`.

Setting `MEMORY_GENERATION_PROFILE` adds `answer_memory(project, query, valid_at?, known_at?, token_budget?, k?)`. It receives the same bound agent credential and has no approval or identity arguments. Container launch and recovery instructions are in [deployment.md](deployment.md).

## Cited answers

```powershell
uv sync --frozen --extra dev --extra models
$env:MEMORY_GENERATION_PROFILE = 'small'
$env:MEMORY_GENERATION_CACHE = "$PWD/.local/generation-cache"
uv run governed-memory answer --project demo 'Which database does storage use?' --valid-at '2030-11-09T00:00:00Z'
```

The first call downloads the pinned Qwen model and tokenizer. `small` is the 0.5B CPU smoke profile; `standard` is the 1.5B evaluation profile. Greedy decoding allows at most 384 output tokens and a 4,096-token complete prompt. An overlong prompt fails closed rather than silently dropping evidence. `HF_HUB_OFFLINE=1` uses previously cached assets. The optional dependencies include LM Format Enforcer at a fixed upstream revision containing its Transformers 5 import fix.

The response includes `answer`, resolved `evidence_ids`, authorized `evidence`, `abstain`, `reason`, generation token counts and model revision. JSON Schema constrains field types and available citation aliases; a separate parser checks whether an answer has citations and abstention has none. Missing evidence, invalid output or generation failure returns a fixed abstention with a reason. Citation presence does not prove that the claim is supported.

The service rechecks all supplied evidence after generation. A withdrawal or changed source discards the answer and context; revoked project access denies the request. It never writes generated text into the ledger, and it does not return malformed raw model output. Evidence remains untrusted data in the prompt. These controls do not establish general prompt-injection resistance or factual correctness.

## Imports and embeddings

`examples/session.jsonl` demonstrates message records with explicit `memory` annotations. Unannotated messages are ignored. `examples/decision.md` demonstrates TOML-frontmatter metadata with a structured value. Text such as “approved” or “I am admin” has no authority. Imports retain a locator, line/frontmatter fragment and full content hash. Repeated imports return the same candidates.

Each file import is one ledger transaction. If any annotated record fails validation or storage, all new candidates, sources and audit events from that import roll back; existing records remain unchanged. Fix the file and retry. Successful imports still stage proposals only and require separate approval.

Default examples make no model calls and bundle their budget tokenizer vocabulary. To enable local CPU models:

```powershell
uv sync --frozen --extra dev --extra models
$env:MEMORY_MODEL_CACHE = "$PWD/.local/model-cache"
$env:MEMORY_LOCAL_EMBEDDING = '1'
$env:MEMORY_LOCAL_RERANKER = '1'
uv run governed-memory project --project demo --rebuild
```

The first use downloads pinned safetensors and tokenizer assets for `sentence-transformers/all-MiniLM-L6-v2` and `cross-encoder/ms-marco-MiniLM-L6-v2`. Subsequent runs can set `HF_HUB_OFFLINE=1` after the weights are cached. Both use two CPU threads and batches of 16. The embedder reads up to 256 wordpieces per fact; the reranker reads up to 512 per query/passage pair. Longer application facts are truncated for model scoring but remain whole in evidence and token-budget checks. The external benchmark uses separately documented message windows. Neural similarity does not guarantee that a question has an answer.

External model support uses Graphiti's `OpenAIEmbedder` interface and has not been exercised against a paid provider in this repository. A model must provide at least 1,024 embedding dimensions; Graphiti's client uses its first 1,024 dimensions. Reproject all snapshots when changing embedding models. Fingerprint checks prevent querying differently embedded graph edges together, with ledger fallback until rebuild. External provider availability and quality are outside the recorded local results.
