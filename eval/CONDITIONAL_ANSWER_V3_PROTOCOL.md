# Conditional answer experiment v3: direct answer or null

Frozen before v3 inference, 2026-11-14 Asia/Shanghai. V1 and v2 both failed the
development positive non-regression gate (46/48 baseline vs42/48 and39/48).
All outputs and failed decisions remain immutable. Neither candidate reached
external inference; external outcomes have not selected these prompt revisions.

V3 removes the separate status classifier. It asks directly for the answer and
citations, using `{"answer":null}` only when evidence is insufficient. The output
schema makes the two branches disjoint and requires citations for a textual
answer. This removes the redundant boolean/status decision and keeps the public
answer/evidence_ids/abstain response unchanged. Schema validity still does not
establish semantic support or prevent hallucination.

Use the same complete80-query paired development set and retain all outputs.
Then, only if its dev gate passes, regenerate all500 unchanged archived contexts.
The [original protocol](CONDITIONAL_ANSWER_PROTOCOL.md) data, model revisions,
token limits, scoring, failure policy and promotion criteria remain unchanged:
dev positive gold inclusion>=legacy, dev negative abstention>=legacy;
all500 runtime errors0, invalid answers<108, valid negative abstentions>6/30,
positive local-judge correct>=154/470 and overall>=169/500. Do not revise v3
after external outcomes. No question selection, cutoff tuning or context removal.

These are development-set iterations. Both the synthetic data and the public
external benchmark have been evaluated previously; claim no blind benchmark or
training-data independence. A default change must identify the actually
validated generation profile, rather than assume transfer to other model sizes.
