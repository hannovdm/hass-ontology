"""Unit tests for the bounded graph gateway foundation."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.ontology.graph_backends import (
    AddonGraphQLBackend,
    DirectMemgraphBackend,
    normalize_graph_node,
)
from custom_components.ontology.graph_gateway import GraphGateway, create_graph_backend


def test_normalize_graph_node_uses_stable_id_and_redacts_bounded_properties() -> None:
    node = normalize_graph_node(
        {
            "labels": ["Entity"],
            "properties": {
                "ha_id": "sensor.kitchen",
                "name": "Kitchen Sensor",
                "password": "must-not-leak",
                **{f"safe_{index}": "x" * 4096 for index in range(30)},
            },
        }
    )

    assert node["id"] == "Entity:sensor.kitchen"
    assert node["haId"] == "sensor.kitchen"
    assert len(node["properties"]) == 25
    assert all(item["name"] != "password" for item in node["properties"])
    assert all(len(item["displayValue"]) <= 2048 for item in node["properties"])


def test_backend_selection_is_fixed_per_config_entry() -> None:
    session = AsyncMock()
    client = AsyncMock()

    addon = create_graph_backend(
        {"graphql_url": "http://addon:4000/graphql", "graphql_token": "secret"},
        client,
        session=session,
    )
    direct = create_graph_backend({}, client, session=session)

    assert isinstance(addon, AddonGraphQLBackend)
    assert isinstance(direct, DirectMemgraphBackend)


@pytest.mark.asyncio
async def test_gateway_normalizes_timeout_without_leaking_backend_details() -> None:
    backend = AsyncMock()
    backend.initial_graph.side_effect = TimeoutError("http://addon:4000 token=secret")
    gateway = GraphGateway(backend)

    result = await gateway.initial_graph()

    assert result == {
        "available": False,
        "error": "gateway_unavailable",
        "nodes": [],
        "relationships": [],
        "truncated": False,
        "nextCursor": None,
        "revision": 0,
    }
    assert "addon" not in repr(gateway.diagnostics())
    assert "secret" not in repr(gateway.diagnostics())
