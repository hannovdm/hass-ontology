"""Integration test: agent audit lifecycle (User Story 8): T064 (an Assist
query records exactly one AssistQueryRecord, an MCP tool call records an
AgentQueryRecord, a rejected write records mcp_write_rejected, a rejected
token records mcp_auth_rejected), T065 (a record past the 30-day retention
window is no longer present after the window elapses)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from homeassistant.core import Context
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import intent
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import agent_audit, intent_handlers, mcp_server
from custom_components.ontology.const import CONF_HOST, CONF_MCP_ENABLED, CONF_PORT, DOMAIN
from custom_components.ontology.memgraph_client import MemgraphClient


async def _setup_entry(hass, memgraph_container, *, mcp_enabled: bool = True) -> MockConfigEntry:
    await async_setup_component(hass, "http", {})
    await hass.async_block_till_done()
    host = memgraph_container.get_container_host_ip()
    port = int(memgraph_container.get_exposed_port(7687))
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: host, CONF_PORT: port},
        options={CONF_MCP_ENABLED: mcp_enabled},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


class _Request:
    def __init__(self, remote: str, headers: dict, body: dict):
        self.remote = remote
        self.headers = headers
        self._body = body

    async def json(self):
        return self._body


async def test_assist_query_records_exactly_one_assist_query_record(
    hass, memgraph_container, memgraph_client: MemgraphClient
) -> None:
    entry = await _setup_entry(hass, memgraph_container, mcp_enabled=False)
    ar.async_get(hass).async_create("Audit Area")
    handler = intent_handlers.OntologyAreaContents()
    intent_obj = intent.Intent(
        hass,
        platform="test",
        intent_type=handler.intent_type,
        slots={"ontology_area": {"value": "Audit Area"}},
        text_input=None,
        context=Context(),
        language="en",
    )

    await handler.async_handle(intent_obj)

    records = await agent_audit.async_get_records(hass, entry.entry_id)
    assist_records = [r for r in records if r["event"] == "assist_query"]
    assert len(assist_records) == 1
    assert assist_records[0]["intent"] == handler.intent_type
    assert assist_records[0]["status"] == "resolved"


async def test_mcp_tool_call_write_rejection_and_auth_rejection_recorded(
    hass, memgraph_container, memgraph_client: MemgraphClient
) -> None:
    entry = await _setup_entry(hass, memgraph_container, mcp_enabled=True)
    ar.async_get(hass).async_create("MCP Audit Area")
    token = await mcp_server.async_get_token(hass, entry.entry_id)
    view = mcp_server.OntologyMcpView(hass, entry)

    # Successful tool call -> mcp_tool_call.
    await view.post(
        _Request(
            "127.0.0.1",
            {"Authorization": f"Bearer {token}"},
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "area_context", "arguments": {"area": "MCP Audit Area"}},
            },
        )
    )
    # Write-intent rejection -> mcp_write_rejected.
    await view.post(
        _Request(
            "127.0.0.1",
            {"Authorization": f"Bearer {token}"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "query", "arguments": {"cypher": "CREATE (n) RETURN n"}},
            },
        )
    )
    # Invalid token -> mcp_auth_rejected.
    await view.post(
        _Request(
            "127.0.0.1",
            {"Authorization": "Bearer wrong-token"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        )
    )

    records = await agent_audit.async_get_records(hass, entry.entry_id)
    events = {r["event"] for r in records}
    assert "mcp_tool_call" in events
    assert "mcp_write_rejected" in events
    assert "mcp_auth_rejected" in events


async def test_record_older_than_thirty_days_pruned_via_sweep(hass) -> None:
    old_timestamp = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    await agent_audit.async_append_record(
        hass,
        "audit-lifecycle-entry",
        {"event": "assist_query", "status": "resolved", "timestamp": old_timestamp},
    )
    assert await agent_audit.async_get_records(hass, "audit-lifecycle-entry")

    await agent_audit.async_prune_expired(hass, "audit-lifecycle-entry")

    assert await agent_audit.async_get_records(hass, "audit-lifecycle-entry") == []
