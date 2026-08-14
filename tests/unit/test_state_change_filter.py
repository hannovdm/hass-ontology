"""Tests for allow-listed state changes and retained debounce snapshots."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event

from custom_components.ontology.event_listener import StateChangeDebouncer


async def test_unrelated_attribute_only_change_is_ignored(hass) -> None:
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


async def test_measurement_attribute_only_change_is_accepted(hass) -> None:
    coordinator = AsyncMock()
    debouncer = StateChangeDebouncer(hass, coordinator)
    hass.states.async_set(
        "sensor.power", "10", {"device_class": "power", "unit_of_measurement": "W"}
    )
    await hass.async_block_till_done()
    old_state = hass.states.get("sensor.power")
    hass.states.async_set(
        "sensor.power", "10", {"device_class": "power", "unit_of_measurement": "kW"}
    )
    await hass.async_block_till_done()
    new_state = hass.states.get("sensor.power")

    with patch("custom_components.ontology.event_listener.STATE_CHANGE_DEBOUNCE_SECONDS", 0.01):
        debouncer.async_handle_state_changed(
            Event(
                EVENT_STATE_CHANGED,
                {
                    "entity_id": "sensor.power",
                    "old_state": old_state,
                    "new_state": new_state,
                },
            )
        )
        await asyncio.sleep(0.02)

    context = coordinator.async_handle_entity_change.call_args.args[1]
    assert context.state is new_state
    assert context.measurement_last_updated == new_state.last_updated


async def test_unrelated_churn_retains_accepted_snapshot_and_timer(hass) -> None:
    coordinator = AsyncMock()
    debouncer = StateChangeDebouncer(hass, coordinator)
    hass.states.async_set(
        "sensor.power", "10", {"device_class": "power", "unit_of_measurement": "W"}
    )
    await hass.async_block_till_done()
    old_state = hass.states.get("sensor.power")
    hass.states.async_set(
        "sensor.power", "11", {"device_class": "power", "unit_of_measurement": "W"}
    )
    await hass.async_block_till_done()
    accepted_state = hass.states.get("sensor.power")

    with patch("custom_components.ontology.event_listener.STATE_CHANGE_DEBOUNCE_SECONDS", 0.03):
        debouncer.async_handle_state_changed(
            Event(
                EVENT_STATE_CHANGED,
                {
                    "entity_id": "sensor.power",
                    "old_state": old_state,
                    "new_state": accepted_state,
                },
            )
        )
        retained_handle = debouncer._timers["sensor.power"]
        hass.states.async_set(
            "sensor.power",
            "11",
            {"device_class": "power", "unit_of_measurement": "W", "unrelated": "new"},
        )
        await hass.async_block_till_done()
        unrelated_state = hass.states.get("sensor.power")
        debouncer.async_handle_state_changed(
            Event(
                EVENT_STATE_CHANGED,
                {
                    "entity_id": "sensor.power",
                    "old_state": accepted_state,
                    "new_state": unrelated_state,
                },
            )
        )
        assert debouncer._timers["sensor.power"] is retained_handle
        await asyncio.sleep(0.04)

    context = coordinator.async_handle_entity_change.call_args.args[1]
    assert context.state is accepted_state


async def test_friendly_name_change_syncs_without_advancing_measurement_time(hass) -> None:
    coordinator = AsyncMock()
    debouncer = StateChangeDebouncer(hass, coordinator)
    hass.states.async_set(
        "sensor.power",
        "10",
        {
            "device_class": "power",
            "unit_of_measurement": "W",
            "friendly_name": "Old",
        },
    )
    await hass.async_block_till_done()
    old_state = hass.states.get("sensor.power")
    hass.states.async_set(
        "sensor.power",
        "10",
        {
            "device_class": "power",
            "unit_of_measurement": "W",
            "friendly_name": "New",
        },
    )
    await hass.async_block_till_done()
    new_state = hass.states.get("sensor.power")

    with patch("custom_components.ontology.event_listener.STATE_CHANGE_DEBOUNCE_SECONDS", 0.01):
        debouncer.async_handle_state_changed(
            Event(
                EVENT_STATE_CHANGED,
                {
                    "entity_id": "sensor.power",
                    "old_state": old_state,
                    "new_state": new_state,
                },
            )
        )
        await asyncio.sleep(0.02)

    context = coordinator.async_handle_entity_change.call_args.args[1]
    assert context.state is new_state
    assert context.measurement_last_updated == old_state.last_updated


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


async def test_coordinator_outage_does_not_block_listener(hass) -> None:
    release_coordinator = asyncio.Event()

    async def stalled_update(*_args: object) -> None:
        await release_coordinator.wait()

    coordinator = AsyncMock()
    coordinator.async_handle_entity_change.side_effect = stalled_update
    debouncer = StateChangeDebouncer(hass, coordinator)

    hass.states.async_set("sensor.power", "10")
    await hass.async_block_till_done()
    first_state = hass.states.get("sensor.power")
    hass.states.async_set("sensor.power", "11")
    await hass.async_block_till_done()
    second_state = hass.states.get("sensor.power")

    with patch(
        "custom_components.ontology.event_listener.STATE_CHANGE_DEBOUNCE_SECONDS", 0.01
    ):
        debouncer.async_handle_state_changed(
            Event(
                EVENT_STATE_CHANGED,
                {
                    "entity_id": "sensor.power",
                    "old_state": first_state,
                    "new_state": second_state,
                },
            )
        )
        await asyncio.sleep(0.02)
        assert coordinator.async_handle_entity_change.await_count == 1

        hass.states.async_set("sensor.other", "on")
        other_state = hass.states.get("sensor.other")
        debouncer.async_handle_state_changed(
            Event(
                EVENT_STATE_CHANGED,
                {
                    "entity_id": "sensor.other",
                    "old_state": None,
                    "new_state": other_state,
                },
            )
        )
        assert "sensor.other" in debouncer._timers

    release_coordinator.set()
    debouncer.async_cancel_all()
    await hass.async_block_till_done()
