"""Unit tests for bounded impact analysis (User Story 3): T026 (result shape),
T027 (has_dependencies == False returns a normal, non-error empty result)."""

from __future__ import annotations

import asyncio
from time import monotonic
from unittest.mock import AsyncMock

import pytest

from custom_components.ontology import impact_analysis


def _client(resolve_row: dict | None, dependency_row: dict | None) -> AsyncMock:
    """A client whose `run_query` first resolves the target, then answers
    any device/area aggregation lookups with empty lists, and whose
    `run_query_limited` answers the bounded dependency traversal."""
    client = AsyncMock()
    client.run_query = AsyncMock(
        side_effect=lambda query, params=None: (
            [{"n": resolve_row}] if resolve_row is not None else []
        )
        if "RETURN n LIMIT 1" in query
        else []
    )
    client.run_query_limited = AsyncMock(
        return_value=([dependency_row] if dependency_row is not None else [], False)
    )
    return client


async def test_entity_scope_returns_impact_analysis_result_shape() -> None:
    client = _client(
        resolve_row={"ha_id": "light.kitchen"},
        dependency_row={
            "automations": [{"ha_id": "automation.morning", "name": "Morning"}],
            "scripts": [],
            "scenes": [],
            "dashboards": [],
            "semantic_assets": [],
        },
    )
    tool_result = await impact_analysis.analyze(client, "entity", "light.kitchen")

    assert tool_result["result_type"] == "impact_analysis"
    result = tool_result["result"]
    for key in (
        "scope",
        "affected_entities",
        "affected_devices",
        "automations",
        "scripts",
        "scenes",
        "dashboards",
        "semantic_assets",
        "has_dependencies",
    ):
        assert key in result
    assert result["scope"] == "entity"
    assert result["has_dependencies"] is True
    assert result["automations"] == [{"ha_id": "automation.morning", "name": "Morning"}]


async def test_entity_scope_with_no_dependencies_returns_normal_empty_result() -> None:
    client = _client(
        resolve_row={"ha_id": "light.kitchen"},
        dependency_row={
            "automations": [],
            "scripts": [],
            "scenes": [],
            "dashboards": [],
            "semantic_assets": [],
        },
    )
    tool_result = await impact_analysis.analyze(client, "entity", "light.kitchen")

    assert tool_result["result_type"] == "impact_analysis"  # not an error/not_found
    result = tool_result["result"]
    assert result["has_dependencies"] is False
    for key in ("automations", "scripts", "scenes", "dashboards", "semantic_assets"):
        assert result[key] == []
    assert tool_result["warnings"] == ["no known dependencies found"]


async def test_dashboard_display_counts_as_entity_dependency() -> None:
    client = _client(
        resolve_row={"ha_id": "light.kitchen"},
        dependency_row={
            "automations": [],
            "scripts": [],
            "scenes": [],
            "dashboards": [{"ha_id": "lovelace", "title": "Home"}],
            "semantic_assets": [],
        },
    )

    tool_result = await impact_analysis.analyze(client, "entity", "light.kitchen")

    assert tool_result["result"]["has_dependencies"] is True
    assert tool_result["result"]["dashboards"] == [{"ha_id": "lovelace", "name": "Home"}]
    assert tool_result["warnings"] == []


async def test_unresolvable_entity_returns_not_found() -> None:
    client = _client(resolve_row=None, dependency_row=None)
    tool_result = await impact_analysis.analyze(client, "entity", "light.missing")
    assert tool_result["result_type"] == "not_found"
    assert tool_result["result"] is None


async def test_unknown_scope_raises_value_error() -> None:
    client = AsyncMock()
    with pytest.raises(ValueError):
        await impact_analysis.analyze(client, "bogus_scope", "anything")


async def test_entity_dependency_collections_are_bounded_with_warning() -> None:
    client = _client(
        resolve_row={"ha_id": "light.kitchen"},
        dependency_row={
            "automations": [
                {"ha_id": f"automation.{index}", "name": str(index)} for index in range(102)
            ],
            "scripts": [],
            "scenes": [],
            "dashboards": [],
            "semantic_assets": [],
        },
    )

    tool_result = await impact_analysis.analyze(client, "entity", "light.kitchen")

    assert len(tool_result["result"]["automations"]) == 100
    assert "automations truncated to 100 items" in tool_result["warnings"]


async def test_device_result_includes_current_area() -> None:
    client = AsyncMock()
    client.run_query = AsyncMock(
        side_effect=[
            [{"n": {"ha_id": "device-1"}}],
            [{"e": {"ha_id": "sensor.one"}, "area": {"ha_id": "new-office", "name": "New Office"}}],
        ]
    )
    client.run_query_limited = AsyncMock(
        return_value=(
            [
                {
                    "automations": [],
                    "scripts": [],
                    "scenes": [],
                    "dashboards": [],
                    "semantic_assets": [],
                }
            ],
            False,
        )
    )

    tool_result = await impact_analysis.analyze(client, "device", "device-1")

    assert tool_result["result"]["current_area"] == {
        "ha_id": "new-office",
        "name": "New Office",
    }


async def test_device_high_fanout_dependencies_run_concurrently(monkeypatch) -> None:
    client = AsyncMock()
    client.run_query = AsyncMock(
        side_effect=[
            [{"n": {"ha_id": "device-1"}}],
            [{"e": {"ha_id": f"sensor.{index}"}, "area": None} for index in range(100)],
        ]
    )

    async def delayed_dependencies(_client, _entity_id):
        await asyncio.sleep(0.02)
        return {
            "automations": [],
            "scripts": [],
            "scenes": [],
            "dashboards": [],
            "semantic_assets": [],
            "_warnings": [],
        }

    monkeypatch.setattr(impact_analysis, "_entity_dependencies", delayed_dependencies)
    started = monotonic()

    tool_result = await impact_analysis.analyze(client, "device", "device-1")

    assert monotonic() - started < 0.5
    assert len(tool_result["result"]["affected_entities"]) == 100
