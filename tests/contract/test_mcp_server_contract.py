"""Contract test (T054): `initialize`, `tools/list` (8 read-only tools with
`inputSchema`), and `tools/call` JSON-RPC shapes (contracts/mcp-endpoint.md)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from custom_components.ontology import mcp_server
from custom_components.ontology.const import MCP_TOOL_NAMES


class _FakeRequest:
    def __init__(self, remote: str | None, headers: dict | None = None, body: dict | None = None):
        self.remote = remote
        self.headers = headers or {}
        self._body = body or {}

    async def json(self):
        return self._body


async def _make_view(hass, entry_id: str, client=None):
    token, _ = await mcp_server.async_get_or_create_token(hass, entry_id)
    entry = SimpleNamespace(
        entry_id=entry_id, runtime_data=SimpleNamespace(memgraph_client=client or AsyncMock())
    )
    return mcp_server.OntologyMcpView(hass, entry), token


async def test_initialize_declares_tools_capability_only(hass) -> None:
    view, token = await _make_view(hass, "mcp_init")
    request = _FakeRequest(
        remote="127.0.0.1",
        headers={"Authorization": f"Bearer {token}"},
        body={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    response = await view.post(request)
    body = json.loads(response.body)
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert body["result"]["capabilities"] == {"tools": {}}


async def test_tools_list_returns_exactly_the_eight_read_only_tools_with_input_schema(hass) -> None:
    view, token = await _make_view(hass, "mcp_list")
    request = _FakeRequest(
        remote="127.0.0.1",
        headers={"Authorization": f"Bearer {token}"},
        body={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    response = await view.post(request)
    body = json.loads(response.body)
    tools = body["result"]["tools"]
    assert {tool["name"] for tool in tools} == set(MCP_TOOL_NAMES)
    assert len(tools) == 8
    for tool in tools:
        assert "inputSchema" in tool
        assert tool["inputSchema"]["type"] == "object"


async def test_tools_call_success_response_shape(hass) -> None:
    client = AsyncMock()
    client.run_query = AsyncMock(return_value=[])
    view, token = await _make_view(hass, "mcp_call", client=client)
    request = _FakeRequest(
        remote="127.0.0.1",
        headers={"Authorization": f"Bearer {token}"},
        body={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "area_context", "arguments": {"area": "kitchen"}},
        },
    )
    response = await view.post(request)
    body = json.loads(response.body)
    assert body["result"]["content"][0]["type"] == "text"
    tool_result = json.loads(body["result"]["content"][0]["text"])
    assert tool_result["result_type"] == "not_found"  # empty rows -> not resolved


async def test_tools_call_write_rejection_is_a_jsonrpc_error(hass) -> None:
    client = AsyncMock()
    client.run_query_limited = AsyncMock(return_value=([], False))
    view, token = await _make_view(hass, "mcp_write_reject", client=client)
    request = _FakeRequest(
        remote="127.0.0.1",
        headers={"Authorization": f"Bearer {token}"},
        body={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "query", "arguments": {"cypher": "CREATE (n) RETURN n"}},
        },
    )
    response = await view.post(request)
    body = json.loads(response.body)
    assert "error" in body
    assert "code" in body["error"]
