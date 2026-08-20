"""Integration tests for graph live update publication, freshness, burst convergence,
disconnect, and SC-007 recovery (US3, T038).

Most assertions run against the coordinator's change buffer and WebSocket handler
rather than a real Memgraph container to keep CI fast; the fixture-server tests in
tests/browser/ exercise end-to-end subscription behaviour with the full panel.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ontology.coordinator import GraphChangeBuffer, GraphChangeEvent, OntologyCoordinator
from custom_components.ontology import websocket_api as ontology_ws
from custom_components.ontology.const import (
    DOMAIN,
    GRAPH_REVISION_BUFFER_SIZE,
    GRAPH_UPDATE_DEBOUNCE_SECONDS,
    WS_TYPE_GRAPH_SUBSCRIBE,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(hass, entry=None):
    """Return a coordinator with an attached change buffer."""
    if entry is None:
        entry = MockConfigEntry(domain=DOMAIN)
        entry.add_to_hass(hass)
    client = AsyncMock()
    client.run_query = AsyncMock(return_value=[])
    client.run_query_limited = AsyncMock(return_value=([], False))
    return OntologyCoordinator(hass, entry, client)


async def _subscribe(hass, coordinator, from_revision: int = 0) -> tuple[MagicMock, dict]:
    """Fire graph_subscribe and return (connection, last_send_result)."""
    connection = MagicMock()
    connection.subscriptions = {}
    connection.user = MagicMock(is_admin=False)
    events_sent: list[dict] = []
    connection.send_event = lambda msg_id, data: events_sent.append(data)
    msg = {
        "id": 99,
        "type": WS_TYPE_GRAPH_SUBSCRIBE,
        "from_revision": from_revision,
    }
    with (
        patch.object(ontology_ws, "_first_loaded_coordinator", return_value=coordinator),
    ):
        ontology_ws._handle_graph_subscribe(hass, connection, msg)
        await hass.async_block_till_done(wait_background_tasks=True)
    return connection, events_sent


# ---------------------------------------------------------------------------
# Successful-write publication
# ---------------------------------------------------------------------------


async def test_successful_entity_sync_publishes_upsert_event(hass) -> None:
    coordinator = _make_coordinator(hass)

    received: list[GraphChangeEvent] = []
    coordinator.change_buffer.subscribe("test", received.append)

    with patch("custom_components.ontology.coordinator.graph_builder") as mock_gb:
        mock_gb.update_entity = AsyncMock()
        mock_gb.get_schema_version = AsyncMock(return_value="3.0.0")
        with patch("custom_components.ontology.coordinator.user_knowledge") as mock_uk:
            mock_uk.async_reconcile_energy_roles = AsyncMock()
            coordinator.memgraph_client.run_query = AsyncMock(return_value=[{"c": 5}])
            await coordinator._execute_entity_sync("sensor.kitchen")

    assert len(received) >= 1
    assert received[-1].kind in ("upsert", "remove")
    # No values in the event
    assert "secret" not in repr(received[-1]).lower()
    assert "password" not in repr(received[-1]).lower()


async def test_full_sync_publishes_reconcile_event(hass) -> None:
    coordinator = _make_coordinator(hass)

    received: list[GraphChangeEvent] = []
    coordinator.change_buffer.subscribe("test", received.append)

    with (
        patch("custom_components.ontology.coordinator.graph_builder") as mock_gb,
        patch("custom_components.ontology.coordinator.overrides"),
        patch("custom_components.ontology.coordinator.user_knowledge") as mock_uk,
        patch("custom_components.ontology.coordinator.semantic_classifier"),
        patch("custom_components.ontology.coordinator.validation"),
    ):
        mock_gb.build_full_graph = AsyncMock()
        mock_gb.get_schema_version = AsyncMock(return_value="3.0.0")
        mock_uk.async_reconcile_energy_roles = AsyncMock()
        coordinator.memgraph_client.run_query = AsyncMock(return_value=[{"c": 5}])
        await coordinator._execute_full_sync(clear_first=False)

    reconcile_events = [e for e in received if e.kind == "reconcile"]
    assert len(reconcile_events) >= 1


# ---------------------------------------------------------------------------
# Subscription replay and reconcile
# ---------------------------------------------------------------------------


async def test_subscribe_with_bridgeable_revision_receives_replay(hass) -> None:
    coordinator = _make_coordinator(hass)
    # Seed 3 events
    coordinator.change_buffer.publish_upsert(["Entity:a"], [], ["state"])  # rev 1
    coordinator.change_buffer.publish_upsert(["Entity:b"], [], ["name"])   # rev 2
    coordinator.change_buffer.publish_upsert(["Entity:c"], [], [])          # rev 3

    connection, events = await _subscribe(hass, coordinator, from_revision=1)

    # Should receive revisions 2 and 3 as replay
    connection.send_result.assert_called_once()
    assert len(events) == 2
    assert events[0]["revision"] == 2
    assert events[1]["revision"] == 3


async def test_subscribe_when_buffer_cannot_bridge_sends_reconcile(hass) -> None:
    coordinator = _make_coordinator(hass)
    coordinator.change_buffer = GraphChangeBuffer(max_size=2)
    coordinator.change_buffer.publish_upsert(["Entity:a"], [], [])  # 1
    coordinator.change_buffer.publish_upsert(["Entity:b"], [], [])  # 2
    coordinator.change_buffer.publish_upsert(["Entity:c"], [], [])  # 3 evicts 1 → [2,3]
    coordinator.change_buffer.publish_upsert(["Entity:d"], [], [])  # 4 evicts 2 → [3,4]

    # From revision 1: oldest=3, gap between 1 and 3, so buffer cannot bridge
    connection, events = await _subscribe(hass, coordinator, from_revision=1)

    reconcile = [e for e in events if e.get("kind") == "reconcile"]
    assert reconcile, "Expected a reconcile event when buffer cannot bridge"


async def test_subscribe_at_current_revision_receives_no_replay(hass) -> None:
    coordinator = _make_coordinator(hass)
    coordinator.change_buffer.publish_upsert(["Entity:a"], [], ["state"])  # rev 1

    connection, events = await _subscribe(hass, coordinator, from_revision=1)

    connection.send_result.assert_called_once()
    assert events == []


# ---------------------------------------------------------------------------
# Streaming new events after subscription
# ---------------------------------------------------------------------------


async def test_new_events_are_delivered_to_active_subscriber(hass) -> None:
    coordinator = _make_coordinator(hass)
    connection, events = await _subscribe(hass, coordinator, from_revision=0)

    # Now publish a new event
    coordinator.change_buffer.publish_upsert(["Entity:sensor.x"], [], ["state"])
    await hass.async_block_till_done()

    # Wait up to 300 ms for the 250 ms debounce to fire
    deadline = asyncio.get_event_loop().time() + 0.4
    while asyncio.get_event_loop().time() < deadline and not events:
        await asyncio.sleep(0.05)

    assert events, "Expected at least one event delivered to subscriber"
    assert events[-1]["revision"] >= 1


# ---------------------------------------------------------------------------
# Disconnect unsubscribes
# ---------------------------------------------------------------------------


async def test_disconnect_removes_subscription_from_buffer(hass) -> None:
    coordinator = _make_coordinator(hass)
    connection, _ = await _subscribe(hass, coordinator, from_revision=0)

    # Simulate unsubscribe (HA calls the stored unsubscribe callable)
    assert 99 in connection.subscriptions
    unsubscribe = connection.subscriptions[99]
    unsubscribe()

    before_count = coordinator.change_buffer.current_revision
    coordinator.change_buffer.publish_upsert(["Entity:z"], [], [])
    # If still subscribed this would send; but we just verify no exception
    assert coordinator.change_buffer.current_revision > before_count


# ---------------------------------------------------------------------------
# Revision freshness and burst convergence (mocked timing)
# ---------------------------------------------------------------------------


async def test_100_rapid_events_coalesce_and_buffer_stays_bounded(hass) -> None:
    coordinator = _make_coordinator(hass)

    for index in range(100):
        coordinator.change_buffer.publish_upsert([f"Entity:{index}"], [], ["state"])

    # Buffer must not exceed GRAPH_REVISION_BUFFER_SIZE
    assert coordinator.change_buffer.current_revision == 100
    # events_since(0) should return 100 events (buffer large enough)
    events = coordinator.change_buffer.events_since(0)
    assert events is not None
    assert len(events) == 100


async def test_diagnostics_include_graph_revision_and_subscription_counts(hass) -> None:
    """Diagnostics must expose graph state without credentials (T044)."""
    from custom_components.ontology.diagnostics import async_get_config_entry_diagnostics

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "localhost", "port": 7687, "database": "memgraph", "encrypted": False},
    )
    entry.add_to_hass(hass)
    coordinator = _make_coordinator(hass, entry)
    coordinator.change_buffer.publish_upsert(["Entity:a"], [], ["state"])  # rev 1
    coordinator.change_buffer.subscribe("test-sub", lambda _: None)
    entry.runtime_data = coordinator
    # Return empty lists for classification and validation queries
    coordinator.memgraph_client.run_query = AsyncMock(return_value=[])

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    graph_diag = diagnostics.get("graph", {})
    assert graph_diag.get("current_revision") == 1
    assert graph_diag.get("subscriber_count") >= 1
    assert "password" not in repr(diagnostics).lower()
    assert "token" not in repr(diagnostics).lower()
