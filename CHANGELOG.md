# Changelog

## 0.9.0

- Add an installed `governed-memory demo` command and `--version`. The demo
  ignores live service configuration and uses an isolated in-memory ledger.
- Verify built wheels outside the source checkout, including core installation
  without PyTorch, offline demo, persistent MCP proposal/approval, denied agent
  self-approval, fresh-process retrieval and warm-process source withdrawal.
- Provide English/Chinese repository guides, visual overview, a first-use ADR,
  release installation constraints and a measurement card with finite denominators.
- Clarify that controlled 60/60 and zero observed stale results are not accuracy
  or production guarantees. Last full-path performance data remain v0.8.1;
  no new retrieval/answer quality or speedup is claimed.

See [installation verification](docs/verification-v0.9.0.md) and the
[release assets](https://github.com/LE0-Lin/governed-memory/releases/tag/v0.9.0).

## 0.8.1

- Establish full same-host retrieval timing through PostgreSQL, Neo4j, OpenFGA
  and MCP stdio. Preserve independent rescores and live-authority probes.
- Revert a pooling candidate after its prespecified latency gate failed;
  retain both complete studies. Production source stays identical to 0.8.0.

## 0.8.0

- Narrow the last fresh evidence read to selected snapshot IDs while preserving
  source/ACL/dependency checks and empty-result reasons. Retain both experimental
  attempts and [paired results](eval/RESULTS-v0.8.md).

## Earlier releases

- **0.7.0:** bounded exact reranker-score reuse, with live authority checks.
- **0.6.1:** corroboration-revocation dependency/outbox repair and upgrade checks.
- **0.6.0:** conditional cited answers and preserved 500-question comparison.
- **0.5.0:** document-vector cache and opt-in relevance filter with transfer limits.
- **0.4.0:** native kernels, semantic review, OpenFGA/OpenLineage and dependencies.

See [evaluation records](eval/README.md), [evaluation scope](docs/evaluation.md)
and the [Git history](https://github.com/LE0-Lin/governed-memory/commits/main) for
original protocols, test evidence and unchanged negative results.
