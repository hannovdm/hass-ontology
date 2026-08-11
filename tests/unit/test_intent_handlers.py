"""Unit tests for Assist intent handlers (User Story 2): T019 (each handler
calls the correct `query_tools` function and translates `ToolResult` into an
`IntentResponse`), T020 (thin wrapper intents delegate correctly)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Context
from homeassistant.helpers import intent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import intent_handlers, query_tools
from custom_components.ontology.const import DOMAIN


async def _setup_loaded_entry(
    hass, mock_memgraph_client, mock_config_entry_data
) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=mock_config_entry_data)
    entry.add_to_hass(hass)
    with patch(
        "custom_components.ontology.MemgraphClient", return_value=mock_memgraph_client
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _make_intent(hass, intent_type: str, slot_name: str, value: str) -> intent.Intent:
    return intent.Intent(
        hass,
        platform="test",
        intent_type=intent_type,
        slots={slot_name: {"value": value}},
        text_input=None,
        context=Context(),
        language="en",
    )


@pytest.mark.parametrize(
    ("handler_cls", "slot_name", "tool_func_name"),
    [
        (intent_handlers.OntologyAutomationDependencies, "entity", "automation_dependencies"),
        (intent_handlers.OntologyAreaContents, "area", "area_context"),
        (intent_handlers.OntologyEntityContext, "entity", "entity_context"),
        (intent_handlers.OntologyDeviceContext, "device", "device_context"),
        (intent_handlers.OntologySearch, "term", "search"),
    ],
)
async def test_intent_calls_correct_query_tools_function(
    hass, mock_memgraph_client, mock_config_entry_data, handler_cls, slot_name, tool_func_name
) -> None:
    await _setup_loaded_entry(hass, mock_memgraph_client, mock_config_entry_data)
    handler = handler_cls()
    intent_obj = _make_intent(hass, handler.intent_type, slot_name, "kitchen")

    fake_result = query_tools.build_tool_result("kitchen", "x", {"matches": []})
    with patch.object(
        query_tools, tool_func_name, AsyncMock(return_value=fake_result)
    ) as mocked:
        response = await handler.async_handle(intent_obj)

    mocked.assert_awaited_once()
    assert response.response_type == intent.IntentResponseType.ACTION_DONE


async def test_impact_analysis_intent_delegates_to_impact_analysis_analyze(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    await _setup_loaded_entry(hass, mock_memgraph_client, mock_config_entry_data)
    handler = intent_handlers.OntologyImpactAnalysis()
    intent_obj = _make_intent(hass, handler.intent_type, "entity", "light.kitchen")

    fake_result = query_tools.build_tool_result(
        "light.kitchen", "impact_analysis", {"has_dependencies": False}
    )
    with patch(
        "custom_components.ontology.intent_handlers.impact_analysis.analyze",
        AsyncMock(return_value=fake_result),
    ) as mocked:
        response = await handler.async_handle(intent_obj)

    mocked.assert_awaited_once()
    assert response.response_type == intent.IntentResponseType.ACTION_DONE


@pytest.mark.parametrize(
    ("handler_cls", "slot_name"),
    [
        (intent_handlers.OntologyAutomationDependencies, "entity"),
        (intent_handlers.OntologyAreaContents, "area"),
        (intent_handlers.OntologyEntityContext, "entity"),
    ],
)
async def test_unresolvable_target_returns_not_found_conversational_response(
    hass, mock_memgraph_client, mock_config_entry_data, handler_cls, slot_name
) -> None:
    mock_memgraph_client.run_query = AsyncMock(return_value=[])
    await _setup_loaded_entry(hass, mock_memgraph_client, mock_config_entry_data)
    handler = handler_cls()
    intent_obj = _make_intent(hass, handler.intent_type, slot_name, "does-not-exist")

    response = await handler.async_handle(intent_obj)

    assert response.response_type != intent.IntentResponseType.ERROR
    assert response.speech
