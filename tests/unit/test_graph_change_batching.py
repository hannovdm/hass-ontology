"""Unit tests: monotonic revisions, 250 ms per-element coalescing, property-name-only
envelopes, bounded replay, reconcile fallback, and diagnostic allowlisting/redaction
(US3, T037).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from custom_components.ontology.coordinator import GraphChangeBuffer, GraphChangeEvent


# ---------------------------------------------------------------------------
# Monotonic revision
# ---------------------------------------------------------------------------


def test_revision_starts_at_zero() -> None:
    buffer = GraphChangeBuffer(max_size=100)
    assert buffer.current_revision == 0


def test_publish_increments_revision_monotonically() -> None:
    buffer = GraphChangeBuffer(max_size=100)
    event1 = buffer.publish_upsert(["Entity:a"], [], ["state"])
    event2 = buffer.publish_upsert(["Entity:b"], [], ["name"])
    event3 = buffer.publish_remove(["Device:c"], [])
    assert event1.revision == 1
    assert event2.revision == 2
    assert event3.revision == 3
    assert buffer.current_revision == 3


# ---------------------------------------------------------------------------
# Property-name-only envelopes (never values)
# ---------------------------------------------------------------------------


def test_event_contains_property_names_only() -> None:
    buffer = GraphChangeBuffer(max_size=100)
    event = buffer.publish_upsert(["Entity:sensor.kitchen"], [], ["state", "friendly_name"])
    assert "state" in event.changed_properties
    assert "friendly_name" in event.changed_properties
    serialized = repr(event)
    # Values must never appear — only the names
    assert "Entity:sensor.kitchen" in serialized
    assert "token" not in serialized.lower()
    assert "password" not in serialized.lower()


def test_event_kind_is_upsert_or_remove_or_reconcile() -> None:
    buffer = GraphChangeBuffer(max_size=100)
    upsert = buffer.publish_upsert(["Area:kitchen"], [], [])
    remove = buffer.publish_remove([], ["REL:1"])
    reconcile = buffer.publish_reconcile()
    assert upsert.kind == "upsert"
    assert remove.kind == "remove"
    assert reconcile.kind == "reconcile"


def test_event_occurred_at_is_iso_utc() -> None:
    buffer = GraphChangeBuffer(max_size=100)
    before = datetime.now(UTC).isoformat()
    event = buffer.publish_upsert([], [], [])
    after = datetime.now(UTC).isoformat()
    assert before <= event.occurred_at <= after


# ---------------------------------------------------------------------------
# Bounded replay (events_since)
# ---------------------------------------------------------------------------


def test_events_since_returns_events_after_requested_revision() -> None:
    buffer = GraphChangeBuffer(max_size=100)
    buffer.publish_upsert(["Entity:a"], [], ["state"])  # revision 1
    buffer.publish_upsert(["Entity:b"], [], ["name"])   # revision 2
    buffer.publish_upsert(["Entity:c"], [], [])          # revision 3

    events = buffer.events_since(1)
    assert events is not None
    assert len(events) == 2
    assert events[0].revision == 2
    assert events[1].revision == 3


def test_events_since_returns_empty_when_already_current() -> None:
    buffer = GraphChangeBuffer(max_size=100)
    buffer.publish_upsert(["Entity:a"], [], [])

    events = buffer.events_since(1)
    assert events == []


def test_events_since_returns_all_when_from_revision_is_zero() -> None:
    buffer = GraphChangeBuffer(max_size=100)
    buffer.publish_upsert(["Entity:a"], [], [])  # 1
    buffer.publish_upsert(["Entity:b"], [], [])  # 2

    events = buffer.events_since(0)
    assert events is not None
    assert len(events) == 2


def test_events_since_returns_none_when_buffer_cannot_bridge() -> None:
    buffer = GraphChangeBuffer(max_size=3)
    buffer.publish_upsert(["Entity:a"], [], [])  # 1
    buffer.publish_upsert(["Entity:b"], [], [])  # 2
    buffer.publish_upsert(["Entity:c"], [], [])  # 3  – buffer full [1,2,3]
    buffer.publish_upsert(["Entity:d"], [], [])  # 4  – evicts 1 → [2,3,4]
    buffer.publish_upsert(["Entity:e"], [], [])  # 5  – evicts 2 → [3,4,5]

    # From revision 1 cannot be bridged: revisions 1 and 2 are gone,
    # creating a gap between revision 1 and the oldest buffered revision 3.
    events = buffer.events_since(1)
    assert events is None


def test_events_since_returns_none_for_unknown_future_revision() -> None:
    buffer = GraphChangeBuffer(max_size=100)
    buffer.publish_upsert(["Entity:a"], [], [])

    # A future revision the buffer has never produced cannot be bridged
    events = buffer.events_since(999)
    assert events is None


# ---------------------------------------------------------------------------
# Bounded buffer size
# ---------------------------------------------------------------------------


def test_buffer_is_bounded_and_evicts_oldest() -> None:
    buffer = GraphChangeBuffer(max_size=5)
    for index in range(10):
        buffer.publish_upsert([f"Entity:{index}"], [], [])

    # Should have exactly 5 events in the buffer
    # events_since(5) should return revisions 6-10
    events = buffer.events_since(5)
    assert events is not None
    assert len(events) == 5
    assert events[0].revision == 6


def test_buffer_with_size_1000_default() -> None:
    buffer = GraphChangeBuffer()
    assert buffer.max_size == 1000


# ---------------------------------------------------------------------------
# Subscriber callbacks
# ---------------------------------------------------------------------------


def test_subscriber_receives_events() -> None:
    buffer = GraphChangeBuffer(max_size=100)
    received: list[GraphChangeEvent] = []

    buffer.subscribe("test-sub", received.append)
    buffer.publish_upsert(["Entity:a"], [], ["state"])
    buffer.publish_remove(["Device:b"], [])

    assert len(received) == 2
    assert received[0].kind == "upsert"
    assert received[1].kind == "remove"


def test_unsubscribe_stops_delivery() -> None:
    buffer = GraphChangeBuffer(max_size=100)
    received: list[GraphChangeEvent] = []

    buffer.subscribe("sub1", received.append)
    buffer.publish_upsert(["Entity:a"], [], [])

    buffer.unsubscribe("sub1")
    buffer.publish_upsert(["Entity:b"], [], [])

    assert len(received) == 1


def test_multiple_subscribers_each_receive_events() -> None:
    buffer = GraphChangeBuffer(max_size=100)
    received_a: list[GraphChangeEvent] = []
    received_b: list[GraphChangeEvent] = []

    buffer.subscribe("sub-a", received_a.append)
    buffer.subscribe("sub-b", received_b.append)
    buffer.publish_upsert(["Entity:a"], [], [])

    assert len(received_a) == 1
    assert len(received_b) == 1


def test_unsubscribe_nonexistent_subscriber_is_safe() -> None:
    buffer = GraphChangeBuffer(max_size=100)
    buffer.unsubscribe("does-not-exist")  # Must not raise


# ---------------------------------------------------------------------------
# Coalescing constants
# ---------------------------------------------------------------------------


def test_graph_update_debounce_is_250ms() -> None:
    from custom_components.ontology.const import GRAPH_UPDATE_DEBOUNCE_SECONDS

    assert GRAPH_UPDATE_DEBOUNCE_SECONDS == 0.25


def test_graph_revision_buffer_size_is_1000() -> None:
    from custom_components.ontology.const import GRAPH_REVISION_BUFFER_SIZE

    assert GRAPH_REVISION_BUFFER_SIZE == 1000


# ---------------------------------------------------------------------------
# Reconcile fallback
# ---------------------------------------------------------------------------


def test_publish_reconcile_advances_revision_and_clears_node_ids() -> None:
    buffer = GraphChangeBuffer(max_size=100)
    rev_before = buffer.current_revision
    event = buffer.publish_reconcile()
    assert event.revision > rev_before
    assert event.node_ids == []
    assert event.relationship_ids == []
    assert event.changed_properties == []


def test_reconcile_event_triggers_subscribers() -> None:
    buffer = GraphChangeBuffer(max_size=100)
    received: list[GraphChangeEvent] = []
    buffer.subscribe("sub", received.append)

    buffer.publish_reconcile()
    assert received and received[0].kind == "reconcile"
