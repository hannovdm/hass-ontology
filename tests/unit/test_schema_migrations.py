"""Unit tests for the exact-predecessor ontology schema migration."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.ontology.const import (
    SCHEMA_PREVIOUS_VERSION,
    SCHEMA_SINGLETON_ID,
    SCHEMA_VERSION,
)
from custom_components.ontology.schema_migrations import migrate_schema_if_supported


class _Transaction:
    def __init__(self, version: str | None) -> None:
        self.version = version
        self.queries: list[tuple[str, dict[str, object]]] = []

    async def run(self, query: str, parameters: dict[str, object] | None = None):
        self.queries.append((query, parameters or {}))
        if "RETURN s.version AS version" in query:
            return _Result(self.version)
        if "target_version" in (parameters or {}):
            self.version = str((parameters or {})["target_version"])
        return _Result(None)


class _Result:
    def __init__(self, version: str | None) -> None:
        self._version = version

    async def single(self):
        return None if self._version is None else {"version": self._version}


@pytest.mark.parametrize("version", [None, SCHEMA_VERSION])
async def test_migration_is_noop_for_empty_or_current_schema(version: str | None) -> None:
    client = AsyncMock()
    version_rows = [] if version is None else [{"version": version}]
    client.run_query.side_effect = [version_rows, [], [], []]

    assert await migrate_schema_if_supported(client) == version
    client.execute_write.assert_not_awaited()


async def test_migration_advances_only_exact_predecessor_in_one_transaction() -> None:
    transaction = _Transaction(SCHEMA_PREVIOUS_VERSION)
    client = AsyncMock()

    async def execute_write(work):
        return await work(transaction)

    client.run_query.side_effect = [
        [{"version": SCHEMA_PREVIOUS_VERSION}],
        [],
        [],
        [],
    ]
    client.execute_write.side_effect = execute_write

    assert await migrate_schema_if_supported(client) == SCHEMA_VERSION
    assert transaction.version == SCHEMA_VERSION
    assert client.run_query.await_args_list[2].args[0] == (
        "CREATE INDEX ON :SupplyAssociation(ha_id)"
    )
    assert client.run_query.await_args_list[3].args[0] == (
        "CREATE INDEX ON :EnergyRoleAssignment(ha_id)"
    )
    assert transaction.queries[-1][1] == {
        "schema_id": SCHEMA_SINGLETON_ID,
        "expected_version": SCHEMA_PREVIOUS_VERSION,
        "target_version": SCHEMA_VERSION,
        "migrated_at": transaction.queries[-1][1]["migrated_at"],
    }
    assert transaction.queries[-1][0].rstrip().endswith("s.version = $target_version")


async def test_migration_leaves_unsupported_predecessor_for_mismatch_repair() -> None:
    client = AsyncMock()
    client.run_query.return_value = [{"version": "1.9.0"}]

    assert await migrate_schema_if_supported(client) == "1.9.0"
    client.execute_write.assert_not_awaited()
    client.run_query.assert_awaited_once()


async def test_migration_callback_failure_propagates_for_rollback() -> None:
    client = AsyncMock()
    client.run_query.side_effect = [
        [{"version": SCHEMA_PREVIOUS_VERSION}],
        [],
        [],
        [],
    ]
    client.execute_write.side_effect = RuntimeError("migration failed")

    with pytest.raises(RuntimeError, match="migration failed"):
        await migrate_schema_if_supported(client)