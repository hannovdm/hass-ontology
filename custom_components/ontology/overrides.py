"""User-managed semantic override CRUD and export/import (User Story 4, 7).

Overrides are ``source = SOURCE_USER`` relationships of type
``REL_OVERRIDE_OF`` linking an Entity/Device/Area to a semantic-type-family
node. They are never created, modified, or deleted by classification,
refresh, rebuild, or resync (FR-006, FR-025).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .const import (
    LABEL_AREA,
    LABEL_DEVICE,
    LABEL_ENTITY,
    LABEL_SEMANTIC_TYPE,
    OVERRIDES_EXPORT_VERSION,
    REL_OVERRIDE_OF,
    SOURCE_USER,
)
from .graph_builder import merge_node, merge_relationship
from .memgraph_client import MemgraphClient

_ALLOWED_SOURCE_LABELS = (LABEL_ENTITY, LABEL_DEVICE, LABEL_AREA)


class OverrideImportRejected(Exception):
    """Raised when an overrides import payload fails validation (fail-closed).

    No entries are written when this is raised - the whole payload is
    validated before any write is attempted (research.md §7).
    """


def _sanitize_label(label: str) -> str:
    """Validate a dynamic node label against the fixed allow-list.

    Guards against Cypher injection via a dynamically interpolated label -
    labels cannot be parameterized in Cypher, so only known-safe constants
    from `_ALLOWED_SOURCE_LABELS` may ever reach a query string.
    """
    if label not in _ALLOWED_SOURCE_LABELS:
        raise ValueError(f"Unsupported override source label: {label!r}")
    return label


async def async_create_override(
    client: MemgraphClient, source_label: str, source_ha_id: str, type_label: str
) -> None:
    """Create (or idempotently re-affirm) a user override (FR-006).

    `source_label` must be one of Entity/Device/Area. Reuses the existing
    `merge_node`/`merge_relationship` graph_builder primitives so the
    override relationship is written with the exact same MERGE semantics
    (and the same `source` bookkeeping) as every other relationship in the
    graph, rather than duplicating raw Cypher here.
    """
    _sanitize_label(source_label)
    await merge_node(
        client, LABEL_SEMANTIC_TYPE, type_label, {"name": type_label}, source=SOURCE_USER
    )
    await merge_relationship(
        client,
        source_label,
        source_ha_id,
        REL_OVERRIDE_OF,
        LABEL_SEMANTIC_TYPE,
        type_label,
        source=SOURCE_USER,
    )


async def async_delete_override(
    client: MemgraphClient, source_label: str, source_ha_id: str, type_label: str
) -> None:
    """Delete a single user override relationship (FR-006)."""
    label = _sanitize_label(source_label)
    query = (
        f"MATCH (s:{label} {{ha_id: $source_ha_id}})"
        f"-[r:{REL_OVERRIDE_OF}]->(t:{LABEL_SEMANTIC_TYPE} {{ha_id: $type_label}}) "
        "DELETE r"
    )
    await client.run_query(query, {"source_ha_id": source_ha_id, "type_label": type_label})


async def async_list_overrides(client: MemgraphClient) -> list[dict[str, Any]]:
    """Return every `source = "user"` override relationship."""
    query = (
        f"MATCH (s)-[r:{REL_OVERRIDE_OF} {{source: $source}}]->(t:{LABEL_SEMANTIC_TYPE}) "
        "RETURN labels(s) AS source_labels, s.ha_id AS source_ha_id, t.ha_id AS type_label"
    )
    rows = await client.run_query(query, {"source": SOURCE_USER})
    overrides: list[dict[str, Any]] = []
    for row in rows:
        source_labels = [
            label for label in row["source_labels"] if label in _ALLOWED_SOURCE_LABELS
        ]
        if not source_labels:
            continue
        overrides.append(
            {
                "relationship_type": REL_OVERRIDE_OF,
                "source_label": source_labels[0],
                "source_ha_id": row["source_ha_id"],
                "type_label": row["type_label"],
            }
        )
    return overrides


async def async_export_overrides(client: MemgraphClient) -> dict[str, Any]:
    """Export every user override as a versioned, importable payload (FR-024)."""
    return {
        "version": OVERRIDES_EXPORT_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "overrides": await async_list_overrides(client),
    }


def _validate_entry(entry: Any, index: int) -> tuple[str, str, str]:
    if not isinstance(entry, dict):
        raise OverrideImportRejected(f"Entry {index}: not an object")
    source_label = entry.get("source_label")
    source_ha_id = entry.get("source_ha_id")
    type_label = entry.get("type_label")
    if source_label not in _ALLOWED_SOURCE_LABELS:
        raise OverrideImportRejected(f"Entry {index}: invalid source_label {source_label!r}")
    if not isinstance(source_ha_id, str) or not source_ha_id:
        raise OverrideImportRejected(f"Entry {index}: invalid source_ha_id")
    if not isinstance(type_label, str) or not type_label:
        raise OverrideImportRejected(f"Entry {index}: invalid type_label")
    return source_label, source_ha_id, type_label


async def async_import_overrides(client: MemgraphClient, payload: Any) -> int:
    """Validate then import a previously exported overrides payload (FR-024).

    Fail-closed: every entry is validated before any entry is written. A
    single malformed entry rejects the entire payload with no partial
    writes (research.md §7). Import is idempotent (MERGE-based), so
    re-importing the same payload multiple times is safe.
    """
    if not isinstance(payload, dict):
        raise OverrideImportRejected("Payload is not an object")
    if payload.get("version") != OVERRIDES_EXPORT_VERSION:
        raise OverrideImportRejected(
            f"Unsupported overrides export version: {payload.get('version')!r}"
        )
    entries = payload.get("overrides")
    if not isinstance(entries, list):
        raise OverrideImportRejected("Payload 'overrides' must be a list")

    validated = [_validate_entry(entry, index) for index, entry in enumerate(entries)]

    for source_label, source_ha_id, type_label in validated:
        await async_create_override(client, source_label, source_ha_id, type_label)
    return len(validated)
