"""Test: a failed incremental update is tracked (never silently dropped) and
can be retried later; repeated failures for the same target accumulate
attempts rather than duplicating entries (FR-020, T046a)."""

from __future__ import annotations

from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology.const import DOMAIN
from custom_components.ontology.coordinator import OntologyCoordinator


async def test_failed_entity_update_is_tracked(hass, mock_memgraph_client) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = OntologyCoordinator(hass, entry, mock_memgraph_client)

    with patch(
        "custom_components.ontology.coordinator.graph_builder.update_entity",
        side_effect=RuntimeError("boom"),
    ):
        await coordinator.async_handle_entity_change("sensor.flaky")

    assert len(coordinator.state.failed_updates) == 1
    item = coordinator.state.failed_updates[0]
    assert item["kind"] == "entity"
    assert item["id"] == "sensor.flaky"
    assert item["attempts"] == 1


async def test_repeated_failure_increments_attempts_without_duplicating(
    hass, mock_memgraph_client
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = OntologyCoordinator(hass, entry, mock_memgraph_client)

    with patch(
        "custom_components.ontology.coordinator.graph_builder.update_entity",
        side_effect=RuntimeError("boom"),
    ):
        await coordinator.async_handle_entity_change("sensor.flaky")
        await coordinator.async_handle_entity_change("sensor.flaky")

    assert len(coordinator.state.failed_updates) == 1
    assert coordinator.state.failed_updates[0]["attempts"] == 2


async def test_successful_retry_clears_failed_update(hass, mock_memgraph_client) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = OntologyCoordinator(hass, entry, mock_memgraph_client)

    with patch(
        "custom_components.ontology.coordinator.graph_builder.update_entity",
        side_effect=RuntimeError("boom"),
    ):
        await coordinator.async_handle_entity_change("sensor.flaky")

    assert len(coordinator.state.failed_updates) == 1

    with patch(
        "custom_components.ontology.coordinator.graph_builder.update_entity",
        return_value=None,
    ):
        await coordinator.async_retry_failed_updates()

    assert coordinator.state.failed_updates == []
