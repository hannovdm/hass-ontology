"""Real-Memgraph coverage for low-battery synchronization and relationships."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import graph_builder
from custom_components.ontology.const import OUTCOME_OK
from custom_components.ontology.memgraph_client import MemgraphClient
from custom_components.ontology.query_tools import low_battery_areas


async def test_low_battery_areas_uses_synced_measurements_and_current_topology(
    hass, memgraph_client: MemgraphClient
) -> None:
    MockConfigEntry(entry_id="test-entry").add_to_hass(hass)
    garage = ar.async_get(hass).async_create("Garage")
    kitchen = ar.async_get(hass).async_create("Kitchen")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id="test-entry",
        identifiers={("test", "remote")},
        name="Remote",
        suggested_area=garage.id,
    )
    registry = er.async_get(hass)
    for entity_id in (
        "sensor.remote_battery",
        "sensor.remote_backup_battery",
    ):
        registry.async_get_or_create(
            domain="sensor",
            platform="test",
            unique_id=entity_id,
            suggested_object_id=entity_id.split(".", 1)[1],
            device_id=device.id,
        )
    direct_entity = registry.async_get_or_create(
        domain="sensor",
        platform="test",
        unique_id="button_battery",
        suggested_object_id="button_battery",
    )
    registry.async_update_entity(direct_entity.entity_id, area_id=kitchen.id)
    stale_entity = registry.async_get_or_create(
        domain="sensor",
        platform="test",
        unique_id="stale_battery",
        suggested_object_id="stale_battery",
    )
    registry.async_update_entity(stale_entity.entity_id, area_id=kitchen.id)
    now = datetime.now(UTC)
    hass.states.async_set(
        "sensor.remote_battery",
        "8",
        {"device_class": "battery", "unit_of_measurement": "%", "friendly_name": "Remote battery"},
    )
    hass.states.async_set(
        "sensor.remote_backup_battery",
        "12",
        {
            "device_class": "battery",
            "unit_of_measurement": "%",
            "friendly_name": "Remote backup battery",
        },
    )
    hass.states.async_set(
        "sensor.button_battery",
        "19",
        {"device_class": "battery", "unit_of_measurement": "%", "friendly_name": "Button battery"},
    )
    hass.states.async_set(
        "sensor.stale_battery",
        "5",
        {"device_class": "battery", "unit_of_measurement": "%"},
    )
    await hass.async_block_till_done()

    await graph_builder.build_full_graph(hass, memgraph_client)
    await memgraph_client.run_query(
        "MATCH (e:Entity {ha_id: $entity_id}) "
        "SET e.measurement_last_updated_epoch = $last_updated_epoch",
        {
            "entity_id": "sensor.stale_battery",
            "last_updated_epoch": now.timestamp() - (25 * 3600),
        },
    )
    result = await low_battery_areas(memgraph_client, now_epoch=now.timestamp())

    assert result["outcome"] == OUTCOME_OK
    assert [area["area_name"] for area in result["result"]["areas"]] == [
        "Garage",
        "Kitchen",
    ]
    garage_item = result["result"]["areas"][0]["items"][0]
    assert garage_item["device_id"] == device.id
    assert sorted(
        measurement["percentage"] for measurement in garage_item["measurements"]
    ) == [8.0, 12.0]
    direct_item = result["result"]["areas"][1]["items"][0]
    assert direct_item["device_id"] is None
    assert direct_item["entity_id"] == "sensor.button_battery"