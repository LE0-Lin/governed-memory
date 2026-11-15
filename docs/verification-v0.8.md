# v0.8 verification record

Verified on 2026-11-15, Asia/Shanghai. The runtime adds one optional exact
snapshot filter to `Ledger.visible` and uses it only for the last fresh read
when reranking has narrowed the pool. Authentication precedes the filter;
source/dependency/time checks remain unchanged. An empty selected subset gets
a full fresh fallback for the original empty-result reason. No schema change,
new cache, authority worker or ranking/generation change is introduced.

## Source and gates

Runtime/evaluation source: `20057750b410eaa278b42fcd7045fa1ed2eb70c4`.
Selected source SHA-256:
`074194f66412f70b1be40aa7131eaa7ce9b9989b1f6ebf0b9105ae3c2be37bb3`.
Final pre-measurement [protocol](../eval/AUTHORITY_REFRESH_V2_PROTOCOL.md) SHA-256:
`73e98137c3007bed654c8f6a312eb69220f3d65b0f999e5c73c10bcc4c382717`.

The exact reference is Git commit `df8349b7abfcdd8485868225e6bb74589f397edb`.
The loader checks that every other runtime/native file is identical before
compiling its Ledger/Retriever classes. PostgreSQL, clock, model revisions,
budgets and separate identical cache capacities are held constant. The source
is clean and unchanged throughout the canonical experiment.

[Regular source CI](https://github.com/LE0-Lin/governed-memory/actions/runs/43717801551)
passes all six jobs. The separate
[authority/deployed-model workflow](https://github.com/LE0-Lin/governed-memory/actions/runs/43717801550)
passes both jobs. Its measurement and model-image checks use separate isolated
Ubuntu runners, so image builds and test suites do not compete with timings.

## Tests and installed runtime

The source collects 371 test configurations. The following CI groups overlap;
their counts must not be added into a unique-test total.

| Group | Passed | Skipped | Deselected | Expected quality failure |
| --- | ---: | ---: | ---: | ---: |
| Core, each of Windows and Ubuntu | 189 | 147 | 35 | 0 |
| Actual PostgreSQL/Neo4j/OPA/OpenFGA, installed core container | 325 | 46 | 0 | 0 |
| Actual CPU models/generation/NLI, separate runner | 32 | 14 | 0 | 1 |
| Native extension, each of Windows and Ubuntu | 8 | 4 | 3 | 0 |
| Installed model MCP, separate runner | 2 | 2 | 0 | 0 |

Optional environment/SQLite-specific skips remain explicit. The pinned small
generator's missing-owner abstention is still an expected quality failure,
not a successful no-answer check. The standard 1.5B answer format and earlier
500-question scores are unchanged; this round generates no new QA predictions.

Regression coverage includes exact historical snapshot payloads, empty-filter
authentication, foreign projects/private audiences, grant removal, updated
support provenance, selected/all evidence disappearing during inference, budget
reasons and survivors beyond 50 initially high-ranked withdrawn facts. Both
SQLite and actual PostgreSQL configurations run in the storage CI.

The deployed model image is built from the actual repository Dockerfile:
`sha256:aead486e2d8631bc13579ffa80233b608ef95f363818b21d68220ef38900ded1`.
The persistent MCP test seeds 52 eligible facts, repeats a query in one process,
then withdraws its selected source. Both relevance modes observe the withdrawal;
the enabled mode retains the correct `no_relevant_evidence` reason while other
facts remain. It uses the installed CPU-model package, UID 10001, a read-only
root and read-only pinned model cache. The regular storage job verifies the
installed core backup/recovery path and real governance services.

Ruff lint/format, Cargo format/Clippy/tests, network-denied core demo, wheel/sdist
builds, Rego 10/10 and the unchanged frozen governance evaluation pass in CI.
The retained logs and source-bound job/artifact metadata are checksummed in the
[machine-readable receipt](../eval/results/verification-v08-2026-11-15/verification.json).
The local locked wheel/sdist build also passes; wheel SHA-256 is
`473ffbcfb06b545ac4a62068f112fb52886744102e16034fc7b7179a29b71568`.

## Paired evidence and limitations

The [v0.8 results](../eval/RESULTS-v0.8.md) retain both attempts. V1 combined
source-column removal with the final-read filter; its largest overall P95
regressed 31.3%, so it was rejected. V2 restores the original columns and passes
the frozen largest-case overall AND first-pass gates. Different runners prevent
an inference about which change caused the v1 regression.

V2 has 1,992 observations, 996 pairs with identical ordered payloads/tokens/
reasons, zero retrieval errors and zero stale evidence. Largest-case overall
P95 is 521.9 -> 408.3 ms (21.8% lower), first-pass 602.9 -> 558.3 ms (7.4%), and
repeat 400.6 -> 378.9 ms (5.4%). Smallest-case and heldout first-pass regressions
of 4.7%/5.0% are retained. Independently rescoring the downloaded artifacts
reproduces all eight groups and verifies the complete observation grid and
explicit fixture labels. Quality is maintained; unrelated negative evidence
and the heldout 97.92% positive recall remain.

The data are previously examined synthetic histories, one caller, warmed CPU
models, PostgreSQL, and Rust ranking. Graph/remote-policy HTTP, transport,
ingestion, model loading and generation are outside timing. This is not an
independent real-history, production-capacity or complete-answer benchmark.
CV engineering features are exercised; those broader claims and 2025 historical
dates still need their own evidence. No old result files or CV were rewritten.

## Local infrastructure failure retained

C: ran critically low (about 1 GB free) during the local model-image build.
Docker failed to create a writable layer with an I/O error. Ubuntu subsequently
failed to start new processes, and local PostgreSQL became unavailable. The
partial core suite recorded 226 passes, 22 skips and 99 setup errors; the model
group recorded 7 passes, one known expected quality failure and 3 PostgreSQL
setup errors. Neither is a passing local acceptance run.

An earlier test-authoring error supplied `valid_from` twice; both failures and
the corrected targeted/reference runs are retained. Before the storage fault,
the corrected targeted group passed 16 and the later reference group 26
(overlapping). The final v2 SQLite-only targeted group passed 8, deselecting
8 PostgreSQL configurations; remote CI supplies the final PostgreSQL coverage.

Final canonical measurement and actual model-container validation ran remotely.
No model, cache, database volume or old image was deleted to recover space.
The dedicated local daemon's exit and project-service shutdown could not be
verified after the I/O fault; local WSL recovery is not claimed. A proposed
backup and official Ubuntu disk migration to E: affects the whole distribution
and awaits explicit user approval. No migration or unrelated WSL/app termination
has been performed. The retained failure logs distinguish this infrastructure
problem from the successful source-bound CI verification.
