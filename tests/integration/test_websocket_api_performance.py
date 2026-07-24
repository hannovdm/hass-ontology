"""Integration test: `ontology/area_context`, `ontology/entity_context`, and
`ontology/search` websocket_api commands respond within 2 seconds against a
graph of ~5,000 nodes (User Story 3, T062, SC-005).

Handlers are invoked directly against a real Memgraph instance (bypassing
the websocket transport itself, consistent with the contract-test pattern
in tests/contract/test_websocket_api_contract.py), with
`_first_loaded_client` patched to return the Docker-backed `memgraph_client`
fixture so no full config-entry setup is required."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from custom_components.ontology import websocket_api as ontology_ws
from custom_components.ontology.memgraph_client import MemgraphClient

_NODE_COUNT = 5000
_RESPONSE_BUDGET_SECONDS = 2.0


async def _seed_graph(client: MemgraphClient) -> None:
    """Bulk-create ~5,000 nodes: Areas, Devices (per area), Entities (per device).

    Links devices/entities to their parent by indexing into an in-memory
    `collect()`-ed list of already-created nodes (rather than re-`MATCH`ing
    by property per row), since the production schema has no index on
    `ha_id` and a per-row property scan against thousands of candidates
    would be prohibitively slow to seed within this test's own setup time."""
    await client.run_query(
        "UNWIND range(0, $count - 1) AS i "
        "CREATE (a:Area {ha_id: 'area-' + toString(i), name: 'Area ' + toString(i), "
        "source: 'home_assistant'})",
        {"count": 50},
    )
    await client.run_query(
        "MATCH (a:Area) WITH collect(a) AS areas "
        "UNWIND range(0, $count - 1) AS i "
        "CREATE (d:Device {ha_id: 'device-' + toString(i), name: 'Device ' + toString(i), "
        "source: 'home_assistant'}) "
        "WITH d, areas[i % size(areas)] AS a "
        "MERGE (a)-[:HAS_DEVICE]->(d)",
        {"count": 950},
    )
    await client.run_query(
        "MATCH (d:Device) WITH collect(d) AS devices "
        "UNWIND range(0, $count - 1) AS i "
        "CREATE (e:Entity {ha_id: 'sensor.entity_' + toString(i), name: 'Entity ' + toString(i), "
        "source: 'home_assistant'}) "
        "WITH e, devices[i % size(devices)] AS d "
        "MERGE (d)-[:HAS_ENTITY]->(e)",
        {"count": _NODE_COUNT - 50 - 950},
    )


async def _call_command(hass, handler, msg: dict) -> MagicMock:
    connection = MagicMock()
    handler(hass, connection, msg)
    # `@websocket_api.async_response` schedules the handler via
    # `hass.async_create_background_task`, which is tracked separately from
    # regular tasks; `async_block_till_done` must be told to wait for
    # background tasks too, or it returns before the handler has run.
    await hass.async_block_till_done(wait_background_tasks=True)
    return connection


async def test_area_context_entity_context_search_respond_within_budget(
    hass, memgraph_client: MemgraphClient
) -> None:
    await _seed_graph(memgraph_client)

    with patch.object(ontology_ws, "_first_loaded_client", return_value=memgraph_client):
        start = time.monotonic()
        connection = await _call_command(
            hass,
            ontology_ws._handle_area_context,
            {"id": 1, "type": "ontology/area_context", "area_id": "area-0"},
        )
        elapsed = time.monotonic() - start
        connection.send_error.assert_not_called()
        assert elapsed < _RESPONSE_BUDGET_SECONDS

        start = time.monotonic()
        connection = await _call_command(
            hass,
            ontology_ws._handle_entity_context,
            {"id": 2, "type": "ontology/entity_context", "entity_id": "sensor.entity_0"},
        )
        elapsed = time.monotonic() - start
        connection.send_error.assert_not_called()
        assert elapsed < _RESPONSE_BUDGET_SECONDS

        start = time.monotonic()
        connection = await _call_command(
            hass,
            ontology_ws._handle_search,
            {"id": 3, "type": "ontology/search", "query": "Entity 1"},
        )
        elapsed = time.monotonic() - start
        connection.send_result.assert_called_once()
        assert elapsed < _RESPONSE_BUDGET_SECONDS
