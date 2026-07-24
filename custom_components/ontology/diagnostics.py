"""Diagnostics support for the Ontology integration.

Per contracts/diagnostics.md: connection status, element counts, and schema
version are included; `password`/secrets are never included, not even
partially masked (FR-004, FR-018, SC-007).
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_DATABASE,
    CONF_ENCRYPTED,
    CONF_HOST,
    CONF_PORT,
    CONF_USERNAME,
    FINDING_STATUS_OPEN,
    LABEL_ENTITY,
    LABEL_SEMANTIC_TYPE,
    LABEL_VALIDATION_FINDING,
    REL_CLASSIFIED_AS,
)
from .memgraph_client import MemgraphClient


async def _async_classification_counts(client: MemgraphClient) -> dict[str, int]:
    """Return entity counts per semantic type (User Story 1, T012)."""
    query = (
        f"MATCH (:{LABEL_ENTITY})-[:{REL_CLASSIFIED_AS}]->(t:{LABEL_SEMANTIC_TYPE}) "
        "RETURN t.name AS semantic_type, count(*) AS entity_count"
    )
    records = await client.run_query(query)
    return {record["semantic_type"]: record["entity_count"] for record in records}


async def _async_validation_finding_counts(client: MemgraphClient) -> dict[str, dict[str, int]]:
    """Return open validation finding counts by category and severity (US5, T041)."""
    query = (
        f"MATCH (f:{LABEL_VALIDATION_FINDING} {{status: $open}}) "
        "RETURN f.category AS category, f.severity AS severity, count(*) AS finding_count"
    )
    records = await client.run_query(query, {"open": FINDING_STATUS_OPEN})
    counts: dict[str, dict[str, int]] = {}
    for record in records:
        category_counts = counts.setdefault(record["category"], {})
        category_counts[record["severity"]] = record["finding_count"]
    return counts


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: Any) -> dict[str, Any]:
    """Return a redacted diagnostics payload for the config entry."""
    coordinator = entry.runtime_data
    state = coordinator.state
    client = coordinator.memgraph_client

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
        "classification_counts": await _async_classification_counts(client),
        "validation_finding_counts": await _async_validation_finding_counts(client),
        "schema_version": state.schema_version,
        "health": state.health,
        "last_error": state.last_error,
        "consecutive_failures": state.consecutive_failures,
        "failed_updates": state.failed_updates,
    }
