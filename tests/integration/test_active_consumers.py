"""Real-Memgraph coverage for energy roles and active consumers."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology.const import (
    DOMAIN,
    ENERGY_ROLE_CONSUMER,
    ENERGY_ROLE_PRODUCER,
    OUTCOME_EMPTY,
    OUTCOME_OK,
    SOURCE_INFERRED,
    SOURCE_USER,
)
from custom_components.ontology.coordinator import OntologyCoordinator
from custom_components.ontology.memgraph_client import MemgraphClient
from custom_components.ontology.query_tools import active_consumers
from custom_components.ontology.user_knowledge import async_set_energy_role


async def _make_power_coordinator(
    hass, memgraph_client: MemgraphClient
) -> OntologyCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, entry_id="test-entry")
    entry.add_to_hass(hass)
    kitchen = ar.async_get(hass).async_create("Kitchen")
    dishwasher = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("test", "dishwasher")},
        name="Dishwasher",
        suggested_area=kitchen.id,
    )
    geyser = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("test", "geyser")},
        name="Geyser",
        suggested_area=kitchen.id,
    )
    solar = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("test", "solar")},
        name="Solar inverter",
        suggested_area=kitchen.id,
    )
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor",
        "test",
        "dishwasher-power",
        suggested_object_id="dishwasher_power",
        device_id=dishwasher.id,
    )
    registry.async_get_or_create(
        "sensor",
        "test",
        "solar-generation",
        suggested_object_id="solar_generation",
        device_id=solar.id,
    )
    registry.async_get_or_create(
        "sensor",
        "test",
        "geyser-power",
        suggested_object_id="geyser_power",
        device_id=geyser.id,
    )
    hass.states.async_set(
        "sensor.dishwasher_power",
        "850",
        {
            "device_class": "power",
            "unit_of_measurement": "W",
            "friendly_name": "Dishwasher consumption",
        },
    )
    hass.states.async_set(
        "sensor.solar_generation",
        "1200",
        {
            "device_class": "power",
            "unit_of_measurement": "W",
            "friendly_name": "Solar generation",
        },
    )
    hass.states.async_set(
        "sensor.geyser_power",
        "2100",
        {
            "device_class": "power",
            "unit_of_measurement": "W",
            "friendly_name": "Channel 1 power",
        },
    )
    await hass.async_block_till_done()

    coordinator = OntologyCoordinator(hass, entry, memgraph_client)
    await coordinator._execute_full_sync(clear_first=False)
    return coordinator


async def _role_rows(client: MemgraphClient) -> list[dict]:
    return await client.run_query(
        "MATCH (assignment:EnergyRoleAssignment)-[:ASSIGNS_ROLE_TO]->(entity:Entity) "
        "RETURN assignment.measurement_entity_id AS entity_id, "
        "assignment.role AS role, assignment.source AS source, "
        "entity.ha_id AS bound_entity_id "
        "ORDER BY entity_id, source"
    )


async def test_active_consumers_uses_effective_roles_and_real_relationships(
    hass, memgraph_client: MemgraphClient
) -> None:
    await _make_power_coordinator(hass, memgraph_client)

    inferred_result = await active_consumers(memgraph_client)

    assert inferred_result["outcome"] == OUTCOME_OK
    assert [item["name"] for item in inferred_result["result"]["consumers"]] == [
        "Dishwasher",
        "Geyser",
    ]
    assert inferred_result["result"]["consumers"][0]["measurements"][0][
        "role_source"
    ] == SOURCE_INFERRED

    await async_set_energy_role(
        memgraph_client, "sensor.dishwasher_power", ENERGY_ROLE_PRODUCER
    )
    overridden_result = await active_consumers(memgraph_client)

    assert overridden_result["outcome"] == OUTCOME_EMPTY
    assert overridden_result["result"]["consumers"] == []


async def test_role_assignments_and_bindings_survive_resync_and_rebuild(
    hass, memgraph_client: MemgraphClient
) -> None:
    coordinator = await _make_power_coordinator(hass, memgraph_client)
    await async_set_energy_role(
        memgraph_client, "sensor.solar_generation", ENERGY_ROLE_CONSUMER
    )

    await coordinator.async_resync()
    after_resync = await _role_rows(memgraph_client)
    await coordinator.async_rebuild()
    after_rebuild = await _role_rows(memgraph_client)

    assert after_resync == after_rebuild
    assert {
        (row["entity_id"], row["role"], row["source"], row["bound_entity_id"])
        for row in after_rebuild
    } == {
        (
            "sensor.dishwasher_power",
            ENERGY_ROLE_CONSUMER,
            SOURCE_INFERRED,
            "sensor.dishwasher_power",
        ),
        (
            "sensor.geyser_power",
            ENERGY_ROLE_CONSUMER,
            SOURCE_INFERRED,
            "sensor.geyser_power",
        ),
        (
            "sensor.solar_generation",
            ENERGY_ROLE_PRODUCER,
            SOURCE_INFERRED,
            "sensor.solar_generation",
        ),
        (
            "sensor.solar_generation",
            ENERGY_ROLE_CONSUMER,
            SOURCE_USER,
            "sensor.solar_generation",
        ),
    }