"""Transactional ontology schema migrations."""

from __future__ import annotations

from datetime import UTC, datetime

from neo4j import AsyncManagedTransaction

from .const import (
    LABEL_ENERGY_ROLE_ASSIGNMENT,
    LABEL_ONTOLOGY_SCHEMA,
    LABEL_SUPPLY_ASSOCIATION,
    SCHEMA_PREVIOUS_VERSION,
    SCHEMA_SINGLETON_ID,
    SCHEMA_VERSION,
)
from .memgraph_client import MemgraphClient


async def _migrate_supported_schema(transaction: AsyncManagedTransaction) -> str | None:
    result = await transaction.run(
        f"MATCH (s:{LABEL_ONTOLOGY_SCHEMA} {{ha_id: $schema_id}}) "
        "RETURN s.version AS version",
        {"schema_id": SCHEMA_SINGLETON_ID},
    )
    record = await result.single()
    if record is None:
        return None

    version = record["version"]
    if version != SCHEMA_PREVIOUS_VERSION:
        return version

    await transaction.run(
        f"MATCH (s:{LABEL_ONTOLOGY_SCHEMA} {{ha_id: $schema_id}}) "
        "WHERE s.version = $expected_version "
        "SET s.previous_version = $expected_version, "
        "s.migrated_at = $migrated_at, "
        "s.updated_at = $migrated_at, "
        "s.version = $target_version",
        {
            "schema_id": SCHEMA_SINGLETON_ID,
            "expected_version": SCHEMA_PREVIOUS_VERSION,
            "target_version": SCHEMA_VERSION,
            "migrated_at": datetime.now(UTC).isoformat(),
        },
    )
    return SCHEMA_VERSION


async def _ensure_v3_indexes(client: MemgraphClient) -> None:
    """Create v3 indexes idempotently using Memgraph-required autocommit DDL."""
    indexes = await client.run_query("SHOW INDEX INFO")
    existing = {
        (row.get("label"), tuple(row.get("property") or ()))
        for row in indexes
    }
    for label in (LABEL_SUPPLY_ASSOCIATION, LABEL_ENERGY_ROLE_ASSIGNMENT):
        if (label, ("ha_id",)) not in existing:
            await client.run_query(f"CREATE INDEX ON :{label}(ha_id)")


async def migrate_schema_if_supported(client: MemgraphClient) -> str | None:
    """Migrate the exact supported predecessor and return the resulting version."""
    rows = await client.run_query(
        f"MATCH (s:{LABEL_ONTOLOGY_SCHEMA} {{ha_id: $schema_id}}) "
        "RETURN s.version AS version",
        {"schema_id": SCHEMA_SINGLETON_ID},
    )
    version = rows[0].get("version") if rows else None
    if version not in (None, SCHEMA_PREVIOUS_VERSION, SCHEMA_VERSION):
        return version

    await _ensure_v3_indexes(client)
    if version != SCHEMA_PREVIOUS_VERSION:
        return version
    return await client.execute_write(_migrate_supported_schema)