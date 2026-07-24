"""Unit tests for semantic classification (User Story 1) and on-demand
refresh (User Story 6).

Covers: T006 (rule matching for all 8 semantic types, including an entity
matching more than one rule), T007 (classification never overwrites an
existing user override), and T042 (`refresh_semantics` recalculates all
entities or a single `entity_id`, preserving user overrides)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.helpers import entity_registry as er

from custom_components.ontology import semantic_classifier
from custom_components.ontology.const import (
    LABEL_BATTERY_POWERED_DEVICE,
    LABEL_CLIMATE_DEVICE,
    LABEL_ENERGY_ASSET,
    LABEL_GAS_CYLINDER,
    LABEL_NETWORK_DEVICE,
    LABEL_OCCUPANCY_SENSOR,
    LABEL_SECURITY_DEVICE,
    LABEL_VEHICLE,
    REL_CLASSIFIED_AS,
)


def _matched_labels(hass, entity_id: str) -> set[str]:
    return {rule.label for rule in semantic_classifier.matching_rules(hass, entity_id)}


async def test_gas_cylinder_classification(hass) -> None:
    hass.states.async_set("sensor.gas_meter", "42", {"device_class": "gas"})
    assert LABEL_GAS_CYLINDER in _matched_labels(hass, "sensor.gas_meter")


async def test_vehicle_classification(hass) -> None:
    hass.states.async_set("device_tracker.my_car", "home", {"friendly_name": "My Car"})
    assert LABEL_VEHICLE in _matched_labels(hass, "device_tracker.my_car")


async def test_energy_asset_classification(hass) -> None:
    hass.states.async_set("sensor.inverter_output", "1200", {"device_class": "power"})
    assert LABEL_ENERGY_ASSET in _matched_labels(hass, "sensor.inverter_output")


async def test_security_device_classification(hass) -> None:
    hass.states.async_set("lock.front_door", "locked", {"device_class": "lock"})
    assert LABEL_SECURITY_DEVICE in _matched_labels(hass, "lock.front_door")


async def test_occupancy_sensor_classification(hass) -> None:
    hass.states.async_set("binary_sensor.hallway_motion", "off", {"device_class": "motion"})
    assert LABEL_OCCUPANCY_SENSOR in _matched_labels(hass, "binary_sensor.hallway_motion")


async def test_climate_device_classification(hass) -> None:
    hass.states.async_set("climate.living_room", "heat", {})
    assert LABEL_CLIMATE_DEVICE in _matched_labels(hass, "climate.living_room")


async def test_network_device_classification(hass) -> None:
    hass.states.async_set("device_tracker.router", "home", {})
    assert LABEL_NETWORK_DEVICE in _matched_labels(hass, "device_tracker.router")


async def test_battery_powered_device_classification(hass) -> None:
    hass.states.async_set("sensor.node_battery", "80", {"device_class": "battery"})
    assert LABEL_BATTERY_POWERED_DEVICE in _matched_labels(hass, "sensor.node_battery")


async def test_entity_can_match_more_than_one_rule(hass) -> None:
    """FR-005: an entity is not limited to a single semantic type."""
    hass.states.async_set(
        "sensor.solar_battery",
        "50",
        {"device_class": "battery", "friendly_name": "Solar Battery Sensor"},
    )
    labels = _matched_labels(hass, "sensor.solar_battery")
    assert LABEL_ENERGY_ASSET in labels
    assert LABEL_BATTERY_POWERED_DEVICE in labels


def _classified_as_calls(mock_client: AsyncMock, from_ha_id: str) -> list:
    return [
        call
        for call in mock_client.run_query_with_retry.call_args_list
        if REL_CLASSIFIED_AS in call.args[0] and call.args[1].get("from_ha_id") == from_ha_id
    ]


async def test_classification_never_overwrites_existing_user_override(
    hass, mock_memgraph_client
) -> None:
    """FR-006: an entity/type pair with an existing `source = "user"`
    override is skipped entirely (no MERGE calls for that pair), while an
    unrelated entity with no override is still classified normally."""
    er.async_get(hass).async_get_or_create(
        "sensor", "demo", "gas-meter-1", suggested_object_id="gas_meter"
    )
    er.async_get(hass).async_get_or_create(
        "device_tracker", "demo", "my-car-1", suggested_object_id="my_car"
    )
    hass.states.async_set("sensor.gas_meter", "42", {"device_class": "gas"})
    hass.states.async_set("device_tracker.my_car", "home", {"friendly_name": "My Car"})

    async def run_query_side_effect(query, params=None):
        params = params or {}
        if params.get("entity_id") == "sensor.gas_meter" and params.get(
            "type_label"
        ) == LABEL_GAS_CYLINDER:
            return [{"c": 1}]
        return [{"c": 0}]

    mock_memgraph_client.run_query = AsyncMock(side_effect=run_query_side_effect)

    await semantic_classifier.async_classify_entities(hass, mock_memgraph_client)

    assert _classified_as_calls(mock_memgraph_client, "sensor.gas_meter") == []
    assert _classified_as_calls(mock_memgraph_client, "device_tracker.my_car") != []


async def test_refresh_semantics_scoped_to_single_entity(hass, mock_memgraph_client) -> None:
    """T042: `refresh_semantics(entity_id=...)` only recalculates that one
    entity, leaving other entities' classification untouched by this call."""
    hass.states.async_set("sensor.gas_meter", "42", {"device_class": "gas"})
    hass.states.async_set("device_tracker.my_car", "home", {"friendly_name": "My Car"})

    matched = await semantic_classifier.async_refresh_semantics(
        hass, mock_memgraph_client, entity_id="sensor.gas_meter"
    )

    assert matched == 1
    assert _classified_as_calls(mock_memgraph_client, "sensor.gas_meter") != []
    assert _classified_as_calls(mock_memgraph_client, "device_tracker.my_car") == []


async def test_refresh_semantics_without_entity_id_classifies_everything(
    hass, mock_memgraph_client
) -> None:
    """T042: `refresh_semantics(entity_id=None)` re-runs the full-graph pass."""
    er.async_get(hass).async_get_or_create(
        "sensor", "demo", "gas-meter-1", suggested_object_id="gas_meter"
    )
    er.async_get(hass).async_get_or_create(
        "device_tracker", "demo", "my-car-1", suggested_object_id="my_car"
    )
    hass.states.async_set("sensor.gas_meter", "42", {"device_class": "gas"})
    hass.states.async_set("device_tracker.my_car", "home", {"friendly_name": "My Car"})

    matched = await semantic_classifier.async_refresh_semantics(hass, mock_memgraph_client)

    assert matched == 2
    assert _classified_as_calls(mock_memgraph_client, "sensor.gas_meter") != []
    assert _classified_as_calls(mock_memgraph_client, "device_tracker.my_car") != []
