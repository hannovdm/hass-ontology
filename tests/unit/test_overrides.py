"""Unit tests for `overrides.py` CRUD (T031) and export/import (T046, T047).

User Story 4 (manual semantic overrides) and User Story 7 (override
export/import). Uses `mock_memgraph_client` - no real Memgraph server."""

from __future__ import annotations

import pytest

from custom_components.ontology import overrides
from custom_components.ontology.const import (
    LABEL_AREA,
    LABEL_DEVICE,
    LABEL_ENTITY,
    LABEL_SEMANTIC_TYPE,
    OVERRIDES_EXPORT_VERSION,
    REL_OVERRIDE_OF,
    SOURCE_USER,
)

# ---------------------------------------------------------------------------
# T031: create / list / delete
# ---------------------------------------------------------------------------


async def test_create_override_merges_type_node_and_relationship(mock_memgraph_client) -> None:
    await overrides.async_create_override(
        mock_memgraph_client, LABEL_ENTITY, "light.lamp", "EnergyAsset"
    )

    queries = [call.args[0] for call in mock_memgraph_client.run_query_with_retry.call_args_list]
    assert any(f"MERGE (n:{LABEL_SEMANTIC_TYPE}" in q for q in queries)
    assert any(REL_OVERRIDE_OF in q and LABEL_ENTITY in q for q in queries)


async def test_create_override_rejects_unsupported_source_label(mock_memgraph_client) -> None:
    with pytest.raises(ValueError, match="Unsupported override source label"):
        await overrides.async_create_override(
            mock_memgraph_client, "SemanticType", "x", "EnergyAsset"
        )
    mock_memgraph_client.run_query_with_retry.assert_not_awaited()


async def test_delete_override_issues_delete_query_scoped_to_pair(mock_memgraph_client) -> None:
    await overrides.async_delete_override(
        mock_memgraph_client, LABEL_DEVICE, "device-1", "GasCylinder"
    )

    mock_memgraph_client.run_query.assert_awaited_once()
    query, params = mock_memgraph_client.run_query.call_args.args
    assert "DELETE r" in query
    assert LABEL_DEVICE in query
    assert params == {"source_ha_id": "device-1", "type_label": "GasCylinder"}


async def test_delete_override_rejects_unsupported_source_label(mock_memgraph_client) -> None:
    with pytest.raises(ValueError, match="Unsupported override source label"):
        await overrides.async_delete_override(mock_memgraph_client, "Bogus", "x", "GasCylinder")
    mock_memgraph_client.run_query.assert_not_awaited()


async def test_list_overrides_returns_relationship_type_and_source_label(
    mock_memgraph_client,
) -> None:
    mock_memgraph_client.run_query.return_value = [
        {
            "source_labels": [LABEL_ENTITY],
            "source_ha_id": "light.lamp",
            "type_label": "EnergyAsset",
        },
        {
            "source_labels": [LABEL_AREA],
            "source_ha_id": "living_room",
            "type_label": "SecurityDevice",
        },
    ]

    result = await overrides.async_list_overrides(mock_memgraph_client)

    assert result == [
        {
            "relationship_type": REL_OVERRIDE_OF,
            "source_label": LABEL_ENTITY,
            "source_ha_id": "light.lamp",
            "type_label": "EnergyAsset",
        },
        {
            "relationship_type": REL_OVERRIDE_OF,
            "source_label": LABEL_AREA,
            "source_ha_id": "living_room",
            "type_label": "SecurityDevice",
        },
    ]
    query, params = mock_memgraph_client.run_query.call_args.args
    assert params == {"source": SOURCE_USER}


async def test_list_overrides_ignores_rows_with_no_allowed_source_label(
    mock_memgraph_client,
) -> None:
    """Defensive: a row whose only label isn't Entity/Device/Area is skipped
    rather than surfaced with an incorrect `source_label`."""
    mock_memgraph_client.run_query.return_value = [
        {"source_labels": ["SemanticType"], "source_ha_id": "x", "type_label": "EnergyAsset"}
    ]

    result = await overrides.async_list_overrides(mock_memgraph_client)

    assert result == []


# ---------------------------------------------------------------------------
# T046: export
# ---------------------------------------------------------------------------


async def test_export_overrides_payload_shape_and_version(mock_memgraph_client) -> None:
    mock_memgraph_client.run_query.return_value = [
        {
            "source_labels": [LABEL_ENTITY],
            "source_ha_id": "light.lamp",
            "type_label": "EnergyAsset",
        }
    ]

    payload = await overrides.async_export_overrides(mock_memgraph_client)

    assert payload["version"] == OVERRIDES_EXPORT_VERSION
    assert "exported_at" in payload
    assert payload["overrides"] == [
        {
            "relationship_type": REL_OVERRIDE_OF,
            "source_label": LABEL_ENTITY,
            "source_ha_id": "light.lamp",
            "type_label": "EnergyAsset",
        }
    ]


async def test_export_overrides_only_includes_user_source_relationships(
    mock_memgraph_client,
) -> None:
    """The export query itself is scoped to `source = "user"` - other-source
    (e.g. Home-Assistant-derived classification) relationships are never
    fetched, so they can never leak into an export payload."""
    await overrides.async_export_overrides(mock_memgraph_client)

    query, params = mock_memgraph_client.run_query.call_args.args
    assert params == {"source": SOURCE_USER}
    assert "{source: $source}" in query


async def test_export_overrides_contains_no_credential_fields(mock_memgraph_client) -> None:
    mock_memgraph_client.run_query.return_value = [
        {
            "source_labels": [LABEL_ENTITY],
            "source_ha_id": "light.lamp",
            "type_label": "EnergyAsset",
        }
    ]

    payload = await overrides.async_export_overrides(mock_memgraph_client)

    for entry in payload["overrides"]:
        assert set(entry.keys()) == {
            "relationship_type",
            "source_label",
            "source_ha_id",
            "type_label",
        }


# ---------------------------------------------------------------------------
# T047: import
# ---------------------------------------------------------------------------


def _payload(*entries: dict) -> dict:
    return {"version": OVERRIDES_EXPORT_VERSION, "overrides": list(entries)}


async def test_import_overrides_creates_each_valid_entry(mock_memgraph_client) -> None:
    payload = _payload(
        {"source_label": LABEL_ENTITY, "source_ha_id": "light.lamp", "type_label": "EnergyAsset"},
        {"source_label": LABEL_DEVICE, "source_ha_id": "device-1", "type_label": "GasCylinder"},
    )

    count = await overrides.async_import_overrides(mock_memgraph_client, payload)

    assert count == 2
    assert mock_memgraph_client.run_query_with_retry.await_count == 4  # 2 entries * 2 merges


async def test_import_overrides_rejects_unsupported_version(mock_memgraph_client) -> None:
    payload = {"version": "not-a-real-version", "overrides": []}

    with pytest.raises(overrides.OverrideImportRejected, match="version"):
        await overrides.async_import_overrides(mock_memgraph_client, payload)
    mock_memgraph_client.run_query_with_retry.assert_not_awaited()


async def test_import_overrides_rejects_missing_version() -> None:
    payload = {"overrides": []}

    with pytest.raises(overrides.OverrideImportRejected):
        await overrides.async_import_overrides(None, payload)  # type: ignore[arg-type]


async def test_import_overrides_is_fail_closed_on_a_single_invalid_entry(
    mock_memgraph_client,
) -> None:
    """A malformed entry rejects the WHOLE payload - zero partial writes,
    even though the payload also contains an otherwise well-formed entry
    (research.md §7; the actual, deliberate fail-closed behavior of
    `async_import_overrides`, not per-entry rejection)."""
    payload = _payload(
        {"source_label": LABEL_ENTITY, "source_ha_id": "light.lamp", "type_label": "EnergyAsset"},
        {"source_label": "NotAllowed", "source_ha_id": "x", "type_label": "GasCylinder"},
    )

    with pytest.raises(overrides.OverrideImportRejected):
        await overrides.async_import_overrides(mock_memgraph_client, payload)

    mock_memgraph_client.run_query_with_retry.assert_not_awaited()


async def test_import_overrides_rejects_non_list_overrides_field(mock_memgraph_client) -> None:
    payload = {"version": OVERRIDES_EXPORT_VERSION, "overrides": "not-a-list"}

    with pytest.raises(overrides.OverrideImportRejected):
        await overrides.async_import_overrides(mock_memgraph_client, payload)


async def test_import_overrides_is_idempotent_on_repeated_import(mock_memgraph_client) -> None:
    """Re-importing the same payload twice succeeds both times (MERGE-based)."""
    payload = _payload(
        {"source_label": LABEL_ENTITY, "source_ha_id": "light.lamp", "type_label": "EnergyAsset"}
    )

    first = await overrides.async_import_overrides(mock_memgraph_client, payload)
    second = await overrides.async_import_overrides(mock_memgraph_client, payload)

    assert first == 1
    assert second == 1
