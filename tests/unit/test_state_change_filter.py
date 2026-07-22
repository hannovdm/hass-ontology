"""Test: `state_changed` events are filtered to primary state changes only —
attribute-only changes (same `.state`, different attributes) never trigger a
coordinator update (FR-012a)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event

from custom_components.ontology.event_listener import StateChangeDebouncer


async def test_attribute_only_change_is_ignored(hass) -> None:
    coordinator = AsyncMock()
    debouncer = StateChangeDebouncer(hass, coordinator)

    hass.states.async_set("sensor.battery_device", "on", {"battery_level": 80})
    await hass.async_block_till_done()
    old_state = hass.states.get("sensor.battery_device")

    hass.states.async_set("sensor.battery_device", "on", {"battery_level": 79})
    await hass.async_block_till_done()
    new_state = hass.states.get("sensor.battery_device")

    with patch("custom_components.ontology.event_listener.STATE_CHANGE_DEBOUNCE_SECONDS", 0.01):
        debouncer.async_handle_state_changed(
            Event(
                EVENT_STATE_CHANGED,
                {
                    "entity_id": "sensor.battery_device",
                    "old_state": old_state,
                    "new_state": new_state,
                },
            )
        )

    assert debouncer._timers == {}
    coordinator.async_handle_entity_change.assert_not_called()


async def test_missing_new_state_is_ignored(hass) -> None:
    coordinator = AsyncMock()
    debouncer = StateChangeDebouncer(hass, coordinator)

    debouncer.async_handle_state_changed(
        Event(
            EVENT_STATE_CHANGED,
            {"entity_id": "sensor.removed", "old_state": None, "new_state": None},
        )
    )

    assert debouncer._timers == {}
    coordinator.async_handle_entity_change.assert_not_called()


async def test_actual_state_change_is_not_ignored(hass) -> None:
    coordinator = AsyncMock()
    debouncer = StateChangeDebouncer(hass, coordinator)

    hass.states.async_set("sensor.actual_change", "on")
    await hass.async_block_till_done()
    old_state = hass.states.get("sensor.actual_change")

    hass.states.async_set("sensor.actual_change", "off")
    await hass.async_block_till_done()
    new_state = hass.states.get("sensor.actual_change")

    with patch("custom_components.ontology.event_listener.STATE_CHANGE_DEBOUNCE_SECONDS", 0.01):
        debouncer.async_handle_state_changed(
            Event(
                EVENT_STATE_CHANGED,
                {
                    "entity_id": "sensor.actual_change",
                    "old_state": old_state,
                    "new_state": new_state,
                },
            )
        )

    assert "sensor.actual_change" in debouncer._timers
    debouncer.async_cancel_all()
