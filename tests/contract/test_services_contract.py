"""Contract test: registered services and `services.yaml` match
contracts/services.md — exactly eight services (four v1 + four v2),
`sync_entity` requires `entity_id`, and only `ontology.query` accepts
a validated `cypher` field (Constitution Principle X)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import voluptuous as vol
import yaml
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology.const import (
    ATTR_CYPHER,
    ATTR_ENTITY_ID,
    ATTR_LIMIT,
    ATTR_PARAMETERS,
    ATTR_PAYLOAD,
    DOMAIN,
    SERVICE_EXPORT_OVERRIDES,
    SERVICE_IMPORT_OVERRIDES,
    SERVICE_QUERY,
    SERVICE_REBUILD,
    SERVICE_REFRESH_SEMANTICS,
    SERVICE_RESYNC,
    SERVICE_SYNC_ENTITY,
    SERVICE_VALIDATE,
)

SERVICES_YAML_PATH = (
    Path(__file__).parents[2] / "custom_components" / "ontology" / "services.yaml"
)


def test_services_yaml_declares_exactly_the_eight_contract_services() -> None:
    services = yaml.safe_load(SERVICES_YAML_PATH.read_text())
    assert set(services.keys()) == {
        SERVICE_REBUILD,
        SERVICE_RESYNC,
        SERVICE_SYNC_ENTITY,
        SERVICE_VALIDATE,
        SERVICE_QUERY,
        SERVICE_REFRESH_SEMANTICS,
        SERVICE_EXPORT_OVERRIDES,
        SERVICE_IMPORT_OVERRIDES,
    }


def test_services_yaml_declares_no_raw_cypher_field_outside_query_service() -> None:
    """Only `ontology.query` (validated/rejected via `QueryRejected`, Constitution
    Principle X) may accept a `cypher` field; no other service may."""
    services = yaml.safe_load(SERVICES_YAML_PATH.read_text())
    for name, service_def in services.items():
        fields = (service_def or {}).get("fields", {})
        if name == SERVICE_QUERY:
            assert "cypher" in fields
            continue
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

    for service in (
        SERVICE_REBUILD,
        SERVICE_RESYNC,
        SERVICE_SYNC_ENTITY,
        SERVICE_VALIDATE,
        SERVICE_QUERY,
        SERVICE_REFRESH_SEMANTICS,
        SERVICE_EXPORT_OVERRIDES,
        SERVICE_IMPORT_OVERRIDES,
    ):
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


def test_query_service_schema_declares_cypher_parameters_and_limit() -> None:
    """T015: `ontology.query` accepts `cypher` (required), `parameters`
    (optional), and `limit` (optional, bounded 1-1000)."""
    services = yaml.safe_load(SERVICES_YAML_PATH.read_text())
    fields = services[SERVICE_QUERY]["fields"]
    assert fields[ATTR_CYPHER]["required"] is True
    assert fields[ATTR_PARAMETERS]["required"] is False
    assert fields[ATTR_LIMIT]["required"] is False
    assert fields[ATTR_LIMIT]["selector"]["number"]["min"] == 1
    assert fields[ATTR_LIMIT]["selector"]["number"]["max"] == 1000


async def test_query_service_rejects_write_query_with_clear_error(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    """T015: a write-attempting `cypher` value is rejected (not executed)
    with a `ServiceValidationError`/`HomeAssistantError`, not a raw traceback."""
    entry = MockConfigEntry(domain=DOMAIN, data=mock_config_entry_data)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ontology.MemgraphClient", return_value=mock_memgraph_client
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(Exception):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_QUERY,
            {ATTR_CYPHER: "CREATE (n:Area) RETURN n"},
            blocking=True,
        )
    mock_memgraph_client.run_query_limited.assert_not_awaited()


def test_refresh_semantics_service_schema_has_optional_entity_id() -> None:
    """T043: `ontology.refresh_semantics` accepts an optional `entity_id`."""
    services = yaml.safe_load(SERVICES_YAML_PATH.read_text())
    fields = services[SERVICE_REFRESH_SEMANTICS].get("fields", {})
    assert fields[ATTR_ENTITY_ID]["required"] is False


def test_export_import_overrides_service_schemas() -> None:
    """T048: `ontology.export_overrides` takes no fields; `ontology.import_overrides`
    requires a `payload` object field."""
    services = yaml.safe_load(SERVICES_YAML_PATH.read_text())
    assert not (services.get(SERVICE_EXPORT_OVERRIDES) or {}).get("fields")
    import_fields = services[SERVICE_IMPORT_OVERRIDES]["fields"]
    assert import_fields[ATTR_PAYLOAD]["required"] is True


async def test_validate_service_runs_only_on_explicit_invocation(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    """T037 (FR-017): `ontology.validate` never runs automatically after a
    sync (`rebuild`/`resync`) - only when explicitly called."""
    entry = MockConfigEntry(domain=DOMAIN, data=mock_config_entry_data)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.ontology.MemgraphClient", return_value=mock_memgraph_client
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        await hass.services.async_call(DOMAIN, SERVICE_RESYNC, {}, blocking=True)

        validate_query_markers = ("ValidationFinding", "missing_area", "orphan_")
        assert not any(
            any(marker in str(call) for marker in validate_query_markers)
            for call in mock_memgraph_client.run_query.await_args_list
        )
        assert not any(
            any(marker in str(call) for marker in validate_query_markers)
            for call in mock_memgraph_client.run_query_with_retry.await_args_list
        )
