"""Test: each diagnostic sensor (health/nodes/relationships/last_sync/
last_error/schema_version) reads its value directly from coordinator state
(contracts/diagnostics.md, User Story 6)."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology.const import DOMAIN
from custom_components.ontology.coordinator import OntologyCoordinator
from custom_components.ontology.sensor import SENSOR_DESCRIPTIONS, OntologySensor


def _build_sensors(hass, mock_memgraph_client):
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = OntologyCoordinator(hass, entry, mock_memgraph_client)
    sensors = {
        description.key: OntologySensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    }
    return coordinator, sensors


async def test_sensors_reflect_current_coordinator_state(hass, mock_memgraph_client) -> None:
    coordinator, sensors = _build_sensors(hass, mock_memgraph_client)

    coordinator.state.health = "ok"
    coordinator.state.node_count = 42
    coordinator.state.relationship_count = 17
    coordinator.state.last_sync = "2025-01-01T00:00:00+00:00"
    coordinator.state.last_error = None
    coordinator.state.schema_version = "1.0.0"

    assert sensors["health"].native_value == "ok"
    assert sensors["nodes"].native_value == 42
    assert sensors["relationships"].native_value == 17
    assert sensors["last_sync"].native_value == "2025-01-01T00:00:00+00:00"
    assert sensors["last_error"].native_value == "none"
    assert sensors["schema_version"].native_value == "1.0.0"


async def test_sensor_unique_ids_are_scoped_to_entry(hass, mock_memgraph_client) -> None:
    _coordinator, sensors = _build_sensors(hass, mock_memgraph_client)

    for key, sensor in sensors.items():
        assert sensor._attr_unique_id.endswith(f"_{key}")
