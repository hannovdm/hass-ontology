"""Integration test: renaming an area / moving a device / adding an entity
updates only the affected node(s)/relationship(s) without a full rebuild
(User Story 5)."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import graph_builder
from custom_components.ontology.const import DOMAIN
from custom_components.ontology.memgraph_client import MemgraphClient


async def test_renaming_area_updates_only_that_area_node(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    area = ar.async_get(hass).async_create("Old Name")
    await graph_builder.build_full_graph(hass, memgraph_client)

    ar.async_get(hass).async_update(area.id, name="New Name")
    await graph_builder.update_area(hass, memgraph_client, area.id)

    rows = await memgraph_client.run_query(
        "MATCH (a:Area {ha_id: $ha_id}) RETURN a.name AS name", {"ha_id": area.id}
    )
    assert rows[0]["name"] == "New Name"


async def test_moving_device_updates_has_device_relationship(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    area_a = ar.async_get(hass).async_create("Area A")
    area_b = ar.async_get(hass).async_create("Area B")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "movable-device")},
        name="Movable Device",
    )
    dr.async_get(hass).async_update_device(device.id, area_id=area_a.id)
    await graph_builder.build_full_graph(hass, memgraph_client)

    dr.async_get(hass).async_update_device(device.id, area_id=area_b.id)
    await graph_builder.update_device(hass, memgraph_client, device.id)

    new_rel_rows = await memgraph_client.run_query(
        "MATCH (:Area {ha_id: $area_id})-[r:HAS_DEVICE]->(:Device {ha_id: $device_id}) "
        "RETURN count(r) AS c",
        {"area_id": area_b.id, "device_id": device.id},
    )
    assert new_rel_rows[0]["c"] == 1


async def test_adding_entity_creates_only_that_entity_node(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    await graph_builder.build_full_graph(hass, memgraph_client)

    entity = er.async_get(hass).async_get_or_create(
        "switch", "test_platform", "new-switch-unique-id"
    )
    hass.states.async_set(entity.entity_id, "off")
    await hass.async_block_till_done()

    await graph_builder.update_entity(hass, memgraph_client, entity.entity_id)

    rows = await memgraph_client.run_query(
        "MATCH (e:Entity {ha_id: $ha_id}) RETURN e.state AS state",
        {"ha_id": entity.entity_id},
    )
    assert rows[0]["state"] == "off"
