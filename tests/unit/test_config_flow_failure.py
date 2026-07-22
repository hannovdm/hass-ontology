"""Test: config flow fails clearly against an unreachable Memgraph (contracts/config-flow.md)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ontology.const import DOMAIN
from custom_components.ontology.memgraph_client import CannotConnect, InvalidAuth


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        (CannotConnect("connection refused"), "cannot_connect"),
        (InvalidAuth("bad credentials"), "invalid_auth"),
    ],
)
async def test_user_step_failure_shows_error(
    hass, mock_config_entry_data, side_effect, expected_error
) -> None:
    """An unreachable/misauthenticated Memgraph re-shows the form with an error
    and does not create a config entry (FR-002)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM

    with (
        patch(
            "custom_components.ontology.config_flow.MemgraphClient.test_connection",
            side_effect=side_effect,
        ),
        patch(
            "custom_components.ontology.config_flow.MemgraphClient.close",
            return_value=None,
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], mock_config_entry_data
        )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {"base": expected_error}

    entries = hass.config_entries.async_entries(DOMAIN)
    assert entries == []
