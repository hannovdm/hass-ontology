"""Real-Memgraph security and parity checks for graph exploration operations."""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from custom_components.ontology.graph_backends import (
    AddonGraphQLBackend,
    DirectMemgraphBackend,
)


async def _seed_graph(client) -> None:
    await client.run_query(
        """
        CREATE (area:Area {ha_id: 'kitchen', name: 'Kitchen', token: 'hidden'})
        CREATE (lamp:Device {ha_id: 'lamp', name: 'Shared name', password: 'hidden'})
        CREATE (sensor:Entity {ha_id: 'sensor.kitchen', name: 'Shared name', state: 'on'})
        CREATE (area)-[:HAS_DEVICE {ha_id: 'primary'}]->(lamp)
        CREATE (lamp)-[:HAS_ENTITY {ha_id: 'first'}]->(sensor)
        CREATE (lamp)-[:HAS_ENTITY {ha_id: 'second'}]->(sensor)
        CREATE (sensor)-[:REFERENCES {ha_id: 'self'}]->(sensor)
        """
    )


async def _graph_counts(client) -> tuple[int, int]:
    rows = await client.run_query(
        "MATCH (n) OPTIONAL MATCH ()-[r]->() RETURN count(DISTINCT n) AS nodes, count(DISTINCT r) AS relationships"
    )
    return rows[0]["nodes"], rows[0]["relationships"]


@pytest.mark.asyncio
async def test_search_detail_and_expand_are_bounded_redacted_and_read_only(memgraph_client) -> None:
    await _seed_graph(memgraph_client)
    before = await _graph_counts(memgraph_client)
    direct = DirectMemgraphBackend(memgraph_client)

    search = await direct.search_graph("Shared name", 100)
    detail = await direct.graph_element("Device:lamp")
    expansion = await direct.expand_node("Entity:sensor.kitchen", 250, 500)

    assert [match["id"] for match in search["matches"]] == ["Device:lamp", "Entity:sensor.kitchen"]
    assert detail and detail["node"]["id"] == "Device:lamp"
    assert {node["id"] for node in expansion["nodes"]} == {"Device:lamp", "Entity:sensor.kitchen"}
    assert len(expansion["relationships"]) == 3
    assert len({relationship["id"] for relationship in expansion["relationships"]}) == 3
    assert any(relationship["source"] == relationship["target"] for relationship in expansion["relationships"])
    relationship_id = next(
        relationship["id"]
        for relationship in expansion["relationships"]
        if relationship["source"] != relationship["target"]
    )
    relationship_detail = await direct.graph_element(relationship_id)
    assert relationship_detail and relationship_detail["relationship"]["id"] == relationship_id
    assert relationship_detail["node"] is None
    assert "hidden" not in repr((search, detail, expansion))
    assert await _graph_counts(memgraph_client) == before

    addon = AddonGraphQLBackend("http://graph.invalid", "secret", session=AsyncMock())
    addon._operation = AsyncMock(
        side_effect=[
            deepcopy(search),
            deepcopy(detail),
            deepcopy(relationship_detail),
            {
                "nodes": deepcopy(expansion["nodes"]),
                "relationships": deepcopy(expansion["relationships"]),
                "pageInfo": {"truncated": expansion["truncated"], "nextCursor": expansion["nextCursor"]},
                "revision": expansion["revision"],
            },
        ]
    )

    assert await addon.search_graph("Shared name", 100) == search
    assert await addon.graph_element("Device:lamp") == detail
    assert await addon.graph_element(relationship_id) == relationship_detail
    assert await addon.expand_node("Entity:sensor.kitchen", 250, 500) == expansion
    assert await _graph_counts(memgraph_client) == before