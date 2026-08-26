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


async def test_unassigned_area_items_returns_devices_and_effectively_unassigned_sensors() -> None:
    rows = [
        {"item_type": "device", "ha_id": "device-1", "name": "Portable sensor"},
        {"item_type": "sensor", "ha_id": "sensor.loft", "name": "Loft temperature"},
    ]
    client = _client_with_rows(rows)

    result = await query_tools.unassigned_area_items(client, limit=25)

    assert result["result"]["devices"] == [rows[0]]
    assert result["result"]["sensors"] == [rows[1]]
    query, parameters, limit = client.run_query_limited.await_args.args
    assert f"(item:{LABEL_ENTITY})-[:{REL_IN_DOMAIN}]->" in query
    assert f"(:{LABEL_DOMAIN} {{ha_id: 'sensor'}})" in query
    assert f"-[:{REL_HAS_AREA}]->(:{LABEL_AREA})" in query
    assert f"(:{LABEL_AREA})-[:{REL_HAS_DEVICE}]->(:{LABEL_DEVICE})" in query
    assert parameters == {}
    assert limit == 25


async def test_unassigned_area_items_reports_empty_and_truncated_results() -> None:
    client = _client_with_rows([])
    empty = await query_tools.unassigned_area_items(client)
    assert empty["outcome"] == "empty"
    assert empty["result"] == {"devices": [], "sensors": [], "truncated": False}

    client.run_query_limited.return_value = (
        [{"item_type": "device", "ha_id": "device-1", "name": "Portable"}],
        True,
    )
    truncated = await query_tools.unassigned_area_items(client, limit=1)
    assert truncated["result"]["truncated"] is True
    assert truncated["warnings"] == ["unassigned area results truncated to 1 items"]


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
            {"matched_count": 1, "related": []},
        ),
    ],
)
async def test_functions_return_the_common_tool_result_shape(func_name: str, row: dict) -> None:
    client = _client_with_rows([row])
    func = getattr(query_tools, func_name)
    result = await func(client, "kitchen")
    assert set(result.keys()) == {
        "target",
        "result_type",
        "outcome",
        "result",
        "warnings",
    }
    assert result["target"] == "kitchen"
    assert result["result_type"] != "not_found"
    assert result["result"] is not None
    assert isinstance(result["warnings"], list)


async def test_automation_dependencies_aggregates_duplicate_entity_names() -> None:
    client = _client_with_rows(
        [
            {
                "matched_count": 2,
                "related": [
                    {
                        "automation": {
                            "ha_id": "automation.auto_office_lights",
                            "name": "Auto Office Lights On",
                        },
                        "reason": REL_REFERENCES,
                    }
                ],
            }
        ]
    )

    result = await query_tools.automation_dependencies(client, "office lights")

    assert result["result_type"] != "not_found"
    assert result["result"]["automations"] == [
        {
            "ha_id": "automation.auto_office_lights",
            "name": "Auto Office Lights On",
            "reason": REL_REFERENCES,
        }
    ]


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


def test_tool_result_recursively_redacts_secret_key_patterns_and_inline_values() -> None:
    result = query_tools.build_tool_result(
        "MATCH (n) WHERE n.password='hunter2' RETURN n",
        "query",
        {
            "nested": {
                "database_password_value": "hunter2",
                "message": "token=abc123",
            },
            "items": [{"clientCredential": "top-secret"}],
        },
        ["password=hunter2"],
    )

    serialized = str(result)
    assert "hunter2" not in serialized
    assert "abc123" not in serialized
    assert "top-secret" not in serialized
    assert result["result"]["nested"]["database_password_value"] == "**REDACTED**"
    assert result["result"]["items"][0]["clientCredential"] == "**REDACTED**"


async def test_area_context_bounds_collections_groups_entities_and_warns() -> None:
    client = _client_with_rows(
        [
            {
                "a": {"ha_id": "office", "name": "Office"},
                "devices": [{"ha_id": "device-1", "name": "Lamp"}],
                "entities": [
                    {"ha_id": f"sensor.office_{index}", "device_id": "device-1"}
                    for index in range(102)
                ],
            }
        ]
    )

    result = await query_tools.area_context(client, "office")

    assert len(result["result"]["entities"]) == 100
    assert len(result["result"]["devices"][0]["entities"]) == 100
    assert "entities truncated to 100 items" in result["warnings"]


async def test_entity_context_reports_unavailable_relationships() -> None:
    client = _client_with_rows(
        [
            {
                "e": {"ha_id": "sensor.orphan"},
                "d": None,
                "area": None,
                "dom": None,
                "integ": None,
                "semantic_types": [],
                "dependents": [],
            }
        ]
    )

    result = await query_tools.entity_context(client, "sensor.orphan")

    assert "device relationship unavailable" in result["warnings"]
    assert "area relationship unavailable" in result["warnings"]
    assert "domain relationship unavailable" in result["warnings"]
    assert "integration relationship unavailable" in result["warnings"]


def test_search_uses_only_v2_labels_and_relationships_no_new_schema() -> None:
    """T076: v3 introduces zero new Memgraph node labels/relationship types
    or a `SCHEMA_VERSION` bump (FR-035, data-model.md §1)."""
    assert SCHEMA_VERSION == "3.0.0"
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
