# Reading the implementation

Start with `examples/demo.py` to see approval, two-time queries and withdrawal in
one process. The package is one service; there are no separate governance workers
or model orchestration layers to learn.

| Question | Read | Useful regression |
| --- | --- | --- |
| Who can propose or approve? | `identity.py`, then `policy.py` and `policies/governance.rego` | `test_identity.py`, `test_policy.py`, `policy/governance_test.rego` |
| What happens when one imported record fails? | `ingest.import_file`, `Ledger.propose_many`, `_stage_proposal` | `test_ingest_mcp.py` |
| How does an approval change history? | `Ledger.decide`, `_advance_head`, `_set_state`, `_activate` in `ledger.py` | `test_ledger.py`, `test_history_constraints.py` |
| How can a second source preserve a fact? | `Ledger.approve_support`, `evidence.approved_source_map`, `Ledger.withdraw_source` | `test_source_support.py` |
| Can a stale graph expose withdrawn evidence? | `Ledger.visible`, `Retriever.search`, then `GraphProjection` | `test_retrieval.py`, `test_graph_integration.py` |
| What really invokes the models? | `local_models.py`, `embedding.py`, `Settings.retriever` | `test_local_models.py` |
| What fits in a response? | `budget.py`, then `tokenizer.py` | `test_retrieval.py` |
| How does an agent use it? | `mcp_server.py`; operator commands are in `cli.py` | `test_ingest_mcp.py` |

The approval path is intentionally explicit: authenticate, lock the logical fact,
check revisions and policy, update lifecycle/history, and queue projection in one
SQL transaction. The small private methods name those steps; they do not commit
independently. `models.py` declares stored records, while `constraints.py` and
`db.py` install database protections.

File imports parse the records, then stage the entire group in one transaction.
Single proposals use the same staging function. A failure in any record rolls
back the group's new sources, candidates and audit events.

`SourceSupport` links one reviewed source candidate to a root assertion. It does
not duplicate `FactVersion`. `approved_source_map` applies each source's current
permissions and known-time rules in two queries, avoiding a query per fact.

The graph adapter returns IDs, not trusted text. `Retriever.search` joins those
IDs back to ledger evidence, checks authority before reranking and serialization,
then packs whole evidence items. Graph failures are visible in the response's
`backend` field. `budget.py` owns the one evidence serializer/token counter.

For evaluation, read `eval/README.md` before the runners. The synthetic suite
tests governance with structured fixtures. LongMemEval keeps input preparation,
retrieval and label scoring in three files; the retrieval case contains no answer
labels. Neither report is a claim about generated-answer accuracy.
