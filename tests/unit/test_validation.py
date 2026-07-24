"""Unit tests for `validation.py`'s 9 finding categories (T035, User Story 5,
FR-051-FR-056). Uses `mock_memgraph_client` and the `hass` fixture - no real
Memgraph server."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.helpers import entity_registry as er

from custom_components.ontology import validation
from custom_components.ontology.const import (
    FINDING_DUPLICATE_ENTITY,
    FINDING_INVALID_RELATIONSHIP,
    FINDING_MISSING_AREA,
    FINDING_MISSING_DEVICE,
    FINDING_MISSING_SEMANTIC_CLASSIFICATION,
    FINDING_ORPHAN_DEVICE,
    FINDING_ORPHAN_ENTITY,
    FINDING_SCHEMA_MISMATCH,
    FINDING_STATUS_OPEN,
    FINDING_STATUS_RESOLVED,
    FINDING_UNAVAILABLE_CRITICAL_ENTITY,
    LABEL_DEVICE,
    LABEL_ENTITY,
    LABEL_VALIDATION_FINDING,
    SCHEMA_VERSION,
    SEVERITY_ERROR,
)

# ---------------------------------------------------------------------------
# Per-category detection
# ---------------------------------------------------------------------------


async def test_detect_missing_area_returns_devices_without_area(mock_memgraph_client) -> None:
    mock_memgraph_client.run_query.return_value = [{"ha_id": "device-1"}]

    result = await validation._detect_missing_area(mock_memgraph_client)

    assert result == [("device-1", LABEL_DEVICE)]


async def test_detect_missing_device_returns_entities_without_device(
    mock_memgraph_client,
) -> None:
    mock_memgraph_client.run_query.return_value = [{"ha_id": "sensor.helper"}]

    result = await validation._detect_missing_device(mock_memgraph_client)

    assert result == [("sensor.helper", LABEL_ENTITY)]


async def test_detect_orphan_entity_returns_entities_with_no_relationships(
    mock_memgraph_client,
) -> None:
    mock_memgraph_client.run_query.return_value = [{"ha_id": "sensor.orphan"}]

    result = await validation._detect_orphan_entity(mock_memgraph_client)

    assert result == [("sensor.orphan", LABEL_ENTITY)]


async def test_detect_orphan_device_returns_devices_with_no_entities(
    mock_memgraph_client,
) -> None:
    mock_memgraph_client.run_query.return_value = [{"ha_id": "device-orphan"}]

    result = await validation._detect_orphan_device(mock_memgraph_client)

    assert result == [("device-orphan", LABEL_DEVICE)]


async def test_detect_duplicate_entity_returns_all_ids_sharing_a_name(
    mock_memgraph_client,
) -> None:
    mock_memgraph_client.run_query.return_value = [
        {"ha_id": "sensor.dup_1"},
        {"ha_id": "sensor.dup_2"},
    ]

    result = await validation._detect_duplicate_entity(mock_memgraph_client)

    assert result == [("sensor.dup_1", LABEL_ENTITY), ("sensor.dup_2", LABEL_ENTITY)]


async def test_detect_unavailable_critical_entity_only_flags_unavailable_state(
    hass, mock_memgraph_client
) -> None:
    mock_memgraph_client.run_query.return_value = [
        {"ha_id": "sensor.gas"},
        {"ha_id": "sensor.energy"},
    ]
    hass.states.async_set("sensor.gas", "unavailable")
    hass.states.async_set("sensor.energy", "42")

    result = await validation._detect_unavailable_critical_entity(hass, mock_memgraph_client)

    assert result == [("sensor.gas", LABEL_ENTITY)]


async def test_detect_unavailable_critical_entity_skips_entities_with_no_state(
    hass, mock_memgraph_client
) -> None:
    """An entity the graph knows about but HA no longer has a state for
    (e.g. removed) is skipped rather than raising."""
    mock_memgraph_client.run_query.return_value = [{"ha_id": "sensor.gone"}]

    result = await validation._detect_unavailable_critical_entity(hass, mock_memgraph_client)

    assert result == []


async def test_detect_invalid_relationship_returns_flagged_ids(mock_memgraph_client) -> None:
    mock_memgraph_client.run_query.return_value = [{"ha_id": "sensor.bad_write"}]

    result = await validation._detect_invalid_relationship(mock_memgraph_client)

    assert result == [("sensor.bad_write", LABEL_ENTITY)]


async def test_detect_schema_mismatch_flags_when_version_differs(mock_memgraph_client) -> None:
    with patch.object(validation, "get_schema_version", return_value="0.0.1-old"):
        result = await validation._detect_schema_mismatch(mock_memgraph_client)

    assert len(result) == 1
    assert result[0][0] == validation.SCHEMA_SINGLETON_ID


async def test_detect_schema_mismatch_is_empty_when_version_matches(
    mock_memgraph_client,
) -> None:
    with patch.object(validation, "get_schema_version", return_value=SCHEMA_VERSION):
        result = await validation._detect_schema_mismatch(mock_memgraph_client)

    assert result == []


async def test_detect_schema_mismatch_is_empty_when_graph_has_no_schema_node(
    mock_memgraph_client,
) -> None:
    """No recorded schema version yet (brand-new graph) is not itself a
    mismatch."""
    with patch.object(validation, "get_schema_version", return_value=None):
        result = await validation._detect_schema_mismatch(mock_memgraph_client)

    assert result == []


async def test_detect_missing_semantic_classification_flags_matching_unclassified_entity(
    hass, mock_memgraph_client
) -> None:
    mock_memgraph_client.run_query.return_value = []
    er.async_get(hass).async_get_or_create(
        "sensor", "demo", "gas-1", suggested_object_id="gas_meter"
    )

    with patch.object(validation.semantic_classifier, "matching_rules", return_value=["rule"]):
        result = await validation._detect_missing_semantic_classification(
            hass, mock_memgraph_client
        )

    assert result == [("sensor.gas_meter", LABEL_ENTITY)]


async def test_detect_missing_semantic_classification_skips_already_classified(
    hass, mock_memgraph_client
) -> None:
    er.async_get(hass).async_get_or_create(
        "sensor", "demo", "gas-1", suggested_object_id="gas_meter"
    )
    mock_memgraph_client.run_query.return_value = [{"ha_id": "sensor.gas_meter"}]

    with patch.object(validation.semantic_classifier, "matching_rules", return_value=["rule"]):
        result = await validation._detect_missing_semantic_classification(
            hass, mock_memgraph_client
        )

    assert result == []


async def test_detect_missing_semantic_classification_skips_no_matching_rule(
    hass, mock_memgraph_client
) -> None:
    er.async_get(hass).async_get_or_create(
        "sensor", "demo", "misc-1", suggested_object_id="misc"
    )
    mock_memgraph_client.run_query.return_value = []

    with patch.object(validation.semantic_classifier, "matching_rules", return_value=[]):
        result = await validation._detect_missing_semantic_classification(
            hass, mock_memgraph_client
        )

    assert result == []


# ---------------------------------------------------------------------------
# Reconciliation and full-run orchestration
# ---------------------------------------------------------------------------


async def test_merge_finding_writes_expected_category_and_severity(
    mock_memgraph_client,
) -> None:
    finding_id = await validation._merge_finding(
        mock_memgraph_client, FINDING_MISSING_AREA, "device-1", LABEL_DEVICE, SEVERITY_ERROR
    )

    assert finding_id == "missing_area::device-1"
    query, params = mock_memgraph_client.run_query.call_args.args
    assert f"MERGE (f:{LABEL_VALIDATION_FINDING}" in query
    assert params["category"] == FINDING_MISSING_AREA
    assert params["severity"] == SEVERITY_ERROR
    assert params["status"] == FINDING_STATUS_OPEN


async def test_reconcile_category_resolves_findings_no_longer_detected(
    mock_memgraph_client,
) -> None:
    count = await validation._reconcile_category(
        mock_memgraph_client, FINDING_ORPHAN_ENTITY, [], SEVERITY_ERROR
    )

    assert count == 0
    queries = [call.args[0] for call in mock_memgraph_client.run_query.call_args_list]
    assert any(FINDING_STATUS_RESOLVED in q for q in queries)
    assert any("DETACH DELETE f" in q for q in queries)


async def test_reconcile_category_tolerates_merge_failure_for_missing_target(
    mock_memgraph_client,
) -> None:
    """A detected finding whose target node no longer exists (race with a
    concurrent delete) is skipped rather than failing the whole run."""

    async def run_query_side_effect(query, params=None):
        if f"MERGE (f:{LABEL_VALIDATION_FINDING}" in query:
            raise RuntimeError("target not found")
        return []

    mock_memgraph_client.run_query.side_effect = run_query_side_effect

    count = await validation._reconcile_category(
        mock_memgraph_client,
        FINDING_ORPHAN_DEVICE,
        [("device-1", LABEL_DEVICE)],
        SEVERITY_ERROR,
    )

    assert count == 0


async def test_async_run_validation_returns_counts_for_all_nine_categories(
    hass, mock_memgraph_client
) -> None:
    with (
        patch.object(validation, "_detect_missing_area", return_value=[("d1", LABEL_DEVICE)]),
        patch.object(validation, "_detect_missing_device", return_value=[]),
        patch.object(validation, "_detect_orphan_entity", return_value=[]),
        patch.object(validation, "_detect_orphan_device", return_value=[]),
        patch.object(validation, "_detect_duplicate_entity", return_value=[]),
        patch.object(validation, "_detect_unavailable_critical_entity", return_value=[]),
        patch.object(validation, "_detect_invalid_relationship", return_value=[]),
        patch.object(validation, "_detect_schema_mismatch", return_value=[]),
        patch.object(validation, "_detect_missing_semantic_classification", return_value=[]),
    ):
        counts = await validation.async_run_validation(hass, mock_memgraph_client)

    assert set(counts) == {
        FINDING_MISSING_AREA,
        FINDING_MISSING_DEVICE,
        FINDING_ORPHAN_ENTITY,
        FINDING_ORPHAN_DEVICE,
        FINDING_DUPLICATE_ENTITY,
        FINDING_UNAVAILABLE_CRITICAL_ENTITY,
        FINDING_INVALID_RELATIONSHIP,
        FINDING_SCHEMA_MISMATCH,
        FINDING_MISSING_SEMANTIC_CLASSIFICATION,
    }
    assert counts[FINDING_MISSING_AREA] == 1
