# Conditional answer experiment v1

Frozen before candidate inference, 2026-11-14 Asia/Shanghai. The v0.5 raw-score
cutoff rejected useful long-conversation context. This experiment keeps every
original retrieved context and changes only answer prompting and its JSON shape.
It does not tune or replace the frozen relevance cutoff.

The candidate first chooses an answer or insufficient-evidence branch. A valid
answer must contain text and at least one permitted citation. The insufficient
branch contains only a fixed status. The application maps both to the existing
answer/evidence_ids/abstain response and retains all authority rechecks. These
constraints enforce output invariants; they cannot prove semantic support.

Use the existing 80-query synthetic development fixtures for a diagnostic paired
generation with all four facts per project. This dataset and its labels were
previously examined; it is not new blind evidence. Run one fixed candidate,
without selecting prompts from external outcomes. Record errors, valid
abstentions and exact gold-value inclusion on positive questions. Preserve every
case, including a failed development diagnostic.

Then regenerate answers for **all 500** archived cross-encoder contexts from
the v0.3 structured run, without filtering, reranking or filling them. Verify
canonical archived predictions SHA-256
`6f2d609e91d6791b839b49c89e9d530491ec9e2c0918cfec5aa02008b21985f6`
and pinned public dataset SHA-256
`d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
Reconstruct original chunk text with the original tokenizer and verify packed
IDs/token counts as in the v0.5 replay. Labels never cross into generation.
Do not reuse old answers as candidate answers. This is an engineering comparison
on previously evaluated public data, not a blind benchmark.

Keep Qwen2.5-1.5B-Instruct revision989aa7980e4cf806f80c7fef2b1adb7bc71aa306,
greedy decoding, 4096 input tokens and 384 generated tokens, the pinned format
enforcer, and a single GPU caller. Save cases incrementally; resume only with
identical source, protocol, model, packages and device. Save and hash all500
predictions before opening references for scoring. Compare with the archived
cross-encoder method only (108 invalid answers,169/500 local judge correct,
154/470 positive correct,6/30 valid explicit abstentions). The old baseline
timings are not a paired latency baseline.

Score with the unchanged local Qwen3-4B judge and category rules; include judge
calibration, raw judgments, invalid answers and full denominators. Local model
scores remain estimates, not official GPT scores or human review. Do not select
questions, discard failures or alter the prompt after external results.

Promote the candidate to the service default only if:

- External runtime errors are zero and every original context is preserved.
- Invalid answers are fewer than108/500 and valid explicit abstentions exceed6/30.
- Local judge positive correctness is at least154/470 and overall correctness
  is at least169/500; gains cannot come solely from abstaining on negatives.
- Development negative abstention and positive gold inclusion do not decrease
  against the same-run legacy format.
- Existing authorization, source-change, MCP, real-model and container checks pass.

If a condition fails, retain the experiment and keep the current service default.
Do not claim general no-answer detection. Old v0.3/v0.4/v0.5 outputs stay immutable.
