# Full cleaned-S retrieval and answer protocol

This extension uses all 500 questions from the same pinned LongMemEval cleaned-S
file as the earlier 14-question comparison. It evaluates retrieval followed by
generated, cited answers. The earlier subset results were already known; this
is an expanded public-data evaluation, not a previously unseen heldout set.

`full_manifest.json` freezes the original unconstrained run's question IDs, dataset revision/checksum,
models and generation limits before inference. All three methods use the same
complete input histories, future-session exclusion, 200-wordpiece windows with
40 overlap, k=8 and a 2,048-token evidence budget. Methods remain BM25, learned
hybrid, and learned hybrid with a cross-encoder. Every method/question pair is
retained, including retrieval failures, malformed answers and abstentions.

Generation uses Qwen2.5-1.5B-Instruct at the pinned manifest revision, greedy
decoding and at most 384 output tokens. The prompt contains the question, date
and retrieved evidence only. Short citation aliases (`E1`, `E2`, ...) map back
to actual evidence IDs; unknown citations or malformed JSON fail closed.
Reference answers, answer-session labels and message answer flags never enter
retrieval or generation. Predictions are finalized and hashed before scoring.

## Format-constraint comparison

During v1 inference, shape-only diagnostics found frequent malformed JSON and
wrong field types. The complete v1 run is retained, including these failures.
Before inspecting reference answers or semantic scores, a second protocol was
frozen as `full_structured_manifest.json`. It keeps all question IDs, model
revisions, retrieval settings, prompts and token limits unchanged, and adds
JSON Schema token constraints using LM Format Enforcer. Field types, required
keys and citation aliases are constrained; `parse_answer` still checks answer
and abstention invariants. Token exhaustion and semantic mistakes can still
fail. The library is pinned to the upstream revision with its Transformers 5
import fix.

This is an engineering comparison motivated by observed format failures on the
same public data. It is not blind validation, a new heldout set or evidence of
semantic-answer tuning. Both complete prediction sets are finalized before
running the same local judge. The unconstrained protocol is reproduced at
commit `54b2593`; the current runner defaults to the structured protocol.

## Scoring and reproducibility

The separate scorer reports exact match and token F1 on answerable questions
other than preference rubrics. A distinct, pinned Qwen3-4B model also judges the
answers using category-specific rules and 20 synthetic sanity checks. This is
a **local model judge estimate**, not the official GPT-graded score or human
review. Invalid/failed answers and judgments remain non-passing in the complete
500-question denominator. Judge outputs, answer errors, calibration and category
counts are preserved. The scorer also exports one official-format hypothesis
file per method so another grader can be used without regenerating answers.
These exports contain the fail-closed answer and a `response_error` field. To
keep this protocol's failure policy, a grader must count any error row as
non-passing; an unmodified external evaluator may accept a fallback abstention
on an unanswerable question instead.

Both stages save per-case files and support `--resume` only with matching code,
protocol, inputs, package versions and device/hardware. Completed cases are not
silently replaced. Model/kernel warmup uses unrelated synthetic text; indexing
cost is measured separately from retrieval-plus-generation latency. Inference
uses one sequential caller and no query/answer cache. CPU and GPU measurements
have separate run provenance and must not be presented as the same measurement.

The benchmark has no organization approval labels and does not exercise the SQL
ledger or Neo4j. Those authorization and deployment paths have separate tests.
The application and benchmark share model adapters, fusion, evidence budgeting,
answer prompting and citation validation. These results do not establish model
training-data independence, general prompt-injection defense or production scale.

```sh
uv sync --frozen --extra dev --extra models
uv run python -m eval.full_run --dataset .local/longmemeval/longmemeval_s_cleaned.json --output .local/full-new --model-cache .local/model-cache --generation-cache .local/generation-cache
uv run python -m eval.full_score --dataset .local/longmemeval/longmemeval_s_cleaned.json --predictions .local/full-new/predictions.jsonl --output .local/full-score-new --generation-cache .local/generation-cache
```

For CUDA, use a matching CUDA PyTorch installation and pass `--device cuda`.
The application lock selects CPU wheels by default; see [the recorded GPU environment](GPU_ENVIRONMENT.md).
Use `--manifest eval/full_manifest.json` when scoring the preserved v1 predictions.
Generation uses bfloat16 on supported Ampere-or-newer
GPUs, float16 on older CUDA GPUs, and float32 on CPU.

Sources: [LongMemEval](https://github.com/xiaowu0162/LongMemEval),
[upstream evaluator at the reviewed revision](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/src/evaluation/evaluate_qa.py),
[Qwen2.5-1.5B](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct),
[Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507).
