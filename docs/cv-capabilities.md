# CV capability acceptance (v0.4)

This is an implementation and evidence checklist, frozen before the new evaluation.
The existing v0.3 LongMemEval outputs and synthetic results remain unchanged.

| CV capability | Acceptance evidence |
| --- | --- |
| Rust and Python memory engine | Owned Rust BM25/vector/RRF kernels called by the Python retriever; native build, parity tests and end-to-end retrieval |
| Semantic chunking | Pinned sentence embeddings determine boundaries; bounded, exact source spans; raw-document ingestion stages proposals only |
| Entity resolution | Semantic suggestions restricted to visible approved entities; explicit operator resolution creates a new immutable proposal and audit link |
| Contradiction detection | Pinned three-way NLI model, interval-aware comparison, actual positive/negative inference; findings do not confer approval |
| OpenFGA and OPA | Real OpenFGA relationship checks restrict local grants, fail closed, and cannot be set by MCP callers; OPA remains mandatory for governance decisions |
| OpenLineage | Schema-valid events in a transactional outbox, real HTTP delivery and retry, source and dependency inputs, no raw source text |
| Supersession/deletion propagation | Immutable dependency DAG binds exact approved snapshots; changes atomically invalidate descendants and queue graph/lineage updates |
| Upgrade and deployment | Additive upgrade from v0.3, PostgreSQL and graph integration, container smoke, clean install and CI |
| Quantitative claims | Frozen controlled protocol, session baseline, raw observations, reproducible aggregates and measured limitations |

## Trust and maintenance boundaries

PostgreSQL remains authoritative. Rust computes ranking and segmentation; it does
not introduce a second persistent store. Native acceleration is optional, and the
Python path remains available for core installs. Both paths use the same authorized
evidence and final eligibility recheck.

Model extraction, entity suggestions and NLI findings are advisory. Only the
existing authenticated operator approval path can create trusted fact snapshots.
Resolution records preserve both original and replacement proposals. Derivations
are separate from independent corroborating sources. Each derivation depends on
specific approved snapshots and source revisions; it must be reviewed again after
one of these inputs changes. Invalidation is conservative and transitive, including
historical reads, just as current source withdrawal overrides historical access.

OpenFGA is an additional authorization intersection, never a replacement for local
ACLs, audience restrictions or OPA. All external configuration belongs to the
operator environment. OpenLineage delivery is at least once: retries retain the
same event/run identifiers, and a collector should deduplicate them.

## Evidence that implementation cannot establish

The CV's 83.2% temporal recall, 26.4% stale-retrieval reduction and 1.12 s P95 are
unverified targets, not acceptance thresholds to tune against. New measurements
will be reported as observed, with their workload, baseline and hardware. Neither
the v0.3 83.3% session recall nor its 33.8% local QA score establishes these claims.
The February–May 2025 project dates need contemporaneous records; coding now does
not establish those dates. Kubernetes and a full frontend are outside this CV entry.

## Verified outcome

All engineering paths above are now exercised; see
[v0.4 verification](verification-v0.4.md) and the
[controlled results](../eval/RESULTS-v0.4.md). The measured warm P95 is 1.264 s;
controlled recall is 100% for both methods and stale-rate reduction is 100% for
this corpus. Negative-query relevance remains limited. These observations do not
retroactively establish the original three CV numbers or the 2025 dates.

## v0.7 measured extension

The [new controlled comparison](../eval/RESULTS-v0.7.md) retains the original
protocol/data and adds a separately frozen scalability/cache experiment. Its
largest case has 1,152 synthetic historical assertions and 84 queries replayed
three times per method: positive temporal Recall@5 is 100% versus 85% for the
session baseline; stale evidence is 0/789 versus 498/816. Overall retrieval P95
is 540.4 ms, compared with 627.9 ms for the same governed retriever without score
reuse. Repeat-query P95 falls from 623.5 to 410.6 ms (34.1%). All 996 paired
governed outputs across the four workloads remain identical.

These are new, bounded measurements that can replace CV numbers when their
synthetic-workload and retrieval scope is retained. They do not reconstruct the
original experiment or establish general answer accuracy, production capacity
or historical dates. First-use gains are not established, and unrelated eligible
negative-query evidence remains a limitation. See the [v0.7 verification](verification-v0.7.md).
