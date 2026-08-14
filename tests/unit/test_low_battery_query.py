"""Tests for the shared low-battery area query."""

from __future__ import annotations

from unittest.mock import AsyncMock

from custom_components.ontology.const import OUTCOME_EMPTY, OUTCOME_OK
from custom_components.ontology.query_tools import low_battery_areas


async def test_groups_fresh_readings_by_area_and_device() -> None:
    client = AsyncMock()
    client.run_query_limited.return_value = (
        [
            {
                "area_id": "garage",
                "area_name": "Garage",
                "device_id": "device-1",
                "entity_id": "sensor.remote_battery",
                "name": "Remote battery",
                "percentage": 8.0,
                "measured_at": "2026-03-20T11:00:00+00:00",
            },
            {
                "area_id": "garage",
                "area_name": "Garage",
                "device_id": "device-1",
                "entity_id": "sensor.remote_backup_battery",
                "name": "Remote backup battery",
                "percentage": 12.0,
                "measured_at": "2026-03-20T11:30:00+00:00",
            },
            {
                "area_id": "kitchen",
                "area_name": "Kitchen",
                "device_id": None,
                "entity_id": "sensor.button_battery",
                "name": "Button battery",
                "percentage": 19.0,
                "measured_at": "2026-03-20T11:45:00+00:00",
            },
        ],
        False,
    )
    client.run_query.return_value = [
        {"status": "invalid_value", "status_count": 1},
        {"status": "unavailable", "status_count": 1},
        {"status": "unsupported_unit", "status_count": 1},
    ]

    result = await low_battery_areas(
        client,
        threshold_percentage=20,
        max_age_hours=24,
        limit=10,
        now_epoch=1_774_008_000,
    )

    assert result["outcome"] == OUTCOME_OK
    assert result["result"] == {
        "threshold_percentage": 20.0,
        "max_age_hours": 24.0,
        "areas": [
            {
                "area_id": "garage",
                "area_name": "Garage",
                "items": [
                    {
                        "device_id": "device-1",
                        "entity_id": "sensor.remote_battery",
                        "name": "Remote battery",
                        "measurements": [
                            {
                                "entity_id": "sensor.remote_battery",
                                "name": "Remote battery",
                                "percentage": 8.0,
                                "measured_at": "2026-03-20T11:00:00+00:00",
                            },
                            {
                                "entity_id": "sensor.remote_backup_battery",
                                "name": "Remote backup battery",
                                "percentage": 12.0,
                                "measured_at": "2026-03-20T11:30:00+00:00",
                            },
                        ],
                    }
                ],
            },
            {
                "area_id": "kitchen",
                "area_name": "Kitchen",
                "items": [
                    {
                        "device_id": None,
                        "entity_id": "sensor.button_battery",
                        "name": "Button battery",
                        "measurements": [
                            {
                                "entity_id": "sensor.button_battery",
                                "name": "Button battery",
                                "percentage": 19.0,
                                "measured_at": "2026-03-20T11:45:00+00:00",
                            }
                        ],
                    }
                ],
            },
        ],
        "unavailable_count": 3,
        "truncated": False,
    }
    assert result["warnings"] == [
        "1 battery measurement unavailable",
        "1 battery measurement invalid",
        "1 battery measurement has an unsupported unit",
    ]
    query, parameters, limit = client.run_query_limited.await_args.args
    assert "battery_percentage < $threshold_percentage" in query
    assert "measurement_last_updated_epoch >= $fresh_after_epoch" in query
    assert parameters["threshold_percentage"] == 20.0
    assert limit == 10


async def test_returns_empty_and_reports_truncation() -> None:
    client = AsyncMock()
    client.run_query_limited.return_value = ([], True)
    client.run_query.return_value = []

    result = await low_battery_areas(client, limit=2, now_epoch=1_774_008_000)

    assert result["outcome"] == OUTCOME_EMPTY
    assert result["result"]["areas"] == []
    assert result["result"]["truncated"] is True
    assert result["warnings"] == ["low battery results truncated to 2 items"]


async def test_strict_threshold_and_freshness_are_parameterized() -> None:
    client = AsyncMock()
    client.run_query_limited.return_value = ([], False)
    client.run_query.return_value = []

    await low_battery_areas(
        client,
        threshold_percentage=35.5,
        max_age_hours=6,
        limit=7,
        now_epoch=10_000,
    )

    query, parameters, limit = client.run_query_limited.await_args.args
    assert "battery_percentage < $threshold_percentage" in query
    assert "measurement_last_updated_epoch >= $fresh_after_epoch" in query
    assert parameters == {
        "threshold_percentage": 35.5,
        "fresh_after_epoch": 10_000 - (6 * 3600),
    }
    assert limit == 7


async def test_warning_counts_exclude_stale_available_readings() -> None:
    client = AsyncMock()
    client.run_query_limited.return_value = ([], False)
    client.run_query.return_value = [
        {"status": "unavailable", "status_count": 2},
        {"status": "invalid_value", "status_count": 3},
        {"status": "unsupported_unit", "status_count": 4},
    ]

    result = await low_battery_areas(client, now_epoch=10_000)

    count_query, count_parameters = client.run_query.await_args.args
    assert "measurement_last_updated_epoch" not in count_query
    assert "available" not in count_parameters["warning_statuses"]
    assert result["result"]["unavailable_count"] == 9
    assert result["warnings"] == [
        "2 battery measurements unavailable",
        "3 battery measurements invalid",
        "4 battery measurements have an unsupported unit",
    ]