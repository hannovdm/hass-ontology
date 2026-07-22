"""Test: ≥3 consecutive sync failures fire the sustained-failure callback
(wired by `__init__.py` to `repairs.async_create_sustained_failure_issue`),
and a subsequent success fires the failure-cleared callback
(contracts/diagnostics.md, User Story 9)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology.const import DOMAIN, SUSTAINED_FAILURE_THRESHOLD
from custom_components.ontology.coordinator import OntologyCoordinator


async def test_sustained_failure_callback_fires_at_threshold(hass, mock_memgraph_client) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = OntologyCoordinator(hass, entry, mock_memgraph_client)
    coordinator.on_sustained_failure = MagicMock()
    coordinator.on_failure_cleared = MagicMock()

    with patch(
        "custom_components.ontology.coordinator.graph_builder.build_full_graph",
        side_effect=RuntimeError("unreachable"),
    ):
        for _ in range(SUSTAINED_FAILURE_THRESHOLD):
            try:
                await coordinator.async_rebuild()
            except RuntimeError:
                pass

    assert coordinator.state.consecutive_failures == SUSTAINED_FAILURE_THRESHOLD
    coordinator.on_sustained_failure.assert_called_once()
    coordinator.on_failure_cleared.assert_not_called()


async def test_failure_cleared_callback_fires_after_recovery(hass, mock_memgraph_client) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = OntologyCoordinator(hass, entry, mock_memgraph_client)
    coordinator.on_sustained_failure = MagicMock()
    coordinator.on_failure_cleared = MagicMock()

    with patch(
        "custom_components.ontology.coordinator.graph_builder.build_full_graph",
        side_effect=RuntimeError("unreachable"),
    ):
        for _ in range(SUSTAINED_FAILURE_THRESHOLD):
            try:
                await coordinator.async_rebuild()
            except RuntimeError:
                pass

    with patch(
        "custom_components.ontology.coordinator.graph_builder.build_full_graph",
        return_value={},
    ):
        await coordinator.async_rebuild()

    assert coordinator.state.consecutive_failures == 0
    coordinator.on_failure_cleared.assert_called_once()


async def test_below_threshold_failures_do_not_fire_callback(hass, mock_memgraph_client) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = OntologyCoordinator(hass, entry, mock_memgraph_client)
    coordinator.on_sustained_failure = MagicMock()

    with patch(
        "custom_components.ontology.coordinator.graph_builder.build_full_graph",
        side_effect=RuntimeError("unreachable"),
    ):
        for _ in range(SUSTAINED_FAILURE_THRESHOLD - 1):
            try:
                await coordinator.async_rebuild()
            except RuntimeError:
                pass

    coordinator.on_sustained_failure.assert_not_called()
