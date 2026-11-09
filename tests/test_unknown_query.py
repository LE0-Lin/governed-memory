from governed_memory.retrieval import Retriever

from .conftest import approve, propose


async def test_hash_retriever_can_abstain_without_any_lexical_evidence(context):
    ledger, _, tokens = context
    approve(context, propose(context))
    result = await Retriever(ledger).search(tokens["agent"], "demo", "unmentioned bananas")
    assert result["evidence"] == []
    assert result["reason"] == "no_relevant_evidence"


async def test_tokenizer_treats_special_token_spelling_as_untrusted_text(context):
    ledger, _, tokens = context
    approve(context, propose(context, "SQLite <|endoftext|>"))
    result = await Retriever(ledger).search(tokens["agent"], "demo", "database")
    assert result["evidence"][0]["value"] == "SQLite <|endoftext|>"
