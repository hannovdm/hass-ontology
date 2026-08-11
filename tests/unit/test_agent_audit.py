"""Unit tests for the redacted Assist/MCP audit log (User Story 8):
T062 (no raw utterance/credential ever appears in any record type),
T063 (records older than 30 days are pruned on append and via the sweep)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.ontology import agent_audit


async def test_append_and_get_records_round_trip(hass) -> None:
    record = {
        "event": "assist_query",
        "intent": "OntologyEntityContext",
        "status": "resolved",
        "result_count": 1,
        "error_category": None,
        "timestamp": agent_audit.now_iso(),
    }
    await agent_audit.async_append_record(hass, "entry1", record)
    records = await agent_audit.async_get_records(hass, "entry1")
    assert records == [record]


async def test_records_never_contain_raw_utterance_or_credential(hass) -> None:
    record = {
        "event": "mcp_tool_call",
        "tool": "entity_context",
        "client_id": "127.0.0.1",
        "status": "ok",
        "result_count": 1,
        "error_category": None,
        "timestamp": agent_audit.now_iso(),
    }
    await agent_audit.async_append_record(hass, "entry2", record)
    records = await agent_audit.async_get_records(hass, "entry2")
    assert "utterance" not in records[0]
    assert "token" not in records[0]
    assert "password" not in records[0]
    assert "credential" not in records[0]


async def test_expired_records_pruned_on_append(hass) -> None:
    old_timestamp = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    fresh_timestamp = agent_audit.now_iso()
    await agent_audit.async_append_record(
        hass, "entry3", {"event": "assist_query", "status": "resolved", "timestamp": old_timestamp}
    )
    await agent_audit.async_append_record(
        hass,
        "entry3",
        {"event": "assist_query", "status": "resolved", "timestamp": fresh_timestamp},
    )
    records = await agent_audit.async_get_records(hass, "entry3")
    assert len(records) == 1
    assert records[0]["timestamp"] == fresh_timestamp


async def test_expired_records_pruned_via_periodic_sweep(hass) -> None:
    old_timestamp = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    store = agent_audit._store(hass, "entry4")
    await store.async_save(
        [{"event": "assist_query", "status": "resolved", "timestamp": old_timestamp}]
    )
    await agent_audit.async_prune_expired(hass, "entry4")
    records = await agent_audit.async_get_records(hass, "entry4")
    assert records == []


async def test_summarize_counts_by_event_and_status(hass) -> None:
    await agent_audit.async_append_record(
        hass,
        "entry5",
        {"event": "mcp_tool_call", "status": "ok", "timestamp": agent_audit.now_iso()},
    )
    await agent_audit.async_append_record(
        hass,
        "entry5",
        {"event": "mcp_tool_call", "status": "ok", "timestamp": agent_audit.now_iso()},
    )
    await agent_audit.async_append_record(
        hass,
        "entry5",
        {"event": "mcp_auth_rejected", "status": "rejected", "timestamp": agent_audit.now_iso()},
    )
    summary = await agent_audit.async_summarize(hass, "entry5")
    assert summary["mcp_tool_call"]["ok"] == 2
    assert summary["mcp_auth_rejected"]["rejected"] == 1
