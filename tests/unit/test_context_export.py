"""Unit tests for allow-list context export (User Story 6): T041 (only
allow-listed fields survive projection), T042 (a secret-looking property
is never present, even if it exists on the underlying node)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from custom_components.ontology import context_export
from custom_components.ontology.const import (
    CONTEXT_EXPORT_ALLOWED_FIELDS,
    LABEL_AREA,
    LABEL_AUTOMATION,
    LABEL_DASHBOARD,
    LABEL_DASHBOARD_CARD,
    LABEL_DEVICE,
    LABEL_ENTITY,
    LABEL_DOMAIN,
    LABEL_INTEGRATION,
    LABEL_SCENE,
    LABEL_SCRIPT,
    LABEL_SEMANTIC_TYPE,
    LABEL_VALIDATION_FINDING,
)


@pytest.mark.parametrize(
    "label",
    [
        LABEL_AREA,
        LABEL_DEVICE,
        LABEL_ENTITY,
        LABEL_DOMAIN,
        LABEL_INTEGRATION,
        LABEL_AUTOMATION,
        LABEL_SCENE,
        LABEL_SCRIPT,
        LABEL_VALIDATION_FINDING,
        LABEL_DASHBOARD,
        LABEL_DASHBOARD_CARD,
    ],
)
def test_projection_includes_only_allow_listed_fields(label: str) -> None:
    allowed = CONTEXT_EXPORT_ALLOWED_FIELDS[label]
    node = {field: f"value-{field}" for field in allowed}
    node["extra_unlisted_field"] = "should never appear"
    projected = context_export.project(node, label)
    assert set(projected.keys()) == set(allowed)
    assert "extra_unlisted_field" not in projected


@pytest.mark.parametrize(
    "sensitive_field",
    ["token", "access_token", "password", "api_key", "secret", "credential", "mcp_token"],
)
def test_projection_never_includes_a_sensitive_field_even_if_present(sensitive_field: str) -> None:
    node = {"ha_id": "kitchen", "name": "Kitchen", "floor_id": "ground", sensitive_field: "leak-me"}
    projected = context_export.project(node, LABEL_AREA)
    assert sensitive_field not in projected
    assert "leak-me" not in str(projected)


def test_semantic_asset_instance_node_projected_via_semantic_type_allow_list() -> None:
    node = {"ha_id": "light.kitchen::GasCylinder", "password": "leak-me"}
    projected = context_export.project(node, "GasCylinder")
    assert set(projected.keys()) == set(CONTEXT_EXPORT_ALLOWED_FIELDS[LABEL_SEMANTIC_TYPE])
    assert projected["asset_type"] == "GasCylinder"
    assert projected["entity_id"] == "light.kitchen"
    assert "password" not in projected


def test_project_returns_none_for_none_node() -> None:
    assert context_export.project(None, LABEL_AREA) is None


async def test_entity_export_includes_all_direct_relationships() -> None:
    client = AsyncMock()
    client.run_query = AsyncMock(
        return_value=[
            {
                "e": {"ha_id": "light.office"},
                "d": {"ha_id": "device-1", "name": "Office light"},
                "area": {"ha_id": "office", "name": "Office"},
                "dom": {"ha_id": "light"},
                "integ": {"ha_id": "hue", "name": "Hue"},
                "semantic_types": ["Lighting"],
                "dependents": ["automation.office"],
            }
        ]
    )

    tool_result = await context_export.export(client, "entity", "light.office")

    relationship_types = {
        relationship["type"] for relationship in tool_result["result"]["relationships"]
    }
    assert relationship_types == {
        "HAS_ENTITY",
        "HAS_AREA",
        "IN_DOMAIN",
        "PROVIDED_BY",
        "CLASSIFIED_AS",
        "REFERENCES",
    }
    assert "password" not in str(tool_result)


async def test_whole_home_export_is_bounded_with_truncation_metadata() -> None:
    client = AsyncMock()
    client.run_query_limited = AsyncMock(
        side_effect=[
            ([{"d": {"ha_id": f"device-{index}"}} for index in range(100)], True),
            ([], False),
            ([], False),
            ([], False),
            ([], False),
        ]
    )

    tool_result = await context_export.export(client, "whole_home")

    assert len(tool_result["result"]["devices"]) == 100
    assert tool_result["result"]["truncated"] is True
    assert tool_result["result"]["truncated_collections"] == ["devices"]
    assert "devices truncated to 100 items" in tool_result["warnings"]
