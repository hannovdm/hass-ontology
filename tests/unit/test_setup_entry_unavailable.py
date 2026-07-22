"""Test: async_setup_entry raises ConfigEntryNotReady (not an unhandled
exception) and never blocks HA startup when Memgraph is unavailable
(User Story 2)."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology.const import DOMAIN
from custom_components.ontology.memgraph_client import CannotConnect, InvalidAuth


async def test_setup_entry_retries_on_cannot_connect(hass, mock_config_entry_data) -> None:
    """A transient connection failure leaves the entry in SETUP_RETRY, not a
    crash, so Home Assistant's own startup remains stable (FR-002)."""
    entry = MockConfigEntry(domain=DOMAIN, data=mock_config_entry_data)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ontology.MemgraphClient.test_connection",
        side_effect=CannotConnect("connection refused"),
    ):
        result = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert result is False
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_entry_retries_on_invalid_auth(hass, mock_config_entry_data) -> None:
    """An auth failure also results in SETUP_RETRY rather than an unhandled
    exception, since credentials could still be corrected via reconfigure."""
    entry = MockConfigEntry(domain=DOMAIN, data=mock_config_entry_data)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ontology.MemgraphClient.test_connection",
        side_effect=InvalidAuth("bad credentials"),
    ):
        result = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert result is False
    assert entry.state is ConfigEntryState.SETUP_RETRY
