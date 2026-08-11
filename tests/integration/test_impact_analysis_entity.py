"""Integration test: entity-level impact analysis correctness against a real
Memgraph fixture (User Story 3): T028 (automations/scripts/scenes/dashboards/
semantic assets referencing the entity), T029 (no-dependencies and
not-found cases)."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
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
    hass.states.async_set(
        "automation.morning_routine",
        "on",
        {"entity_id": [entity.entity_id], "friendly_name": "Morning routine"},
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
