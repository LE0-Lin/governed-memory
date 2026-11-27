# Verification evidence, 2026-11-15

`verification.json` binds the final source, paired comparison, installed model
image, test counts, artifact metadata and SHA-256 hashes. The report is
[`docs/verification-v0.8.md`](../../../docs/verification-v0.8.md).

- `source-ci.log` and `source-ci.json`: successful regular six-job CI at source
  `20057750b410eaa278b42fcd7045fa1ed2eb70c4`. Job groups overlap.
- `connected-ci.json`: source-bound GitHub job and artifact metadata for the
  regular workflow and the separate paired/installed-model workflow.
- `installed-model-mcp.xml` and `model-image-id.txt`: actual installed CPU model
  container; two passed PostgreSQL relevance modes and two SQLite skips.
- `local-rescore-v1.json` / `local-rescore-v2.json`: independent local rescores
  of both downloaded canonical runs. Full data remain in their sibling folders.
- `local-corrected-targeted-tests.txt`, `local-reference-tests.txt` and
  `local-v2-sqlite-tests.txt`: overlapping small checks, not a full local pass.
- `local-initial-test-authoring-failure.txt`: two duplicate-argument mistakes
  corrected before acceptance. These were test setup, not product failures.
- `local-failed-model-build.txt`, `local-partial-*-tests.*` and
  `local-daemon.log`: retained C:/WSL I/O and PostgreSQL infrastructure failures.
  These runs do not count as passing acceptance or a clean local shutdown.
- `local-build.txt` and `local-backward-rescore.txt`: successful local packaging
  and compatibility of the independent audit with the older v0.7 observations.

Logs are retained byte for byte. The dated state is not a live machine-health
monitor. No local recovery/migration, deletion of model/data/cache/old images,
new 500-question generation or production-capacity claim is implied.
