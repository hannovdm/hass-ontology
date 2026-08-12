"""Unit tests for Assist intent handlers (User Story 2): T019 (each handler
calls the correct `query_tools` function and translates `ToolResult` into an
`IntentResponse`), T020 (thin wrapper intents delegate correctly)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Context
from homeassistant.helpers import intent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ontology import agent_audit, intent_handlers, query_tools
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


def _installed_managed_sentence_path(hass) -> intent_handlers.Path:
    target_dir = intent_handlers.Path(hass.config.path("custom_sentences", "en"))
    return next(
        path
        for path in target_dir.glob("hass-ontology-managed*.yaml")
        if path.read_text(encoding="utf-8").startswith(
            intent_handlers._CUSTOM_SENTENCES_MARKER
        )
    )


@pytest.mark.parametrize(
    ("handler_cls", "slot_name", "tool_func_name"),
    [
        (
            intent_handlers.OntologyAutomationDependencies,
            "ontology_entity",
            "automation_dependencies",
        ),
        (intent_handlers.OntologyAreaContents, "ontology_area", "area_context"),
        (intent_handlers.OntologyEntityContext, "ontology_entity", "entity_context"),
        (intent_handlers.OntologyDeviceContext, "ontology_device", "device_context"),
        (intent_handlers.OntologySearch, "ontology_term", "search"),
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
    intent_obj = _make_intent(hass, handler.intent_type, "ontology_entity", "light.kitchen")

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


async def test_intent_exception_audits_sanitized_error_category(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    entry = await _setup_loaded_entry(hass, mock_memgraph_client, mock_config_entry_data)
    handler = intent_handlers.OntologySearch()
    intent_obj = _make_intent(hass, handler.intent_type, "ontology_term", "kitchen")

    with patch.object(
        query_tools,
        "search",
        AsyncMock(side_effect=RuntimeError("token=do-not-store")),
    ):
        response = await handler.async_handle(intent_obj)

    records = await agent_audit.async_get_records(hass, entry.entry_id)
    assert response.response_type != intent.IntentResponseType.ERROR
    assert records[-1]["status"] == "error"
    assert records[-1]["error_category"] == "RuntimeError"
    assert "do-not-store" not in str(records[-1])


def test_impact_analysis_speech_names_affected_dashboard() -> None:
    handler = intent_handlers.OntologyImpactAnalysis()
    tool_result = query_tools.build_tool_result(
        "light.kitchen",
        "impact_analysis",
        {
            "has_dependencies": True,
            "automations": [],
            "scripts": [],
            "scenes": [],
            "dashboards": [{"ha_id": "lovelace", "name": "Home"}],
            "semantic_assets": [],
        },
    )

    speech = handler._speech_for_found(tool_result)

    assert "dashboard" in speech.lower()
    assert "Home" in speech


@pytest.mark.parametrize(
    ("handler_cls", "slot_name"),
    [
        (intent_handlers.OntologyAutomationDependencies, "ontology_entity"),
        (intent_handlers.OntologyAreaContents, "ontology_area"),
        (intent_handlers.OntologyEntityContext, "ontology_entity"),
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


async def test_ensure_custom_sentences_writes_into_config_custom_sentences_dir(hass) -> None:
    """Regression test: Home Assistant's default Assist agent only loads
    custom intent sentences from `<config>/custom_sentences/<language>/`
    (`homeassistant.components.conversation.default_agent`) - never from an
    `intents/<language>.yaml` bundled inside a custom integration's own
    package. Without copying the file there, every Assist query for this
    integration fails with "Sorry, I couldn't understand that"."""
    await intent_handlers.async_ensure_custom_sentences(hass)

    target_path = _installed_managed_sentence_path(hass)
    assert target_path.is_file()
    content = target_path.read_text(encoding="utf-8")
    assert "OntologyAutomationDependencies" in content
    assert "ontology_entity" in content


async def test_ensure_custom_sentences_is_idempotent(hass) -> None:
    await intent_handlers.async_ensure_custom_sentences(hass)
    target_path = _installed_managed_sentence_path(hass)
    first_mtime = target_path.stat().st_mtime_ns

    await intent_handlers.async_ensure_custom_sentences(hass)

    assert target_path.stat().st_mtime_ns == first_mtime


async def test_ensure_custom_sentences_preserves_user_file_on_name_collision(
    hass, monkeypatch
) -> None:
    target_dir = intent_handlers.Path(hass.config.path("custom_sentences", "en"))
    target_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(intent_handlers, "_CUSTOM_SENTENCES_FILENAME", "collision-test.yaml")
    collision_path = target_dir / "collision-test.yaml"
    managed_path = target_dir / "hass-ontology-managed-2.yaml"
    collision_path.unlink(missing_ok=True)
    managed_path.unlink(missing_ok=True)
    collision_path.write_text("language: user-authored\n", encoding="utf-8")

    try:
        await intent_handlers.async_ensure_custom_sentences(hass)

        assert collision_path.read_text(encoding="utf-8") == "language: user-authored\n"
        assert managed_path.read_text(encoding="utf-8").startswith(
            intent_handlers._CUSTOM_SENTENCES_MARKER
        )
        assert "OntologyAutomationDependencies" in managed_path.read_text(encoding="utf-8")
    finally:
        collision_path.unlink(missing_ok=True)
        managed_path.unlink(missing_ok=True)


def test_names_from_deduplicates_case_insensitively_preserving_order() -> None:
    items = [
        {"ha_id": "device-1", "name": "Dining Table Lamp"},
        {"ha_id": "device-2", "name": "dining table lamp"},
        {"ha_id": "device-3", "name": "Ceiling Fan"},
    ]
    assert intent_handlers._names_from(items) == ["Dining Table Lamp", "Ceiling Fan"]


def test_bullet_list_renders_one_deduplicated_item_per_line() -> None:
    items = [
        {"ha_id": "device-1", "name": "Dining Table Lamp"},
        {"ha_id": "device-2", "name": "Dining Table Lamp"},
        {"ha_id": "device-3", "name": "Ceiling Fan"},
    ]
    assert intent_handlers._bullet_list(items) == "- Dining Table Lamp\n- Ceiling Fan"


async def test_area_contents_speech_deduplicates_and_uses_bullet_list(
    hass, mock_memgraph_client, mock_config_entry_data
) -> None:
    await _setup_loaded_entry(hass, mock_memgraph_client, mock_config_entry_data)
    handler = intent_handlers.OntologyAreaContents()
    intent_obj = _make_intent(hass, handler.intent_type, "ontology_area", "Dining Room")

    fake_result = query_tools.build_tool_result(
        "Dining Room",
        "area_context",
        {
            "devices": [
                {"ha_id": "device-1", "name": "Dining Table Lamp"},
                {"ha_id": "device-2", "name": "Dining Table Lamp"},
                {"ha_id": "device-3", "name": "Ceiling Fan"},
            ]
        },
    )
    with patch.object(query_tools, "area_context", AsyncMock(return_value=fake_result)):
        response = await handler.async_handle(intent_obj)

    assert response.speech["plain"]["speech"] == (
        "Dining Room contains:\n- Dining Table Lamp\n- Ceiling Fan"
    )


def test_automation_dependency_speech_includes_relationship_reason() -> None:
    speech = intent_handlers.OntologyAutomationDependencies()._speech_for_found(
        query_tools.build_tool_result(
            "light.office",
            "automation_dependencies",
            {
                "automations": [
                    {
                        "ha_id": "automation.office",
                        "name": "Office Lights",
                        "reason": "REFERENCES",
                    }
                ]
            },
        )
    )
    assert "Office Lights (references)" in speech


def test_entity_context_speech_includes_all_available_relationships() -> None:
    speech = intent_handlers.OntologyEntityContext()._speech_for_found(
        query_tools.build_tool_result(
            "sensor.office",
            "entity_context",
            {
                "device": {"name": "Office Sensor"},
                "area": {"name": "Office"},
                "domain": "sensor",
                "integration": "mqtt",
                "semantic_types": ["OccupancySensor"],
                "dependents": ["automation.office"],
            },
        )
    )
    for expected in (
        "Office Sensor",
        "Office",
        "sensor",
        "mqtt",
        "OccupancySensor",
        "automation.office",
    ):
        assert expected in speech
