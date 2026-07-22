"""Test: each `ontology.*` service handler dispatches to the correct
coordinator method across every currently-loaded config entry
(contracts/services.md)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import ServiceCall

from custom_components.ontology import (
    _async_handle_rebuild,
    _async_handle_resync,
    _async_handle_sync_entity,
    _async_handle_validate,
)
from custom_components.ontology.const import (
    ATTR_ENTITY_ID,
    DOMAIN,
    SERVICE_REBUILD,
    SERVICE_RESYNC,
    SERVICE_SYNC_ENTITY,
    SERVICE_VALIDATE,
)


async def test_rebuild_service_calls_async_rebuild_on_every_loaded_coordinator(hass) -> None:
    coordinator_1 = AsyncMock()
    coordinator_2 = AsyncMock()
    call = ServiceCall(hass, DOMAIN, SERVICE_REBUILD, {})

    with patch(
        "custom_components.ontology._loaded_coordinators",
        return_value=[coordinator_1, coordinator_2],
    ):
        await _async_handle_rebuild(call)

    coordinator_1.async_rebuild.assert_awaited_once()
    coordinator_2.async_rebuild.assert_awaited_once()


async def test_resync_service_calls_async_resync(hass) -> None:
    coordinator = AsyncMock()
    call = ServiceCall(hass, DOMAIN, SERVICE_RESYNC, {})

    with patch("custom_components.ontology._loaded_coordinators", return_value=[coordinator]):
        await _async_handle_resync(call)

    coordinator.async_resync.assert_awaited_once()


async def test_sync_entity_service_passes_entity_id(hass) -> None:
    coordinator = AsyncMock()
    call = ServiceCall(hass, DOMAIN, SERVICE_SYNC_ENTITY, {ATTR_ENTITY_ID: "light.kitchen"})

    with patch("custom_components.ontology._loaded_coordinators", return_value=[coordinator]):
        await _async_handle_sync_entity(call)

    coordinator.async_sync_entity.assert_awaited_once_with("light.kitchen")


async def test_validate_service_calls_async_validate(hass) -> None:
    coordinator = AsyncMock()
    call = ServiceCall(hass, DOMAIN, SERVICE_VALIDATE, {})

    with patch("custom_components.ontology._loaded_coordinators", return_value=[coordinator]):
        await _async_handle_validate(call)

    coordinator.async_validate.assert_awaited_once()


async def test_service_handler_is_noop_when_no_entries_loaded(hass) -> None:
    call = ServiceCall(hass, DOMAIN, SERVICE_REBUILD, {})

    with patch("custom_components.ontology._loaded_coordinators", return_value=[]):
        await _async_handle_rebuild(call)  # must not raise
