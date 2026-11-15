from eval.reference_v07 import reference_classes

from .conftest import approve, propose


def test_exact_v07_reference_reads_the_same_immutable_database(context):
    ledger, _, tokens = context
    approve(context, propose(context))
    old_ledger, old_retriever, metadata = reference_classes()
    reference = old_ledger(ledger.engine, ledger.clock)
    assert reference.visible(tokens["agent"], "demo") == ledger.visible(tokens["agent"], "demo")
    assert old_retriever is not None and metadata["shared_runtime_unchanged"]
    assert metadata["commit"] == "df8349b7abfcdd8485868225e6bb74589f397edb"
