"""Tests for deterministic operation-aware target resolution."""

from __future__ import annotations

from unittest.mock import AsyncMock

from custom_components.ontology.const import (
    OUTCOME_AMBIGUOUS,
    OUTCOME_EMPTY,
    OUTCOME_NOT_FOUND,
    OUTCOME_OK,
    RESULT_TYPE_DEVICE_CONTEXT,
)
from custom_components.ontology.query_tools import (
    build_tool_result,
    not_found_result,
    resolve_target,
)


async def test_exact_stable_id_takes_precedence_over_duplicate_name() -> None:
    client = AsyncMock()
    client.run_query.return_value = [
        {
            "target_type": "entity",
            "target_id": "sensor.garage",
            "name": "Garage sensor",
            "area_name": "Garage",
        },
        {
            "target_type": "device",
            "target_id": "sensor.garage",
            "name": "Different device",
            "area_name": None,
        },
        {
            "target_type": "entity",
            "target_id": "sensor.other",
            "name": "sensor.garage",
            "area_name": None,
        },
    ]

    resolution = await resolve_target(
        client, "sensor.garage", ("entity",), limit=10
    )

    assert resolution.outcome == OUTCOME_OK
    assert resolution.target_id == "sensor.garage"
    assert resolution.target_type == "entity"
    assert resolution.candidates == []


async def test_unique_case_insensitive_name_resolves() -> None:
    client = AsyncMock()
    client.run_query.return_value = [
        {
            "target_type": "device",
            "target_id": "device-1",
            "name": "Garage Sensor",
            "area_name": "Garage",
        }
    ]

    resolution = await resolve_target(
        client, "garage sensor", ("device",), limit=10
    )

    assert resolution.outcome == OUTCOME_OK
    assert resolution.target_id == "device-1"


async def test_duplicate_names_return_bounded_stably_ordered_candidates(
    ambiguous_target_rows,
) -> None:
    client = AsyncMock()
    client.run_query.return_value = [
        *ambiguous_target_rows(),
        {
            "target_type": "entity",
            "target_id": "sensor.garage_b",
            "name": "Garage sensor",
            "area_name": "Garage",
        },
    ]

    resolution = await resolve_target(
        client, "Garage sensor", ("entity", "device"), limit=2
    )

    assert resolution.outcome == OUTCOME_AMBIGUOUS
    assert resolution.truncated is True
    assert resolution.candidates == [
        {
            "target_type": "device",
            "target_id": "device-b",
            "name": "Garage sensor",
            "area_name": None,
        },
        {
            "target_type": "entity",
            "target_id": "sensor.garage_a",
            "name": "Garage sensor",
            "area_name": "Garage",
        },
    ]


async def test_not_found_is_explicit_and_query_is_bounded() -> None:
    client = AsyncMock()
    client.run_query.return_value = []

    resolution = await resolve_target(
        client, "missing", ("device",), limit=7
    )

    assert resolution.outcome == OUTCOME_NOT_FOUND
    _, parameters = client.run_query.await_args.args
    assert parameters["candidate_limit"] == 8


def test_tool_result_adds_outcome_without_removing_existing_keys() -> None:
    result = build_tool_result(
        "garage",
        RESULT_TYPE_DEVICE_CONTEXT,
        {"device": {"ha_id": "device-1"}},
    )

    assert set(result) == {"target", "result_type", "outcome", "result", "warnings"}
    assert result["outcome"] == OUTCOME_OK


def test_tool_result_supports_empty_and_not_found_outcomes() -> None:
    empty = build_tool_result(
        "garage", RESULT_TYPE_DEVICE_CONTEXT, {"entities": []}, outcome=OUTCOME_EMPTY
    )
    missing = not_found_result("missing", RESULT_TYPE_DEVICE_CONTEXT)

    assert empty["outcome"] == OUTCOME_EMPTY
    assert missing["outcome"] == OUTCOME_NOT_FOUND