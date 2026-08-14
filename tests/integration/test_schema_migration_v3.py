"""Integration tests for the v2-to-v3 managed schema migration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from custom_components.ontology.const import (
    SCHEMA_PREVIOUS_VERSION,
    SCHEMA_VERSION,
)
from custom_components.ontology.memgraph_client import MemgraphClient
from custom_components.ontology.schema_migrations import migrate_schema_if_supported


async def test_fresh_schema_is_a_noop(memgraph_client: MemgraphClient) -> None:
    assert await migrate_schema_if_supported(memgraph_client) is None
    rows = await memgraph_client.run_query("MATCH (s:OntologySchema) RETURN count(s) AS count")
    assert rows == [{"count": 0}]


async def test_current_schema_is_a_noop(
    memgraph_client: MemgraphClient,
    seed_schema_version: Callable[[MemgraphClient, str], Awaitable[None]],
    query_schema_marker: Callable[[MemgraphClient], Awaitable[dict[str, Any]]],
) -> None:
    await seed_schema_version(memgraph_client, SCHEMA_VERSION)

    assert await migrate_schema_if_supported(memgraph_client) == SCHEMA_VERSION
    assert await query_schema_marker(memgraph_client) == {
        "ha_id": "home_assistant_ontology",
        "version": SCHEMA_VERSION,
    }


async def test_unsupported_schema_is_not_modified(
    memgraph_client: MemgraphClient,
    seed_schema_version: Callable[[MemgraphClient, str], Awaitable[None]],
    query_schema_marker: Callable[[MemgraphClient], Awaitable[dict[str, Any]]],
) -> None:
    await seed_schema_version(memgraph_client, "1.9.0")

    assert await migrate_schema_if_supported(memgraph_client) == "1.9.0"
    assert (await query_schema_marker(memgraph_client))["version"] == "1.9.0"


async def test_failed_managed_migration_rolls_back_all_writes(
    memgraph_client: MemgraphClient,
    seed_schema_version: Callable[[MemgraphClient, str], Awaitable[None]],
    query_schema_marker: Callable[[MemgraphClient], Awaitable[dict[str, Any]]],
) -> None:
    await seed_schema_version(memgraph_client, SCHEMA_PREVIOUS_VERSION)

    async def fail_after_additive_write(transaction) -> None:
        await transaction.run("CREATE (:MigrationProbe {ha_id: 'must-roll-back'})")
        raise RuntimeError("injected migration failure")

    with pytest.raises(RuntimeError, match="injected migration failure"):
        await memgraph_client.execute_write(fail_after_additive_write)

    rows = await memgraph_client.run_query(
        "MATCH (n:MigrationProbe {ha_id: 'must-roll-back'}) RETURN count(n) AS count"
    )
    assert rows == [{"count": 0}]
    assert (await query_schema_marker(memgraph_client))["version"] == SCHEMA_PREVIOUS_VERSION


async def test_exact_predecessor_migrates_idempotently_without_touching_user_data(
    memgraph_client: MemgraphClient,
    seed_schema_version: Callable[[MemgraphClient, str], Awaitable[None]],
    query_schema_marker: Callable[[MemgraphClient], Awaitable[dict[str, Any]]],
    query_user_owned_nodes: Callable[
        [MemgraphClient], Awaitable[list[dict[str, Any]]]
    ],
) -> None:
    await seed_schema_version(memgraph_client, SCHEMA_PREVIOUS_VERSION)
    await memgraph_client.run_query(
        "CREATE (:UserKnowledge {ha_id: 'keep-me', source: 'user', value: 42})"
    )

    assert await migrate_schema_if_supported(memgraph_client) == SCHEMA_VERSION
    first_marker = await query_schema_marker(memgraph_client)
    assert await migrate_schema_if_supported(memgraph_client) == SCHEMA_VERSION

    second_marker = await query_schema_marker(memgraph_client)
    assert first_marker == second_marker
    assert second_marker["version"] == SCHEMA_VERSION
    assert second_marker["previous_version"] == SCHEMA_PREVIOUS_VERSION
    assert second_marker["migrated_at"] == second_marker["updated_at"]
    assert await query_user_owned_nodes(memgraph_client) == [
        {"ha_id": "keep-me", "value": 42}
    ]
    indexes = await memgraph_client.run_query("SHOW INDEX INFO")
    indexed_labels = {
        row.get("label")
        for row in indexes
        if row.get("property") == ["ha_id"]
    }
    assert {"SupplyAssociation", "EnergyRoleAssignment"} <= indexed_labels