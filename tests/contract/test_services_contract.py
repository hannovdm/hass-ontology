"""Contract test: registered services and `services.yaml` match
contracts/services.md — eight v1/v2 services plus seven v3 predefined
query-tool/impact-analysis/context-export services (T010), `sync_entity`
requires `entity_id`, and only `ontology.query` accepts a validated
`cypher` field (Constitution Principle X)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
import yaml
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology.const import (
    ATTR_AREA,
    ATTR_CYPHER,
    ATTR_DEVICE,
    ATTR_ENTITY,
    ATTR_ENTITY_ID,
    ATTR_EXPORT_TYPE,
    ATTR_LIMIT,
    ATTR_MAX_AGE_HOURS,
        ATTR_ROLE,
    ATTR_PARAMETERS,
    ATTR_PAYLOAD,
        ATTR_THRESHOLD_WATTS,
    ATTR_TARGET,
    ATTR_TARGET_TYPE,
    ATTR_TERM,
    ATTR_THRESHOLD_PERCENTAGE,
        SERVICE_ACTIVE_CONSUMERS,
    CONF_LOW_BATTERY_THRESHOLD,
    CONF_MAX_MEASUREMENT_AGE_HOURS,
    CONF_RELATIONSHIP_RESULT_LIMIT,
    DOMAIN,
    SERVICE_AREA_CONTEXT,
        SERVICE_DELETE_ENERGY_ROLE,
    SERVICE_AUTOMATION_DEPENDENCIES,
    SERVICE_DEVICE_CONTEXT,
        SERVICE_SET_ENERGY_ROLE,
    SERVICE_ENTITY_CONTEXT,
    SERVICE_EXPORT_CONTEXT,
    SERVICE_EXPORT_OVERRIDES,
    SERVICE_IMPACT_ANALYSIS,
    SERVICE_IMPORT_OVERRIDES,
    SERVICE_LOW_BATTERY_AREAS,
    SERVICE_QUERY,
    SERVICE_REBUILD,
    SERVICE_REFRESH_SEMANTICS,
    SERVICE_RESYNC,
    SERVICE_SEARCH,
    SERVICE_SYNC_ENTITY,
    SERVICE_VALIDATE,
)

SERVICES_YAML_PATH = (
    Path(__file__).parents[2] / "custom_components" / "ontology" / "services.yaml"
)

ALL_V3_SERVICES = (
    SERVICE_SEARCH,
    SERVICE_AREA_CONTEXT,
    SERVICE_DEVICE_CONTEXT,
    SERVICE_ENTITY_CONTEXT,
    SERVICE_AUTOMATION_DEPENDENCIES,
    SERVICE_IMPACT_ANALYSIS,
    SERVICE_EXPORT_CONTEXT,
    SERVICE_LOW_BATTERY_AREAS,
    SERVICE_ACTIVE_CONSUMERS,
    SERVICE_SET_ENERGY_ROLE,
    SERVICE_DELETE_ENERGY_ROLE,
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
        *ALL_V3_SERVICES,
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
        *ALL_V3_SERVICES,
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


def test_energy_role_and_active_consumer_service_schemas() -> None:
    services = yaml.safe_load(SERVICES_YAML_PATH.read_text())
    active_fields = services[SERVICE_ACTIVE_CONSUMERS]["fields"]
    assert active_fields[ATTR_THRESHOLD_WATTS]["required"] is False
    assert active_fields[ATTR_MAX_AGE_HOURS]["required"] is False
    assert active_fields[ATTR_LIMIT]["required"] is False

    set_fields = services[SERVICE_SET_ENERGY_ROLE]["fields"]
    assert set_fields[ATTR_ENTITY]["required"] is True
    assert set_fields[ATTR_ROLE]["required"] is True
    assert services[SERVICE_DELETE_ENERGY_ROLE]["fields"][ATTR_ENTITY]["required"] is True


async def test_active_consumers_service_dispatches_configured_defaults(hass) -> None:
    from homeassistant.core import ServiceCall

    from custom_components.ontology import _async_handle_active_consumers

    coordinator = AsyncMock()
    coordinator.entry.options = {
        CONF_MAX_MEASUREMENT_AGE_HOURS: 12.0,
        CONF_RELATIONSHIP_RESULT_LIMIT: 25,
    }
    call = ServiceCall(hass, DOMAIN, SERVICE_ACTIVE_CONSUMERS, {})
    expected = {"outcome": "empty"}

    with (
        patch("custom_components.ontology._loaded_coordinators", return_value=[coordinator]),
        patch(
            "custom_components.ontology.query_tools.active_consumers",
            AsyncMock(return_value=expected),
        ) as active_consumers,
    ):
        assert await _async_handle_active_consumers(call) == expected

    active_consumers.assert_awaited_once_with(
        coordinator.memgraph_client,
        threshold_watts=1.0,
        max_age_hours=12.0,
        limit=25,
    )


async def test_energy_role_services_reject_non_admin_before_graph_write(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    from homeassistant.core import Context
    from homeassistant.exceptions import Unauthorized

    entry = MockConfigEntry(domain=DOMAIN, data=mock_config_entry_data)
    entry.add_to_hass(hass)
    await hass.auth.async_create_user("owner")
    user = await hass.auth.async_create_user("non-admin")

    with patch(
        "custom_components.ontology.MemgraphClient", return_value=mock_memgraph_client
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        mock_memgraph_client.reset_mock()

        with pytest.raises(Unauthorized):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SET_ENERGY_ROLE,
                {ATTR_ENTITY: "sensor.dryer_power", ATTR_ROLE: "consumer"},
                blocking=True,
                return_response=True,
                context=Context(user_id=user.id),
            )

    mock_memgraph_client.run_query.assert_not_awaited()


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


# --- T010: v3 predefined query-tool / impact-analysis / context-export -----


def test_search_service_schema_declares_term_and_optional_limit() -> None:
    services = yaml.safe_load(SERVICES_YAML_PATH.read_text())
    fields = services[SERVICE_SEARCH]["fields"]
    assert fields[ATTR_TERM]["required"] is True
    assert fields[ATTR_LIMIT]["required"] is False


@pytest.mark.parametrize(
    ("service", "attr"),
    [
        (SERVICE_AREA_CONTEXT, ATTR_AREA),
        (SERVICE_DEVICE_CONTEXT, ATTR_DEVICE),
        (SERVICE_ENTITY_CONTEXT, ATTR_ENTITY),
        (SERVICE_AUTOMATION_DEPENDENCIES, ATTR_ENTITY),
    ],
)
def test_v3_context_service_schema_requires_its_target_field(service: str, attr: str) -> None:
    services = yaml.safe_load(SERVICES_YAML_PATH.read_text())
    fields = services[service]["fields"]
    assert fields[attr]["required"] is True


def test_impact_analysis_service_schema_requires_target_type_and_target() -> None:
    services = yaml.safe_load(SERVICES_YAML_PATH.read_text())
    fields = services[SERVICE_IMPACT_ANALYSIS]["fields"]
    assert fields[ATTR_TARGET_TYPE]["required"] is True
    assert fields[ATTR_TARGET]["required"] is True


def test_export_context_service_schema_requires_export_type_target_optional() -> None:
    services = yaml.safe_load(SERVICES_YAML_PATH.read_text())
    fields = services[SERVICE_EXPORT_CONTEXT]["fields"]
    assert fields[ATTR_EXPORT_TYPE]["required"] is True
    assert fields[ATTR_TARGET]["required"] is False


async def test_v3_services_return_the_common_tool_result_shape(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    """Every v3 service response is the shared `ToolResult` shape
    (data-model.md §2): `target`, `result_type`, `result`, `warnings`."""
    entry = MockConfigEntry(domain=DOMAIN, data=mock_config_entry_data)
    entry.add_to_hass(hass)
    mock_memgraph_client.run_query = AsyncMock(return_value=[])
    mock_memgraph_client.run_query_limited = AsyncMock(return_value=([], False))

    with patch(
        "custom_components.ontology.MemgraphClient", return_value=mock_memgraph_client
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.services.async_call(
        DOMAIN, SERVICE_SEARCH, {ATTR_TERM: "kitchen"}, blocking=True, return_response=True
    )
    assert set(result.keys()) == {
        "target",
        "result_type",
        "outcome",
        "result",
        "warnings",
    }
    assert result["result_type"] == "search"

    result = await hass.services.async_call(
        DOMAIN,
        SERVICE_ENTITY_CONTEXT,
        {ATTR_ENTITY: "light.missing"},
        blocking=True,
        return_response=True,
    )
    assert result["result_type"] == "not_found"
    assert result["result"] is None


def test_low_battery_service_schema_declares_validated_optional_overrides() -> None:
    services = yaml.safe_load(SERVICES_YAML_PATH.read_text())
    fields = services[SERVICE_LOW_BATTERY_AREAS]["fields"]

    assert set(fields) == {
        ATTR_THRESHOLD_PERCENTAGE,
        ATTR_MAX_AGE_HOURS,
        ATTR_LIMIT,
    }
    assert all(field["required"] is False for field in fields.values())
    assert fields[ATTR_THRESHOLD_PERCENTAGE]["selector"]["number"] == {
        "min": 1,
        "max": 100,
        "mode": "box",
    }
    assert fields[ATTR_MAX_AGE_HOURS]["selector"]["number"]["min"] > 0
    assert fields[ATTR_LIMIT]["selector"]["number"]["min"] == 1


async def test_low_battery_service_uses_options_and_accepts_valid_overrides(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=mock_config_entry_data,
        options={
            CONF_LOW_BATTERY_THRESHOLD: 15,
            CONF_MAX_MEASUREMENT_AGE_HOURS: 12,
            CONF_RELATIONSHIP_RESULT_LIMIT: 25,
        },
    )
    entry.add_to_hass(hass)
    expected = {
        "target": "home",
        "result_type": "low_battery_areas",
        "outcome": "empty",
        "result": {"areas": []},
        "warnings": [],
    }

    with (
        patch(
            "custom_components.ontology.MemgraphClient",
            return_value=mock_memgraph_client,
        ),
        patch(
            "custom_components.ontology.query_tools.low_battery_areas",
            AsyncMock(return_value=expected),
        ) as low_battery,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.services.async_call(
            DOMAIN,
            SERVICE_LOW_BATTERY_AREAS,
            {},
            blocking=True,
            return_response=True,
        )
        assert result == expected
        low_battery.assert_awaited_once_with(
            mock_memgraph_client,
            threshold_percentage=15,
            max_age_hours=12,
            limit=25,
        )

        await hass.services.async_call(
            DOMAIN,
            SERVICE_LOW_BATTERY_AREAS,
            {
                ATTR_THRESHOLD_PERCENTAGE: 30,
                ATTR_MAX_AGE_HOURS: 2,
                ATTR_LIMIT: 5,
            },
            blocking=True,
            return_response=True,
        )
        low_battery.assert_awaited_with(
            mock_memgraph_client,
            threshold_percentage=30,
            max_age_hours=2,
            limit=5,
        )


@pytest.mark.parametrize(
    "data",
    [
        {ATTR_THRESHOLD_PERCENTAGE: 0},
        {ATTR_THRESHOLD_PERCENTAGE: 101},
        {ATTR_MAX_AGE_HOURS: 0},
        {ATTR_LIMIT: 0},
        {ATTR_LIMIT: 1001},
    ],
)
async def test_low_battery_service_rejects_invalid_overrides_before_query(
    hass, mock_memgraph_client, mock_config_entry_data, data
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=mock_config_entry_data)
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.ontology.MemgraphClient",
            return_value=mock_memgraph_client,
        ),
        patch(
            "custom_components.ontology.query_tools.low_battery_areas",
            AsyncMock(),
        ) as low_battery,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        with pytest.raises(vol.Invalid):
            await hass.services.async_call(
                DOMAIN,
                SERVICE_LOW_BATTERY_AREAS,
                data,
                blocking=True,
                return_response=True,
            )
        low_battery.assert_not_awaited()

