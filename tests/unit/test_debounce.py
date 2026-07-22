"""Test: rapid successive `state_changed` events for the same entity collapse
into a single debounced coordinator update (research.md §5, FR-011)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event

from custom_components.ontology.event_listener import StateChangeDebouncer


async def test_rapid_state_changes_collapse_into_single_update(hass) -> None:
    coordinator = AsyncMock()
    debouncer = StateChangeDebouncer(hass, coordinator)

    hass.states.async_set("sensor.rapid", "1")
    await hass.async_block_till_done()
    state_1 = hass.states.get("sensor.rapid")

    hass.states.async_set("sensor.rapid", "2")
    await hass.async_block_till_done()
    state_2 = hass.states.get("sensor.rapid")

    hass.states.async_set("sensor.rapid", "3")
    await hass.async_block_till_done()
    state_3 = hass.states.get("sensor.rapid")

    with patch("custom_components.ontology.event_listener.STATE_CHANGE_DEBOUNCE_SECONDS", 0.05):
        debouncer.async_handle_state_changed(
            Event(
                EVENT_STATE_CHANGED,
                {"entity_id": "sensor.rapid", "old_state": None, "new_state": state_1},
            )
        )
        debouncer.async_handle_state_changed(
            Event(
                EVENT_STATE_CHANGED,
                {"entity_id": "sensor.rapid", "old_state": state_1, "new_state": state_2},
            )
        )
        debouncer.async_handle_state_changed(
            Event(
                EVENT_STATE_CHANGED,
                {"entity_id": "sensor.rapid", "old_state": state_2, "new_state": state_3},
            )
        )

        # Only one timer should be pending for this entity: earlier ones were
        # cancelled and replaced.
        assert len(debouncer._timers) == 1

        await asyncio.sleep(0.1)
        await hass.async_block_till_done()

    coordinator.async_handle_entity_change.assert_called_once_with("sensor.rapid")
