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

## v0.8 final authority read

The [paired v0.8 study](../eval/RESULTS-v0.8.md) compares the exact v0.7 runtime
with a narrowed final live read. In the largest synthetic case, overall P95 is
521.9 -> 408.3 ms (21.8% lower), first-pass P95 602.9 -> 558.3 ms (7.4%), and
repeat P95 400.6 -> 378.9 ms (5.4%). Both variants retain 100% positive temporal
Recall@5 and zero stale evidence. All 996 pairs match complete ordered evidence,
tokens and reasons; 1,992 observations complete without retrieval errors.
The runner differs from v0.7, so only within-run deltas are valid.

The first version was slower overall and was rejected, with its raw results
preserved. The final version clears the prespecified largest-case overall and
first-pass gates; smallest-case and heldout first-pass P95 still worsen 4.7%
and 5.0%. This round does not establish a quality gain or universal acceleration.
Regular six-job CI and the separate paired/model-container jobs pass; see
[v0.8 verification](verification-v0.8.md).

The CV's listed engineering features are exercised. Current synthetic recall,
stale filtering and retrieval latency support a scoped replacement for its
unverified numbers. Independent real histories, full graph/remote-policy and
transport latency, production/concurrency evidence and contemporaneous 2025
records remain unproved. No numerical completion percentage follows from this
checklist, and no CV wording or date was changed.

## v0.8.1 full-path evidence

The [full MCP baseline](../eval/RESULTS-v0.8.1.md) adds actual Neo4j and OpenFGA
HTTP plus caller-observed stdio transport. Current large-case positive temporal
Recall@5 is 100%, stale evidence 0/792, retrieval P95 0.762 s (first 0.806/repeat 0.516).
The CV original values remain 83.2%, 26.4% fewer stale retrievals and 1.12 s; the
archived session comparison established 100% stale-rate reduction, not a new
full-path session baseline. Preserve those different scopes.

The proposed pooling optimization regressed largest overall/first P95 by 8.8%/
11.7% and was reverted. Production source is identical to v0.8; this release
improves evidence coverage, not runtime performance. The final full-path run
has 1008 observations, 504 exact pairs and no errors/stale results, with actual
warm-process revocation/downgrade and stale-graph withdrawal checks. This closes
the prior same-host graph/authorization/transport timing gap. Independent real
histories, WAN/concurrency/production performance and historical dates remain.
