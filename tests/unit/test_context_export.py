"""Unit tests for allow-list context export (User Story 6): T041 (only
allow-listed fields survive projection), T042 (a secret-looking property
is never present, even if it exists on the underlying node)."""

from __future__ import annotations

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
