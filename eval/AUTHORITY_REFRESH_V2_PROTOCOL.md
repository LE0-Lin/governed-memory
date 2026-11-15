# Final authority read comparison v2

Frozen before this revision's measurement, 2026-11-15. The complete v1 run
(GitHub43716291311, source63eec49) is retained. It had1,992 error-free
observations and996 identical pairs, but the large-case overall P95 regressed
371.6->488.0 ms (+31.3%), first-pass454.4->528.5 ms (+16.3%). Repeat P95 improved
369.8->340.0 ms (-8.0%). It does not justify a general performance promotion.

## Revision and unchanged gates

Restore the original Source ORM columns/materialization. The candidate now
changes only the final visibility query's optional exact-snapshot restriction,
and its empty-subset fallback that preserves existing reason codes. Keep the
first three reads, source object loading, models, caches, kernels, budgets,
ordering and source/ACL/dependency checks exactly as before. This isolates the
late restriction from the other v1 change; it does not assume which caused the
regression. Runtime files may still differ only in ledger.py and retrieval.py.

Use the exact same reference commit, shared-file validation, four known
synthetic workload recipes, explicit labels, model revisions, cache capacities,
single caller, rotating method order and three replays from
AUTHORITY_REFRESH_PROTOCOL.md. Both methods start with empty caches and warm
only unrelated text. Expected1,992 observations,996 pairs,8 summary groups.
Record all first-pass and repeat costs and all errors/outliers. Preserve v1
and every subsequent attempt, with distinct run identities and source hashes.

Run on one isolated GitHub-hosted CPU runner with actual PostgreSQL, because
the local C: storage fault prevents WSL execution. Record actual hardware and
versions. Compare only within each paired run; do not subtract the old Ryzen
timings or v1 runner results from v2 as if they were controlled speedups.

The immutable exact-output, zero-stale/error and regression gates remain.
For this round's objective, do not promote the candidate if the largest
case's first-pass OR overall P95 is worse than its same-run reference. A
repeat-only gain cannot compensate for this regression. Report smaller-case
regressions explicitly too. No inference about production accuracy/capacity,
unseen histories, full graph/remote-policy latency or CV dates is permitted.
The installed-model MCP test and regular six-job CI must pass for the final
runtime. No CV edits or new500-answer generation are authorized by this run.
