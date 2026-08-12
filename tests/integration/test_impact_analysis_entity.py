"""Integration test: entity-level impact analysis correctness against a real
Memgraph fixture (User Story 3): T028 (automations/scripts/scenes/dashboards/
semantic assets referencing the entity), T029 (no-dependencies and
not-found cases)."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import graph_builder, impact_analysis
from custom_components.ontology.const import DOMAIN
from custom_components.ontology.memgraph_client import MemgraphClient


async def _seed_entity_with_automation(hass, entry_id: str) -> str:
    area = ar.async_get(hass).async_create("Kitchen")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry_id,
        identifiers={(DOMAIN, "impact-device-1")},
        name="Kitchen Light Controller",
    )
    dr.async_get(hass).async_update_device(device.id, area_id=area.id)
    entity = er.async_get(hass).async_get_or_create(
        "light", "test_platform", "impact-entity-1", device_id=device.id
    )
    hass.states.async_set(entity.entity_id, "on")
    # A real automation is required (not a fake state): HA automation
    # entities only expose their referenced entities via the in-memory
    # `referenced_entities` property, not via state attributes.
    await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "alias": "Morning routine",
                    "trigger": [{"platform": "event", "event_type": "test_event"}],
                    "action": [
                        {
                            "service": "homeassistant.turn_on",
                            "target": {"entity_id": entity.entity_id},
                        }
                    ],
                }
            ]
        },
    )
    await hass.async_block_till_done()
    return entity.entity_id


async def test_entity_impact_analysis_finds_referencing_automation(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    entity_id = await _seed_entity_with_automation(hass, entry.entry_id)
    await graph_builder.build_full_graph(hass, memgraph_client)

    tool_result = await impact_analysis.analyze(memgraph_client, "entity", entity_id)

    assert tool_result["result_type"] == "impact_analysis"
    result = tool_result["result"]
    assert result["has_dependencies"] is True
    assert any(a["ha_id"] == "automation.morning_routine" for a in result["automations"])


async def test_all_dependency_types_propagate_to_entity_device_and_area_scopes(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    area = ar.async_get(hass).async_create("Impact Coverage")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "impact-coverage-device")},
        name="Impact Coverage Device",
    )
    dr.async_get(hass).async_update_device(device.id, area_id=area.id)
    entity = er.async_get(hass).async_get_or_create(
        "light", "test_platform", "impact-coverage-entity", device_id=device.id
    )
    hass.states.async_set(entity.entity_id, "on")
    await hass.async_block_till_done()
    await graph_builder.build_full_graph(hass, memgraph_client)
    await memgraph_client.run_query(
        "MATCH (e:Entity {ha_id: $entity_id}) "
        "MERGE (script:Script {ha_id: 'script.impact_coverage'}) "
        "SET script.name = 'Impact Script' "
        "MERGE (script)-[:REFERENCES]->(e) "
        "MERGE (scene:Scene {ha_id: 'scene.impact_coverage'}) "
        "SET scene.name = 'Impact Scene' "
        "MERGE (scene)-[:CONTROLS]->(e) "
        "MERGE (dashboard:Dashboard {ha_id: 'impact-dashboard'}) "
        "SET dashboard.name = 'Impact Dashboard' "
        "MERGE (card:DashboardCard {ha_id: 'impact-card'}) "
        "MERGE (dashboard)-[:CONTAINS_CARD]->(card) "
        "MERGE (card)-[:DISPLAYS_ENTITY]->(e) "
        "MERGE (asset:GasCylinder {ha_id: 'impact-asset'}) "
        "SET asset.name = 'Impact Asset' "
        "MERGE (e)-[:CLASSIFIED_AS]->(asset)",
        {"entity_id": entity.entity_id},
    )

    for scope, target in (
        ("entity", entity.entity_id),
        ("device", device.id),
        ("area", area.id),
    ):
        result = (await impact_analysis.analyze(memgraph_client, scope, target))["result"]
        assert {item["ha_id"] for item in result["scripts"]} == {
            "script.impact_coverage"
        }
        assert {item["ha_id"] for item in result["scenes"]} == {
            "scene.impact_coverage"
        }
        assert {item["ha_id"] for item in result["dashboards"]} == {
            "impact-dashboard"
        }
        assert {item["ha_id"] for item in result["semantic_assets"]} == {
            "impact-asset"
        }


async def test_entity_with_no_dependencies_returns_empty_not_error(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    entity = er.async_get(hass).async_get_or_create(
        "sensor", "test_platform", "lonely-entity-1"
    )
    hass.states.async_set(entity.entity_id, "23.5")
    await hass.async_block_till_done()
    await graph_builder.build_full_graph(hass, memgraph_client)

    tool_result = await impact_analysis.analyze(memgraph_client, "entity", entity.entity_id)

    assert tool_result["result_type"] == "impact_analysis"
    result = tool_result["result"]
    assert result["has_dependencies"] is False
    assert result["automations"] == []
    assert tool_result["warnings"] == ["no known dependencies found"]


async def test_unresolvable_entity_target_returns_not_found(
    hass, memgraph_client: MemgraphClient
) -> None:
    tool_result = await impact_analysis.analyze(
        memgraph_client, "entity", "sensor.does_not_exist_at_all"
    )
    assert tool_result["result_type"] == "not_found"
    assert tool_result["result"] is None
