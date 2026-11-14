# v0.6 verification record

Verified on 2026-11-14, Asia/Shanghai. The `standard` 1.5B profile uses
conditional answers, with `MEMORY_ANSWER_FORMAT=json_schema` available for
compatibility. Other profiles retain their legacy default. Public answer fields
and authority checks remain unchanged. The [complete experiment](../eval/RESULTS-v0.6.md)
documents semantic regressions and uncertainty as well as format reliability.

## Local acceptance

Non-overlapping final test groups cover all **296 configurations**:

| Group | Passed | Skipped | Expected quality failure |
| --- | ---: | ---: | ---: |
| Core and actual PostgreSQL/Neo4j/OPA/OpenFGA | 267 | 9 | 0 |
| Actual embedding, generation and NLI models | 9 | 0 | 1 |
| Installed core image: backup/recovery and MCP | 1 | 1 | 0 |
| Installed model image: existing 0.5B/semantic workflows | 3 | 3 | 0 |
| Installed model image: actual 1.5B MCP workflow | 1 | 1 | 0 |
| Total | **281** | **14** | **1** |

Nine skips are SQLite configurations of PostgreSQL-only checks; five are the
native extension absent from the local Windows development environment. Native
Windows/Ubuntu CI jobs compile and test the extension with pinned Rust 1.90.0.

The expected failure is an explicit 0.5B missing-owner quality counterexample.
That probe first verifies error-free generation and positive/structural checks;
runtime or format errors fail normally. Its unsupported answer is not counted
as a passing no-answer check, and the small profile's default remains unchanged.

Ruff checking/formatting, complete collection, native Rego (10/10), the unchanged
frozen governance suite (768 retrievals and 48 operation checks), the external-
network-denied example and locked wheel/sdist builds pass. Additional targeted
promotion/configuration runs overlap the groups above and are not added to the
totals. [Runtime-source CI](https://github.com/LE0-Lin/governed-memory/actions/runs/43533826175)
passes all six jobs: two core platforms, two native platforms, real storage/
evaluation and actual models.

## Installed runtime and model checks

Both images were rebuilt from the repository Dockerfile. They run installed
package 0.6.0 as UID 10001 with a read-only root, no Linux capabilities and a
temporary filesystem. Core imports the native extension with networking disabled
and contains no PyTorch. The model variant uses CPU wheels and read-only weights.

- Core: `sha256:454341ed3617c3243f51153ee305d27f2de007f83dd34b9598247240b00ed3c8`.
- Models: `sha256:2115254538f32aa2756631dc64274b0200a526544555ea48ffbd5834f7c4714d`.
- Wheel: `758c258eb243f072cb1d5eb634f7c38d77d7ec0fb8cdfe1304a74485212028ae`.

The new 1.5B regression starts an actual stdio MCP process, answers the fictional
SQLite question, checks resolved citations and `generation.format=conditional`,
then withdraws the source while the process remains active. The next answer
returns empty evidence and `no_eligible_evidence` without another generation.
Both fictional time axes are explicit. This large-model check runs sequentially
against PostgreSQL after the other test services stop to leave memory available.
It verifies this workflow, not CPU equivalence with the full GPU benchmark.

Existing container regressions still exercise the actual 0.5B answer, semantic
proposal/approval/review, bounded-cache retrieval, source withdrawal, binary
PostgreSQL backup/restore and graph reconstruction. Temporary application
containers are observed exiting before final shutdown.

## Evidence identity and limits

The released runtime's selected source SHA-256 is
`c5ea8570a7ecbb436ecc737586cab7b7429f7662a72906a503f32410ebecee5d`.
The full GPU experiment used frozen commit `bf35814` before profile promotion;
its prompt, schema, parser and generation helpers are AST-identical to the
released helpers. Profile selection, operator configuration and version metadata
are the integration changes. The [compatibility receipt](../eval/results/conditional-full-v3-2026-11-14/runtime-compatibility.json)
and [machine-readable verification](../eval/results/verification-v06-2026-11-14.json)
bind the evidence.

All 500 original contexts are preserved, predictions are sealed before labels
are scored, and independent counts satisfy the registered data/model gates.
Format errors fall from 108 to zero; valid explicit negative abstentions rise
from 6/30 to 13/30. The local judge estimate changes from 169/500 to 181/500,
with 43 previously correct positive answers lost and 49 newly correct positives.
These results do not establish a reliable semantic quality gain. The first two
development failures, small-model counterexamples and all old results remain
available. No official score, human review, historical CV date or production
capacity is asserted.
