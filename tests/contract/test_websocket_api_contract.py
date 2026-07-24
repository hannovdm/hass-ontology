"""Contract tests for the ontology explorer's `websocket_api` commands
(User Story 3, contracts/websocket-api.md): `ontology/area_context`,
`ontology/entity_context`, `ontology/search`.

Handlers are invoked directly (bypassing the real websocket transport,
which pytest-homeassistant-custom-component does not expose a client
fixture for) since `@websocket_api.async_response` only schedules the
underlying coroutine as a background task - calling the decorated
function and then `hass.async_block_till_done()` runs it to completion
exactly as the real dispatcher would (T020, T021, T022)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import voluptuous as vol
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import websocket_api as ontology_ws
from custom_components.ontology.const import DOMAIN, MAX_QUERY_LIMIT


async def _setup_loaded_entry(
    hass, mock_memgraph_client, mock_config_entry_data
) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=mock_config_entry_data)
    entry.add_to_hass(hass)
    with patch("custom_components.ontology.MemgraphClient", return_value=mock_memgraph_client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def _call_command(hass, handler, msg: dict) -> MagicMock:
    connection = MagicMock()
    handler(hass, connection, msg)
    await hass.async_block_till_done()
    return connection


# ---------------------------------------------------------------------------
# ontology/area_context (T020, FR-031)
# ---------------------------------------------------------------------------


async def test_area_context_returns_area_devices_and_entities_shape(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    await _setup_loaded_entry(hass, mock_memgraph_client, mock_config_entry_data)
    mock_memgraph_client.run_query.return_value = [
        {
            "a": {"ha_id": "living_room", "name": "Living Room"},
            "devices": [{"ha_id": "device-1", "name": "Lamp"}],
            "entities": [
                {
                    "entity": {"ha_id": "light.lamp", "name": "Lamp"},
                    "semantic_types": ["EnergyAsset"],
                }
            ],
        }
    ]

    connection = await _call_command(
        hass,
        ontology_ws._handle_area_context,
        {"id": 1, "type": "ontology/area_context", "area_id": "living_room"},
    )

    connection.send_result.assert_called_once()
    call_id, result = connection.send_result.call_args.args
    assert call_id == 1
    assert set(result.keys()) == {"area", "devices", "entities"}
    assert result["area"]["ha_id"] == "living_room"
    assert result["devices"][0]["ha_id"] == "device-1"
    assert result["entities"][0]["entity"]["ha_id"] == "light.lamp"
    assert result["entities"][0]["semantic_types"] == ["EnergyAsset"]
    connection.send_error.assert_not_called()


async def test_area_context_not_found_sends_error(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    await _setup_loaded_entry(hass, mock_memgraph_client, mock_config_entry_data)
    mock_memgraph_client.run_query.return_value = []

    connection = await _call_command(
        hass,
        ontology_ws._handle_area_context,
        {"id": 2, "type": "ontology/area_context", "area_id": "nowhere"},
    )

    connection.send_error.assert_called_once()
    call_id, error_code, _message = connection.send_error.call_args.args
    assert call_id == 2
    assert error_code == "not_found"
    connection.send_result.assert_not_called()


async def test_area_context_result_is_credential_free(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    """The response shape (area/devices/entities) never surfaces the
    Memgraph connection's host/username/password (only graph node data)."""
    await _setup_loaded_entry(hass, mock_memgraph_client, mock_config_entry_data)
    mock_memgraph_client.run_query.return_value = [
        {"a": {"ha_id": "living_room", "name": "Living Room"}, "devices": [], "entities": []}
    ]

    connection = await _call_command(
        hass,
        ontology_ws._handle_area_context,
        {"id": 3, "type": "ontology/area_context", "area_id": "living_room"},
    )

    _call_id, result = connection.send_result.call_args.args
    assert set(result.keys()) == {"area", "devices", "entities"}
    assert "password" not in result["area"]
    assert "host" not in result["area"]


# ---------------------------------------------------------------------------
# ontology/entity_context (T021, FR-032)
# ---------------------------------------------------------------------------


async def test_entity_context_returns_full_shape(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    await _setup_loaded_entry(hass, mock_memgraph_client, mock_config_entry_data)
    mock_memgraph_client.run_query.return_value = [
        {
            "e": {"ha_id": "light.lamp", "name": "Lamp"},
            "d": {"ha_id": "device-1", "name": "Lamp Device"},
            "area": {"ha_id": "living_room", "name": "Living Room"},
            "semantic_types": ["EnergyAsset"],
            "dependents": [{"ha_id": "dashboard-1"}],
            "cards": [{"ha_id": "dashboard-1::0::0"}],
        }
    ]

    connection = await _call_command(
        hass,
        ontology_ws._handle_entity_context,
        {"id": 1, "type": "ontology/entity_context", "entity_id": "light.lamp"},
    )

    connection.send_result.assert_called_once()
    _call_id, result = connection.send_result.call_args.args
    assert set(result.keys()) == {
        "entity",
        "state",
        "device",
        "area",
        "semantic_types",
        "dependents",
        "cards",
    }
    assert result["entity"]["ha_id"] == "light.lamp"
    assert result["device"]["ha_id"] == "device-1"
    assert result["area"]["ha_id"] == "living_room"
    assert result["semantic_types"] == ["EnergyAsset"]
    assert result["dependents"] == [{"ha_id": "dashboard-1"}]
    assert result["cards"] == [{"ha_id": "dashboard-1::0::0"}]


async def test_entity_context_not_found_sends_error(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    await _setup_loaded_entry(hass, mock_memgraph_client, mock_config_entry_data)
    mock_memgraph_client.run_query.return_value = []

    connection = await _call_command(
        hass,
        ontology_ws._handle_entity_context,
        {"id": 2, "type": "ontology/entity_context", "entity_id": "light.missing"},
    )

    connection.send_error.assert_called_once()
    _call_id, error_code, _message = connection.send_error.call_args.args
    assert error_code == "not_found"


async def test_entity_context_result_is_credential_free(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    await _setup_loaded_entry(hass, mock_memgraph_client, mock_config_entry_data)
    mock_memgraph_client.run_query.return_value = [
        {
            "e": {"ha_id": "light.lamp", "name": "Lamp"},
            "d": None,
            "area": None,
            "semantic_types": [],
            "dependents": [],
            "cards": [],
        }
    ]

    connection = await _call_command(
        hass,
        ontology_ws._handle_entity_context,
        {"id": 3, "type": "ontology/entity_context", "entity_id": "light.lamp"},
    )

    _call_id, result = connection.send_result.call_args.args
    assert "password" not in result["entity"]
    assert "host" not in result["entity"]


# ---------------------------------------------------------------------------
# ontology/search (T022, FR-033)
# ---------------------------------------------------------------------------


async def test_search_returns_typed_results_shape(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    await _setup_loaded_entry(hass, mock_memgraph_client, mock_config_entry_data)
    mock_memgraph_client.run_query_limited.return_value = (
        [{"labels": ["Entity"], "node": {"ha_id": "light.lamp", "name": "Lamp"}}],
        False,
    )

    connection = await _call_command(
        hass,
        ontology_ws._handle_search,
        {"id": 1, "type": "ontology/search", "query": "lamp"},
    )

    connection.send_result.assert_called_once()
    _call_id, result = connection.send_result.call_args.args
    assert set(result.keys()) == {"results", "truncated"}
    assert result["truncated"] is False
    assert result["results"] == [{"type": "Entity", "ha_id": "light.lamp", "name": "Lamp"}]


async def test_search_input_validation_requires_query_field() -> None:
    """T022: the registered schema rejects a message missing `query`."""
    schema = ontology_ws._handle_search._ws_schema
    with pytest.raises(vol.Invalid):
        schema({"id": 1, "type": "ontology/search"})
    # A well-formed message passes validation.
    schema({"id": 1, "type": "ontology/search", "query": "lamp"})


async def test_search_limit_is_bounded_by_max_query_limit(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    await _setup_loaded_entry(hass, mock_memgraph_client, mock_config_entry_data)
    mock_memgraph_client.run_query_limited.return_value = ([], False)

    await _call_command(
        hass,
        ontology_ws._handle_search,
        {"id": 1, "type": "ontology/search", "query": "lamp", "limit": 999999},
    )

    mock_memgraph_client.run_query_limited.assert_awaited_once()
    _query, _params, limit = mock_memgraph_client.run_query_limited.call_args.args
    assert limit == MAX_QUERY_LIMIT


async def test_search_result_is_credential_free(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    await _setup_loaded_entry(hass, mock_memgraph_client, mock_config_entry_data)
    mock_memgraph_client.run_query_limited.return_value = (
        [{"labels": ["Entity"], "node": {"ha_id": "light.lamp", "name": "Lamp"}}],
        False,
    )

    connection = await _call_command(
        hass,
        ontology_ws._handle_search,
        {"id": 1, "type": "ontology/search", "query": "lamp"},
    )

    _call_id, result = connection.send_result.call_args.args
    for entry in result["results"]:
        assert set(entry.keys()) == {"type", "ha_id", "name"}
