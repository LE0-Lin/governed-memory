# v0.3 verification record

The application source verified here is commit `fcb9775`, code SHA-256
`03344d41a45c682d0013457317336706597af76f71b55334543977424c7fbe29`.
Later verification records do not change that application code. The full
LongMemEval model runs retain their own earlier frozen commits and environments.

- Complete local regression: **171 passed / 5 skipped**, with real PostgreSQL,
  Neo4j, OPA, cached neural models/generation and both container images enabled.
  Skips are SQLite's two PostgreSQL concurrency cases, NUL-text rejection and
  two PostgreSQL/container cases.
- Native OPA/Rego: **10/10**. Rules and tests were mounted read-only into the
  pinned official image, without container network access.
- Container suite: **2 passed / 2 SQLite skips**. A non-root/read-only core
  container exercises MCP proposal, denied self-approval, operator approval,
  binary PostgreSQL backup/restore, graph reconstruction, a fresh MCP server
  and source withdrawal. The CPU model image also performs CLI import/approval,
  an actual cited answer with the agent credential, and withdrawal suppression.
- The installed CPU model image and host environment use **PyTorch 2.15.0+cpu**;
  the test verifies `torch.version.cuda is None`. PyTorch is a direct optional
  dependency so the CPU index mapping applies on Linux/Windows. Core installs
  still omit it.
- An isolated installed 0.3.0 core wheel contains no PyTorch. It passes the real
  UTF-8 CLI subprocess regression under a legacy pipe encoding, and the example
  passes with external network connections/name resolution blocked. The wheel
  was built from the verified source, not imported from the editable checkout.
- The unchanged frozen synthetic suite passes `--check`: **768 retrieval calls
  and 48 operation checks**, zero failures, with `uncommitted_changes=false`.
  Heldout governed results retain 66/66 answerable coverage, 30/30 empty-gold
  controls, zero unapproved/withdrawal query successes and no future metadata.

The UTF-8 regression first failed on a valid Chinese/emoji import: the record
committed before native GBK output raised `UnicodeEncodeError`. The CLI now
sets UTF-8 before emitting command JSON. The CPU-image build likewise exposed
the previously ineffective transitive-only index override; the fixed lock no
longer pulls CUDA dependencies on Linux. Both changes have actual runtime checks.

Ruff lint/format, source/wheel builds, local Markdown links and archived
LongMemEval checksums pass. Exact image IDs and the built wheel checksum are in
[verification.json](../eval/results/2026-11-12-v0.3/verification.json).
The [synthetic raw outputs](../eval/results/2026-11-12-v0.3) retain their original
summary/provenance. Earlier failed runs and the 14-question result remain intact.

The [full answer report](../eval/RESULTS-v0.3.md) reports a highest local judge
estimate of 169/500 (33.8%) and preserves all validation failures and the host
interruption timing outlier. Passing the service tests does not establish
production answer quality, general prompt-injection defense or distributed
failover. No human code review or official GPT grading is claimed.
