# Get started

Use Python **3.12** and [uv](https://docs.astral.sh/uv/). Windows and Linux are
tested. Start with the core package; it does not install PyTorch or need API
keys. Installing dependencies needs network access; the core demo itself is offline.

## Install from source

```sh
git clone https://github.com/LE0-Lin/governed-memory.git
cd governed-memory
uv sync --frozen
uv run --no-sync governed-memory --version
uv run --no-sync governed-memory demo
```

The six JSON records demonstrate a current decision, a historical decision,
two views of a late correction, denied agent self-approval and withdrawal.
The demo uses its own in-memory SQLite ledger and ignores your live service
configuration. It leaves no persistent database and requires no model download.

## Install a release wheel

No checkout is needed for the packaged demo. This command pins the release and
its exported core dependency constraints; it works in PowerShell and POSIX shells:

```sh
uvx --python 3.12 --constraints https://github.com/LE0-Lin/governed-memory/releases/download/v0.9.0/requirements-core.txt --from https://github.com/LE0-Lin/governed-memory/releases/download/v0.9.0/governed_memory-0.9.0-py3-none-any.whl governed-memory demo
```

Alternatively download the wheel and `requirements-core.txt` from the
[release](https://github.com/LE0-Lin/governed-memory/releases/tag/v0.9.0), create
a Python 3.12 environment and install with
`python -m pip install -c requirements-core.txt governed_memory-0.9.0-py3-none-any.whl`.
Then run `governed-memory demo`. Releases include `SHA256SUMS` and the installed
verification receipts. A GitHub wheel URL is intentional; this guide does not
assume a package has been published on PyPI.

The remaining walkthrough uses a source checkout so its example ADR is present.
Run `uv sync --frozen` once before using the `--no-sync` commands below.

## Keep a real local ledger

Choose a new local ledger. If the file is already initialized, keep its existing
credentials or choose another path; `init` will not overwrite it or issue a new
administrator. The example below uses SQLite and no external services.

### PowerShell

```powershell
New-Item -ItemType Directory -Path .local -Force | Out-Null
$env:MEMORY_DATABASE_URL = 'sqlite:///.local/quickstart.db'
$setup = uv run --no-sync governed-memory init --project quickstart | ConvertFrom-Json
$admin = $setup.admin_token
$env:MEMORY_TOKEN = $admin
$agent = (uv run --no-sync governed-memory credential --project quickstart --principal coding-agent --role agent | ConvertFrom-Json).token
$staged = uv run --no-sync governed-memory ingest --project quickstart examples/quickstart.md | ConvertFrom-Json
$candidate = @($staged)[0]
$review = uv run --no-sync governed-memory preview --project quickstart $candidate.id | ConvertFrom-Json
$review | ConvertTo-Json -Depth 5
```

Inspect the value, source locator/hash, overlaps and revisions before approval:

```powershell
uv run --no-sync governed-memory approve --project quickstart $candidate.id --expected-revision $review.revision --expected-head $review.head_revision --reason 'Accept the example storage decision'
$env:MEMORY_TOKEN = $agent
uv run --no-sync governed-memory search --project quickstart 'storage database'
```

### POSIX shell

```sh
mkdir -p .local
export MEMORY_DATABASE_URL='sqlite:///.local/quickstart.db'
uv run --no-sync governed-memory init --project quickstart
# Save the returned admin_token outside the repository.
export MEMORY_TOKEN='YOUR_ADMIN_TOKEN'
uv run --no-sync governed-memory credential --project quickstart --principal coding-agent --role agent
# Save the returned agent token separately.
uv run --no-sync governed-memory ingest --project quickstart examples/quickstart.md
uv run --no-sync governed-memory preview --project quickstart CANDIDATE_ID
```

After inspecting the preview, substitute its actual candidate/head revisions:

```sh
uv run --no-sync governed-memory approve --project quickstart CANDIDATE_ID --expected-revision CANDIDATE_REVISION --expected-head HEAD_REVISION --reason 'Accept the example storage decision'
export MEMORY_TOKEN='YOUR_AGENT_TOKEN'
uv run --no-sync governed-memory search --project quickstart 'storage database'
```

Expected: evidence containing `PostgreSQL`, a source locator/content hash and a
token count. Before approval, the same query has no trusted evidence. Example
dates are fictional; `examples/quickstart.md` is effective in the past so a
present-time query works. The older `examples/decision.md` uses future synthetic
dates and needs an explicit matching `--valid-at`.

`MEMORY_TOKEN` is bound to the process. Keep the administrator credential in the
operator's shell; only the separate agent token goes into an agent client.
Do not commit real tokens, databases or source documents to the repository.

## Connect an MCP client

For a client that accepts `mcpServers`, adapt this JSON to its configuration:

```json
{
  "mcpServers": {
    "governed-memory": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/governed-memory", "run", "--no-sync", "governed-memory", "serve"],
      "env": {
        "MEMORY_DATABASE_URL": "sqlite:///.local/quickstart.db",
        "MEMORY_TOKEN": "YOUR_AGENT_TOKEN"
      }
    }
  }
}
```

On Windows, use a path such as `E:/OpenSource/governed-memory`. `uv --directory`
sets the working directory, so the relative SQLite path points to the same
ledger as the operator commands. If the desktop client cannot find `uv`, use
its full executable path (`Get-Command uv` in PowerShell, `command -v uv` on POSIX).
Client configuration formats differ; the server transport is **local stdio**.

After reconnecting the client, expect `propose_memory`, `search_memory` and
`explain_memory`. Try `search_memory` with project `quickstart` and query
`storage database`. Approval/withdrawal/credential commands are not agent tools.
The MCP process persists across queries, and a fresh process reads the same ledger.

## Verify withdrawal

Use the operator token and the source ID from the imported candidate/search:

```powershell
$env:MEMORY_TOKEN = $admin
uv run --no-sync governed-memory withdraw-source --project quickstart $candidate.source_id
```

On POSIX, set `MEMORY_TOKEN` back to the saved administrator token and substitute
the source ID in the same command. The already-running agent must no longer
retrieve that withdrawn source; restart is not required. Historical queries
also respect current source withdrawal. This does not physically erase audit history.

## Add semantic retrieval or full storage

Use the locked source setup for optional models/native dependencies, including
the declared CPU PyTorch index. A generic wheel-extra install does not apply
uv's project-specific source overrides.

```sh
uv sync --frozen --extra models
# Optional Rust kernels, with a Rust toolchain installed:
uv sync --frozen --extra models --extra native
```

Enable `MEMORY_LOCAL_EMBEDDING=1` and `MEMORY_LOCAL_RERANKER=1` in the process
environment. First use downloads pinned retrieval models; keep using
`uv run --no-sync` after syncing the desired extras. CPU retrieval models and
optional answer generators have separate download/memory costs. See
[model configuration](usage.md#imports-and-embeddings) and
[answer limitations](usage.md#cited-answers).

For PostgreSQL, Neo4j, OPA/OpenFGA, container operation, upgrades and backups, see
[deployment](deployment.md), [operator configuration](usage.md) and
[semantic/governance workflows](operators-v0.4.md). The measured full-path
configuration is more than the lightweight core demo; read the
[evaluation card](evaluation.md) before quoting its performance.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Python version rejected | Use Python 3.12; `uv` can manage that interpreter. |
| Empty evidence | Confirm project/token, approved state, validity/known time, source withdrawal and token budget. Import alone does not approve. |
| `already initialized` | Keep the existing credential or choose a different new ledger. Do not delete an actual ledger to repeat a tutorial. |
| `uv` not found by desktop client | Configure an absolute executable path and absolute repository directory. |
| Native extension unavailable | Use the Python fallback, or build `--extra native` with Rust from source. |
| Answer/semantic model unavailable | Install the relevant extras and cache weights first. The core demo does not use them. |
| Relevant-looking but wrong evidence/answer | Authorization is not semantic correctness. Inspect provenance and [known quality limits](evaluation.md). |

Check `governed-memory --version` and [report a reproducible issue](https://github.com/LE0-Lin/governed-memory/issues/new/choose)
with credentials and private source text removed.
