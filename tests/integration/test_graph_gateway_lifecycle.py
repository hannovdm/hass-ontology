"""Lifecycle checks for config-entry-scoped graph gateways."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.ontology.graph_gateway import async_attach_graph_gateway
from custom_components.ontology import async_unload_entry


@pytest.mark.asyncio
async def test_gateway_attaches_to_coordinator_and_closes_cleanly() -> None:
    entry = MagicMock()
    entry.data = {}
    entry.options = {}
    coordinator = MagicMock()
    coordinator.memgraph_client = AsyncMock()
    gateway = await async_attach_graph_gateway(entry, coordinator, session=AsyncMock())

    assert coordinator.graph_gateway is gateway
    gateway.backend.close = AsyncMock(return_value=None)
    await gateway.close()
    gateway.backend.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_gateway_unavailability_is_non_fatal_to_coordinator() -> None:
    coordinator = MagicMock()
    coordinator.async_resync = AsyncMock(return_value=None)
    coordinator.memgraph_client = AsyncMock()
    entry = MagicMock(data={}, options={})
    entry.async_on_unload = MagicMock()
    gateway = await async_attach_graph_gateway(entry, coordinator, session=AsyncMock())
    gateway.backend.initial_graph = AsyncMock(side_effect=ConnectionError("offline"))

    result = await gateway.initial_graph()
    await coordinator.async_resync()

    assert result["error"] == "gateway_unavailable"
    coordinator.async_resync.assert_awaited_once()


@pytest.mark.asyncio
async def test_integration_unload_closes_gateway_and_memgraph_client() -> None:
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    coordinator = MagicMock()
    coordinator.graph_gateway.close = AsyncMock(return_value=None)
    coordinator.memgraph_client.close = AsyncMock(return_value=None)
    entry = MagicMock()
    entry.runtime_data = coordinator

    assert await async_unload_entry(hass, entry) is True
    coordinator.graph_gateway.close.assert_awaited_once()
    coordinator.memgraph_client.close.assert_awaited_once()
