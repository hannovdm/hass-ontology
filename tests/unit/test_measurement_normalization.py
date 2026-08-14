"""Tests for strict current battery and power measurement normalization."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.ontology.const import (
    MEASUREMENT_BATTERY_PERCENTAGE,
    MEASUREMENT_KIND,
    MEASUREMENT_KIND_BATTERY,
    MEASUREMENT_KIND_POWER,
    MEASUREMENT_LAST_UPDATED,
    MEASUREMENT_LAST_UPDATED_EPOCH,
    MEASUREMENT_POWER_WATTS,
    MEASUREMENT_STATUS,
    MEASUREMENT_STATUS_AVAILABLE,
    MEASUREMENT_STATUS_INVALID_VALUE,
    MEASUREMENT_STATUS_UNAVAILABLE,
    MEASUREMENT_STATUS_UNSUPPORTED_UNIT,
)
from custom_components.ontology.graph_builder import normalize_current_measurement


def test_normalizes_battery_percentage_and_source_timestamp(battery_state_builder) -> None:
    updated = datetime(2025, 6, 1, 8, 30, tzinfo=UTC)
    state = battery_state_builder(value="19.5", last_updated=updated)

    result = normalize_current_measurement(state)

    assert result == {
        MEASUREMENT_KIND: MEASUREMENT_KIND_BATTERY,
        MEASUREMENT_STATUS: MEASUREMENT_STATUS_AVAILABLE,
        MEASUREMENT_BATTERY_PERCENTAGE: 19.5,
        MEASUREMENT_LAST_UPDATED: updated.isoformat(),
        MEASUREMENT_LAST_UPDATED_EPOCH: updated.timestamp(),
    }


@pytest.mark.parametrize(("unit", "value", "expected"), [("W", "7.5", 7.5), ("kW", "1.25", 1250.0)])
def test_normalizes_only_supported_power_units(power_state_builder, unit, value, expected) -> None:
    result = normalize_current_measurement(power_state_builder(value=value, unit=unit))

    assert result[MEASUREMENT_KIND] == MEASUREMENT_KIND_POWER
    assert result[MEASUREMENT_STATUS] == MEASUREMENT_STATUS_AVAILABLE
    assert result[MEASUREMENT_POWER_WATTS] == expected


@pytest.mark.parametrize("unit", ["% ", "percent", "V", "w", "KW", "Wh", ""])
def test_rejects_non_contract_units(battery_state_builder, power_state_builder, unit) -> None:
    state = (
        battery_state_builder(unit=unit)
        if unit.startswith("%") or unit == "percent"
        else power_state_builder(unit=unit)
    )
    result = normalize_current_measurement(state)

    assert result[MEASUREMENT_STATUS] == MEASUREMENT_STATUS_UNSUPPORTED_UNIT
    assert MEASUREMENT_BATTERY_PERCENTAGE not in result
    assert MEASUREMENT_POWER_WATTS not in result


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "not-a-number", "-1", "101"])
def test_rejects_invalid_battery_values(battery_state_builder, value) -> None:
    result = normalize_current_measurement(battery_state_builder(value=value))

    assert result[MEASUREMENT_STATUS] == MEASUREMENT_STATUS_INVALID_VALUE
    assert MEASUREMENT_BATTERY_PERCENTAGE not in result


@pytest.mark.parametrize("value", ["unknown", "unavailable"])
def test_unavailable_transition_clears_numeric_fields(battery_state_builder, value) -> None:
    result = normalize_current_measurement(battery_state_builder(value=value))

    assert result[MEASUREMENT_STATUS] == MEASUREMENT_STATUS_UNAVAILABLE
    assert MEASUREMENT_BATTERY_PERCENTAGE not in result
    assert MEASUREMENT_POWER_WATTS not in result


def test_explicit_measurement_timestamp_overrides_newer_state_timestamp(
    power_state_builder,
) -> None:
    accepted_at = datetime(2025, 1, 1, tzinfo=UTC)
    later_state = power_state_builder(last_updated=datetime(2026, 1, 1, tzinfo=UTC))

    result = normalize_current_measurement(later_state, measurement_last_updated=accepted_at)

    assert result[MEASUREMENT_LAST_UPDATED] == accepted_at.isoformat()
    assert result[MEASUREMENT_LAST_UPDATED_EPOCH] == accepted_at.timestamp()