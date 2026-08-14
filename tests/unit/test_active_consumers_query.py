"""Tests for the shared active-electricity-consumer query."""

from __future__ import annotations

from unittest.mock import AsyncMock

from custom_components.ontology.const import OUTCOME_EMPTY, OUTCOME_OK
from custom_components.ontology.query_tools import active_consumers


async def test_returns_only_role_filtered_devices_with_unsummed_measurements() -> None:
    client = AsyncMock()
    client.run_query_limited.return_value = (
        [
            {
                "device_id": "dishwasher-device",
                "name": "Dishwasher",
                "area_id": "kitchen",
                "area_name": "Kitchen",
                "measurements": [
                    {
                        "entity_id": "sensor.dishwasher_power",
                        "name": "Dishwasher power",
                        "watts": 850.0,
                        "source_unit": "W",
                        "role": "consumer",
                        "role_source": "user",
                        "measured_at": "2026-08-12T12:00:00+00:00",
                    },
                    {
                        "entity_id": "sensor.dishwasher_aux_power",
                        "name": "Dishwasher auxiliary power",
                        "watts": 12.5,
                        "source_unit": "kW",
                        "role": "consumer",
                        "role_source": "inferred",
                        "measured_at": "2026-08-12T12:00:00+00:00",
                    },
                ],
            }
        ],
        False,
    )
    client.run_query.return_value = [{"unresolved_role_count": 2}]

    result = await active_consumers(
        client,
        threshold_watts=1,
        max_age_hours=24,
        limit=10,
        now_epoch=1_786_536_000,
    )

    assert result["outcome"] == OUTCOME_OK
    assert result["result"] == {
        "threshold_watts": 1.0,
        "max_age_hours": 24.0,
        "consumers": [
            {
                "device_id": "dishwasher-device",
                "name": "Dishwasher",
                "area_id": "kitchen",
                "area_name": "Kitchen",
                "measurements": [
                    {
                        "entity_id": "sensor.dishwasher_power",
                        "name": "Dishwasher power",
                        "watts": 850.0,
                        "source_unit": "W",
                        "role": "consumer",
                        "role_source": "user",
                        "measured_at": "2026-08-12T12:00:00+00:00",
                    },
                    {
                        "entity_id": "sensor.dishwasher_aux_power",
                        "name": "Dishwasher auxiliary power",
                        "watts": 12.5,
                        "source_unit": "kW",
                        "role": "consumer",
                        "role_source": "inferred",
                        "measured_at": "2026-08-12T12:00:00+00:00",
                    },
                ],
            }
        ],
        "unresolved_role_count": 2,
        "truncated": False,
    }
    assert "total_watts" not in result["result"]["consumers"][0]
    assert result["warnings"] == ["2 active power measurements have no effective energy role"]

    query, parameters, limit = client.run_query_limited.await_args.args
    assert "e.power_watts > $threshold_watts" in query
    assert "e.measurement_last_updated_epoch >= $fresh_after_epoch" in query
    assert "coalesce(user_role.role, inferred_role.role)" in query
    assert "effective_role = $consumer_role" in query
    assert "sum(" not in query.lower()
    assert parameters["threshold_watts"] == 1.0
    assert limit == 10


async def test_empty_result_and_truncation_are_explicit() -> None:
    client = AsyncMock()
    client.run_query_limited.return_value = ([], True)
    client.run_query.return_value = [{"unresolved_role_count": 0}]

    result = await active_consumers(client, limit=2, now_epoch=10_000)

    assert result["outcome"] == OUTCOME_EMPTY
    assert result["result"]["consumers"] == []
    assert result["result"]["truncated"] is True
    assert result["warnings"] == ["active consumer results truncated to 2 devices"]


async def test_threshold_and_freshness_are_strict_and_parameterized() -> None:
    client = AsyncMock()
    client.run_query_limited.return_value = ([], False)
    client.run_query.return_value = [{"unresolved_role_count": 0}]

    await active_consumers(
        client,
        threshold_watts=0,
        max_age_hours=2,
        limit=7,
        now_epoch=10_000,
    )

    _, parameters, limit = client.run_query_limited.await_args.args
    assert parameters["threshold_watts"] == 0.0
    assert parameters["fresh_after_epoch"] == 10_000 - (2 * 3600)
    assert limit == 7