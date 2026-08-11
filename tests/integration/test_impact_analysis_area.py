"""Integration test: area-level impact analysis (User Story 5): T037
(affected devices/entities/automations/scripts/scenes/dashboards where
available), T038 (empty area returns empty-but-present result)."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import graph_builder, impact_analysis
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
    hass.states.async_set(
        "automation.garage_alert",
        "on",
        {"entity_id": [entity.entity_id], "friendly_name": "Garage alert"},
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
