# v0.4 verification

Verified on 2026-11-13 (Asia/Shanghai). This release fills the engineering gaps in
the [CV acceptance matrix](cv-capabilities.md); it does not establish historical
project dates or turn prewritten CV numbers into measured results.

## Implemented paths

- Owned Rust kernels calculate BM25, cosine/RRF and semantic boundaries. Python
  retains the authoritative ledger, approval transactions and eligibility checks.
- Pinned MiniLM segmentation preserves exact Unicode source spans. Local extraction
  can stage only bounded assertions whose subject/value occur in the original
  chunk. Separate operator approval remains mandatory.
- Entity matching and English NLI operate only on visible approved snapshots.
  Resolution preserves the original proposal and stages a separately reviewable
  replacement. Findings cannot change trust or identity.
- OpenFGA intersects local roles, including OPA and private-source checks. The
  pinned model uses higher-consistency reads and fails closed on service errors.
- Immutable dependencies bind exact snapshots and source revisions. Supersession,
  revocation and source withdrawal invalidate descendants in the same transaction,
  even when a graph worker or lineage collector is unavailable.
- Standard OpenLineage events use an immutable transactional outbox with separate
  retry bookkeeping. Payloads exclude raw source text and credentials.

## Checks

The [verified source CI](https://github.com/LE0-Lin/governed-memory/actions/runs/43283570683)
passed all six jobs: Windows/Ubuntu core, Windows/Ubuntu native, real storage and
evaluation, and actual local models. The native jobs compile the extension, run
Cargo tests, formatting and Clippy, then install through the native extra and run
Python integration tests. The storage job uses PostgreSQL, Neo4j, OPA and durable
OpenFGA/PostgreSQL through Compose.

Local Windows checks with actual storage, embedding/reranking, NLI and generation
enabled passed **212 tests**, with **9 skips**, excluding the container module.
Additional checks passed separately:

| Check | Observed result |
| --- | --- |
| Core hardened container, backup/restore and fresh MCP session | 1 passed, 1 SQLite skip |
| Real CPU answering and semantic operator commands in the model container | 2 passed, 2 SQLite skips |
| Compiled Linux native kernels with SQL/governance regressions | 39 passed |
| Rust unit tests | 2 passed; formatting and Clippy passed |
| Native OPA rules | 10 passed in CI |
| Core wheel in an isolated installation | No PyTorch; network-blocked example passed |
| Native wheel distribution | Compiled abi3 wheel; MIT notice verified inside the wheel |
| v0.3-compatible schema upgrade | Approved records preserved when adding new tables/triggers |
| OpenFGA persistence | Migrations succeeded; relationships remained usable after server restart |
| Lineage collector failure | Real HTTP 503/retry; same run IDs; official schemas validated offline |
| Concurrent approval and withdrawal | No derived assertion remained active or visible |
| Stale graph and dependency invalidation | Immediate SQL exclusion, followed by removal of derived graph edges |

The semantic container check exercises raw-file ingestion, invisible pending
proposals, explicit approval, Rust-backed search, derivation, NLI review, entity
resolution and source withdrawal through installed CLI processes. It uses UID
10001, a read-only root, capability removal, temporary storage and read-only model
caches. Its cold-process duration is not retrieval-service latency.

## Artifacts and limits

The [controlled comparison](../eval/RESULTS-v0.4.md) retains all 504 observations,
the frozen protocol, source commit/hash, actual model revisions and hardware.
[The execution receipt](../eval/results/cv-v0.4-2026-11-13/verification.json)
records image digests and individual CI jobs. The runtime model image uses CPU
PyTorch; model weights remain in the private cache and are not committed.

Local model-image builds needed the existing host proxy forwarded to the build;
initial connection failures were build-network failures. Dependency pins and
application behavior were unchanged. The temporary benchmark image adds Git only
to record the mounted source commit; production images do not need it.

The prior [500-question QA results](../eval/RESULTS-v0.3.md), including invalid
answers, low local-judge accuracy and the original timing outlier, are unchanged.
This release remains an experimental service with bounded, explicit governance
paths. NLI and extraction are advisory; controlled retrieval results do not certify
general answer accuracy or production-scale latency.
