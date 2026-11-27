# v0.6: conditional answers without discarding retrieval context

Recorded 2026-11-14, Asia/Shanghai. The 1.5B `standard` service profile now uses
a textual answer with citations, or `{"answer":null}` when evidence is
insufficient. The application normalizes either branch to the existing public
answer/evidence_ids/abstain response. Retrieval, source authority checks and the
v0.5 opt-in relevance cutoff are unchanged. Other profiles retain legacy format;
`MEMORY_ANSWER_FORMAT=json_schema` also restores it for `standard`.

## Development and frozen external execution

Three complete 80-question development comparisons were retained. Each uses the
same four explicit facts per group and the same pinned 1.5B generator. These
fixtures were previously examined; literal gold-value inclusion is a limited
diagnostic, not a human correctness judgment.

| Format | Positive gold value included /48 | Valid negative abstention /32 | Format errors /80 |
| --- | ---: | ---: | ---: |
| Legacy, same-run control | 46 | 17 | 5 |
| V1, separate sufficiency status | 42 | 32 | 0 |
| V2, revised status prompt | 39 | 32 | 0 |
| V3, direct answer or null | 47 | 18 | 0 |

V1/V2 failed the preregistered positive non-regression gate and never reached
external inference. Their raw outputs, failed decisions and original protocols
remain archived. V3 was fixed after development-only iteration and before any
new external generation or scoring. The [v3 protocol](CONDITIONAL_ANSWER_V3_PROTOCOL.md)
keeps the original model/context/token settings and promotion thresholds.
No v3 prompt change followed external results.

For **all 500** archived cross-encoder contexts, the runner verifies the original
prediction and dataset checksums, reconstructs exact packed IDs and token counts,
and newly generates answers. It neither filters nor reranks nor fills context.
Every original context is preserved. This is an engineering comparison on a
previously evaluated public benchmark, not a blind benchmark. Reference answers
do not enter generation; all predictions are sealed before scoring.

Generator: Qwen2.5-1.5B-Instruct@989aa7980e4cf806f80c7fef2b1adb7bc71aa306,
greedy, 384 output tokens, 4,096 input tokens, BF16 on the existing RTX 4080 Laptop
GPU. Source commit `bf35814b099ef0f4846f4e2ab68ef7702bd8f66b`; selected source SHA
`6de1a8a0578b6282e08d71cad1f16ca30a5e1c8572977f2f9f9e9ba838d4ae13`.
Packages, hardware and protocol hashes are in the
[generation provenance](results/conditional-full-v3-2026-11-14/provenance.json).

## Complete results and regressions

The unchanged local Qwen3-4B judge and category rules score every question.
Its 20 calibration checks pass, with no invalid judgments. Scores are local
model estimates, not official GPT results or human review.

| Metric | Archived legacy cross-encoder | Conditional v3 |
| --- | ---: | ---: |
| Questions | 500 | 500 |
| Runtime errors | 0 | 0 |
| Invalid answers | 108 | 0 |
| Valid explicit abstentions on negative questions | 6/30 | 13/30 |
| Negative responses accepted by local judge | 15/30 | 21/30 |
| Positive responses accepted by local judge | 154/470 | 160/470 |
| Overall local judge correct | 169/500 (33.8%) | 181/500 (36.2%) |

The format reliability improvement is clear; the semantic estimate improves by
only 12 questions. Positive questions gain 49 newly accepted answers and lose 43
previously accepted answers; 111 are accepted in both runs. Negative questions
gain 9 and lose 3; 12 are accepted in both. **Aggregate preservation does not mean
every formerly correct answer is preserved.** The descriptive paired exact
test is p≈0.281, so this run does not establish a reliable semantic quality gain.
For 135 unchanged answers with unchanged error status, the judge verdict also
stays unchanged. See the [paired receipt](results/conditional-full-v3-2026-11-14/independent-verification.json)
and [judge stability record](results/conditional-full-v3-2026-11-14/judge-stability.json).

Explicit abstention and a judge-accepted missing-information response are
different metrics: an answer can acknowledge uncertainty in text while its
structured abstain flag remains false. Schema constraints cannot prove that a
cited passage supports an answer. Seventeen negative questions still lack a
valid explicit abstention. General no-answer detection remains unresolved.

The nine recorded data/model gates pass, including development non-regression,
fewer invalid answers, more explicit negative abstentions and aggregate positive
correctness. This supports deploying the format change for the evaluated
`standard` profile, with the legacy override retained. It does not establish
equivalent quality across devices, models or languages.

The 0.5B smoke profile has an observed related-context/owner counterexample and
retains its legacy default. Its opt-in quality probe is an explicit expected
failure after structural/positive checks; runtime or format errors still fail
normally. The [v1 counterexample](results/conditional-small-v1-2026-11-14.json)
and [v2 diagnostic](results/conditional-small-v2-2026-11-14.json) remain visible.

## Artifacts and reproduction

[Predictions](results/conditional-full-v3-2026-11-14/predictions.jsonl),
[judgments](results/conditional-full-v3-2026-11-14/score/scored.jsonl),
[category summaries](results/conditional-full-v3-2026-11-14/score/summary.json),
calibration, hypotheses and checkpoints are archived. Original v0.3/v0.4/v0.5
results are unchanged. Canonical LF SHA-256 values:

- New predictions: `dc1f711b02ba3807feca540ebd06f20040eee427c8de069f4f3ead8edaf88088`.
- New judgments: `37461296e1e3cc4f96e3830ca100cc937ecaeba02b08427d2179d3351a9f5587`.
- Original predictions: `6f2d609e91d6791b839b49c89e9d530491ec9e2c0918cfec5aa02008b21985f6`.

The final runtime changes profile selection/configuration and version metadata;
the evaluated prompt, schema, parser and generation functions are unchanged.
Their AST comparison is in the [compatibility receipt](results/conditional-full-v3-2026-11-14/runtime-compatibility.json).
The bare `generate_answer` helper retains legacy default for old frozen runners.

```sh
python -m eval.conditional_run --stage external --dataset PATH/longmemeval_s_cleaned.json \
  --output .local/new-conditional --model-cache PATH/retrieval \
  --generation-cache PATH/generation --device cuda
python -m eval.full_score --dataset PATH/longmemeval_s_cleaned.json \
  --predictions .local/new-conditional/predictions.jsonl --output .local/new-conditional-score \
  --manifest eval/conditional_v3_manifest.json --generation-cache PATH/generation --device cuda
python scripts/check_conditional_evidence.py \
  --dev eval/results/conditional-dev-v3-2026-11-14 --external .local/new-conditional \
  --score .local/new-conditional-score --output .local/new-conditional-check.json
```

Use the frozen experiment commit and matching CUDA environment to reproduce the
recorded run. Fresh output paths are required; checkpoints support matching-input
resume. New generation latency is retained, but excludes context reconstruction,
retrieval and model loading. It is not a paired comparison with the archived
baseline's retrieval-plus-generation timing, and does not supersede the v0.5
paired retrieval latency evidence. [Runtime verification](../docs/verification-v0.6.md)
covers installation, authorization, configuration and deployment.
