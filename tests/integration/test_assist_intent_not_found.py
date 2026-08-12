"""Integration test: an unresolvable entity/device/area reference through
Assist returns a clear "not found" conversational response without running
an unbounded query (User Story 2, T021, FR-012, SC-006)."""

from __future__ import annotations

from homeassistant.core import Context
from homeassistant.helpers import intent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import intent_handlers
from custom_components.ontology.const import CONF_HOST, CONF_PORT, DOMAIN
from custom_components.ontology.memgraph_client import MemgraphClient


async def _setup_entry(hass, memgraph_container) -> MockConfigEntry:
    host = memgraph_container.get_container_host_ip()
    port = int(memgraph_container.get_exposed_port(7687))
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: host, CONF_PORT: port})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_unresolvable_entity_returns_not_found_via_entity_context_intent(
    hass, memgraph_container, memgraph_client: MemgraphClient
) -> None:
    await _setup_entry(hass, memgraph_container)
    handler = intent_handlers.OntologyEntityContext()
    intent_obj = intent.Intent(
        hass,
        platform="test",
        intent_type=handler.intent_type,
        slots={"ontology_entity": {"value": "light.does_not_exist_anywhere"}},
        text_input=None,
        context=Context(),
        language="en",
    )

    response = await handler.async_handle(intent_obj)

    assert response.response_type != intent.IntentResponseType.ERROR
    assert response.speech


async def test_unresolvable_area_returns_not_found_via_area_contents_intent(
    hass, memgraph_container, memgraph_client: MemgraphClient
) -> None:
    await _setup_entry(hass, memgraph_container)
    handler = intent_handlers.OntologyAreaContents()
    intent_obj = intent.Intent(
        hass,
        platform="test",
        intent_type=handler.intent_type,
        slots={"ontology_area": {"value": "nonexistent-area-xyz"}},
        text_input=None,
        context=Context(),
        language="en",
    )

    response = await handler.async_handle(intent_obj)

    assert response.response_type != intent.IntentResponseType.ERROR
    assert response.speech
