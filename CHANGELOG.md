# Changelog

## 0.9.1

- Enable the decomposed `minilm-relevance-v2` gate by default when the local
  reranker is active (`MEMORY_RELEVANCE_FILTER=auto`), cutting unrelated negative
  items from `324` to `15` across three replays on the 80-query blind heldout set
  while retaining `47/48` (97.92%) positive recall.
- Add a 16-record non-template engineering ADR and coding-session evaluation
  corpus (`14/14` positive recall, `0/54` stale/unsafe items vs. `63/180` on the
  session baseline).
- Update GitHub Actions workflows to current Node 24 action releases.

## 0.9.0

- Add an installed `governed-memory demo` command and `--version`. The demo
  ignores live service configuration and uses an isolated in-memory ledger.
- Verify built wheels outside the source checkout, including core installation
  without PyTorch, offline demo, persistent MCP proposal/approval, denied agent
  self-approval, fresh-process retrieval and warm-process source withdrawal.
- Provide English/Chinese repository guides, visual overview, a first-use ADR,
  release installation constraints and a measurement summary with finite denominators.

See [installation verification](docs/verification-v0.9.0.md) and the
[latest release](https://github.com/LE0-Lin/governed-memory/releases/latest).

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
- **0.4.0:** native Rust kernels, semantic review, OpenFGA/OpenLineage and dependencies.

See [evaluation records](eval/README.md) and [evaluation scope](docs/evaluation.md)
for protocols, test evidence and retained negative results.
