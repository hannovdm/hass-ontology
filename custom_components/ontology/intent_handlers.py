"""Native Home Assistant Assist intents for the ontology (User Story 2).

Registers `IntentHandler` subclasses invocable through Home Assistant's
default (non-LLM) conversation agent (research.md §1). Every intent
delegates to the shared `query_tools`/`impact_analysis` functions and
translates the resulting `ToolResult` into an `intent.IntentResponse`
(contracts/assist-intents.md). No intent ever mutates Home Assistant or the
ontology graph (FR-033).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import intent

from . import agent_audit, impact_analysis, query_tools
from .const import (
    AUDIT_EVENT_ASSIST_QUERY,
    DOMAIN,
    IMPACT_SCOPE_ENTITY,
    RESULT_TYPE_NOT_FOUND,
)
from .memgraph_client import MemgraphClient

_LOGGER = logging.getLogger(__name__)

INTENT_AUTOMATION_DEPENDENCIES = "OntologyAutomationDependencies"
INTENT_AREA_CONTENTS = "OntologyAreaContents"
INTENT_ENTITY_CONTEXT = "OntologyEntityContext"
INTENT_DEVICE_CONTEXT = "OntologyDeviceContext"
INTENT_IMPACT_ANALYSIS = "OntologyImpactAnalysis"
INTENT_SEARCH = "OntologySearch"

_SENTENCES_SOURCE_PATH = Path(__file__).parent / "intents" / "en.yaml"
_CUSTOM_SENTENCES_FILENAME = "hass-ontology-managed.yaml"
_CUSTOM_SENTENCES_MARKER = "# Managed by the Home Assistant Ontology integration.\n"


def _first_loaded_entry(hass: HomeAssistant) -> ConfigEntry | None:
    """Return the first loaded Ontology config entry, if any.

    Duplicated (rather than imported from `__init__.py`) to avoid a circular
    import, mirroring `websocket_api._first_loaded_client`.
    """
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED and entry.runtime_data is not None:
            return entry
    return None


def _names_from(items: list[dict[str, Any]]) -> list[str]:
    """Extract a display name per item, de-duplicated (case-insensitive,
    order-preserving) so the same name is never listed twice (e.g. distinct
    graph nodes that happen to share a display name)."""
    names: list[str] = []
    seen: set[str] = set()
    for item in items:
        name = item.get("name") or item.get("ha_id")
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _bullet_list(items: list[dict[str, Any]]) -> str:
    """Render a de-duplicated bullet list (one name per line) for speech."""
    return "\n".join(f"- {name}" for name in _names_from(items))



class _OntologyIntentHandler(intent.IntentHandler):
    """Shared not-found handling + `AssistQueryRecord` audit trail."""

    slot_name: str = "target"

    @property
    def slot_schema(self) -> dict[str, Any]:
        return {self.slot_name: cv.string}

    async def _async_call_tool(
        self, hass: HomeAssistant, client: MemgraphClient, value: str
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _speech_for_found(self, tool_result: dict[str, Any]) -> str:
        return f"Here is what I found for {tool_result['target']}."

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        hass = intent_obj.hass
        response = intent_obj.create_response()
        slots = self.async_validate_slots(intent_obj.slots)
        value = slots[self.slot_name]["value"]

        entry = _first_loaded_entry(hass)
        status = "not_found"
        result_count = 0
        error_category = None
        try:
            if entry is None:
                tool_result = query_tools.not_found_result(value, self.intent_type)
            else:
                tool_result = await self._async_call_tool(
                    hass, entry.runtime_data.memgraph_client, value
                )

            if tool_result["result_type"] == RESULT_TYPE_NOT_FOUND:
                status = "not_found"
                response.async_set_speech(f"I couldn't find {value} in the ontology.")
            else:
                status = "resolved"
                result_count = query_tools.count_results(tool_result["result"])
                response.async_set_speech(self._speech_for_found(tool_result))
                response.async_set_speech_slots({"result": tool_result["result"]})
        except Exception as err:  # noqa: BLE001 - never let an intent crash Assist
            status = "error"
            error_category = type(err).__name__
            _LOGGER.exception("Error handling %s intent", self.intent_type)
            response.async_set_speech("Something went wrong answering that ontology question.")
        finally:
            if entry is not None:
                await agent_audit.async_append_record(
                    hass,
                    entry.entry_id,
                    {
                        "event": AUDIT_EVENT_ASSIST_QUERY,
                        "intent": self.intent_type,
                        "status": status,
                        "result_count": result_count,
                        "error_category": error_category,
                        "timestamp": agent_audit.now_iso(),
                    },
                )
        return response


class OntologyAutomationDependencies(_OntologyIntentHandler):
    """"what automations depend on {ontology_entity}" (FR-008, US2 Scenario 1)."""

    intent_type = INTENT_AUTOMATION_DEPENDENCIES
    slot_name = "ontology_entity"

    async def _async_call_tool(self, hass, client, value):
        return await query_tools.automation_dependencies(client, value)

    def _speech_for_found(self, tool_result):
        automations = tool_result["result"].get("automations", [])
        if not automations:
            return f"No automations depend on {tool_result['target']}."
        lines = []
        for automation in automations:
            name = automation.get("name") or automation.get("ha_id")
            reason = automation.get("reason")
            lines.append(f"- {name} ({reason.lower()})" if reason else f"- {name}")
        return f"These automations depend on {tool_result['target']}:\n" + "\n".join(lines)


class OntologyAreaContents(_OntologyIntentHandler):
    """"what devices are in {ontology_area}" (FR-009, US2 Scenario 2)."""

    intent_type = INTENT_AREA_CONTENTS
    slot_name = "ontology_area"

    async def _async_call_tool(self, hass, client, value):
        return await query_tools.area_context(client, value)

    def _speech_for_found(self, tool_result):
        devices = tool_result["result"].get("devices", [])
        if not devices:
            return f"There are no known devices in {tool_result['target']}."
        return f"{tool_result['target']} contains:\n{_bullet_list(devices)}"


class OntologyEntityContext(_OntologyIntentHandler):
    """"what is {ontology_entity} connected to" (FR-010, US2 Scenario 3)."""

    intent_type = INTENT_ENTITY_CONTEXT
    slot_name = "ontology_entity"

    async def _async_call_tool(self, hass, client, value):
        return await query_tools.entity_context(client, value)

    def _speech_for_found(self, tool_result):
        result = tool_result["result"]
        device = (result.get("device") or {}).get("name")
        area = (result.get("area") or {}).get("name")
        parts = []
        if device:
            parts.append(f"on device {device}")
        if area:
            parts.append(f"in area {area}")
        location = " ".join(parts) if parts else "with no known device or area"
        details = []
        for key, label in (
            ("domain", "domain"),
            ("integration", "integration"),
        ):
            if result.get(key):
                details.append(f"{label} {result[key]}")
        if result.get("semantic_types"):
            details.append("classifications " + ", ".join(result["semantic_types"]))
        if result.get("dependents"):
            details.append("dependencies " + ", ".join(result["dependents"]))
        suffix = " " + "; ".join(details) if details else ""
        return f"{tool_result['target']} is {location}.{suffix}"


class OntologyDeviceContext(_OntologyIntentHandler):
    """Thin Assist wrapper over `query_tools.device_context` (FR-011)."""

    intent_type = INTENT_DEVICE_CONTEXT
    slot_name = "ontology_device"

    async def _async_call_tool(self, hass, client, value):
        return await query_tools.device_context(client, value)


class OntologyImpactAnalysis(_OntologyIntentHandler):
    """Thin Assist wrapper over `impact_analysis.analyze` (entity scope, FR-011)."""

    intent_type = INTENT_IMPACT_ANALYSIS
    slot_name = "ontology_entity"

    async def _async_call_tool(self, hass, client, value):
        return await impact_analysis.analyze(client, IMPACT_SCOPE_ENTITY, value)

    def _speech_for_found(self, tool_result):
        result = tool_result["result"]
        if not result.get("has_dependencies"):
            return f"Nothing known depends on {tool_result['target']}."

        sections = []
        for key, label in (
            ("automations", "Automations"),
            ("scripts", "Scripts"),
            ("scenes", "Scenes"),
            ("dashboards", "Dashboards"),
            ("semantic_assets", "Semantic assets"),
        ):
            items = result.get(key) or []
            if items:
                sections.append(f"{label}:\n{_bullet_list(items)}")
        return f"Removing {tool_result['target']} would affect:\n" + "\n".join(sections)


class OntologySearch(_OntologyIntentHandler):
    """Thin Assist wrapper over `query_tools.search` (FR-011)."""

    intent_type = INTENT_SEARCH
    slot_name = "ontology_term"

    async def _async_call_tool(self, hass, client, value):
        return await query_tools.search(client, value)

    def _speech_for_found(self, tool_result):
        matches = tool_result["result"].get("matches", [])
        if not matches:
            return f"I found nothing matching {tool_result['target']}."
        return f"I found:\n{_bullet_list(matches)}"


ALL_INTENT_HANDLERS: tuple[_OntologyIntentHandler, ...] = (
    OntologyAutomationDependencies(),
    OntologyAreaContents(),
    OntologyEntityContext(),
    OntologyDeviceContext(),
    OntologyImpactAnalysis(),
    OntologySearch(),
)


def async_register_intents(hass: HomeAssistant) -> None:
    """Register every ontology Assist intent, once per Home Assistant instance."""
    if hass.data.setdefault(f"{DOMAIN}_intents_registered", False):
        return
    for handler in ALL_INTENT_HANDLERS:
        intent.async_register(hass, handler)
    hass.data[f"{DOMAIN}_intents_registered"] = True


def _write_custom_sentences_sync(hass: HomeAssistant) -> bool:
    """Copy the bundled sentence definitions into `<config>/custom_sentences/en/`.

    Blocking (file I/O) - must be run via the executor. Returns True if the
    file was newly written/changed.

    Home Assistant's default Assist agent (`homeassistant.components.
    conversation.default_agent`) only loads custom intent sentences from two
    places: the bundled `home-assistant-intents` PyPI package (core intents
    only) and the config directory's `custom_sentences/<language>/*.yaml`
    files. It does NOT auto-discover an `intents/<language>.yaml` bundled
    inside a custom integration's own package - that file is a template we
    ship, but copying it into the config's `custom_sentences` directory is
    what actually makes Assist recognize these sentences.
    """
    target_dir = Path(hass.config.path("custom_sentences", "en"))
    target_path = target_dir / _CUSTOM_SENTENCES_FILENAME
    suffix = 2
    while target_path.is_file() and not target_path.read_text(
        encoding="utf-8"
    ).startswith(_CUSTOM_SENTENCES_MARKER):
        target_path = target_dir / f"hass-ontology-managed-{suffix}.yaml"
        suffix += 1
    content = _CUSTOM_SENTENCES_MARKER + _SENTENCES_SOURCE_PATH.read_text(encoding="utf-8")
    if target_path.is_file() and target_path.read_text(encoding="utf-8") == content:
        return False
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    return True


async def async_ensure_custom_sentences(hass: HomeAssistant) -> None:
    """Ensure the bundled Assist sentences are installed and loaded (FR-008-FR-011).

    Best-effort: never raises/blocks setup if writing fails or the
    `conversation` integration/service isn't available (e.g. minimal test
    harnesses) - Assist support is a bonus capability, not a hard dependency
    of the integration loading successfully.
    """
    try:
        changed = await hass.async_add_executor_job(_write_custom_sentences_sync, hass)
    except OSError:
        _LOGGER.exception("Failed to install ontology Assist custom sentences")
        return
    if changed and hass.services.has_service("conversation", "reload"):
        await hass.services.async_call("conversation", "reload", blocking=False)
