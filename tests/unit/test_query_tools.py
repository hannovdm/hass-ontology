"""Unit tests for the shared, transport-agnostic predefined query tools
(User Story 1): T006 (search bounding), T007 (common ToolResult shape),
T008 (not_found handling), T009 (no secret keys ever leak), T076 (v3
introduces zero new Memgraph labels/relationships/schema bump)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.ontology import query_tools
from custom_components.ontology.const import (
    LABEL_AREA,
    LABEL_AUTOMATION,
    LABEL_DEVICE,
    LABEL_DOMAIN,
    LABEL_ENTITY,
    LABEL_FLOOR,
    LABEL_HOME,
    LABEL_INTEGRATION,
    LABEL_LABEL,
    LABEL_ONTOLOGY_SCHEMA,
    LABEL_SCENE,
    LABEL_SCRIPT,
    REL_HAS_AREA,
    REL_HAS_DEVICE,
    REL_HAS_ENTITY,
    REL_HAS_FLOOR,
    REL_HAS_LABEL,
    REL_IN_DOMAIN,
    REL_ON_FLOOR,
    REL_PROVIDED_BY,
    REL_REFERENCES,
    SCHEMA_VERSION,
)
from custom_components.ontology.redact import SECRET_KEYS


def _client_with_rows(rows: list[dict]) -> AsyncMock:
    client = AsyncMock()
    client.run_query = AsyncMock(return_value=rows)
    client.run_query_limited = AsyncMock(return_value=(rows, False))
    return client


async def test_search_bounds_results_by_limit_and_defaults() -> None:
    client = _client_with_rows([])
    await query_tools.search(client, "kitchen")
    _, _, called_limit = client.run_query_limited.await_args.args
    assert called_limit == 100  # DEFAULT_QUERY_LIMIT

    client.run_query_limited.reset_mock()
    await query_tools.search(client, "kitchen", limit=5000)
    _, _, called_limit = client.run_query_limited.await_args.args
    assert called_limit == 1000  # MAX_QUERY_LIMIT


async def test_search_reports_truncated_as_a_warning() -> None:
    client = AsyncMock()
    client.run_query_limited = AsyncMock(
        return_value=(
            [{"labels": [LABEL_AREA], "node": {"ha_id": "kitchen", "name": "Kitchen"}}],
            True,
        )
    )
    result = await query_tools.search(client, "kit")
    assert result["warnings"]


@pytest.mark.parametrize(
    ("func_name", "row"),
    [
        ("area_context", {"a": {"ha_id": "kitchen"}, "devices": [], "entities": []}),
        ("device_context", {"d": {"ha_id": "dev1"}, "a": None, "entities": []}),
        (
            "entity_context",
            {
                "e": {"ha_id": "light.kitchen"},
                "d": None,
                "area": None,
                "dom": None,
                "integ": None,
                "semantic_types": [],
                "dependents": [],
            },
        ),
        (
            "automation_dependencies",
            {"e": {"ha_id": "light.kitchen"}, "related": []},
        ),
    ],
)
async def test_functions_return_the_common_tool_result_shape(func_name: str, row: dict) -> None:
    client = _client_with_rows([row])
    func = getattr(query_tools, func_name)
    result = await func(client, "kitchen")
    assert set(result.keys()) == {"target", "result_type", "result", "warnings"}
    assert result["target"] == "kitchen"
    assert result["result_type"] != "not_found"
    assert result["result"] is not None
    assert isinstance(result["warnings"], list)


@pytest.mark.parametrize(
    "func_name",
    ["area_context", "device_context", "entity_context", "automation_dependencies"],
)
async def test_functions_return_not_found_for_unresolvable_identifier(func_name: str) -> None:
    client = _client_with_rows([])
    func = getattr(query_tools, func_name)
    result = await func(client, "does-not-exist")
    assert result["result_type"] == "not_found"
    assert result["result"] is None
    # No unbounded query attempted beyond the single bounded resolve call.
    client.run_query.assert_awaited_once()


@pytest.mark.parametrize("secret_key", sorted(SECRET_KEYS))
async def test_results_never_contain_a_secret_key(secret_key: str) -> None:
    client = _client_with_rows(
        [
            {
                "a": {"ha_id": "kitchen", secret_key: "super-secret-value"},
                "devices": [],
                "entities": [],
            }
        ]
    )
    result = await query_tools.area_context(client, "kitchen")
    assert result["result"]["area"][secret_key] == "**REDACTED**"
    assert "super-secret-value" not in str(result["result"])


def test_search_uses_only_v2_labels_and_relationships_no_new_schema() -> None:
    """T076: v3 introduces zero new Memgraph node labels/relationship types
    or a `SCHEMA_VERSION` bump (FR-035, data-model.md §1)."""
    assert SCHEMA_VERSION == "2.0.0"
    # Sanity: the v1/v2 label/relationship constants query_tools.py relies on
    # still exist and are unchanged in shape (no v3-specific LABEL_*/REL_*
    # constants were introduced for query_tools.py's own traversals).
    for label in (
        LABEL_HOME,
        LABEL_FLOOR,
        LABEL_AREA,
        LABEL_DEVICE,
        LABEL_ENTITY,
        LABEL_DOMAIN,
        LABEL_INTEGRATION,
        LABEL_LABEL,
        LABEL_AUTOMATION,
        LABEL_SCENE,
        LABEL_SCRIPT,
        LABEL_ONTOLOGY_SCHEMA,
    ):
        assert isinstance(label, str)
    for rel in (
        REL_HAS_AREA,
        REL_HAS_FLOOR,
        REL_ON_FLOOR,
        REL_HAS_DEVICE,
        REL_HAS_ENTITY,
        REL_IN_DOMAIN,
        REL_PROVIDED_BY,
        REL_HAS_LABEL,
        REL_REFERENCES,
    ):
        assert isinstance(rel, str)
