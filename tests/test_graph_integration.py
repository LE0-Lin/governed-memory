import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from governed_memory.graph_adapter import GraphProjection, project_pending
from governed_memory.ledger import Conflict
from governed_memory.retrieval import Retriever

from .conftest import approve, propose
from .test_source_support import add_support


@pytest.mark.integration
async def test_real_graph_stable_ids_hybrid_history_and_stale_source(context):
    uri = os.environ.get("GM_TEST_NEO4J_URI")
    if not uri:
        pytest.skip("set GM_TEST_NEO4J_URI for a real Graphiti/Neo4j projection")
    ledger, _, tokens = context
    first = approve(context, propose(context))
    candidate = ledger.propose(
        tokens["agent"],
        "demo",
        subject="storage",
        predicate="database",
        value="PostgreSQL",
        valid_from="2030-01-04T00:00:00Z",
    )
    second = approve(context, candidate)
    graph = GraphProjection(uri, "neo4j", os.environ["GM_TEST_NEO4J_PASSWORD"])
    # Keep graph fixture groups independent when the same database is reused.
    group = "test-" + first["id"]
    original_upsert = graph.upsert

    async def isolated_upsert(item):
        from dataclasses import replace

        await original_upsert(replace(item, project=group))

    graph.upsert = isolated_upsert
    original_rank = graph.rank

    async def isolated_rank(query, project, allowed_ids, limit):
        return await original_rank(query, group, allowed_ids, limit)

    graph.rank = isolated_rank
    try:
        await graph.initialize()
        result = await project_pending(ledger, graph)
        assert result["failed"] == 0
        ids = [item.id for item in ledger.visible(tokens["agent"], "demo")]
        ranked = await graph.rank("database PostgreSQL", group, ids, 5)
        assert ranked == ids
        response = await Retriever(ledger, graph).search(tokens["agent"], "demo", "database")
        assert response["backend"] == "graphiti-hybrid-rrf"
        assert response["evidence"][0]["candidate_id"] == second["id"]
        await graph.graph.driver.execute_query(
            "MATCH ()-[e:RELATES_TO]->() WHERE e.uuid IN $ids "
            "SET e.embedding_profile='different-model'",
            ids=ids,
        )
        assert await graph.rank("database PostgreSQL", group, ids, 5) == []
        # Replaying a job uses MERGE on the same relationship UUID.
        current = ledger.visible(tokens["agent"], "demo")[0]
        await graph.upsert(current)
        records, _, _ = await graph.graph.driver.execute_query(
            "MATCH ()-[e:RELATES_TO]->() WHERE e.group_id=$group RETURN count(e) AS n",
            group=group,
        )
        assert records[0]["n"] == 3  # closed prior belief, retained past slice, new belief
        historical = ledger.visible(tokens["agent"], "demo", known_at="2030-01-03T00:00:00Z")
        assert (await graph.rank("SQLite database", group, [historical[0].id], 5)) == [
            historical[0].id
        ]
        ledger.withdraw_source(tokens["admin"], "demo", second["source_id"])
        result = await Retriever(ledger, graph).search(tokens["agent"], "demo", "database")
        assert result["evidence"] == []
    finally:
        await graph.graph.driver.execute_query(
            "MATCH (n:Entity {group_id:$group}) DETACH DELETE n",
            group=group,
        )
        await graph.close()


@pytest.mark.integration
def test_postgres_concurrent_approval_only_records_one_decision(context):
    ledger, clock, tokens = context
    if ledger.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL advisory lock check")
    c = propose(context)
    clock.advance()
    barrier = Barrier(2)

    def decide():
        barrier.wait(timeout=10)
        try:
            ledger.decide(
                tokens["admin"], "demo", c["id"], "approve", 0, reason="parallel", expected_head=0
            )
            return "approved"
        except Conflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: decide(), range(2)))
    assert sorted(results) == ["approved", "conflict"]
    assert len(ledger.visible(tokens["agent"], "demo")) == 1


@pytest.mark.integration
async def test_dependency_invalidation_hides_stale_graph_then_removes_derived_edges(context):
    from dataclasses import replace
    from uuid import uuid4

    from .test_dependencies import derive

    uri = os.environ.get("GM_TEST_NEO4J_URI")
    if not uri:
        pytest.skip("set GM_TEST_NEO4J_URI for real dependency projection checks")
    ledger, _, tokens = context
    root = approve(context, propose(context))
    child = approve(context, derive(context, root))
    graph = GraphProjection(uri, "neo4j", os.environ["GM_TEST_NEO4J_PASSWORD"])
    group = "dependency-" + uuid4().hex
    original_upsert, original_rank = graph.upsert, graph.rank

    async def upsert(item):
        await original_upsert(replace(item, project=group))

    async def rank(query, project, ids, limit):
        return await original_rank(query, group, ids, limit)

    graph.upsert, graph.rank = upsert, rank
    try:
        await graph.initialize()
        assert (await project_pending(ledger, graph))["failed"] == 0
        snapshot = next(
            e.id for e in ledger.visible(tokens["admin"], "demo") if e.candidate_id == child["id"]
        )
        ledger.withdraw_source(tokens["admin"], "demo", root["source_id"])
        # The graph still contains the old edge until outbox delivery, but the service hides it now.
        assert not (
            await Retriever(ledger, graph).search(tokens["reader"], "demo", "deployment decision")
        )["evidence"]
        assert (await project_pending(ledger, graph))["failed"] == 0
        records, _, _ = await graph.graph.driver.execute_query(
            "MATCH ()-[e:RELATES_TO]->() WHERE e.uuid=$id RETURN count(e) AS n", id=snapshot
        )
        assert records[0]["n"] == 0
    finally:
        await graph.graph.driver.execute_query(
            "MATCH (n:Entity {group_id:$group}) DETACH DELETE n", group=group
        )
        await graph.close()


@pytest.mark.integration
async def test_real_graph_retains_remaining_support_and_deletes_after_the_last_withdrawal(context):
    uri = os.environ.get("GM_TEST_NEO4J_URI")
    if not uri:
        pytest.skip("set GM_TEST_NEO4J_URI for real source-withdrawal propagation")
    from dataclasses import replace
    from uuid import uuid4

    ledger, _, tokens = context
    target = approve(context, propose(context))
    support = add_support(context, target)
    group = "support-test-" + uuid4().hex
    graph = GraphProjection(uri, "neo4j", os.environ["GM_TEST_NEO4J_PASSWORD"])
    upsert = graph.upsert

    async def isolated(item):
        await upsert(replace(item, project=group))

    graph.upsert = isolated
    try:
        await graph.initialize()
        assert (await project_pending(ledger, graph))["failed"] == 0
        ledger.withdraw_source(tokens["admin"], "demo", target["source_id"])
        assert (await project_pending(ledger, graph))["failed"] == 0
        records, _, _ = await graph.graph.driver.execute_query(
            "MATCH ()-[e:RELATES_TO]->() WHERE e.group_id=$group "
            "RETURN e.support_source_ids AS sources",
            group=group,
        )
        assert [record["sources"] for record in records] == [[support["source_id"]]]
        ledger.withdraw_source(tokens["admin"], "demo", support["source_id"])
        assert (await project_pending(ledger, graph))["failed"] == 0
        records, _, _ = await graph.graph.driver.execute_query(
            "MATCH ()-[e:RELATES_TO]->() WHERE e.group_id=$group RETURN count(e) AS n", group=group
        )
        assert records[0]["n"] == 0
    finally:
        await graph.graph.driver.execute_query(
            "MATCH (n:Entity {group_id:$group}) DETACH DELETE n", group=group
        )
        await graph.close()
