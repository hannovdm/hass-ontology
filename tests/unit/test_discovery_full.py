"""Test: discovery reads the full set of populated registries (floor, area,
device, label, entity) and captures each entity's domain and source
integration (User Story 3, T029-T031)."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers import label_registry as lr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import graph_builder
from custom_components.ontology.const import DOMAIN


def _merge_node_calls(mock_client, label: str) -> list:
    return [
        call
        for call in mock_client.run_query_with_retry.call_args_list
        if f"MERGE (n:{label} " in call.args[0]
    ]


async def test_discovery_full_registries(hass, mock_memgraph_client) -> None:
    """Full registries (floor, area, label, device, entity) are all read and
    each entity's domain and source integration are captured."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    floor = fr.async_get(hass).async_create("Ground Floor")
    area = ar.async_get(hass).async_create("Living Room", floor_id=floor.floor_id)
    label = lr.async_get(hass).async_create("important")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "device-1")},
        manufacturer="Acme",
        model="Widget",
        name="Living Room Light",
    )
    dr.async_get(hass).async_update_device(device.id, area_id=area.id)

    entity_entry = er.async_get(hass).async_get_or_create(
        "light",
        "demo",
        "unique-1",
        device_id=device.id,
        config_entry=entry,
    )
    er.async_get(hass).async_update_entity(entity_entry.entity_id, labels={label.label_id})
    hass.states.async_set(entity_entry.entity_id, "on")
    await hass.async_block_till_done()

    await graph_builder.collect_floors(hass, mock_memgraph_client)
    await graph_builder.collect_areas(hass, mock_memgraph_client)
    await graph_builder.collect_devices(hass, mock_memgraph_client)
    await graph_builder.collect_labels(hass, mock_memgraph_client)
    entity_ids, domains, integrations = await graph_builder.collect_entities(
        hass, mock_memgraph_client
    )

    assert entity_entry.entity_id in entity_ids
    assert "light" in domains
    assert "demo" in integrations

    assert _merge_node_calls(mock_memgraph_client, "Floor")
    assert _merge_node_calls(mock_memgraph_client, "Area")
    assert _merge_node_calls(mock_memgraph_client, "Device")
    assert _merge_node_calls(mock_memgraph_client, "Label")
    entity_calls = _merge_node_calls(mock_memgraph_client, "Entity")
    assert any(call.args[1]["ha_id"] == entity_entry.entity_id for call in entity_calls)

    has_label_calls = [
        call
        for call in mock_memgraph_client.run_query_with_retry.call_args_list
        if "HAS_LABEL" in call.args[0]
    ]
    assert has_label_calls
