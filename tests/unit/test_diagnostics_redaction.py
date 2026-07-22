"""Test: diagnostics payload never includes plaintext credentials — only a
`username_configured` boolean, never the password (contracts/diagnostics.md,
Constitution Principle II, FR-004)."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology.const import DOMAIN
from custom_components.ontology.coordinator import OntologyCoordinator
from custom_components.ontology.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics_excludes_password_and_username(hass, mock_memgraph_client) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "localhost",
            "port": 7687,
            "username": "neo4j",
            "password": "super-secret-value",
            "database": "memgraph",
            "encrypted": False,
        },
    )
    entry.add_to_hass(hass)
    coordinator = OntologyCoordinator(hass, entry, mock_memgraph_client)
    entry.runtime_data = coordinator

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    serialized = repr(diagnostics)
    assert "super-secret-value" not in serialized
    assert "neo4j" not in serialized
    assert diagnostics["connection"]["username_configured"] is True
    assert diagnostics["connection"]["host"] == "localhost"
    assert diagnostics["connection"]["database"] == "memgraph"


async def test_diagnostics_includes_health_and_counts(hass, mock_memgraph_client) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = OntologyCoordinator(hass, entry, mock_memgraph_client)
    coordinator.state.node_count = 5
    coordinator.state.relationship_count = 3
    coordinator.state.schema_version = "1.0.0"
    entry.runtime_data = coordinator

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["counts"] == {"nodes": 5, "relationships": 3}
    assert diagnostics["schema_version"] == "1.0.0"
