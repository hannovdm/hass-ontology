"""Integration test: query row-limit enforcement and write-query rejection
against a real Memgraph instance (User Story 2, T016)."""

from __future__ import annotations

import pytest

from custom_components.ontology import query_service
from custom_components.ontology.memgraph_client import MemgraphClient


async def test_row_limit_truncates_result_and_reports_truncated(
    memgraph_client: MemgraphClient,
) -> None:
    for i in range(10):
        await memgraph_client.run_query(
            "CREATE (:RowLimitProbe {ha_id: $ha_id})", {"ha_id": f"probe-{i}"}
        )

    result = await query_service.execute_query(
        memgraph_client, "MATCH (n:RowLimitProbe) RETURN n.ha_id AS ha_id", limit=5
    )

    assert result["row_count"] == 5
    assert len(result["rows"]) == 5
    assert result["truncated"] is True


async def test_result_under_limit_is_not_truncated(memgraph_client: MemgraphClient) -> None:
    for i in range(3):
        await memgraph_client.run_query(
            "CREATE (:RowLimitProbe {ha_id: $ha_id})", {"ha_id": f"small-{i}"}
        )

    result = await query_service.execute_query(
        memgraph_client,
        "MATCH (n:RowLimitProbe) WHERE n.ha_id STARTS WITH 'small-' RETURN n.ha_id AS ha_id",
        limit=100,
    )

    assert result["row_count"] == 3
    assert result["truncated"] is False


async def test_requested_limit_above_max_is_clamped_to_max_query_limit(
    memgraph_client: MemgraphClient,
) -> None:
    result = await query_service.execute_query(
        memgraph_client,
        "MATCH (n:RowLimitProbe) RETURN n.ha_id AS ha_id",
        limit=query_service.MAX_QUERY_LIMIT + 1000,
    )

    assert result["row_count"] <= query_service.MAX_QUERY_LIMIT


@pytest.mark.parametrize(
    "cypher",
    [
        "CREATE (:Malicious {ha_id: 'should-not-exist'})",
        "MATCH (n) DETACH DELETE n",
        "MATCH (n:RowLimitProbe) SET n.hacked = true",
        "MERGE (n:Malicious {ha_id: 'should-not-exist'})",
    ],
)
async def test_write_queries_are_rejected_before_execution(
    memgraph_client: MemgraphClient, cypher: str
) -> None:
    with pytest.raises(query_service.QueryRejected):
        await query_service.execute_query(memgraph_client, cypher)

    rows = await memgraph_client.run_query(
        "MATCH (n:Malicious {ha_id: 'should-not-exist'}) RETURN count(n) AS c"
    )
    assert rows[0]["c"] == 0
