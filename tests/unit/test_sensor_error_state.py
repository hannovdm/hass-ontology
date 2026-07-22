"""Test: the `last_error` sensor never leaks a secret value that appeared in
the underlying exception text — it is redacted before being stored on
coordinator state (Constitution Principle II, FR-004, SC-007)."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology.const import DOMAIN
from custom_components.ontology.coordinator import OntologyCoordinator
from custom_components.ontology.redact import REDACTED
from custom_components.ontology.sensor import SENSOR_DESCRIPTIONS, OntologySensor


async def test_last_error_sensor_redacts_leaked_secret(hass, mock_memgraph_client) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = OntologyCoordinator(hass, entry, mock_memgraph_client)

    description = next(d for d in SENSOR_DESCRIPTIONS if d.key == "last_error")
    error_sensor = OntologySensor(coordinator, entry, description)

    coordinator._record_failure(RuntimeError("connect failed: password=hunter2"))

    value = error_sensor.native_value
    assert "hunter2" not in value
    assert REDACTED in value


async def test_health_sensor_reflects_error_state(hass, mock_memgraph_client) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = OntologyCoordinator(hass, entry, mock_memgraph_client)

    description = next(d for d in SENSOR_DESCRIPTIONS if d.key == "health")
    health_sensor = OntologySensor(coordinator, entry, description)

    coordinator._record_failure(RuntimeError("unreachable"))

    assert health_sensor.native_value == "error"
