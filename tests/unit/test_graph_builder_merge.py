"""Test: `merge_node`/`merge_relationship` always emit idempotent MERGE
Cypher keyed on `ha_id`, stamp `source`/`updated_at`, and reject unsafe
label/relationship-type identifiers (data-model.md "Common conventions",
Constitution Principle III/VI)."""

from __future__ import annotations

import pytest

from custom_components.ontology import graph_builder
from custom_components.ontology.const import SOURCE_GENERATED, SOURCE_HOME_ASSISTANT


async def test_merge_node_uses_merge_keyed_on_ha_id(mock_memgraph_client) -> None:
    await graph_builder.merge_node(mock_memgraph_client, "Area", "area-1", {"name": "Kitchen"})

    query, params = mock_memgraph_client.run_query_with_retry.call_args.args
    assert "MERGE (n:Area {ha_id: $ha_id})" in query
    assert params["ha_id"] == "area-1"
    assert params["properties"]["name"] == "Kitchen"
    assert params["properties"]["source"] == SOURCE_HOME_ASSISTANT
    assert "updated_at" in params["properties"]


async def test_merge_node_honors_explicit_source(mock_memgraph_client) -> None:
    await graph_builder.merge_node(
        mock_memgraph_client, "Automation", "automation-1", {}, source=SOURCE_GENERATED
    )

    _query, params = mock_memgraph_client.run_query_with_retry.call_args.args
    assert params["properties"]["source"] == SOURCE_GENERATED


async def test_merge_relationship_matches_both_nodes_and_merges_edge(mock_memgraph_client) -> None:
    await graph_builder.merge_relationship(
        mock_memgraph_client, "Area", "area-1", "HAS_DEVICE", "Device", "device-1"
    )

    query, params = mock_memgraph_client.run_query_with_retry.call_args.args
    assert "MATCH (a:Area {ha_id: $from_ha_id}), (b:Device {ha_id: $to_ha_id})" in query
    assert "MERGE (a)-[r:HAS_DEVICE]->(b)" in query
    assert params["from_ha_id"] == "area-1"
    assert params["to_ha_id"] == "device-1"


@pytest.mark.parametrize("unsafe_label", ["Area; DROP", "Area DELETE", "Area-1", "Area'"])
async def test_merge_node_rejects_unsafe_label(mock_memgraph_client, unsafe_label) -> None:
    with pytest.raises(ValueError):
        await graph_builder.merge_node(mock_memgraph_client, unsafe_label, "id-1", {})


async def test_merge_relationship_rejects_unsafe_rel_type(mock_memgraph_client) -> None:
    with pytest.raises(ValueError):
        await graph_builder.merge_relationship(
            mock_memgraph_client, "Area", "area-1", "HAS_DEVICE; DROP", "Device", "device-1"
        )
