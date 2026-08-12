"""Local, opt-in, token-authenticated MCP-compatible endpoint (User Story 7).

Mounted at `POST /api/ontology/mcp` (contracts/mcp-endpoint.md), registered
only when `CONF_MCP_ENABLED` is on (default off, FR-023, SC-003). Implements
the minimal non-streaming JSON-RPC-over-HTTP subset of MCP needed for v3:
`initialize`, `tools/list`, `tools/call` (research.md §2), dispatching to the
same shared `query_tools`/`impact_analysis`/`context_export`/`query_service`
functions used by services and Assist intents (research.md §7).
"""

from __future__ import annotations

import ipaddress
import json
import logging
import secrets
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from . import agent_audit, context_export, impact_analysis, query_tools
from .const import (
    AUDIT_EVENT_MCP_AUTH_REJECTED,
    AUDIT_EVENT_MCP_TOOL_CALL,
    AUDIT_EVENT_MCP_WRITE_REJECTED,
    CONF_MCP_ALLOWED_NETWORKS,
    CONF_MCP_ENABLED,
    DEFAULT_MCP_ALLOWED_NETWORKS,
    DEFAULT_MCP_ENABLED,
    EXPORT_TYPES,
    IMPACT_SCOPES,
    MCP_ENDPOINT_URL,
    MCP_TOKEN_STORE_KEY_PREFIX,
    MCP_TOKEN_STORE_VERSION,
    MCP_TOOL_NAMES,
    RESULT_TYPE_QUERY,
)
from .memgraph_client import MemgraphClient
from .query_service import QueryRejected, execute_query, find_denylisted_keyword

_LOGGER = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2024-11-05"

_LOCAL_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)

_TOOL_INPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "search": {
        "type": "object",
        "properties": {"term": {"type": "string"}, "limit": {"type": "integer"}},
        "required": ["term"],
    },
    "entity_context": {
        "type": "object",
        "properties": {"entity": {"type": "string"}},
        "required": ["entity"],
    },
    "area_context": {
        "type": "object",
        "properties": {"area": {"type": "string"}},
        "required": ["area"],
    },
    "device_context": {
        "type": "object",
        "properties": {"device": {"type": "string"}},
        "required": ["device"],
    },
    "automation_dependencies": {
        "type": "object",
        "properties": {"entity": {"type": "string"}},
        "required": ["entity"],
    },
    "impact_analysis": {
        "type": "object",
        "properties": {
            "target_type": {"type": "string", "enum": list(IMPACT_SCOPES)},
            "target": {"type": "string"},
        },
        "required": ["target_type", "target"],
    },
    "query": {
        "type": "object",
        "properties": {
            "cypher": {"type": "string"},
            "parameters": {"type": "object"},
            "limit": {"type": "integer"},
        },
        "required": ["cypher"],
    },
    "export_context": {
        "type": "object",
        "properties": {
            "export_type": {"type": "string", "enum": list(EXPORT_TYPES)},
            "target": {"type": "string"},
        },
        "required": ["export_type"],
    },
}


def _token_store(hass: HomeAssistant, entry_id: str) -> Store:
    return Store(hass, MCP_TOKEN_STORE_VERSION, f"{MCP_TOKEN_STORE_KEY_PREFIX}{entry_id}")


async def async_get_or_create_token(hass: HomeAssistant, entry_id: str) -> tuple[str, bool]:
    """Return `(token, created)`; generates + persists a token on first use (research.md §3)."""
    store = _token_store(hass, entry_id)
    data = await store.async_load()
    if data and data.get("token"):
        return data["token"], False
    token = secrets.token_urlsafe(32)
    await store.async_save(
        {"entry_id": entry_id, "token": token, "created_at": agent_audit.now_iso()}
    )
    return token, True


async def async_regenerate_token(hass: HomeAssistant, entry_id: str) -> str:
    """Regenerate the MCP access token, immediately invalidating the previous one."""
    store = _token_store(hass, entry_id)
    token = secrets.token_urlsafe(32)
    await store.async_save(
        {"entry_id": entry_id, "token": token, "created_at": agent_audit.now_iso()}
    )
    return token


async def async_get_token(hass: HomeAssistant, entry_id: str) -> str | None:
    data = await _token_store(hass, entry_id).async_load()
    return data.get("token") if data else None


def _is_local_remote(remote: str | None) -> bool:
    """True if `remote` is loopback or within a local/private network range (FR-024)."""
    if not remote:
        return False
    try:
        address = ipaddress.ip_address(remote)
    except ValueError:
        return False
    return any(address in network for network in _LOCAL_NETWORKS)


def _is_remote_allowed(remote: str | None, configured_networks: str) -> bool:
    """Check HA's trusted-proxy-resolved remote against configured CIDRs."""
    if not remote:
        return False
    try:
        address = ipaddress.ip_address(remote)
        networks = [
            ipaddress.ip_network(value.strip(), strict=False)
            for value in configured_networks.split(",")
            if value.strip()
        ]
    except ValueError:
        return False
    return any(address in network for network in networks)


def _jsonrpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "hass-ontology", "version": "3"},
    }


def _tools_list_result() -> dict[str, Any]:
    return {
        "tools": [
            {"name": name, "inputSchema": _TOOL_INPUT_SCHEMAS[name]} for name in MCP_TOOL_NAMES
        ]
    }


class OntologyMcpView(HomeAssistantView):
    """`POST /api/ontology/mcp` - see contracts/mcp-endpoint.md."""

    url = MCP_ENDPOINT_URL
    name = "api:ontology:mcp"
    # Auth is enforced by this view itself (a per-entry local access token),
    # not Home Assistant's own user/long-lived-token auth (FR-034,
    # research.md §3) - so any local MCP client can call it, not only an
    # authenticated HA frontend session.
    requires_auth = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry

    async def _async_audit(self, record: dict[str, Any]) -> None:
        await agent_audit.async_append_record(self._hass, self._entry.entry_id, record)

    async def post(self, request: web.Request) -> web.Response:
        if not self._entry.options.get(CONF_MCP_ENABLED, DEFAULT_MCP_ENABLED):
            return web.json_response({"error": "Not Found"}, status=404)

        configured_networks = self._entry.options.get(
            CONF_MCP_ALLOWED_NETWORKS, DEFAULT_MCP_ALLOWED_NETWORKS
        )
        # Home Assistant's forwarded middleware has already replaced
        # request.remote only when X-Forwarded-For came through a trusted proxy.
        if not _is_remote_allowed(request.remote, configured_networks):
            await self._async_audit(
                {
                    "event": AUDIT_EVENT_MCP_AUTH_REJECTED,
                    "tool": None,
                    "client_id": request.remote or "unknown",
                    "status": "rejected",
                    "result_count": None,
                    "error_category": "network_not_allowed",
                    "timestamp": agent_audit.now_iso(),
                }
            )
            return web.json_response({"error": "Forbidden: not a local request"}, status=403)

        token = await async_get_token(self._hass, self._entry.entry_id)
        auth_header = request.headers.get("Authorization", "")
        supplied = auth_header[7:] if auth_header.startswith("Bearer ") else None
        if not token or not supplied or not secrets.compare_digest(supplied, token):
            await self._async_audit(
                {
                    "event": AUDIT_EVENT_MCP_AUTH_REJECTED,
                    "tool": None,
                    "client_id": request.remote or "unknown",
                    "status": "rejected",
                    "result_count": None,
                    "error_category": "invalid_token",
                    "timestamp": agent_audit.now_iso(),
                }
            )
            return web.json_response({"error": "Unauthorized"}, status=401)

        try:
            payload = await request.json()
        except (ValueError, json.JSONDecodeError):
            await self._async_audit(
                {
                    "event": AUDIT_EVENT_MCP_TOOL_CALL,
                    "tool": None,
                    "client_id": request.remote or "unknown",
                    "status": "error",
                    "result_count": None,
                    "error_category": "parse_error",
                    "timestamp": agent_audit.now_iso(),
                }
            )
            return web.json_response(_jsonrpc_error(None, -32700, "Parse error"), status=400)

        method = payload.get("method")
        request_id = payload.get("id")
        client = self._entry.runtime_data.memgraph_client

        if method == "initialize":
            return web.json_response(_jsonrpc_result(request_id, _initialize_result()))
        if method == "tools/list":
            return web.json_response(_jsonrpc_result(request_id, _tools_list_result()))
        if method == "tools/call":
            return await self._handle_tools_call(
                request, request_id, client, payload.get("params") or {}
            )
        await self._async_audit(
            {
                "event": AUDIT_EVENT_MCP_TOOL_CALL,
                "tool": None,
                "client_id": request.remote or "unknown",
                "status": "rejected",
                "result_count": None,
                "error_category": "unknown_method",
                "timestamp": agent_audit.now_iso(),
            }
        )
        return web.json_response(
            _jsonrpc_error(request_id, -32601, f"Unknown method {method!r}"), status=400
        )

    async def _handle_tools_call(
        self,
        request: web.Request,
        request_id: Any,
        client: MemgraphClient,
        params: dict[str, Any],
    ) -> web.Response:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        client_id = request.remote or "unknown"

        if name == "query":
            cypher = arguments.get("cypher", "")
            try:
                result = await execute_query(
                    client, cypher, arguments.get("parameters"), arguments.get("limit")
                )
            except QueryRejected as err:
                rejected_operation = find_denylisted_keyword(cypher)
                await self._async_audit(
                    {
                        "event": AUDIT_EVENT_MCP_WRITE_REJECTED,
                        "tool": name,
                        "client_id": client_id,
                        "status": "rejected",
                        "result_count": None,
                        "error_category": "write_intent_detected",
                        "rejected_operation": rejected_operation,
                        "timestamp": agent_audit.now_iso(),
                    }
                )
                return web.json_response(
                    _jsonrpc_error(request_id, -32000, str(err)), status=400
                )
            tool_result = query_tools.build_tool_result(cypher, RESULT_TYPE_QUERY, result)
        else:
            try:
                if name == "search":
                    tool_result = await query_tools.search(
                        client, arguments.get("term", ""), arguments.get("limit")
                    )
                elif name == "area_context":
                    tool_result = await query_tools.area_context(client, arguments.get("area", ""))
                elif name == "device_context":
                    tool_result = await query_tools.device_context(
                        client, arguments.get("device", "")
                    )
                elif name == "entity_context":
                    tool_result = await query_tools.entity_context(
                        client, arguments.get("entity", "")
                    )
                elif name == "automation_dependencies":
                    tool_result = await query_tools.automation_dependencies(
                        client, arguments.get("entity", "")
                    )
                elif name == "impact_analysis":
                    tool_result = await impact_analysis.analyze(
                        client, arguments.get("target_type", ""), arguments.get("target", "")
                    )
                elif name == "export_context":
                    tool_result = await context_export.export(
                        client, arguments.get("export_type", ""), arguments.get("target")
                    )
                else:
                    await self._async_audit(
                        {
                            "event": AUDIT_EVENT_MCP_TOOL_CALL,
                            "tool": name,
                            "client_id": client_id,
                            "status": "rejected",
                            "result_count": None,
                            "error_category": "unknown_tool",
                            "timestamp": agent_audit.now_iso(),
                        }
                    )
                    return web.json_response(
                        _jsonrpc_error(request_id, -32601, f"Unknown tool {name!r}"), status=400
                    )
            except Exception as err:
                await self._async_audit(
                    {
                        "event": AUDIT_EVENT_MCP_TOOL_CALL,
                        "tool": name,
                        "client_id": client_id,
                        "status": "error",
                        "result_count": 0,
                        "error_category": type(err).__name__,
                        "timestamp": agent_audit.now_iso(),
                    }
                )
                return web.json_response(
                    _jsonrpc_error(request_id, -32603, "Internal error"), status=500
                )

        await self._async_audit(
            {
                "event": AUDIT_EVENT_MCP_TOOL_CALL,
                "tool": name,
                "client_id": client_id,
                "status": (
                    "not_found"
                    if tool_result.get("result_type") == "not_found"
                    else "ok"
                ),
                "result_count": query_tools.count_results(tool_result.get("result")),
                "error_category": None,
                "timestamp": agent_audit.now_iso(),
            }
        )
        return web.json_response(
            _jsonrpc_result(
                request_id, {"content": [{"type": "text", "text": json.dumps(tool_result)}]}
            )
        )
