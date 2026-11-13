# v0.5 verification record

Verified on 2026-11-14, Asia/Shanghai. This release adds bounded document-vector
reuse and an explicitly enabled relevance filter. The filter remains disabled
by default because its full500 transfer cost is unacceptable for general use.
The [evaluation report](../eval/RESULTS-v0.5.md) retains both gains and failures;
this record covers implementation and deployment checks.

## Regression and actual models

Local acceptance ran in separate, non-overlapping groups: **258 passed and
13 skipped** across 271 collected configurations. The groups comprise:

| Checks | Passed | Skipped |
| --- | ---: | ---: |
| Core and real PostgreSQL/Neo4j/OPA/OpenFGA, excluding models/containers | 242 | 9 |
| Explicit opt-in regression added after the core run, SQLite + PostgreSQL | 2 | 0 |
| Actual embedding, reranker, generator and NLI models | 10 | 0 |
| Installed core container, backup/recovery and MCP withdrawal | 1 | 1 |
| Installed CPU-model container, CLI and persistent MCP session | 3 | 3 |

Eight skips are SQLite configurations of PostgreSQL-only checks; five are the
native extension not installed in the local Windows development environment.
The [six-job CI run](https://github.com/LE0-Lin/governed-memory/actions/runs/43471343399)
passed Windows/Ubuntu core, Windows/Ubuntu Rust/native, real storage/evaluation
and actual model checks. Native jobs compile and test the extension with pinned
Rust 1.90.0. Runtime source at that commit is identical to the final selected
source hash below; subsequent changes add documentation and test coverage.

Ruff checking/formatting and the native OPA policy suite (10/10) passed. The
unchanged frozen synthetic governance suite ran 768 retrievals and 48 operation
checks with no execution failures. Its baseline deficiencies remain visible;
this is separate from the new neural retrieval experiment.

Regression exercises exact project/model/text cache keys, bounded LRU eviction,
mutable-return isolation, invalid vectors/scores, current grants and withdrawal
on cache hits, withdrawal during scoring, cutoff boundaries and deterministic
ties, empty-answer generation avoidance and the default opt-in behavior.

## Installed containers and packaging

Both variants were rebuilt from the repository Dockerfile and install package
0.5.0. They run as UID 10001 with a read-only root, no capabilities and a tmpfs
for temporary files. The core image contains no PyTorch; its bundled native
extension and relevance artifact load with networking disabled. The model image
uses CPU PyTorch (`torch.version.cuda is None`) and read-only cached weights.

- Core image: `sha256:bd2c8c836a484332fe4807311e0d6df3e1bc5ef18519de52896028473e5a64f4`.
- Model image: `sha256:5dcc098a1a05eaa6f9d6cb2eb8f3106499864d4ef0efcda86425193ffcb19a95`.

The new deployed MCP check uses actual MiniLM models against an isolated
PostgreSQL schema. With museum evidence alone, a Berlin population question
returns `no_relevant_evidence`; the intentionally missing generator cache is
never needed. Two supported museum searches run through that same process with
the document cache enabled. Withdrawing the source then suppresses the evidence
in that still-running session. Separate model CLI checks exercise a real Qwen
answer, withdrawal, semantic ingestion, review, approval and dependency workflow.

The core deployment regression verifies binary PostgreSQL backup/restore, graph
reconstruction and retrieval through a fresh MCP process. The offline example
passes with external networking denied. Locked wheel/sdist builds pass, and
the wheel includes the frozen relevance artifact and its 1.4 cutoff. Wheel
SHA-256: `01dc1971a2a8338d2a64f733864a9743fbde8f2c6cfbef0937f8bf076035c22d`.

## Evidence and corrections

The [machine-readable receipt](../eval/results/verification-v05-2026-11-14.json)
records checks and image IDs. The service experiment uses selected source SHA
`9a6b2db838035416816e88186d9b2c275b10986c8714a230078b9c9c00299db3`;
the final runtime matches it. Raw 1,476-observation results, 1,000 external replay
decisions and their independent rescore receipt are linked in the evaluation
report. No original v0.3/v0.4 result was overwritten.

An initial deployment-test helper used an absolute `conftest` import and failed
collection. The corrected package-relative import passed complete collection
and CI; the earlier failed CI run remains visible. The deployed synthetic fixture
also specifies both fictional 2030 time axes explicitly. Replay reconstruction
failures and their diagnosis are retained with the raw results. The relevance
cutoff was not changed to improve validation scores.

These checks establish the exercised local workflows, not distributed recovery,
general answerability, production capacity, historical CV dates or human review.
