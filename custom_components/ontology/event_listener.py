"""Registry and state_changed event listeners for the Ontology integration.

Registry changes (area/device/entity add/remove/update) are forwarded to the
coordinator immediately. `state_changed` events are filtered to primary
state changes only (FR-012a) and debounced per-entity (research.md §5,
FR-011) before being forwarded, so rapid successive changes collapse into a
single sync.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import STATE_CHANGE_DEBOUNCE_SECONDS
from .coordinator import OntologyCoordinator
from .graph_builder import EntitySyncContext

_LOGGER = logging.getLogger(__name__)


class StateChangeDebouncer:
    """Collapses rapid `state_changed` events for the same entity into a
    single coordinator update within a debounce window (research.md §5)."""

    def __init__(self, hass: HomeAssistant, coordinator: OntologyCoordinator) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self._contexts: dict[str, EntitySyncContext] = {}

    @callback
    def async_handle_state_changed(self, event: Event) -> None:
        """Retain accepted state/attribute changes and ignore unrelated churn."""
        entity_id = event.data.get("entity_id")
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if entity_id is None or new_state is None:
            return
        measurement_last_updated = new_state.last_updated
        if old_state is not None and old_state.state == new_state.state:
            changed_attributes = {
                key
                for key in ("friendly_name", "device_class", "unit_of_measurement")
                if old_state.attributes.get(key) != new_state.attributes.get(key)
            }
            if not changed_attributes:
                return
            if changed_attributes == {"friendly_name"}:
                measurement_last_updated = old_state.last_updated

        existing = self._timers.pop(entity_id, None)
        if existing is not None:
            existing.cancel()

        self._contexts[entity_id] = EntitySyncContext(
            state=new_state,
            measurement_last_updated=measurement_last_updated,
        )
        handle = self._hass.loop.call_later(
            STATE_CHANGE_DEBOUNCE_SECONDS, self._fire, entity_id
        )
        self._timers[entity_id] = handle

    def _fire(self, entity_id: str) -> None:
        self._timers.pop(entity_id, None)
        context = self._contexts.pop(entity_id)
        self._hass.async_create_task(
            self._coordinator.async_handle_entity_change(entity_id, context)
        )

    def async_cancel_all(self) -> None:
        """Cancel all pending debounce timers (called on unload)."""
        for handle in self._timers.values():
            handle.cancel()
        self._timers.clear()
        self._contexts.clear()


def async_register_listeners(
    hass: HomeAssistant, coordinator: OntologyCoordinator
) -> Callable[[], None]:
    """Register all registry/state listeners; returns an unsubscribe callable."""
    debouncer = StateChangeDebouncer(hass, coordinator)

    @callback
    def _on_area_registry_updated(event: Event) -> None:
        if hass.state is not CoreState.running:
            return
        area_id = event.data.get("area_id")
        if area_id:
            hass.async_create_task(coordinator.async_handle_area_change(area_id))

    @callback
    def _on_device_registry_updated(event: Event) -> None:
        if hass.state is not CoreState.running:
            return
        device_id = event.data.get("device_id")
        if device_id:
            hass.async_create_task(coordinator.async_handle_device_change(device_id))

    @callback
    def _on_entity_registry_updated(event: Event) -> None:
        if hass.state is not CoreState.running:
            return
        entity_id = event.data.get("entity_id")
        if entity_id:
            hass.async_create_task(coordinator.async_handle_entity_change(entity_id))

    @callback
    def _on_state_changed(event: Event) -> None:
        if hass.state is CoreState.running:
            debouncer.async_handle_state_changed(event)

    unsub_area = hass.bus.async_listen(ar.EVENT_AREA_REGISTRY_UPDATED, _on_area_registry_updated)
    unsub_device = hass.bus.async_listen(
        dr.EVENT_DEVICE_REGISTRY_UPDATED, _on_device_registry_updated
    )
    unsub_entity = hass.bus.async_listen(
        er.EVENT_ENTITY_REGISTRY_UPDATED, _on_entity_registry_updated
    )
    unsub_state = hass.bus.async_listen(EVENT_STATE_CHANGED, _on_state_changed)

    def _unsubscribe() -> None:
        unsub_area()
        unsub_device()
        unsub_entity()
        unsub_state()
        debouncer.async_cancel_all()

    return _unsubscribe
