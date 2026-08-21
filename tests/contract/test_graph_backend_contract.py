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
async def test_direct_initial_graph_requests_area_only_overview() -> None:
    client = AsyncMock()
    client.run_query.return_value = [
        {
            "nodes": [
                {"labels": ["Area"], "properties": {"ha_id": "kitchen", "name": "Kitchen"}},
                {"labels": ["Device"], "properties": {"ha_id": "lamp", "name": "Lamp"}},
            ],
            "relationships": [
                {
                    "type": "HAS_DEVICE",
                    "source": "Area:kitchen",
                    "target": "Device:lamp",
                    "id": "0",
                    "source_class": "HA_REGISTRY",
                    "properties": {},
                }
            ],
        }
    ]
    backend = DirectMemgraphBackend(client)

    result = await backend.initial_graph()

    query, parameters = client.run_query.await_args.args
    assert "MATCH (n:Area)" in query
    assert "n:Device" not in query
    assert parameters == {"node_limit": 101, "edge_limit": 101}
    assert result["relationships"] == [
        {
            "id": "HAS_DEVICE:Area:kitchen:Device:lamp:0",
            "type": "HAS_DEVICE",
            "source": "Area:kitchen",
            "target": "Device:lamp",
            "directed": True,
            "sourceClass": "HA_REGISTRY",
            "properties": [],
        }
    ]


@pytest.mark.asyncio
async def test_direct_initial_graph_drops_elements_cytoscape_cannot_render() -> None:
    client = AsyncMock()
    area = {"labels": ["Area"], "properties": {"ha_id": "kitchen"}}
    client.run_query.return_value = [
        {
            "nodes": [area, area],
            "relationships": [
                {
                    "type": "HAS_DEVICE",
                    "source": "Area:kitchen",
                    "target": "Device:missing",
                    "id": "orphan",
                    "properties": {},
                },
                {
                    "type": "RELATED_TO",
                    "source": "Area:kitchen",
                    "target": "Area:kitchen",
                    "id": "loop",
                    "properties": {},
                },
                {
                    "type": "RELATED_TO",
                    "source": "Area:kitchen",
                    "target": "Area:kitchen",
                    "id": "loop",
                    "properties": {},
                },
            ],
        }
    ]

    result = await DirectMemgraphBackend(client).initial_graph()

    assert [node["id"] for node in result["nodes"]] == ["Area:kitchen"]
    assert [relationship["id"] for relationship in result["relationships"]] == [
        "RELATED_TO:Area:kitchen:Area:kitchen:loop"
    ]


@pytest.mark.asyncio
async def test_backend_close_is_idempotent() -> None:
    client = AsyncMock()
    backend = DirectMemgraphBackend(client)

    await backend.close()
    await backend.close()

    client.close.assert_not_awaited()
