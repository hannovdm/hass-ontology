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


def _first_loaded_entry(hass: HomeAssistant) -> ConfigEntry | None:
    """Return the first loaded Ontology config entry, if any.

    Duplicated (rather than imported from `__init__.py`) to avoid a circular
    import, mirroring `websocket_api._first_loaded_client`.
    """
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED and entry.runtime_data is not None:
            return entry
    return None



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
        except Exception:  # noqa: BLE001 - never let an intent crash Assist
            status = "error"
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
                        "error_category": None,
                        "timestamp": agent_audit.now_iso(),
                    },
                )
        return response


class OntologyAutomationDependencies(_OntologyIntentHandler):
    """"what automations depend on {entity}" (FR-008, US2 Scenario 1)."""

    intent_type = INTENT_AUTOMATION_DEPENDENCIES
    slot_name = "entity"

    async def _async_call_tool(self, hass, client, value):
        return await query_tools.automation_dependencies(client, value)

    def _speech_for_found(self, tool_result):
        automations = tool_result["result"].get("automations", [])
        if not automations:
            return f"No automations depend on {tool_result['target']}."
        names = ", ".join(a.get("name") or a.get("ha_id") for a in automations)
        return f"These automations depend on {tool_result['target']}: {names}."


class OntologyAreaContents(_OntologyIntentHandler):
    """"what devices are in {area}" (FR-009, US2 Scenario 2)."""

    intent_type = INTENT_AREA_CONTENTS
    slot_name = "area"

    async def _async_call_tool(self, hass, client, value):
        return await query_tools.area_context(client, value)

    def _speech_for_found(self, tool_result):
        devices = tool_result["result"].get("devices", [])
        if not devices:
            return f"There are no known devices in {tool_result['target']}."
        names = ", ".join(d.get("name") or d.get("ha_id") for d in devices)
        return f"{tool_result['target']} contains: {names}."


class OntologyEntityContext(_OntologyIntentHandler):
    """"what is {entity} connected to" (FR-010, US2 Scenario 3)."""

    intent_type = INTENT_ENTITY_CONTEXT
    slot_name = "entity"

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
        return f"{tool_result['target']} is {location}."


class OntologyDeviceContext(_OntologyIntentHandler):
    """Thin Assist wrapper over `query_tools.device_context` (FR-011)."""

    intent_type = INTENT_DEVICE_CONTEXT
    slot_name = "device"

    async def _async_call_tool(self, hass, client, value):
        return await query_tools.device_context(client, value)


class OntologyImpactAnalysis(_OntologyIntentHandler):
    """Thin Assist wrapper over `impact_analysis.analyze` (entity scope, FR-011)."""

    intent_type = INTENT_IMPACT_ANALYSIS
    slot_name = "entity"

    async def _async_call_tool(self, hass, client, value):
        return await impact_analysis.analyze(client, IMPACT_SCOPE_ENTITY, value)

    def _speech_for_found(self, tool_result):
        if not tool_result["result"].get("has_dependencies"):
            return f"Nothing known depends on {tool_result['target']}."
        return f"Removing {tool_result['target']} would affect other parts of the ontology."


class OntologySearch(_OntologyIntentHandler):
    """Thin Assist wrapper over `query_tools.search` (FR-011)."""

    intent_type = INTENT_SEARCH
    slot_name = "term"

    async def _async_call_tool(self, hass, client, value):
        return await query_tools.search(client, value)

    def _speech_for_found(self, tool_result):
        matches = tool_result["result"].get("matches", [])
        if not matches:
            return f"I found nothing matching {tool_result['target']}."
        names = ", ".join(m.get("name") or m.get("ha_id") for m in matches)
        return f"I found: {names}."


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
