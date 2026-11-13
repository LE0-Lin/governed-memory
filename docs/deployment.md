# Container operation and recovery

The runtime image runs the installed package as UID/GID 10001. It uses stdio
MCP and opens no application HTTP port. Compose supplies a read-only root,
temporary `/tmp`, no Linux capabilities and persistent PostgreSQL, Neo4j and
model-cache volumes. The core image has no PyTorch or model weights.
Both runtime variants include compiled Rust kernels. The optional OpenFGA
database, semantic operator commands and OpenLineage delivery are described in
[the v0.4 workflow](operators-v0.4.md).

## Start a local stack

From the repository, using PowerShell:

```powershell
docker compose --profile app build memory
docker compose up -d --wait
$initial = docker compose run --rm -T memory init --project demo | ConvertFrom-Json
$env:MEMORY_TOKEN = $initial.admin_token
$agent = docker compose run --rm -T -e MEMORY_TOKEN memory credential --project demo --principal coding-agent --role agent | ConvertFrom-Json
$env:MEMORY_AGENT_TOKEN = $agent.token
```

Keep the administrator credential in the operator process. `-e MEMORY_TOKEN`
explicitly forwards it for operator commands; the ordinary service receives only
`MEMORY_AGENT_TOKEN`. Initialization applies to an empty ledger, not an existing
deployment. Import and inspect a candidate before approving it:

```powershell
$candidate = (docker compose run --rm -T -e MEMORY_TOKEN memory ingest --project demo examples/decision.md | ConvertFrom-Json)[0]
$preview = docker compose run --rm -T -e MEMORY_TOKEN memory preview --project demo $candidate.id | ConvertFrom-Json
# Inspect the source and value in $preview before accepting them.
docker compose run --rm -T -e MEMORY_TOKEN memory approve --project demo $candidate.id --expected-revision $preview.revision --expected-head $preview.head_revision --reason 'Accept the database decision'
docker compose run --rm -T -e MEMORY_TOKEN memory project --project demo
docker compose run --rm -T memory search --project demo 'storage database' --valid-at '2030-11-09T00:00:00Z'
```

The development passwords and loopback port bindings come from `compose.yaml`.
`POSTGRES_PASSWORD` and `NEO4J_PASSWORD` override the defaults when initializing
fresh storage. Changing environment variables does not rotate an existing
database credential. The image contains the example files; additional imports
need an explicit read-only source mount.

Configure an MCP client to launch `docker compose --project-directory
ABSOLUTE_REPOSITORY_PATH run --rm --no-deps -T memory serve`, passing the issued
agent credential as `MEMORY_AGENT_TOKEN`. Each connection starts a new server
process; ledger and graph state remain in the storage services. Do not allocate
a TTY for MCP. Operator commands remain separate from the client's tools.

For OPA, start `docker compose --profile policy up -d --wait` and set
`MEMORY_CONTAINER_OPA_URL=http://opa:8181` before launching a container process.
Use the host URL `http://127.0.0.1:58181` for host-side commands instead.

## Optional CPU answers

```powershell
$env:INSTALL_MODELS = 'true'
docker compose --profile app build memory
$env:MEMORY_GENERATION_PROFILE = 'small'
docker compose run --rm -T memory answer --project demo 'Which database is used?' --valid-at '2030-11-09T00:00:00Z'
```

This installs the optional CPU dependencies and downloads the pinned model on
first use into the `models` volume. After a successful cached run,
`HF_HUB_OFFLINE=1` allows disconnected startup. Weights are not embedded in the
image. The application supports CUDA on the host; this Compose file does not
configure a container GPU runtime. See [answer behavior](usage.md#cited-answers)
and [the recorded GPU environment](../eval/GPU_ENVIRONMENT.md).

For learned retrieval, enable `MEMORY_LOCAL_EMBEDDING=1` and
`MEMORY_LOCAL_RERANKER=1` in the same model-enabled server. Compose forwards
`MEMORY_RELEVANCE_FILTER` (default `0`) and `MEMORY_DOCUMENT_CACHE_SIZE` (default
`2048`). The former opts into a development-calibrated MiniLM cutoff; the latter
bounds document vectors within each process. An empty filtered answer does not
load the generator. Reuse requires repeated calls to the same MCP process;
restarting a process or launching another CLI command starts an empty cache.
See [the behavior and limitations](usage.md#relevance-filtering-and-vector-reuse).

## Back up the ledger and verify recovery

Stop application/projection processes during the recovery exercise. Keep a copy
of the application revision and its lock file alongside the database backup.
Use PostgreSQL's binary dump file rather than piping binary data through older
PowerShell text redirection:

```powershell
docker compose exec -T postgres pg_dump -U memory -Fc -f /tmp/memory.dump memory
docker compose cp postgres:/tmp/memory.dump .local/memory.dump
docker compose exec -T postgres createdb -U memory memory_restore
docker compose exec -T postgres pg_restore -U memory -d memory_restore --no-owner /tmp/memory.dump
```

For an actual recovery, copy the saved dump to the target PostgreSQL server
first. Restore into a new database, point `MEMORY_DATABASE_URL` at it and use a
separate empty Neo4j instance. Retain the restored administrator credential.
Run `project --project demo --rebuild`, then repeat `project --project demo`
until no queued jobs remain. Verify an agent search, source withdrawal and
historical query against the recovered service before switching callers.
PostgreSQL is authoritative; rebuilding Neo4j does not require restoring its
old projection. A dump contains stored data and credential hashes and needs
the same access controls as the original ledger.

The opt-in [deployment regression](../tests/test_container_deployment.py) uses
a real runtime container and disposable PostgreSQL schemas/database. It checks
non-root/read-only execution, MCP proposal and denied self-approval, operator
approval, a binary `pg_dump`/`pg_restore`, graph reconstruction, retrieval through
a fresh MCP process, and withdrawal while that process is running. CI runs it
with real PostgreSQL/Neo4j/OPA. This verifies this local recovery path, not
distributed failover, a public endpoint or production capacity.

The additional real-model CLI regression is opt-in: build a separate image with
`docker build --build-arg INSTALL_MODELS=true -t governed-memory:models .`, set
`GM_TEST_GENERATION_IMAGE=governed-memory:models` and
`GM_TEST_GENERATION_CACHE_MOUNT` to the Docker daemon's absolute path to a cache
containing the pinned small Qwen weights. With `GM_TEST_DATABASE_URL` set, run
`uv run pytest -q tests/test_container_deployment.py`. The test mounts the cache
read-only, disables Hugging Face downloads, imports/approves the fictional ADR,
answers using an agent credential and verifies withdrawal suppresses the answer.

`docker compose down` stops the local stack while retaining its named volumes.
Removing volumes discards their state, so it is not part of ordinary shutdown.
