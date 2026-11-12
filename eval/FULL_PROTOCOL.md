# Full cleaned-S retrieval and answer protocol

This extension uses all 500 questions from the same pinned LongMemEval cleaned-S
file as the earlier 14-question comparison. It evaluates retrieval followed by
generated, cited answers. The earlier subset results were already known; this
is an expanded public-data evaluation, not a previously unseen heldout set.

`full_manifest.json` freezes all question IDs, the dataset revision/checksum,
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

The separate scorer reports exact match and token F1 on answerable questions
other than preference rubrics. A distinct, pinned Qwen3-4B model also judges the
answers using category-specific rules and 20 synthetic sanity checks. This is
a **local model judge estimate**, not the official GPT-graded score or human
review. Invalid/failed answers and judgments remain non-passing in the complete
500-question denominator. Judge outputs, answer errors, calibration and category
counts are preserved. The scorer also exports one official-format hypothesis
file per method so another grader can be used without regenerating answers.

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
The application lock selects CPU wheels by default; the recorded GPU environment
is documented separately. Generation uses bfloat16 on supported Ampere-or-newer
GPUs, float16 on older CUDA GPUs, and float32 on CPU.

Sources: [LongMemEval](https://github.com/xiaowu0162/LongMemEval),
[upstream evaluator at the reviewed revision](https://github.com/xiaowu0162/LongMemEval/blob/9e0b455f4ef0e2ab8f2e582289761153549043fc/src/evaluation/evaluate_qa.py),
[Qwen2.5-1.5B](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct),
[Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507).
