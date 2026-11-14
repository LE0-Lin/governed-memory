# v0.6.1 verification record

Verified locally on 2026-11-14, Asia/Shanghai. This patch repairs a core governance
consistency defect; it changes neither answer generation nor benchmark settings.

## Reproduction and change

After a primary source was withdrawn, an independently approved corroborating
source could support a new derivation. Revoking that corroborating **approval**
correctly hid the derivation during reads, but left its stored candidate state
active and its completed graph job unqueued. Further descendants and pending
proposals were likewise not transitioned. The graph could retain their stale
edges, although authoritative reads already excluded them.

The originating revocation transaction now finds dependencies bound to both the
corroborated assertion's snapshot and the revoked support's source. It propagates
the existing lifecycle invalidation through descendants, appending audit and
OpenLineage events and requeuing graph jobs atomically. A valid primary-bound
derivation and other assertions in the same imported JSONL source are preserved.
Protected descendants also lose eligibility when their bound input is retracted.

An administrator can run `upgrade --project PROJECT` to repair inconsistencies
left by earlier versions. It reports `dependency_repairs`, appends ordinary
lifecycle records, and is project-scoped and idempotent. Workers must then drain
the queued graph jobs. No schema version or answer format changed. The
[operator instructions](usage.md#upgrade-an-existing-installation) describe backup,
shutdown and the explicit repair boundary.

## Validation

The new SQLite regressions first produced four failures and one passing control
on the original runtime. After the fix, the complete core/storage group reports
**279 passed, 9 skipped** with real PostgreSQL, Neo4j, OPA and OpenFGA configured.
It covers selective propagation, protected/transitive/pending descendants,
historical reads, audit/lineage delivery, rollback after an injected outbox
failure, and administrator-only repeatable repair.

Two actual installed-container workflows pass, with two SQLite-only skips:
existing MCP permissions/persistence/backup/recovery, and an old-to-new upgrade.
The latter runs the published **v0.6.0** image to create inconsistent states in
two projects and drain the old outbox. Three graph edges remain per project:
two stale descendants and one independent fact. The new **v0.6.1** image repairs
two approved descendants and one pending proposal only in the selected project;
a repeat repairs zero. Source hashes and all prior audit/lineage records are
preserved. Draining two new graph jobs removes the stale edges and retains the
independent fact. The second project changes only when explicitly upgraded.

These non-overlapping local groups total **281 passed and 11 skipped** across
292 configurations. Five skips are the optional native extension absent from
the Windows development environment; six are SQLite configurations of
PostgreSQL-only checks. The unchanged ten model configurations and eight model
container configurations were not rerun locally for this ledger-only patch.
The full collection contains 310 configurations. Earlier model results remain
documented in the [v0.6 record](verification-v0.6.md).

Ruff checking/formatting, native OPA 1.22.2 Rego tests (10/10), the unchanged
frozen governance suite (768 retrievals, 48 operation checks, zero execution
failures), the network-denied example and wheel/sdist builds pass. The frozen
suite uses SQLite and lexical hash embeddings; it establishes no new model,
latency or general QA result. Repository CI is pending for this patch.

## Installed artifacts and limits

The core image is `sha256:00c3700eaac0effe03c8d434d39ee57eca3b6def70b487f3ebb94c9b87c69bb1`.
It runs installed 0.6.1 as UID 10001, with a read-only root, no capabilities and
the native extension; a network-disabled probe confirms no PyTorch installation.
The old image is the unchanged v0.6 core image recorded previously.

The repair preserves the original parent/source binding. It does not silently
rebind a derivation to another source, resurrect revoked candidates, or rewrite
past approvals. A replacement derivation requires a fresh review. The old
500-question outputs, quality limitations, historical CV dates and unsupported
prewritten CV percentages remain unchanged.
