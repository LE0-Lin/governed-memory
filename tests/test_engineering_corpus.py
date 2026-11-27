import json
from pathlib import Path

from eval.controlled_run import database
from eval.relevance_v2_study import ENGINEERING, populate_engineering
from governed_memory.retrieval import Retriever

ROOT = Path(__file__).resolve().parents[1]


async def test_engineering_corpus_exercises_bitemporal_withdrawal_corroboration_and_dependencies():
    data = json.loads(ENGINEERING.read_text(encoding="utf-8"))
    assert len(data["records"]) == 16
    assert len(data["queries"]) == 20
    with database() as engine:
        ledger, queries, _ = populate_engineering(engine, data)
        by_id = {q["id"]: q for q in queries}

        # Before vs. after incident postmortem on the same effective date (Feb 20)
        assert by_id["eng-q03"]["gold_ids"] != by_id["eng-q04"]["gold_ids"]
        assert set(by_id["eng-q03"]["gold_ids"]) <= set(by_id["eng-q03"]["eligible_ids"])
        assert set(by_id["eng-q04"]["gold_ids"]) <= set(by_id["eng-q04"]["eligible_ids"])

        # Corroborated token-budget decision survives withdrawal of temporary session notes
        q_corr = by_id["eng-q13"]
        assert set(q_corr["gold_ids"]) <= set(q_corr["eligible_ids"])

        # Withdrawn mTLS draft and its derived Envoy SDS config are both ineligible
        retriever = Retriever(ledger)
        for neg_id in ("eng-q15", "eng-q16", "eng-q20"):
            q = by_id[neg_id]
            res = await retriever.search(
                q["token"],
                q["project"],
                q["query"],
                valid_at=q["valid_at"],
                known_at=q["known_at"],
            )
            assert res["evidence"] == []
