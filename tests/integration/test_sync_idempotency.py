"""Integration test: running full synchronization twice does not create
duplicate nodes/relationships (User Story 4, Constitution Principle III/VI)."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import graph_builder
from custom_components.ontology.const import DOMAIN
from custom_components.ontology.memgraph_client import MemgraphClient


async def test_running_full_sync_twice_does_not_duplicate(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    area = ar.async_get(hass).async_create("Living Room")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "device-2")},
        name="Living Room Sensor",
    )
    dr.async_get(hass).async_update_device(device.id, area_id=area.id)
    entity = er.async_get(hass).async_get_or_create(
        "sensor", "test_platform", "living-room-sensor-unique-id", device_id=device.id
    )
    hass.states.async_set(entity.entity_id, "21.5")
    await hass.async_block_till_done()

    await graph_builder.build_full_graph(hass, memgraph_client)
    await graph_builder.build_full_graph(hass, memgraph_client)

    area_rows = await memgraph_client.run_query(
        "MATCH (a:Area {ha_id: $ha_id}) RETURN count(a) AS c", {"ha_id": area.id}
    )
    assert area_rows[0]["c"] == 1

    device_rows = await memgraph_client.run_query(
        "MATCH (d:Device {ha_id: $ha_id}) RETURN count(d) AS c", {"ha_id": device.id}
    )
    assert device_rows[0]["c"] == 1

    entity_rows = await memgraph_client.run_query(
        "MATCH (e:Entity {ha_id: $ha_id}) RETURN count(e) AS c",
        {"ha_id": entity.entity_id},
    )
    assert entity_rows[0]["c"] == 1

    has_device_rows = await memgraph_client.run_query(
        "MATCH (:Area {ha_id: $area_id})-[r:HAS_DEVICE]->(:Device {ha_id: $device_id}) "
        "RETURN count(r) AS c",
        {"area_id": area.id, "device_id": device.id},
    )
    assert has_device_rows[0]["c"] == 1

    schema_rows = await memgraph_client.run_query("MATCH (s:OntologySchema) RETURN count(s) AS c")
    assert schema_rows[0]["c"] == 1
