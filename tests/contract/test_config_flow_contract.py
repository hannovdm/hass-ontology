"""Contract test: config flow schema/steps match contracts/config-flow.md."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
import voluptuous as vol
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ontology.config_flow import _options_schema
from custom_components.ontology.const import (
    CONF_ACTIVE_POWER_THRESHOLD,
    CONF_LOW_BATTERY_THRESHOLD,
    CONF_MAX_MEASUREMENT_AGE_HOURS,
    CONF_RELATIONSHIP_RESULT_LIMIT,
    DEFAULT_ACTIVE_POWER_THRESHOLD,
    DEFAULT_LOW_BATTERY_THRESHOLD,
    DEFAULT_MAX_MEASUREMENT_AGE_HOURS,
    DEFAULT_RELATIONSHIP_RESULT_LIMIT,
    DOMAIN,
)

STRINGS_PATH = Path(__file__).parents[2] / "custom_components" / "ontology" / "strings.json"


async def test_user_step_schema_fields(hass) -> None:
    """The `user` step exposes exactly the fields defined in the contract."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    field_names = {field.schema for field in result["data_schema"].schema}
    assert field_names == {
        "host",
        "port",
        "username",
        "password",
        "database",
        "encrypted",
    }


def test_strings_declare_contract_error_keys() -> None:
    """strings.json declares the `cannot_connect`/`invalid_auth` error keys."""
    strings = json.loads(STRINGS_PATH.read_text())
    errors = strings["config"]["error"]
    assert "cannot_connect" in errors
    assert "invalid_auth" in errors


def test_strings_declare_user_and_reconfigure_steps() -> None:
    """strings.json declares both the `user` and `reconfigure` steps."""
    strings = json.loads(STRINGS_PATH.read_text())
    steps = strings["config"]["step"]
    assert "user" in steps
    assert "reconfigure" in steps


def _connection_options(**overrides: object) -> dict[str, object]:
    return {
        "host": "localhost",
        "port": 7687,
        "username": "",
        "password": "",
        "database": "",
        "encrypted": False,
        **overrides,
    }


def test_relationship_options_use_contract_defaults() -> None:
    validated = _options_schema()(_connection_options())

    assert validated[CONF_LOW_BATTERY_THRESHOLD] == DEFAULT_LOW_BATTERY_THRESHOLD
    assert validated[CONF_ACTIVE_POWER_THRESHOLD] == DEFAULT_ACTIVE_POWER_THRESHOLD
    assert validated[CONF_MAX_MEASUREMENT_AGE_HOURS] == DEFAULT_MAX_MEASUREMENT_AGE_HOURS
    assert validated[CONF_RELATIONSHIP_RESULT_LIMIT] == DEFAULT_RELATIONSHIP_RESULT_LIMIT


@pytest.mark.parametrize("value", [1, 100, 37.5])
def test_low_battery_threshold_accepts_contract_range(value: float) -> None:
    validated = _options_schema()(
        _connection_options(**{CONF_LOW_BATTERY_THRESHOLD: value})
    )
    assert validated[CONF_LOW_BATTERY_THRESHOLD] == value


@pytest.mark.parametrize("value", [0, 101, math.nan, math.inf, -math.inf])
def test_low_battery_threshold_rejects_out_of_range_or_nonfinite(value: float) -> None:
    with pytest.raises(vol.Invalid):
        _options_schema()(_connection_options(**{CONF_LOW_BATTERY_THRESHOLD: value}))


@pytest.mark.parametrize("value", [0, 1.5, 1000000])
def test_active_power_threshold_accepts_finite_nonnegative(value: float) -> None:
    validated = _options_schema()(
        _connection_options(**{CONF_ACTIVE_POWER_THRESHOLD: value})
    )
    assert validated[CONF_ACTIVE_POWER_THRESHOLD] == value


@pytest.mark.parametrize("value", [-0.1, math.nan, math.inf, -math.inf])
def test_active_power_threshold_rejects_negative_or_nonfinite(value: float) -> None:
    with pytest.raises(vol.Invalid):
        _options_schema()(_connection_options(**{CONF_ACTIVE_POWER_THRESHOLD: value}))


@pytest.mark.parametrize("value", [0, -1, math.nan, math.inf])
def test_max_measurement_age_rejects_nonpositive_or_nonfinite(value: float) -> None:
    with pytest.raises(vol.Invalid):
        _options_schema()(_connection_options(**{CONF_MAX_MEASUREMENT_AGE_HOURS: value}))


@pytest.mark.parametrize("value", [0, 1001, 1.5])
def test_relationship_result_limit_rejects_out_of_range_or_fractional(value: float) -> None:
    with pytest.raises(vol.Invalid):
        _options_schema()(_connection_options(**{CONF_RELATIONSHIP_RESULT_LIMIT: value}))


def test_relationship_options_preserve_saved_values_as_form_defaults() -> None:
    saved = _connection_options(
        **{
            CONF_LOW_BATTERY_THRESHOLD: 15,
            CONF_ACTIVE_POWER_THRESHOLD: 2.5,
            CONF_MAX_MEASUREMENT_AGE_HOURS: 12,
            CONF_RELATIONSHIP_RESULT_LIMIT: 75,
        }
    )
    validated = _options_schema(saved)(_connection_options())

    assert validated[CONF_LOW_BATTERY_THRESHOLD] == 15
    assert validated[CONF_ACTIVE_POWER_THRESHOLD] == 2.5
    assert validated[CONF_MAX_MEASUREMENT_AGE_HOURS] == 12
    assert validated[CONF_RELATIONSHIP_RESULT_LIMIT] == 75


def test_strings_declare_relationship_option_labels() -> None:
    strings = json.loads(STRINGS_PATH.read_text())
    option_fields = strings["options"]["step"]["init"]["data"]

    assert CONF_LOW_BATTERY_THRESHOLD in option_fields
    assert CONF_ACTIVE_POWER_THRESHOLD in option_fields
    assert CONF_MAX_MEASUREMENT_AGE_HOURS in option_fields
    assert CONF_RELATIONSHIP_RESULT_LIMIT in option_fields
