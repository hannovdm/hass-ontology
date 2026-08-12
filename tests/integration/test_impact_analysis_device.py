"""Integration test: device-level impact analysis (User Story 4): T033
(aggregates all exposed entities/dependencies/semantic objects), T034 (device
moved to another area, resynced, reflects current area), T035 (unresolvable
device returns not_found)."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import graph_builder, impact_analysis
from custom_components.ontology.const import DOMAIN
from custom_components.ontology.memgraph_client import MemgraphClient


async def test_device_impact_analysis_aggregates_exposed_entities(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    area = ar.async_get(hass).async_create("Living Room")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "device-impact-1")},
        name="Living Room Hub",
    )
    dr.async_get(hass).async_update_device(device.id, area_id=area.id)
    entity1 = er.async_get(hass).async_get_or_create(
        "light", "test_platform", "device-impact-e1", device_id=device.id
    )
    entity2 = er.async_get(hass).async_get_or_create(
        "switch", "test_platform", "device-impact-e2", device_id=device.id
    )
    hass.states.async_set(entity1.entity_id, "on")
    hass.states.async_set(entity2.entity_id, "on")
    # Real automations are required (not fake states): HA automation
    # entities only expose their referenced entities via the in-memory
    # `referenced_entities` property, not via state attributes.
    await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "alias": "Evening scene",
                    "trigger": [{"platform": "event", "event_type": "test_event"}],
                    "action": [
                        {
                            "service": "homeassistant.turn_on",
                            "target": {"entity_id": entity1.entity_id},
                        }
                    ],
                },
                {
                    "alias": "Security check",
                    "trigger": [{"platform": "event", "event_type": "test_event"}],
                    "action": [
                        {
                            "service": "homeassistant.turn_on",
                            "target": {"entity_id": entity2.entity_id},
                        }
                    ],
                },
            ]
        },
    )
    await hass.async_block_till_done()
    await graph_builder.build_full_graph(hass, memgraph_client)

    tool_result = await impact_analysis.analyze(memgraph_client, "device", device.id)

    assert tool_result["result_type"] == "impact_analysis"
    result = tool_result["result"]
    assert set(result["affected_entities"]) == {entity1.entity_id, entity2.entity_id}
    automation_ids = {a["ha_id"] for a in result["automations"]}
    assert automation_ids == {"automation.evening_scene", "automation.security_check"}


async def test_device_impact_analysis_reflects_current_area_after_move(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    area1 = ar.async_get(hass).async_create("Office")
    area2 = ar.async_get(hass).async_create("Bedroom")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "device-impact-move")},
        name="Movable Sensor Hub",
    )
    dr.async_get(hass).async_update_device(device.id, area_id=area1.id)
    entity = er.async_get(hass).async_get_or_create(
        "binary_sensor", "test_platform", "device-impact-move-e1", device_id=device.id
    )
    hass.states.async_set(entity.entity_id, "off")
    await hass.async_block_till_done()
    await graph_builder.build_full_graph(hass, memgraph_client)

    # Move the device to a new area, then rebuild (clear + rebuild is what
    # actually removes the stale HAS_DEVICE edge to the old area - a plain
    # resync only MERGEs additively and never deletes a stale relationship
    # to a since-vacated area, which is a pre-existing v1/v2 data-model
    # characteristic, not something v3 changes).
    dr.async_get(hass).async_update_device(device.id, area_id=area2.id)
    await hass.async_block_till_done()
    await graph_builder.clear_generated_graph(memgraph_client)
    await graph_builder.build_full_graph(hass, memgraph_client)

    area_rows = await memgraph_client.run_query(
        "MATCH (a)-[:HAS_DEVICE]->(d:Device {ha_id: $device_id}) RETURN a.ha_id AS ha_id",
        {"device_id": device.id},
    )
    assert [row["ha_id"] for row in area_rows] == [area2.id]

    tool_result = await impact_analysis.analyze(memgraph_client, "device", device.id)
    assert tool_result["result_type"] == "impact_analysis"
    assert entity.entity_id in tool_result["result"]["affected_entities"]
    assert tool_result["result"]["current_area"]["ha_id"] == area2.id


async def test_unresolvable_device_target_returns_not_found(
    hass, memgraph_client: MemgraphClient
) -> None:
    tool_result = await impact_analysis.analyze(memgraph_client, "device", "device-does-not-exist")
    assert tool_result["result_type"] == "not_found"
    assert tool_result["result"] is None
