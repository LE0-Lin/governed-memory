# v0.2 verification — 2026-11-10

The frozen synthetic suite was rerun after the optional policy/model integration
and source-corroboration changes. Data, methods, k=3 and the 1,024-token evidence
budget are unchanged. The recorded source commit is
`c47751a176ed30d5cdb81cbca7269f3cff10e7d7`; provenance reports clean source.

Raw output: [predictions](results/2026-11-10-v0.2/predictions.jsonl),
[operations](results/2026-11-10-v0.2/operations.jsonl),
[summary](results/2026-11-10-v0.2/summary.json),
[provenance](results/2026-11-10-v0.2/provenance.json).
All 768 retrieval calls and 48 operation checks completed without errors.

On 33 heldout retrieval/time controls, both complete governance and the temporal
baseline recalled all 45 required facts for the 30 answerable queries and
correctly returned no evidence for the three empty-gold queries. Governed P50/P95
was 4.61/6.13 ms versus 1.46/2.02 ms for the temporal baseline. These are local
SQLite/hash-vector measurements, not a throughput comparison or proof that the
new implementation is faster than v0.1.

Across all 96 heldout queries, the governed method covered 66/66 answerable
queries, handled 30/30 empty-gold cases, returned 84/84 complete provenance
records and exposed no stale, unapproved, withdrawn or future system-time
metadata. Unauthorized query retrieval succeeded 0/30 times; withdrawal leaks
were 0/15. Across both splits, unauthorized approvals succeeded 0/24 times and
legitimate approvals succeeded 24/24 times. The
[original analysis and limitations](RESULTS.md) still apply; the small synthetic
suite is not a general security guarantee.

## Integration and package checks

- Local full regression: **123 passed, 2 skipped** with PostgreSQL 17.6, Neo4j
  5.26.12, OPA 1.22.2 and the actual pinned neural models enabled. The skips are
  PostgreSQL-only concurrency cases in the SQLite parameterization.
- Native policy checks: **10/10 Rego tests**. The HTTP integration also compares
  built-in/OPA decisions across 400 role/action/state/protection combinations and
  checks transaction rollback when policy evaluation fails.
- CI [run 42682819631](https://github.com/LE0-Lin/governed-memory/actions/runs/42682819631):
  Windows core, Ubuntu core, real storage/evaluation and local models all passed.
  Storage ran 119 tests with six applicable environment skips; the separate model
  job ran three learned-model tests. The combined local run above also exercised
  learned graph retrieval. The preceding run failed workflow validation before
  any tests: a job environment used the unavailable `runner` context. The cache
  path was moved to a workspace-relative value and CI then ran successfully.
- Ruff lint/format and wheel/sdist build passed. A fresh core environment installed
  locked dependencies and the v0.2 wheel offline. The wheel includes Rego and the
  vendored tokenizer license, does not install optional PyTorch, and runs the
  demonstration with external network access blocked.
- An actual v0.1 CLI created a ledger and approved a fact. The v0.2 installed wheel
  required explicit `upgrade`, then preserved the original ID, revision and admin
  credential. Through CLI commands, approved corroboration kept the fact visible
  after the original source was withdrawn; withdrawing the remaining source hid
  it. This supports the additive upgrade, not arbitrary migration/rollback.

The optional learned retrieval comparison is recorded separately in
[LONGMEMEVAL.md](LONGMEMEVAL.md). It preserves a missed-session result and shows
no gain from reranking over BM25 on its 14-question subset. Neither evaluation
uses an answer generator or claims human code review.
