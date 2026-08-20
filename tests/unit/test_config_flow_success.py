"""Test: config flow succeeds against a reachable Memgraph (contracts/config-flow.md)."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from custom_components.ontology.const import CONF_GRAPHQL_TOKEN, CONF_GRAPHQL_URL, DOMAIN


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


async def test_hassio_discovery_preserves_internal_graphql_connection(hass) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "hassio"},
        data=HassioServiceInfo(
            config={
                "host": "local-memgraph",
                "port": 7687,
                CONF_GRAPHQL_URL: "http://local-memgraph:4000/graphql",
                CONF_GRAPHQL_TOKEN: "discovery-secret",
            },
            name="Memgraph",
            slug="memgraph",
            uuid="addon-uuid",
        ),
    )

    assert result["type"] == FlowResultType.FORM
    defaults = {field.schema: field.default() for field in result["data_schema"].schema}
    assert defaults[CONF_GRAPHQL_URL] == "http://local-memgraph:4000/graphql"
    assert defaults[CONF_GRAPHQL_TOKEN] == "discovery-secret"
