"""Integration test: full initial synchronization against a real Memgraph
container produces the expected nodes/relationships (User Story 4)."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import graph_builder
from custom_components.ontology.const import DOMAIN
from custom_components.ontology.memgraph_client import MemgraphClient


async def test_initial_sync_creates_expected_nodes_and_relationships(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)

    area = ar.async_get(hass).async_create("Kitchen")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "device-1")},
        name="Kitchen Light Controller",
    )
    dr.async_get(hass).async_update_device(device.id, area_id=area.id)
    entity = er.async_get(hass).async_get_or_create(
        "light", "test_platform", "kitchen-light-unique-id", device_id=device.id
    )
    hass.states.async_set(entity.entity_id, "on")
    await hass.async_block_till_done()

    counts = await graph_builder.build_full_graph(hass, memgraph_client)

    assert counts["entities"] >= 1

    home_rows = await memgraph_client.run_query("MATCH (h:Home) RETURN h.ha_id AS ha_id")
    assert len(home_rows) == 1

    area_rows = await memgraph_client.run_query(
        "MATCH (a:Area {ha_id: $ha_id}) RETURN a.name AS name", {"ha_id": area.id}
    )
    assert area_rows[0]["name"] == "Kitchen"

    device_rows = await memgraph_client.run_query(
        "MATCH (d:Device {ha_id: $ha_id}) RETURN d.name AS name", {"ha_id": device.id}
    )
    assert len(device_rows) == 1

    entity_rows = await memgraph_client.run_query(
        "MATCH (e:Entity {ha_id: $ha_id}) RETURN e.state AS state",
        {"ha_id": entity.entity_id},
    )
    assert entity_rows[0]["state"] == "on"

    has_entity_rows = await memgraph_client.run_query(
        "MATCH (:Device {ha_id: $device_id})-[:HAS_ENTITY]->(:Entity {ha_id: $entity_id}) "
        "RETURN count(*) AS c",
        {"device_id": device.id, "entity_id": entity.entity_id},
    )
    assert has_entity_rows[0]["c"] == 1

    schema_rows = await memgraph_client.run_query(
        "MATCH (s:OntologySchema) RETURN s.version AS version"
    )
    assert len(schema_rows) == 1
