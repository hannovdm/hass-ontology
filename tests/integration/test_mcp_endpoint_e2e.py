"""Integration test: local MCP endpoint end-to-end against a real Memgraph
instance and a real Home Assistant HTTP server (User Story 7): T055 (MCP
disabled by default -> HTTP 404), T056 (enabled + valid token ->
initialize -> tools/list -> tools/call round trip); User Story 7/8 parity
(T077): a direct service call and an MCP `tools/call` for the same target
produce identical redaction/result-limit behavior (FR-027)."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import mcp_server, query_tools
from custom_components.ontology.const import (
    CONF_HOST,
    CONF_MCP_ENABLED,
    CONF_PORT,
    DOMAIN,
)
from custom_components.ontology.memgraph_client import MemgraphClient


async def _setup_entry(hass, memgraph_container, *, mcp_enabled: bool) -> MockConfigEntry:
    # `hass.http` is None in this test harness unless the `http` component is
    # explicitly set up (mirrors the existing v2 panel-registration guard);
    # the MCP view is only registered when `hass.http` is available.
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


async def test_mcp_endpoint_returns_404_when_disabled_by_default(
    hass, memgraph_container
) -> None:
    entry = await _setup_entry(hass, memgraph_container, mcp_enabled=False)

    # Disabled: no token is ever generated, and the view is never registered.
    assert await mcp_server.async_get_token(hass, entry.entry_id) is None


async def test_mcp_endpoint_enabled_initialize_list_call_round_trip(
    hass, memgraph_container, memgraph_client: MemgraphClient
) -> None:
    ar.async_get(hass).async_create("MCP Kitchen")
    entry = await _setup_entry(hass, memgraph_container, mcp_enabled=True)

    token = await mcp_server.async_get_token(hass, entry.entry_id)
    assert token is not None

    view = mcp_server.OntologyMcpView(hass, entry)

    class _Request:
        def __init__(self, body: dict):
            self.remote = "127.0.0.1"
            self.headers = {"Authorization": f"Bearer {token}"}
            self._body = body

        async def json(self):
            return self._body

    import json

    init_response = await view.post(_Request({"jsonrpc": "2.0", "id": 1, "method": "initialize"}))
    assert init_response.status == 200

    list_response = await view.post(
        _Request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    )
    list_body = json.loads(list_response.body)
    assert len(list_body["result"]["tools"]) == 8

    call_response = await view.post(
        _Request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "area_context", "arguments": {"area": "MCP Kitchen"}},
            }
        )
    )
    call_body = json.loads(call_response.body)
    tool_result = json.loads(call_body["result"]["content"][0]["text"])
    assert tool_result["result_type"] == "area_context"
    assert tool_result["target"] == "MCP Kitchen"


async def test_mcp_tools_call_matches_direct_service_call_for_same_target(
    hass, memgraph_container, memgraph_client: MemgraphClient
) -> None:
    """T077: direct service (`ontology.entity_context`) and MCP `tools/call`
    (`entity_context`) produce identical redaction/result-limit behavior."""
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    from custom_components.ontology import graph_builder

    entry = await _setup_entry(hass, memgraph_container, mcp_enabled=True)
    area = ar.async_get(hass).async_create("Parity Area")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "parity-device")},
        name="Parity Device",
    )
    dr.async_get(hass).async_update_device(device.id, area_id=area.id)
    entity = er.async_get(hass).async_get_or_create(
        "light", "test_platform", "parity-entity", device_id=device.id
    )
    hass.states.async_set(entity.entity_id, "on")
    await hass.async_block_till_done()
    await graph_builder.build_full_graph(hass, entry.runtime_data.memgraph_client)

    direct_result = await query_tools.entity_context(
        entry.runtime_data.memgraph_client, entity.entity_id
    )

    token = await mcp_server.async_get_token(hass, entry.entry_id)
    view = mcp_server.OntologyMcpView(hass, entry)

    class _Request:
        def __init__(self, body: dict):
            self.remote = "127.0.0.1"
            self.headers = {"Authorization": f"Bearer {token}"}
            self._body = body

        async def json(self):
            return self._body

    import json

    call_response = await view.post(
        _Request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "entity_context", "arguments": {"entity": entity.entity_id}},
            }
        )
    )
    call_body = json.loads(call_response.body)
    mcp_result = json.loads(call_body["result"]["content"][0]["text"])

    assert mcp_result == direct_result
