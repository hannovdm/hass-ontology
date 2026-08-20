"""Contract tests for the authenticated area-first graph snapshot command."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol

from custom_components import ontology
from custom_components.ontology import websocket_api as ontology_ws
from custom_components.ontology.const import (
    GRAPH_EXPAND_EDGE_LIMIT,
    GRAPH_EXPAND_NODE_LIMIT,
    GRAPH_INITIAL_NODE_LIMIT,
    GRAPH_SEARCH_LIMIT,
)


async def _call_snapshot(hass, result: dict, msg: dict | None = None) -> tuple[MagicMock, AsyncMock]:
    gateway = AsyncMock()
    gateway.initial_graph.return_value = result
    connection = MagicMock()
    connection.user = MagicMock(is_admin=False)
    message = {
        "id": 1,
        "type": "ontology/graph_snapshot",
        "limit": GRAPH_INITIAL_NODE_LIMIT,
        "cursor": None,
        **(msg or {}),
    }

    with patch.object(ontology_ws, "_first_loaded_gateway", return_value=gateway):
        ontology_ws._handle_graph_snapshot(hass, connection, message)
        await hass.async_block_till_done(wait_background_tasks=True)

    return connection, gateway


async def _call_graph_handler(
    hass,
    handler,
    gateway: AsyncMock,
    message: dict,
) -> MagicMock:
    connection = MagicMock()
    connection.user = MagicMock(is_admin=False)
    with patch.object(ontology_ws, "_first_loaded_gateway", return_value=gateway):
        handler(hass, connection, message)
        await hass.async_block_till_done(wait_background_tasks=True)
    return connection


def test_graph_snapshot_schema_defaults_to_100_and_accepts_legacy_requests() -> None:
    schema = ontology_ws._handle_graph_snapshot._ws_schema

    assert schema({"id": 1, "type": "ontology/graph_snapshot"})["limit"] == 100
    assert schema({"id": 1, "type": "ontology/graph_snapshot", "limit": 1})["limit"] == 1
    assert schema({"id": 1, "type": "ontology/graph_snapshot", "limit": 500})["limit"] == 500
    with pytest.raises(vol.Invalid):
        schema({"id": 1, "type": "ontology/graph_snapshot", "limit": 501})
    with pytest.raises(vol.Invalid):
        schema({"id": 1, "type": "ontology/graph_snapshot", "limit": 0})


async def test_graph_snapshot_allows_authenticated_non_admin_and_shapes_response(hass) -> None:
    result = {
        "nodes": [
            {
                "id": "Area:kitchen",
                "haId": "kitchen",
                "type": "AREA",
                "label": "Kitchen",
                "icon": "mdi:countertop-outline",
                "unavailable": False,
                "properties": [],
            },
            {
                "id": "Device:orphan",
                "haId": "orphan",
                "type": "DEVICE",
                "label": "Portable sensor",
                "icon": None,
                "unavailable": True,
                "properties": [],
            },
        ],
        "relationships": [],
        "truncated": True,
        "nextCursor": "opaque-page-2",
        "revision": 7,
    }

    connection, gateway = await _call_snapshot(hass, result)

    gateway.initial_graph.assert_awaited_once_with(100, None)
    connection.send_error.assert_not_called()
    call_id, response = connection.send_result.call_args.args
    assert call_id == 1
    assert response == {
        "nodes": result["nodes"],
        "relationships": [],
        "truncated": True,
        "next_cursor": "opaque-page-2",
        "revision": 7,
    }
    assert response["nodes"][1]["id"] == "Device:orphan"
    assert all(node["id"] != "presentation:unassigned" for node in response["nodes"])
    assert "token" not in repr(response).lower()
    assert "password" not in repr(response).lower()


async def test_graph_snapshot_passes_cursor_and_requested_limit(hass) -> None:
    connection, gateway = await _call_snapshot(
        hass,
        {
            "nodes": [],
            "relationships": [],
            "truncated": False,
            "nextCursor": None,
            "revision": 3,
        },
        {"limit": 125, "cursor": "opaque-page-1"},
    )

    gateway.initial_graph.assert_awaited_once_with(125, "opaque-page-1")
    connection.send_result.assert_called_once()


async def test_graph_snapshot_reports_gateway_unavailability_without_details(hass) -> None:
    connection, _gateway = await _call_snapshot(
        hass,
        {
            "available": False,
            "error": "gateway_unavailable",
            "nodes": [],
            "relationships": [],
            "truncated": False,
            "nextCursor": None,
            "revision": 0,
        },
    )

    connection.send_result.assert_not_called()
    call_id, code, message = connection.send_error.call_args.args
    assert call_id == 1
    assert code == "gateway_unavailable"
    assert "token" not in message.lower()
    assert "graphql" not in message.lower()


def test_graph_exploration_schemas_enforce_contract_defaults_and_maxima() -> None:
    search_schema = ontology_ws._handle_graph_search._ws_schema
    detail_schema = ontology_ws._handle_graph_detail._ws_schema
    expand_schema = ontology_ws._handle_graph_expand._ws_schema

    assert search_schema({"id": 1, "type": "ontology/graph_search", "term": " kitchen "})["limit"] == GRAPH_SEARCH_LIMIT
    assert detail_schema({"id": 1, "type": "ontology/graph_detail", "element_id": "Device:lamp"})["element_id"] == "Device:lamp"
    expanded = expand_schema({"id": 1, "type": "ontology/graph_expand", "node_id": "Device:lamp"})
    assert expanded["node_limit"] == GRAPH_EXPAND_NODE_LIMIT
    assert expanded["edge_limit"] == GRAPH_EXPAND_EDGE_LIMIT
    assert expanded["cursor"] is None

    with pytest.raises(vol.Invalid):
        search_schema({"id": 1, "type": "ontology/graph_search", "term": "", "limit": 1})
    with pytest.raises(vol.Invalid):
        search_schema({"id": 1, "type": "ontology/graph_search", "term": "x", "limit": 101})
    with pytest.raises(vol.Invalid):
        expand_schema({"id": 1, "type": "ontology/graph_expand", "node_id": "Device:lamp", "node_limit": 251})
    with pytest.raises(vol.Invalid):
        expand_schema({"id": 1, "type": "ontology/graph_expand", "node_id": "Device:lamp", "edge_limit": 501})


async def test_graph_search_returns_backend_neutral_matches(hass) -> None:
    gateway = AsyncMock()
    gateway.search_graph.return_value = {
        "matches": [{"id": "Device:lamp", "haId": "lamp", "type": "DEVICE", "label": "Kitchen lamp", "icon": "mdi:lightbulb"}],
        "truncated": False,
        "revision": 8,
    }
    connection = await _call_graph_handler(
        hass,
        ontology_ws._handle_graph_search,
        gateway,
        {"id": 2, "type": "ontology/graph_search", "term": " Kitchen lamp ", "limit": 50},
    )

    gateway.search_graph.assert_awaited_once_with("Kitchen lamp", 50)
    connection.send_result.assert_called_once_with(2, gateway.search_graph.return_value)
    assert "token" not in repr(connection.send_result.call_args).lower()


async def test_graph_detail_returns_safe_element_and_not_found(hass) -> None:
    gateway = AsyncMock()
    gateway.graph_element.return_value = None
    connection = await _call_graph_handler(
        hass,
        ontology_ws._handle_graph_detail,
        gateway,
        {"id": 3, "type": "ontology/graph_detail", "element_id": "Device:missing"},
    )

    connection.send_result.assert_not_called()
    connection.send_error.assert_called_once_with(3, "not_found", "Graph element was not found")


@pytest.mark.parametrize("element_id", ["missing-colon", ":lamp", "Device:", "Device:lamp\nsecret"])
async def test_graph_detail_rejects_malformed_stable_ids(hass, element_id: str) -> None:
    gateway = AsyncMock()
    connection = await _call_graph_handler(
        hass,
        ontology_ws._handle_graph_detail,
        gateway,
        {"id": 4, "type": "ontology/graph_detail", "element_id": element_id},
    )

    gateway.graph_element.assert_not_awaited()
    connection.send_error.assert_called_once_with(4, "invalid_format", "Graph element ID is invalid")


async def test_graph_expand_passes_defaults_and_shapes_cursor(hass) -> None:
    gateway = AsyncMock()
    gateway.expand_node.return_value = {
        "nodes": [{"id": "Device:lamp"}],
        "relationships": [],
        "truncated": True,
        "nextCursor": "revision-8:page-2",
        "revision": 8,
    }
    connection = await _call_graph_handler(
        hass,
        ontology_ws._handle_graph_expand,
        gateway,
        {"id": 5, "type": "ontology/graph_expand", "node_id": "Device:lamp", "node_limit": 100, "edge_limit": 250, "cursor": None},
    )

    gateway.expand_node.assert_awaited_once_with("Device:lamp", 100, 250, None)
    connection.send_result.assert_called_once_with(
        5,
        {
            "nodes": [{"id": "Device:lamp"}],
            "relationships": [],
            "truncated": True,
            "next_cursor": "revision-8:page-2",
            "revision": 8,
        },
    )


@pytest.mark.parametrize("error", ["not_found", "stale_cursor"])
async def test_graph_expand_maps_expected_backend_errors(hass, error: str) -> None:
    gateway = AsyncMock()
    gateway.expand_node.return_value = {"available": False, "error": error}
    connection = await _call_graph_handler(
        hass,
        ontology_ws._handle_graph_expand,
        gateway,
        {"id": 6, "type": "ontology/graph_expand", "node_id": "Device:lamp", "node_limit": 100, "edge_limit": 250, "cursor": "old"},
    )

    connection.send_result.assert_not_called()
    connection.send_error.assert_called_once_with(6, error, "Graph expansion could not be completed")


async def test_panel_registration_allows_authenticated_non_admin_users() -> None:
    hass = MagicMock()
    hass.data = {}
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()

    integration = MagicMock(version="4.0.0b8")
    with (
        patch.object(ontology, "async_get_integration", new=AsyncMock(return_value=integration)),
        patch.object(ontology.panel_custom, "async_register_panel", new=AsyncMock()) as register,
    ):
        await ontology._async_register_panel(hass)

    static_paths = hass.http.async_register_static_paths.await_args.args[0]
    assert static_paths[0].url_path == "/ontology_static"
    register.assert_awaited_once()
    assert register.await_args.kwargs["module_url"] == "/ontology_static/ontology-panel.js?v=4.0.0b8"
    assert register.await_args.kwargs["require_admin"] is False