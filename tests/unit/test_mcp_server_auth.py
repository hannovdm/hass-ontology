"""Unit tests for the local MCP endpoint's auth/binding/write-rejection
logic (User Story 7): T050 (token generation/persistence/regeneration),
T051 (non-local `request.remote` rejected 403), T052 (missing/invalid
bearer token rejected 401, no tool executes), T053 (a `query` tool call
containing any disallowed keyword - including mixed read+write - is
rejected in full before execution)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.ontology import mcp_server


class _FakeRequest:
    def __init__(self, remote: str | None, headers: dict | None = None, body: dict | None = None):
        self.remote = remote
        self.headers = headers or {}
        self._body = body or {}

    async def json(self):
        return self._body


async def test_token_generated_persisted_and_reused(hass) -> None:
    token1, created1 = await mcp_server.async_get_or_create_token(hass, "entry1")
    assert created1 is True
    assert len(token1) > 20

    token2, created2 = await mcp_server.async_get_or_create_token(hass, "entry1")
    assert created2 is False
    assert token2 == token1


async def test_regenerate_token_invalidates_previous(hass) -> None:
    token1, _ = await mcp_server.async_get_or_create_token(hass, "entry2")
    token2 = await mcp_server.async_regenerate_token(hass, "entry2")
    assert token2 != token1
    assert await mcp_server.async_get_token(hass, "entry2") == token2


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("192.168.1.5", True),
        ("10.0.0.5", True),
        ("8.8.8.8", False),
        (None, False),
        ("not-an-ip", False),
    ],
)
def test_is_local_remote(remote: str | None, expected: bool) -> None:
    assert mcp_server._is_local_remote(remote) is expected


async def test_non_local_request_rejected_with_403(hass) -> None:
    entry = SimpleNamespace(entry_id="entry3", runtime_data=SimpleNamespace(memgraph_client=None))
    view = mcp_server.OntologyMcpView(hass, entry)
    request = _FakeRequest(remote="8.8.8.8")

    response = await view.post(request)
    assert response.status == 403


async def test_missing_or_invalid_token_rejected_with_401_and_no_tool_executes(hass) -> None:
    await mcp_server.async_get_or_create_token(hass, "entry4")
    client = AsyncMock()
    entry = SimpleNamespace(entry_id="entry4", runtime_data=SimpleNamespace(memgraph_client=client))
    view = mcp_server.OntologyMcpView(hass, entry)
    request = _FakeRequest(
        remote="127.0.0.1",
        headers={"Authorization": "Bearer wrong-token"},
        body={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search"}},
    )

    response = await view.post(request)
    assert response.status == 401
    client.run_query.assert_not_awaited()
    client.run_query_limited.assert_not_awaited()


@pytest.mark.parametrize(
    "cypher",
    [
        "CREATE (n:Area) RETURN n",
        "MATCH (n:Entity) RETURN n LIMIT 1 CREATE (m:Area) RETURN m",  # mixed read+write
        "MATCH (n) DETACH DELETE n",
    ],
)
async def test_query_tool_write_intent_rejected_before_execution(hass, cypher: str) -> None:
    token, _ = await mcp_server.async_get_or_create_token(hass, "entry5")
    client = AsyncMock()
    client.run_query_limited = AsyncMock(return_value=([], False))
    entry = SimpleNamespace(entry_id="entry5", runtime_data=SimpleNamespace(memgraph_client=client))
    view = mcp_server.OntologyMcpView(hass, entry)
    request = _FakeRequest(
        remote="127.0.0.1",
        headers={"Authorization": f"Bearer {token}"},
        body={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "query", "arguments": {"cypher": cypher}},
        },
    )

    response = await view.post(request)
    body = json.loads(response.body)
    assert "error" in body
    client.run_query_limited.assert_not_awaited()

    records = await mcp_server.agent_audit.async_get_records(hass, "entry5")
    assert any(r["event"] == "mcp_write_rejected" for r in records)
