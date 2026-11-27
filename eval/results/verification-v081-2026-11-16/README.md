# Verification receipts, 2026-11-16

`verification.json` binds the final unchanged-runtime baseline and the rejected
pooling study to source-bound CI metadata, raw file hashes and installed image
IDs. See [`docs/verification-v0.8.1.md`](../../../docs/verification-v0.8.1.md).

`final-*` files cover final source eb6e50f, six-job CI43826351086, full-path/model
CI43826351173, local independent rescore, targeted 9 pass/3 skip, lock check and the
actual installed model MCP JUnit. CI groups overlap and must not be added.

`rejected-*` cover source5b32311, CI43823918887/43823918983 and its actual model
image. Correctness passed, but largest latency gates failed; none of its runtime
changes ship. Full raw runs are in the sibling system-transport-v1 and
system-baseline-v081 folders. Initial/corrected local candidate test logs and
the Windows protocol-stub diagnostic remain explicit diagnostic evidence.

No files imply local WSL recovery, independent real-world data, production/WAN
capacity or new 500-question QA scores.

The initial offline lock resolution failed because registry metadata was no
longer cached. Only the project's version entry was updated; the final offline
lock check passes and dependency versions are unchanged. Both receipts remain.
