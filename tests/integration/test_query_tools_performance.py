"""Integration test: every predefined query-tool call and every
impact-analysis call complete within 3 seconds on a several-thousand-node
fixture graph (User Story 5, T039, SC-005)."""

from __future__ import annotations

import time

from custom_components.ontology import impact_analysis, query_tools
from custom_components.ontology.memgraph_client import MemgraphClient

_NODE_COUNT = 5000
_RESPONSE_BUDGET_SECONDS = 3.0


async def _seed_graph(client: MemgraphClient) -> None:
    """Bulk-create ~5,000 Area/Device/Entity nodes plus a handful of
    Automations referencing some entities (mirrors
    test_websocket_api_performance.py's seeding pattern)."""
    await client.run_query(
        "UNWIND range(0, $count - 1) AS i "
        "CREATE (a:Area {ha_id: 'perf-area-' + toString(i), name: 'Perf Area ' + toString(i), "
        "source: 'home_assistant'})",
        {"count": 50},
    )
    await client.run_query(
        "MATCH (a:Area) WHERE a.ha_id STARTS WITH 'perf-area-' WITH collect(a) AS areas "
        "UNWIND range(0, $count - 1) AS i "
        "CREATE (d:Device {ha_id: 'perf-device-' + toString(i), "
        "name: 'Perf Device ' + toString(i), "
        "source: 'home_assistant'}) "
        "WITH d, areas[i % size(areas)] AS a "
        "MERGE (a)-[:HAS_DEVICE]->(d)",
        {"count": 950},
    )
    await client.run_query(
        "MATCH (d:Device) WHERE d.ha_id STARTS WITH 'perf-device-' WITH collect(d) AS devices "
        "UNWIND range(0, $count - 1) AS i "
        "CREATE (e:Entity {ha_id: 'sensor.perf_entity_' + toString(i), "
        "name: 'Perf Entity ' + toString(i), source: 'home_assistant'}) "
        "WITH e, devices[i % size(devices)] AS d "
        "MERGE (d)-[:HAS_ENTITY]->(e)",
        {"count": _NODE_COUNT - 50 - 950},
    )
    await client.run_query(
        "MATCH (e:Entity) WHERE e.ha_id STARTS WITH 'sensor.perf_entity_' "
        "WITH e LIMIT 20 "
        "CREATE (auto:Automation {ha_id: 'automation.perf_' + e.ha_id, name: 'Perf automation', "
        "source: 'home_assistant'})-[:REFERENCES]->(e)"
    )


async def _assert_within_budget(coro) -> None:
    start = time.monotonic()
    await coro
    elapsed = time.monotonic() - start
    assert elapsed < _RESPONSE_BUDGET_SECONDS, (
        f"Took {elapsed:.2f}s, budget is {_RESPONSE_BUDGET_SECONDS}s"
    )


async def test_query_tools_and_impact_analysis_respond_within_budget(
    memgraph_client: MemgraphClient,
) -> None:
    await _seed_graph(memgraph_client)

    await _assert_within_budget(query_tools.search(memgraph_client, "Perf Entity 1"))
    await _assert_within_budget(query_tools.area_context(memgraph_client, "perf-area-0"))
    await _assert_within_budget(query_tools.device_context(memgraph_client, "perf-device-0"))
    await _assert_within_budget(
        query_tools.entity_context(memgraph_client, "sensor.perf_entity_0")
    )
    await _assert_within_budget(
        query_tools.automation_dependencies(memgraph_client, "sensor.perf_entity_0")
    )
    await _assert_within_budget(
        impact_analysis.analyze(memgraph_client, "entity", "sensor.perf_entity_0")
    )
    await _assert_within_budget(
        impact_analysis.analyze(memgraph_client, "device", "perf-device-0")
    )
    await _assert_within_budget(impact_analysis.analyze(memgraph_client, "area", "perf-area-0"))
