"""Test: config flow succeeds against a reachable Memgraph (contracts/config-flow.md)."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.data_entry_flow import FlowResultType

from custom_components.ontology.const import DOMAIN


async def test_user_step_success_creates_entry(hass, mock_config_entry_data) -> None:
    """A reachable Memgraph connection creates a config entry (FR-001, FR-002)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM

    with (
        patch(
            "custom_components.ontology.config_flow.MemgraphClient.test_connection",
            return_value=None,
        ),
        patch(
            "custom_components.ontology.config_flow.MemgraphClient.close",
            return_value=None,
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], mock_config_entry_data
        )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"] == mock_config_entry_data
