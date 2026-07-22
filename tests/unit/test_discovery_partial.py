"""Test: discovery still captures entities/devices/areas with missing
relationships (no device, no area, no floor) as incomplete data rather than
failing (FR-006, User Story 3)."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import graph_builder
from custom_components.ontology.const import DOMAIN


async def test_entity_with_no_device_is_still_captured(hass, mock_memgraph_client) -> None:
    """An entity registered directly (no `device_id`) is still written as an
    Entity node linked to its Domain, with no HAS_ENTITY relationship
    written for it (FR-006)."""
    entry = er.async_get(hass).async_get_or_create(
        "sensor", "test_platform", "no-device-unique-id"
    )
    assert entry.device_id is None

    entity_ids, domains, _integrations = await graph_builder.collect_entities(
        hass, mock_memgraph_client
    )

    assert entry.entity_id in entity_ids
    assert "sensor" in domains
    has_entity_calls = [
        call
        for call in mock_memgraph_client.run_query_with_retry.call_args_list
        if "HAS_ENTITY" in call.args[0]
    ]
    assert not has_entity_calls


async def test_device_with_no_area_is_still_captured(hass, mock_memgraph_client) -> None:
    """A device that isn't assigned to any area is still written as a Device
    node, with no HAS_DEVICE relationship written for it."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "orphan-device")},
        name="Orphan Device",
    )
    assert device.area_id is None

    device_ids = await graph_builder.collect_devices(hass, mock_memgraph_client)

    assert device.id in device_ids
    has_device_calls = [
        call
        for call in mock_memgraph_client.run_query_with_retry.call_args_list
        if "HAS_DEVICE" in call.args[0]
    ]
    assert not has_device_calls


async def test_area_with_no_floor_is_still_captured(hass, mock_memgraph_client) -> None:
    """An area with no floor assignment is still written, with no ON_FLOOR
    relationship written for it."""
    area = ar.async_get(hass).async_create("Basement")
    assert area.floor_id is None

    area_ids = await graph_builder.collect_areas(hass, mock_memgraph_client)

    assert area.id in area_ids
    on_floor_calls = [
        call
        for call in mock_memgraph_client.run_query_with_retry.call_args_list
        if "ON_FLOOR" in call.args[0]
    ]
    assert not on_floor_calls
