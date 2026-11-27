# Semantic ingestion and external governance

Use the existing [operator credential workflow](usage.md). Agent MCP tools can
propose dependencies; only the operator CLI can approve, resolve entities, manage
OpenFGA relationships or export lineage.

## Native ranking and semantic ingestion

```sh
uv sync --frozen --extra dev --extra models --extra native
```

Native builds require Rust 1.83+ and Python 3.12; Windows also needs MSVC C++ build
tools. CI builds Linux and Windows. The container includes compiled Rust kernels
without a compiler. `MEMORY_RANKING_BACKEND=rust` requires the extension; `python`
selects the reference implementation. Default `auto` uses Rust when installed.
Responses report `ranking_engine`. PostgreSQL still owns all authoritative state.

Set `MEMORY_LOCAL_EMBEDDING=1`, `MEMORY_MODEL_CACHE`,
`MEMORY_GENERATION_CACHE` and a pinned `MEMORY_GENERATION_PROFILE` (`small` or
`standard`). The first model download needs network access; cached models support
`HF_HUB_OFFLINE=1`.

```sh
uv run governed-memory ingest-document --project demo notes.txt \
  --locator session:design-meeting --valid-from 2030-01-01T00:00:00Z
uv run governed-memory review --project demo CANDIDATE_ID
uv run governed-memory resolve-entity --project demo CANDIDATE_ID \
  --target APPROVED_SNAPSHOT_ID --expected-revision 0 --reason "Same component"
```

MiniLM sentence embeddings choose boundaries under a 180-token default cap, with
exact Unicode character spans and no dropped source text. The generator proposes
at most three assertions per chunk. Subject and value must occur verbatim in the
chunk; the application binds the source quote itself. Dates are caller supplied.
An invalid or unfinished extraction aborts the entire import. Predicates and
interpretation still require review; no extraction accuracy is claimed.

`review` suggests visible approved entities and compares at most 20 related,
overlapping snapshots with pinned three-way NLI. The DeBERTa NLI model is English;
contradiction is flagged at 0.8. Scores are advisory, not calibrated probabilities
of factual correctness. All input authority is rechecked after inference.
`resolve-entity` rejects the original proposal, stages a canonicalized replacement
and records an immutable link. Inspect source spans and use ordinary
`preview`/`approve` with the returned revisions to approve the replacement.
Generated text never writes directly to Graphiti.

## Derived memories

```sh
uv run governed-memory derive --project demo --subject deployment \
  --predicate decision --value "Use the approved database" \
  --valid-from 2030-01-01T00:00:00Z --parent APPROVED_SNAPSHOT_ID \
  --locator decision:deployment-plan
```

Repeat `--parent` for up to 32 inputs. They must be current approved snapshots in
the same project, visible to the proposer and cover the complete derived interval.
Approval rechecks input revisions. Reading requires current access to every input;
a public derived source cannot declassify a private ancestor.

Revocation, overlapping supersession or withdrawal of a bound source atomically
invalidates descendants and queues graph/lineage changes. Active or superseded
descendants become revoked; pending ones become rejected. This includes protected
descendants: a protection flag cannot restore missing evidence. Invalidation is
conservative across a complete derivation, even when a parent retains another
time slice or independent source. Review a new derivation after a change. Current
invalidation overrides historical reads; audit history remains stored. Only new
proposals may depend on approved snapshots, preventing cycles. Depth beyond 32
fails closed. Independent corroboration (`approve-support`) is a separate relation.

## OpenFGA and OPA

```sh
docker compose --profile policy --profile governance up -d --wait
```

The governance profile includes dedicated persistent PostgreSQL storage, OpenFGA
migrations and the pinned official image. Set
`MEMORY_OPA_URL=http://127.0.0.1:58181` and, initially, only
`MEMORY_FGA_URL=http://127.0.0.1:58080`. With a local admin credential:

```sh
uv run governed-memory fga-setup --project demo
```

Save the returned `MEMORY_FGA_STORE_ID` and `MEMORY_FGA_MODEL_ID` in the server
environment. Setup provisions a dedicated store/model with that project's current
grants. Later local credentials also need an external relationship:

```sh
uv run governed-memory fga-grant --project demo --principal agent-name --role agent
uv run governed-memory fga-grant --project demo --principal agent-name --role agent --remove
```

Roles inherit admin → approver → writer → reader. Each request uses the pinned
model and `HIGHER_CONSISTENCY`, with no allow cache. The effective role intersects
local and external grants, including OPA and private-source checks. Incomplete
configuration, unavailable services and malformed decisions fail closed. Local
withdrawal independently denies access. The management API is operator
infrastructure; configure upstream authentication for shared deployments and pass
`MEMORY_FGA_API_KEY` when needed. Bootstrap additional projects in their own store,
or administer a shared model with upstream tools. App containers use
`MEMORY_CONTAINER_FGA_URL=http://openfga:8080` with the same store/model IDs.

## OpenLineage and upgrades

Set `MEMORY_LINEAGE_ENDPOINT` to the complete collector events URL (for example,
`http://collector:5000/api/v1/lineage`); `MEMORY_LINEAGE_API_KEY` is optional.

```sh
uv run governed-memory lineage --project demo --limit 100
uv run governed-memory upgrade --project demo
```

Governance, resolution, snapshot and source changes enqueue schema-valid
OpenLineage `COMPLETE` events in their SQL transaction. Source/snapshot/candidate
datasets include stable IDs, dependency inputs and lifecycle facets. Raw source
text, claim values and credentials are not exported. Payloads are immutable and
delivery bookkeeping is separate. Collector failures leave events pending. Delivery
is at least once: collectors should deduplicate by stable `runId`. SQL invalidation
continues while the collector or graph is unavailable.

Upgrade adds current tables/triggers to v0.3 without rewriting approved records.
Follow the [backup/recovery procedure](deployment.md), including OpenFGA's separate
database when external authorization is enabled.
