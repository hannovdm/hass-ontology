"""Unit coverage for durable energy-role assignments."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology.const import (
    ENERGY_ROLE_CONSUMER,
    ENERGY_ROLE_GRID_EXPORT,
    ENERGY_ROLE_GRID_IMPORT,
    ENERGY_ROLE_PRODUCER,
    ENERGY_ROLE_STORAGE,
    SOURCE_INFERRED,
    SOURCE_USER,
)
from custom_components.ontology.semantic_classifier import infer_energy_role
from custom_components.ontology.user_knowledge import (
    EnergyRoleRejected,
    async_delete_user_energy_role,
    async_reconcile_energy_roles,
    async_set_energy_role,
    energy_role_assignment_id,
)


def test_energy_role_identity_is_deterministic_and_source_specific() -> None:
    first = energy_role_assignment_id(SOURCE_USER, "sensor.dishwasher_power")
    second = energy_role_assignment_id(SOURCE_USER, "sensor.dishwasher_power")
    inferred = energy_role_assignment_id(SOURCE_INFERRED, "sensor.dishwasher_power")

    assert first == second
    assert first != inferred
    assert len(first) == 36


@pytest.mark.parametrize("role", ["unknown", "", "Consumer", None])
async def test_set_energy_role_rejects_invalid_roles_without_writing(role) -> None:
    client = AsyncMock()

    with pytest.raises(EnergyRoleRejected, match="energy role"):
        await async_set_energy_role(client, "sensor.dishwasher_power", role)

    client.run_query.assert_not_awaited()


async def test_user_assignment_overrides_inferred_assignment() -> None:
    client = AsyncMock()
    client.run_query.side_effect = [
        [
            {
                "entity_id": "sensor.dishwasher_power",
                "name": "Dishwasher power",
                "measurement_kind": "power",
            }
        ],
        [
            {
                "assignment_id": energy_role_assignment_id(
                    SOURCE_USER, "sensor.dishwasher_power"
                ),
                "entity_id": "sensor.dishwasher_power",
                "role": ENERGY_ROLE_CONSUMER,
                "source": SOURCE_USER,
                "effective_role": ENERGY_ROLE_CONSUMER,
                "effective_source": SOURCE_USER,
            }
        ],
    ]

    result = await async_set_energy_role(
        client, "Dishwasher power", ENERGY_ROLE_CONSUMER
    )

    assert result["effective_role"] == ENERGY_ROLE_CONSUMER
    assert result["effective_source"] == SOURCE_USER
    write_query, parameters = client.run_query.await_args_list[1].args
    assert "MERGE (assignment:EnergyRoleAssignment" in write_query
    assert parameters["assignment_id"] == energy_role_assignment_id(
        SOURCE_USER, "sensor.dishwasher_power"
    )
    assert parameters["source"] == SOURCE_USER


async def test_delete_user_assignment_reveals_inferred_role() -> None:
    client = AsyncMock()
    client.run_query.side_effect = [
        [
            {
                "entity_id": "sensor.solar_power",
                "name": "Solar power",
                "measurement_kind": "power",
            }
        ],
        [
            {
                "deleted": 1,
                "entity_id": "sensor.solar_power",
                "effective_role": ENERGY_ROLE_PRODUCER,
                "effective_source": SOURCE_INFERRED,
            }
        ],
    ]

    result = await async_delete_user_energy_role(client, "sensor.solar_power")

    assert result == {
        "deleted": True,
        "entity_id": "sensor.solar_power",
        "effective_role": ENERGY_ROLE_PRODUCER,
        "effective_source": SOURCE_INFERRED,
    }
    delete_query = client.run_query.await_args_list[1].args[0]
    assert "source: $source" in delete_query
    assert "DETACH DELETE assignment" in delete_query


async def test_role_mutation_rejects_ambiguous_or_non_power_entities() -> None:
    client = AsyncMock()
    client.run_query.return_value = [
        {
            "entity_id": "sensor.kitchen_power_1",
            "name": "Kitchen power",
            "measurement_kind": "power",
        },
        {
            "entity_id": "sensor.kitchen_power_2",
            "name": "Kitchen power",
            "measurement_kind": "power",
        },
    ]

    with pytest.raises(EnergyRoleRejected, match="ambiguous"):
        await async_set_energy_role(client, "Kitchen power", ENERGY_ROLE_CONSUMER)

    assert client.run_query.await_count == 1


@pytest.mark.parametrize(
    ("entity_id", "friendly_name", "expected"),
    [
        ("sensor.solar_output", "Solar generation", ENERGY_ROLE_PRODUCER),
        ("sensor.home_battery_power", "Battery storage power", ENERGY_ROLE_STORAGE),
        ("sensor.grid_import", "Grid import power", ENERGY_ROLE_GRID_IMPORT),
        ("sensor.grid_export", "Grid export power", ENERGY_ROLE_GRID_EXPORT),
        ("sensor.dishwasher_load", "Dishwasher consumption", ENERGY_ROLE_CONSUMER),
        ("sensor.main_power", "Main power", None),
    ],
)
async def test_energy_role_inference_is_conservative(
    hass, entity_id: str, friendly_name: str, expected: str | None
) -> None:
    hass.states.async_set(
        entity_id,
        "10",
        {
            "device_class": "power",
            "unit_of_measurement": "W",
            "friendly_name": friendly_name,
        },
    )

    assert infer_energy_role(hass, entity_id) == expected


async def test_device_backed_power_measurement_infers_consumer(hass) -> None:
    MockConfigEntry(entry_id="test-entry").add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id="test-entry",
        identifiers={("test", "generic-appliance")},
        name="Generic appliance",
    )
    entry = er.async_get(hass).async_get_or_create(
        "sensor",
        "test",
        "generic-appliance-power",
        suggested_object_id="generic_appliance_power",
        device_id=device.id,
    )
    hass.states.async_set(
        entry.entity_id,
        "125",
        {
            "device_class": "power",
            "unit_of_measurement": "W",
            "friendly_name": "Channel 1 power",
        },
    )

    assert infer_energy_role(hass, entry.entity_id) == ENERGY_ROLE_CONSUMER


async def test_unattached_generic_power_measurement_remains_unknown(hass) -> None:
    hass.states.async_set(
        "sensor.whole_home_power",
        "125",
        {
            "device_class": "power",
            "unit_of_measurement": "W",
            "friendly_name": "Whole home power",
        },
    )

    assert infer_energy_role(hass, "sensor.whole_home_power") is None


async def test_reconciliation_upserts_inferred_source_and_repairs_bindings(hass) -> None:
    hass.states.async_set(
        "sensor.solar_output",
        "500",
        {
            "device_class": "power",
            "unit_of_measurement": "W",
            "friendly_name": "Solar generation",
        },
    )
    client = AsyncMock()
    client.run_query.return_value = []

    reconciled = await async_reconcile_energy_roles(hass, client)

    assert reconciled == 1
    inferred_write = next(
        call
        for call in client.run_query.await_args_list
        if "MERGE (assignment:EnergyRoleAssignment" in call.args[0]
    )
    assert inferred_write.args[1]["assignment_id"] == energy_role_assignment_id(
        SOURCE_INFERRED, "sensor.solar_output"
    )
    assert inferred_write.args[1]["source"] == SOURCE_INFERRED
    repair_query = client.run_query.await_args_list[-1].args[0]
    assert "DELETE binding" in repair_query
    assert "MERGE (assignment)-[binding:ASSIGNS_ROLE_TO]->(entity)" in repair_query