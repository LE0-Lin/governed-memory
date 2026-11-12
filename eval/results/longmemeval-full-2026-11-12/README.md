# Full cleaned-S raw evidence — 2026-11-12

Each variant contains all 500 questions × three methods (1,500 outputs).
`v1` is unconstrained JSON at commit54b2593; `v2` is constrained JSON at
commitbdb3112. Both use the same pinned models, contexts, prompts and limits.

- `v1/` and `v2/`: predictions, raw model text, retrieval-only scoring,
  start/provenance records and original inference logs.
- Each `score/`: all 1,500 judgments, category summaries, 20-item calibration,
  scoring provenance, and three official-format hypothesis exports.
- `comparison.json`: independent format/citation diagnostics and retrieval-ID
  rescore/context-match checks.
- `timing-interruption.json`: the retained multi-hour cross-encoder answer outlier;
  total wall time is not continuous GPU compute.
- `scoring-walltimes.json`: UTC receipts for both judge stages.
- `checksums.json`: SHA-256 of every artifact before this README, with CRLF
  normalized to LF, matching the runner's hash convention.

The complete source dataset/model weights and local per-case resume caches are
not included. Excerpts are from the public MIT-licensed LongMemEval cleaned-S
dataset, not private user conversations. See [attribution](../../../THIRD_PARTY.md).

Read [the report](../../RESULTS-v0.3.md) and [frozen protocol](../../FULL_PROTOCOL.md).
Scores are local model estimates; no human or official GPT grading is claimed.
