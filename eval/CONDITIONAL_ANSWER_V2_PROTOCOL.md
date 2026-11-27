# Conditional answer experiment v2

Frozen before v2 inference, 2026-11-14 Asia/Shanghai. V1 failed its development
gate: positive literal gold inclusion46/48 ->42/48, despite valid negative
abstention17/32 ->32/32 and errors5 ->0. The failure, all outputs and original
protocol remain in the repository. No v1 external inference was started and no
external references or new external scores motivated this revision.

V2 keeps the conditional output schema, pinned model, complete contexts and all
the [v1 protocol](CONDITIONAL_ANSWER_PROTOCOL.md) parameters, scoring rules and
promotion thresholds. Its prompt stays closer to the legacy instructions and
explicitly permits matching equivalent wording to a stated fact. It removes the
v1 instruction to establish sufficiency for every part before attempting to
answer. This is development-set prompt iteration, not new blind validation.

Run the same complete80-query paired development diagnostic with both formats.
Record all outputs and do not promote if positive gold inclusion or valid
negative abstention decreases. If it passes, evaluate the one frozen v2 candidate
on all500 archived contexts and use the unchanged judge only after predictions
are finalized. Do not revise v2 after external results. Preserve all errors and
use the same full denominators. Keep the service default unchanged until the
preregistered criteria and runtime regressions pass.

The 0.5B smoke model is not the 1.5B experiment model. Its observed failure to
emit the insufficient-evidence branch for an owner question is a separate model
quality limitation. Any default change must name the model profile it actually
validates rather than assuming transfer across sizes.
