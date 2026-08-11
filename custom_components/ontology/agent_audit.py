"""Redacted Assist/MCP audit log (User Story 8, data-model.md §5).

Every Assist ontology-query invocation, MCP tool call, and rejected MCP
write/authentication attempt is appended here as a small redacted dict -
never the raw utterance, token, or credential value (FR-028, FR-029,
FR-030). Entries older than `AGENT_AUDIT_RETENTION_DAYS` are pruned on every
append and via the periodic sweep registered in `__init__.py` (FR-036).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    AGENT_AUDIT_RETENTION_DAYS,
    AGENT_AUDIT_STORE_KEY_PREFIX,
    AGENT_AUDIT_STORE_VERSION,
)


def now_iso() -> str:
    """Current UTC timestamp in ISO-8601 (data-model.md §5 `timestamp` field)."""
    return datetime.now(UTC).isoformat()


def _store(hass: HomeAssistant, entry_id: str) -> Store:
    # Not cached at module scope: `Store.__init__` performs no I/O, and a
    # module-level cache keyed only by `entry_id` would risk returning a
    # `Store` bound to a stale/closed `hass` instance if an `entry_id` is
    # ever reused across Home Assistant restarts within the same process
    # (e.g. tests, each with a fresh `hass` fixture).
    return Store(hass, AGENT_AUDIT_STORE_VERSION, f"{AGENT_AUDIT_STORE_KEY_PREFIX}{entry_id}")


def _is_expired(record: dict[str, Any], now: datetime) -> bool:
    timestamp = record.get("timestamp")
    if not timestamp:
        return False
    try:
        recorded_at = datetime.fromisoformat(timestamp)
    except ValueError:
        return False
    return (now - recorded_at) > timedelta(days=AGENT_AUDIT_RETENTION_DAYS)


async def async_append_record(hass: HomeAssistant, entry_id: str, record: dict[str, Any]) -> None:
    """Append one audit record, pruning any entry past the retention window (FR-036)."""
    store = _store(hass, entry_id)
    records: list[dict[str, Any]] = list(await store.async_load() or [])
    now = datetime.now(UTC)
    records = [r for r in records if not _is_expired(r, now)]
    records.append(record)
    await store.async_save(records)


async def async_prune_expired(hass: HomeAssistant, entry_id: str) -> None:
    """Periodic sweep: remove any record past the retention window (FR-036, research.md §4)."""
    store = _store(hass, entry_id)
    records: list[dict[str, Any]] = list(await store.async_load() or [])
    now = datetime.now(UTC)
    pruned = [r for r in records if not _is_expired(r, now)]
    if len(pruned) != len(records):
        await store.async_save(pruned)


async def async_get_records(hass: HomeAssistant, entry_id: str) -> list[dict[str, Any]]:
    """Return every non-expired audit record (used by diagnostics summaries only)."""
    store = _store(hass, entry_id)
    return list(await store.async_load() or [])


async def async_summarize(hass: HomeAssistant, entry_id: str) -> dict[str, dict[str, int]]:
    """Redacted diagnostics summary: counts by event/status, never raw entries."""
    records = await async_get_records(hass, entry_id)
    summary: dict[str, dict[str, int]] = {}
    for record in records:
        event = record.get("event", "unknown")
        status = record.get("status", "unknown")
        by_status = summary.setdefault(event, {})
        by_status[status] = by_status.get(status, 0) + 1
    return summary
