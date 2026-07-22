"""Integration test: an entity/device/area is deleted in Home Assistant while
another update is in flight; the queued update is handled as a removal
without corrupting the graph or crashing the coordinator (edge case,
spec.md Edge Cases, T045a)."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import graph_builder
from custom_components.ontology.const import DOMAIN
from custom_components.ontology.memgraph_client import MemgraphClient


async def test_deleted_entity_update_is_treated_as_removal(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    entity = er.async_get(hass).async_get_or_create(
        "sensor", "test_platform", "soon-to-be-deleted-unique-id"
    )
    hass.states.async_set(entity.entity_id, "42")
    await hass.async_block_till_done()
    await graph_builder.build_full_graph(hass, memgraph_client)

    entity_id = entity.entity_id
    er.async_get(hass).async_remove(entity_id)
    hass.states.async_remove(entity_id)

    # Should not raise even though the registry entry no longer exists.
    await graph_builder.update_entity(hass, memgraph_client, entity_id)

    rows = await memgraph_client.run_query(
        "MATCH (e:Entity {ha_id: $ha_id}) RETURN count(e) AS c", {"ha_id": entity_id}
    )
    assert rows[0]["c"] == 0


async def test_deleted_device_update_is_treated_as_removal(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "soon-to-be-deleted-device")},
        name="Temporary Device",
    )
    await graph_builder.build_full_graph(hass, memgraph_client)

    device_id = device.id
    dr.async_get(hass).async_remove_device(device_id)

    await graph_builder.update_device(hass, memgraph_client, device_id)

    rows = await memgraph_client.run_query(
        "MATCH (d:Device {ha_id: $ha_id}) RETURN count(d) AS c", {"ha_id": device_id}
    )
    assert rows[0]["c"] == 0


async def test_deleted_area_update_is_treated_as_removal(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    area = ar.async_get(hass).async_create("Temporary Area")
    await graph_builder.build_full_graph(hass, memgraph_client)

    area_id = area.id
    ar.async_get(hass).async_delete(area_id)

    await graph_builder.update_area(hass, memgraph_client, area_id)

    rows = await memgraph_client.run_query(
        "MATCH (a:Area {ha_id: $ha_id}) RETURN count(a) AS c", {"ha_id": area_id}
    )
    assert rows[0]["c"] == 0
