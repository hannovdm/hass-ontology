"""Integration test: area-level impact analysis (User Story 5): T037
(affected devices/entities/automations/scripts/scenes/dashboards where
available), T038 (empty area returns empty-but-present result)."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import graph_builder, impact_analysis, query_tools
from custom_components.ontology.const import DOMAIN
from custom_components.ontology.memgraph_client import MemgraphClient


async def test_area_impact_analysis_aggregates_devices_entities_and_automations(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    area = ar.async_get(hass).async_create("Garage")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "area-impact-device-1")},
        name="Garage Controller",
    )
    dr.async_get(hass).async_update_device(device.id, area_id=area.id)
    entity = er.async_get(hass).async_get_or_create(
        "cover", "test_platform", "area-impact-e1", device_id=device.id
    )
    hass.states.async_set(entity.entity_id, "closed")
    # A real automation is required (not a fake state): HA automation
    # entities only expose their referenced entities via the in-memory
    # `referenced_entities` property, not via state attributes.
    await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "alias": "Garage alert",
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
    await graph_builder.build_full_graph(hass, memgraph_client)

    tool_result = await impact_analysis.analyze(memgraph_client, "area", area.id)

    assert tool_result["result_type"] == "impact_analysis"
    result = tool_result["result"]
    assert result["affected_devices"] == [device.id]
    assert entity.entity_id in result["affected_entities"]
    assert any(a["ha_id"] == "automation.garage_alert" for a in result["automations"])
    assert result["has_dependencies"] is True


async def test_area_with_no_devices_or_entities_returns_empty_with_explanation(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    area = ar.async_get(hass).async_create("Empty Room")
    await hass.async_block_till_done()
    await graph_builder.build_full_graph(hass, memgraph_client)

    tool_result = await impact_analysis.analyze(memgraph_client, "area", area.id)

    assert tool_result["result_type"] == "impact_analysis"
    result = tool_result["result"]
    assert result["affected_devices"] == []
    assert result["affected_entities"] == []
    assert result["has_dependencies"] is False
    assert tool_result["warnings"] == ["no known dependencies found"]


async def test_direct_entity_area_override_is_in_context_and_impact(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    area = ar.async_get(hass).async_create("Direct Entity Area")
    entity = er.async_get(hass).async_get_or_create(
        "sensor", "test_platform", "direct-area-impact"
    )
    er.async_get(hass).async_update_entity(entity.entity_id, area_id=area.id)
    hass.states.async_set(entity.entity_id, "ready")
    await hass.async_block_till_done()
    await graph_builder.build_full_graph(hass, memgraph_client)

    area_context = await query_tools.area_context(memgraph_client, area.id)
    area_impact = await impact_analysis.analyze(memgraph_client, "area", area.id)

    assert entity.entity_id in {
        item["ha_id"] for item in area_context["result"]["entities"]
    }
    assert entity.entity_id in area_impact["result"]["affected_entities"]
