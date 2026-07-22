"""Diagnostics support for the Ontology integration.

Per contracts/diagnostics.md: connection status, element counts, and schema
version are included; `password`/secrets are never included, not even
partially masked (FR-004, FR-018, SC-007).
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_DATABASE, CONF_ENCRYPTED, CONF_HOST, CONF_PORT, CONF_USERNAME


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: Any) -> dict[str, Any]:
    """Return a redacted diagnostics payload for the config entry."""
    coordinator = entry.runtime_data
    state = coordinator.state

    return {
        "connection": {
            "host": entry.data.get(CONF_HOST),
            "port": entry.data.get(CONF_PORT),
            "username_configured": bool(entry.data.get(CONF_USERNAME)),
            "database": entry.data.get(CONF_DATABASE),
            "encrypted": entry.data.get(CONF_ENCRYPTED),
            "reachable": state.health != "unavailable" and state.health != "error",
            "last_check": state.last_sync,
        },
        "counts": {
            "nodes": state.node_count,
            "relationships": state.relationship_count,
        },
        "schema_version": state.schema_version,
        "health": state.health,
        "last_error": state.last_error,
        "consecutive_failures": state.consecutive_failures,
        "failed_updates": state.failed_updates,
    }
