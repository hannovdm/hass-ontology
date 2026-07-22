"""Contract test: registered services and `services.yaml` match
contracts/services.md — exactly four services, `sync_entity` requires
`entity_id`, and no service accepts arbitrary Cypher (Constitution Principle X)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import voluptuous as vol
import yaml
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology.const import (
    ATTR_ENTITY_ID,
    DOMAIN,
    SERVICE_REBUILD,
    SERVICE_RESYNC,
    SERVICE_SYNC_ENTITY,
    SERVICE_VALIDATE,
)

SERVICES_YAML_PATH = (
    Path(__file__).parents[2] / "custom_components" / "ontology" / "services.yaml"
)


def test_services_yaml_declares_exactly_the_four_contract_services() -> None:
    services = yaml.safe_load(SERVICES_YAML_PATH.read_text())
    assert set(services.keys()) == {
        SERVICE_REBUILD,
        SERVICE_RESYNC,
        SERVICE_SYNC_ENTITY,
        SERVICE_VALIDATE,
    }


def test_services_yaml_declares_no_raw_cypher_field() -> None:
    services = yaml.safe_load(SERVICES_YAML_PATH.read_text())
    for service_def in services.values():
        fields = (service_def or {}).get("fields", {})
        assert "query" not in fields
        assert "cypher" not in fields


def test_sync_entity_requires_entity_id_field() -> None:
    services = yaml.safe_load(SERVICES_YAML_PATH.read_text())
    assert services[SERVICE_SYNC_ENTITY]["fields"][ATTR_ENTITY_ID]["required"] is True


async def test_all_four_services_registered_after_setup(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=mock_config_entry_data)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ontology.MemgraphClient", return_value=mock_memgraph_client
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    for service in (SERVICE_REBUILD, SERVICE_RESYNC, SERVICE_SYNC_ENTITY, SERVICE_VALIDATE):
        assert hass.services.has_service(DOMAIN, service)


async def test_sync_entity_schema_rejects_missing_entity_id(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=mock_config_entry_data)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ontology.MemgraphClient", return_value=mock_memgraph_client
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, SERVICE_SYNC_ENTITY, {}, blocking=True)
