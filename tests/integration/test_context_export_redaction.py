"""Integration test: area/entity/whole-home export documents against a real
Memgraph fixture seeded with known fake sensitive values - confirm zero
secrets/tokens/credentials appear in any export (User Story 6, T044)."""

from __future__ import annotations

from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import context_export, graph_builder
from custom_components.ontology.const import DOMAIN
from custom_components.ontology.memgraph_client import MemgraphClient

_FAKE_SECRET = "sk-fake-super-secret-token-123456"


async def _seed(hass, memgraph_client: MemgraphClient, entry_id: str) -> tuple[str, str, str]:
    area = ar.async_get(hass).async_create("Sensitive Area")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry_id,
        identifiers={(DOMAIN, "export-device-1")},
        name="Export Device",
    )
    dr.async_get(hass).async_update_device(device.id, area_id=area.id)
    entity = er.async_get(hass).async_get_or_create(
        "light", "test_platform", "export-entity-1", device_id=device.id
    )
    hass.states.async_set(entity.entity_id, "on")
    await hass.async_block_till_done()
    await graph_builder.build_full_graph(hass, memgraph_client)

    # Inject known fake sensitive values directly onto graph nodes, as if a
    # future/unexpected write had leaked them onto an otherwise-legitimate
    # node - the allow-list projection must exclude them regardless.
    await memgraph_client.run_query(
        "MATCH (a:Area {ha_id: $area_id}) SET a.api_key = $secret, a.password = $secret",
        {"area_id": area.id, "secret": _FAKE_SECRET},
    )
    await memgraph_client.run_query(
        "MATCH (d:Device {ha_id: $device_id}) SET d.access_token = $secret",
        {"device_id": device.id, "secret": _FAKE_SECRET},
    )
    await memgraph_client.run_query(
        "MATCH (e:Entity {ha_id: $entity_id}) SET e.secret = $secret, e.credential = $secret",
        {"entity_id": entity.entity_id, "secret": _FAKE_SECRET},
    )
    return area.id, entity.entity_id, device.id


async def test_area_export_contains_zero_secrets(hass, memgraph_client: MemgraphClient) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    area_id, _entity_id, _device_id = await _seed(hass, memgraph_client, entry.entry_id)

    tool_result = await context_export.export(memgraph_client, "area", area_id)

    assert tool_result["result_type"] == "export_context"
    assert _FAKE_SECRET not in str(tool_result["result"])


async def test_entity_export_contains_zero_secrets(hass, memgraph_client: MemgraphClient) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    _area_id, entity_id, _device_id = await _seed(hass, memgraph_client, entry.entry_id)

    tool_result = await context_export.export(memgraph_client, "entity", entity_id)

    assert tool_result["result_type"] == "export_context"
    assert _FAKE_SECRET not in str(tool_result["result"])


async def test_whole_home_export_contains_zero_secrets(
    hass, memgraph_client: MemgraphClient
) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    await _seed(hass, memgraph_client, entry.entry_id)

    tool_result = await context_export.export(memgraph_client, "whole_home")

    assert tool_result["result_type"] == "export_context"
    assert _FAKE_SECRET not in str(tool_result["result"])


async def test_device_export_contains_zero_secrets(hass, memgraph_client: MemgraphClient) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    _area_id, _entity_id, device_id = await _seed(hass, memgraph_client, entry.entry_id)

    tool_result = await context_export.export(memgraph_client, "device", device_id)

    assert tool_result["result_type"] == "export_context"
    assert _FAKE_SECRET not in str(tool_result["result"])
