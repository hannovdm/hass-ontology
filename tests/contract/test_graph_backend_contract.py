"""Contract shared by the add-on GraphQL and direct Memgraph backends."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.ontology.const import GRAPH_OPERATION_NAMES
from custom_components.ontology.graph_backends import DirectMemgraphBackend


def test_graph_operation_names_are_fixed_and_do_not_accept_query_text() -> None:
    assert GRAPH_OPERATION_NAMES == (
        "initial_graph",
        "expand_node",
        "search_graph",
        "graph_element",
        "graph_health",
    )


@pytest.mark.asyncio
async def test_direct_backend_uses_parameterized_bounded_read_only_cypher() -> None:
    client = AsyncMock()
    client.run_query.return_value = []
    backend = DirectMemgraphBackend(client)

    await backend.expand_node("Entity:sensor.kitchen", node_limit=9999, edge_limit=9999)

    query, parameters = client.run_query.await_args.args
    assert "$id" in query
    assert "sensor.kitchen" not in query
    assert parameters["id"] == "Entity:sensor.kitchen"
    assert parameters["node_limit"] == 251
    assert parameters["edge_limit"] == 501
    assert not any(
        keyword in query.upper()
        for keyword in ("CREATE", "MERGE", "DELETE", " SET ", "REMOVE", "DROP", "CALL")
    )


@pytest.mark.asyncio
async def test_backend_close_is_idempotent() -> None:
    client = AsyncMock()
    backend = DirectMemgraphBackend(client)

    await backend.close()
    await backend.close()

    client.close.assert_not_awaited()
