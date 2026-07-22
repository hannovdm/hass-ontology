"""Contract test: config flow schema/steps match contracts/config-flow.md."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.data_entry_flow import FlowResultType

from custom_components.ontology.const import DOMAIN

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
