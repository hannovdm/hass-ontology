"""Tests that accepted event snapshots reach graph writes unchanged."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.ontology.coordinator import OntologyCoordinator
from custom_components.ontology.graph_builder import EntitySyncContext


async def test_entity_change_serializes_accepted_state_context(hass, power_state_builder) -> None:
    client = AsyncMock()
    entry = MagicMock()
    entry.options = {}
    coordinator = OntologyCoordinator(hass, entry, client)
    state = power_state_builder(last_updated=datetime(2026, 1, 1, tzinfo=UTC))
    accepted_at = datetime(2025, 1, 1, tzinfo=UTC)
    context = EntitySyncContext(state=state, measurement_last_updated=accepted_at)

    with (
        patch(
            "custom_components.ontology.coordinator.graph_builder.update_entity",
            AsyncMock(),
        ) as update,
        patch(
            "custom_components.ontology.coordinator.user_knowledge.async_reconcile_energy_roles",
            AsyncMock(),
        ) as reconcile,
        patch.object(coordinator, "_refresh_counts", AsyncMock()),
    ):
        await coordinator.async_handle_entity_change(state.entity_id, context)

    update.assert_awaited_once_with(hass, client, state.entity_id, context)
    reconcile.assert_awaited_once_with(hass, client, state.entity_id)