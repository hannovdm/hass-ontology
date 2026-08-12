"""Home Assistant Ontology Integration.

Synchronizes Home Assistant registry metadata (areas, floors, devices,
entities, domains, integrations, labels, automations, scenes, scripts) into a
local Memgraph graph database as an idempotent, versioned ontology.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

import voluptuous as vol
from homeassistant.components import panel_custom, persistent_notification
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval

from . import (
    agent_audit,
    context_export,
    impact_analysis,
    intent_handlers,
    mcp_server,
    query_tools,
    websocket_api,
)
from .const import (
    AGENT_AUDIT_SWEEP_INTERVAL_SECONDS,
    ATTR_AREA,
    ATTR_CYPHER,
    ATTR_DEVICE,
    ATTR_ENTITY,
    ATTR_ENTITY_ID,
    ATTR_EXPORT_TYPE,
    ATTR_LIMIT,
    ATTR_PARAMETERS,
    ATTR_PAYLOAD,
    ATTR_TARGET,
    ATTR_TARGET_TYPE,
    ATTR_TERM,
    CONF_DATABASE,
    CONF_ENCRYPTED,
    CONF_HOST,
    CONF_MCP_ENABLED,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    DEFAULT_ENCRYPTED,
    DEFAULT_MCP_ENABLED,
    DOMAIN,
    EXPORT_TYPES,
    FAILED_UPDATE_RETRY_INTERVAL_SECONDS,
    IMPACT_SCOPES,
    PLATFORMS,
    RESULT_TYPE_AREA_CONTEXT,
    RESULT_TYPE_AUTOMATION_DEPENDENCIES,
    RESULT_TYPE_DEVICE_CONTEXT,
    RESULT_TYPE_ENTITY_CONTEXT,
    RESULT_TYPE_EXPORT_CONTEXT,
    RESULT_TYPE_IMPACT_ANALYSIS,
    RESULT_TYPE_SEARCH,
    SCHEMA_VERSION,
    SERVICE_AREA_CONTEXT,
    SERVICE_AUTOMATION_DEPENDENCIES,
    SERVICE_DEVICE_CONTEXT,
    SERVICE_ENTITY_CONTEXT,
    SERVICE_EXPORT_CONTEXT,
    SERVICE_EXPORT_OVERRIDES,
    SERVICE_IMPACT_ANALYSIS,
    SERVICE_IMPORT_OVERRIDES,
    SERVICE_QUERY,
    SERVICE_REBUILD,
    SERVICE_REFRESH_SEMANTICS,
    SERVICE_RESYNC,
    SERVICE_SEARCH,
    SERVICE_SYNC_ENTITY,
    SERVICE_VALIDATE,
)
from .coordinator import OntologyCoordinator
from .event_listener import async_register_listeners
from .graph_builder import get_schema_version
from .memgraph_client import CannotConnect, InvalidAuth, MemgraphClient
from .overrides import OverrideImportRejected
from .query_service import QueryRejected
from .redact import redact_exception
from .repairs import (
    async_clear_schema_mismatch_issue,
    async_clear_sustained_failure_issue,
    async_create_schema_mismatch_issue,
    async_create_sustained_failure_issue,
)

_LOGGER = logging.getLogger(__name__)

type OntologyConfigEntry = ConfigEntry[OntologyCoordinator]

PANEL_URL_PATH = "ontology"
PANEL_JS_URL = "/ontology_static/ontology-panel.js"
PANEL_JS_PATH = os.path.join(os.path.dirname(__file__), "panel", "ontology-panel.js")

_SYNC_ENTITY_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_id})
_REFRESH_SEMANTICS_SCHEMA = vol.Schema({vol.Optional(ATTR_ENTITY_ID): cv.entity_id})
_QUERY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CYPHER): str,
        vol.Optional(ATTR_PARAMETERS): dict,
        vol.Optional(ATTR_LIMIT): int,
    }
)
_IMPORT_OVERRIDES_SCHEMA = vol.Schema({vol.Required(ATTR_PAYLOAD): dict})

# v3 predefined query tool / impact analysis / context export schemas
# (contracts/services.md v3 additions).
_SEARCH_SCHEMA = vol.Schema({vol.Required(ATTR_TERM): str, vol.Optional(ATTR_LIMIT): int})
_AREA_CONTEXT_SCHEMA = vol.Schema({vol.Required(ATTR_AREA): str})
_DEVICE_CONTEXT_SCHEMA = vol.Schema({vol.Required(ATTR_DEVICE): str})
_ENTITY_CONTEXT_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY): str})
_AUTOMATION_DEPENDENCIES_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY): str})
_IMPACT_ANALYSIS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TARGET_TYPE): vol.In(IMPACT_SCOPES),
        vol.Required(ATTR_TARGET): str,
    }
)
_EXPORT_CONTEXT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_EXPORT_TYPE): vol.In(EXPORT_TYPES),
        vol.Optional(ATTR_TARGET): str,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: OntologyConfigEntry) -> bool:
    """Set up the Ontology integration from a config entry."""
    client = MemgraphClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        username=entry.data.get(CONF_USERNAME) or None,
        password=entry.data.get(CONF_PASSWORD) or None,
        database=entry.data.get(CONF_DATABASE) or None,
        encrypted=entry.data.get(CONF_ENCRYPTED, DEFAULT_ENCRYPTED),
    )
    try:
        await client.test_connection()
    except InvalidAuth as err:
        await client.close()
        raise ConfigEntryNotReady(
            f"Invalid Memgraph credentials: {redact_exception(err)}"
        ) from err
    except CannotConnect as err:
        await client.close()
        # Transient/unavailable: raising ConfigEntryNotReady keeps HA startup
        # stable and lets HA's own retry mechanism reload later (FR-002, US2).
        raise ConfigEntryNotReady(
            f"Cannot connect to Memgraph: {redact_exception(err)}"
        ) from err

    # Schema-version safety check (User Story 8, FR-017, T056): never write
    # to the graph if an existing OntologySchema.version doesn't match ours.
    existing_version = await get_schema_version(client)
    if existing_version is not None and existing_version != SCHEMA_VERSION:
        async_create_schema_mismatch_issue(hass, entry, existing_version, SCHEMA_VERSION)
        await client.close()
        raise ConfigEntryNotReady(
            f"Ontology schema version mismatch: graph has {existing_version}, "
            f"integration expects {SCHEMA_VERSION}. Resolve manually before retrying."
        )
    async_clear_schema_mismatch_issue(hass, entry)

    coordinator = OntologyCoordinator(hass, entry, client)
    coordinator.on_sustained_failure = lambda: async_create_sustained_failure_issue(hass, entry)
    coordinator.on_failure_cleared = lambda: async_clear_sustained_failure_issue(hass, entry)
    entry.runtime_data = coordinator
    # Connection already validated above: record healthy state up front so
    # the health sensors (User Story 6) reflect it even before the first
    # full sync completes (User Story 2, FR-*).
    coordinator._record_success()

    # Run the initial full sync in the background instead of awaiting it
    # here (FR-013, T038): installations with many entities/relationships
    # can take longer than Home Assistant's config-entry setup timeout to
    # sync, and awaiting it inline gets the whole setup cancelled mid-sync.
    hass.async_create_task(
        coordinator.async_resync(),
        name=f"ontology_initial_sync_{entry.entry_id}",
    )

    entry.async_on_unload(async_register_listeners(hass, coordinator))

    @callback
    def _async_retry_failed_updates(_now: datetime) -> None:
        """Periodic sweep that drains any queued failed_updates (FR-020).

        A burst of many entities changing state at once (e.g. right after a
        restart, as other integrations initialize) can exceed the
        single-pending-slot serialization (FR-013a) and get rejected. This
        runs automatically so end-users never need to press a button to
        recover from that.
        """
        if coordinator.state.failed_updates:
            hass.async_create_task(
                coordinator.async_retry_failed_updates(),
                name=f"ontology_retry_failed_updates_{entry.entry_id}",
            )

    entry.async_on_unload(
        async_track_time_interval(
            hass,
            _async_retry_failed_updates,
            timedelta(seconds=FAILED_UPDATE_RETRY_INTERVAL_SECONDS),
        )
    )

    @callback
    def _async_prune_agent_audit(_now: datetime) -> None:
        """Periodic sweep pruning Assist/MCP audit records past retention (FR-036)."""
        hass.async_create_task(
            agent_audit.async_prune_expired(hass, entry.entry_id),
            name=f"ontology_prune_agent_audit_{entry.entry_id}",
        )

    entry.async_on_unload(
        async_track_time_interval(
            hass,
            _async_prune_agent_audit,
            timedelta(seconds=AGENT_AUDIT_SWEEP_INTERVAL_SECONDS),
        )
    )

    _async_register_services(hass)
    websocket_api.async_register_commands(hass)
    intent_handlers.async_register_intents(hass)
    await intent_handlers.async_ensure_custom_sentences(hass)
    if entry.options.get(CONF_MCP_ENABLED, DEFAULT_MCP_ENABLED):
        await _async_register_mcp_view(hass, entry)
    await _async_register_panel(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: OntologyConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.memgraph_client.close()
        _async_unregister_services(hass)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: OntologyConfigEntry) -> None:
    """Reload a config entry after options/reconfigure changes (FR-003)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_mcp_view(hass: HomeAssistant, entry: OntologyConfigEntry) -> None:
    """Register the opt-in MCP endpoint view (FR-023, User Story 7).

    Generates (or reuses) the entry's local access token; on first
    generation, surfaces it once via a persistent notification
    (research.md §3) since it is never shown again afterwards.
    """
    if hass.http is None:
        return
    token, created = await mcp_server.async_get_or_create_token(hass, entry.entry_id)
    if created:
        persistent_notification.async_create(
            hass,
            f"Local MCP access token generated for the Ontology integration:\n\n{token}\n\n"
            "This token will not be shown again. Regenerate it any time via the "
            "'Regenerate MCP token' button if it is lost or compromised.",
            title="Ontology MCP token generated",
            notification_id=f"ontology_mcp_token_{entry.entry_id}",
        )
    hass.http.register_view(mcp_server.OntologyMcpView(hass, entry))


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Register the optional Ontology sidebar panel (User Story 8, T054).

    Safe to call once regardless of loaded-entry count: guarded so the
    static path and `panel_custom` registration only happen once.
    """
    if hass.data.setdefault(f"{DOMAIN}_panel_registered", False):
        return
    if hass.http is None:
        # No HTTP component available (e.g. minimal test harness); skip panel
        # registration rather than failing config entry setup.
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_JS_URL, PANEL_JS_PATH, cache_headers=False)]
    )
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="ontology-panel",
        frontend_url_path=PANEL_URL_PATH,
        module_url=PANEL_JS_URL,
        sidebar_title="Ontology",
        sidebar_icon="mdi:graph-outline",
        require_admin=True,
    )
    hass.data[f"{DOMAIN}_panel_registered"] = True


def _loaded_coordinators(hass: HomeAssistant) -> list[OntologyCoordinator]:
    """Return coordinators for all currently-loaded Ontology config entries."""
    return [
        entry.runtime_data
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]


async def _async_handle_rebuild(call: ServiceCall) -> None:
    """Handle the `ontology.rebuild` service call (contracts/services.md)."""
    for coordinator in _loaded_coordinators(call.hass):
        await coordinator.async_rebuild()


async def _async_handle_resync(call: ServiceCall) -> None:
    """Handle the `ontology.resync` service call (contracts/services.md)."""
    for coordinator in _loaded_coordinators(call.hass):
        await coordinator.async_resync()


async def _async_handle_sync_entity(call: ServiceCall) -> None:
    """Handle the `ontology.sync_entity` service call (contracts/services.md)."""
    entity_id = call.data[ATTR_ENTITY_ID]
    for coordinator in _loaded_coordinators(call.hass):
        await coordinator.async_sync_entity(entity_id)


async def _async_handle_validate(call: ServiceCall) -> None:
    """Handle the `ontology.validate` service call (contracts/services.md)."""
    for coordinator in _loaded_coordinators(call.hass):
        await coordinator.async_validate()


async def _async_handle_refresh_semantics(call: ServiceCall) -> None:
    """Handle the `ontology.refresh_semantics` service call (contracts/services.md)."""
    entity_id = call.data.get(ATTR_ENTITY_ID)
    for coordinator in _loaded_coordinators(call.hass):
        await coordinator.async_refresh_semantics(entity_id)


async def _async_handle_query(call: ServiceCall) -> ServiceResponse:
    """Handle the `ontology.query` service call (contracts/services.md)."""
    coordinators = _loaded_coordinators(call.hass)
    if not coordinators:
        return {"rows": [], "truncated": False, "row_count": 0}
    try:
        return await coordinators[0].async_query(
            call.data[ATTR_CYPHER], call.data.get(ATTR_PARAMETERS), call.data.get(ATTR_LIMIT)
        )
    except QueryRejected as err:
        raise ServiceValidationError(str(err)) from err


async def _async_handle_export_overrides(call: ServiceCall) -> ServiceResponse:
    """Handle the `ontology.export_overrides` service call (contracts/services.md)."""
    coordinators = _loaded_coordinators(call.hass)
    if not coordinators:
        return {"version": 1, "exported_at": None, "overrides": []}
    return await coordinators[0].async_export_overrides()


async def _async_handle_import_overrides(call: ServiceCall) -> ServiceResponse:
    """Handle the `ontology.import_overrides` service call (contracts/services.md)."""
    coordinators = _loaded_coordinators(call.hass)
    if not coordinators:
        return {"imported_count": 0}
    try:
        imported_count = await coordinators[0].async_import_overrides(call.data[ATTR_PAYLOAD])
    except OverrideImportRejected as err:
        raise ServiceValidationError(str(err)) from err
    return {"imported_count": imported_count}


async def _async_handle_search(call: ServiceCall) -> ServiceResponse:
    """Handle the `ontology.search` service call (contracts/services.md v3 additions)."""
    coordinators = _loaded_coordinators(call.hass)
    if not coordinators:
        return query_tools.not_found_result(call.data[ATTR_TERM], RESULT_TYPE_SEARCH)
    return await query_tools.search(
        coordinators[0].memgraph_client, call.data[ATTR_TERM], call.data.get(ATTR_LIMIT)
    )


async def _async_handle_area_context(call: ServiceCall) -> ServiceResponse:
    """Handle the `ontology.area_context` service call (contracts/services.md v3 additions)."""
    coordinators = _loaded_coordinators(call.hass)
    if not coordinators:
        return query_tools.not_found_result(call.data[ATTR_AREA], RESULT_TYPE_AREA_CONTEXT)
    return await query_tools.area_context(coordinators[0].memgraph_client, call.data[ATTR_AREA])


async def _async_handle_device_context(call: ServiceCall) -> ServiceResponse:
    """Handle the `ontology.device_context` service call (contracts/services.md v3 additions)."""
    coordinators = _loaded_coordinators(call.hass)
    if not coordinators:
        return query_tools.not_found_result(call.data[ATTR_DEVICE], RESULT_TYPE_DEVICE_CONTEXT)
    return await query_tools.device_context(coordinators[0].memgraph_client, call.data[ATTR_DEVICE])


async def _async_handle_entity_context(call: ServiceCall) -> ServiceResponse:
    """Handle the `ontology.entity_context` service call (contracts/services.md v3 additions)."""
    coordinators = _loaded_coordinators(call.hass)
    if not coordinators:
        return query_tools.not_found_result(call.data[ATTR_ENTITY], RESULT_TYPE_ENTITY_CONTEXT)
    return await query_tools.entity_context(coordinators[0].memgraph_client, call.data[ATTR_ENTITY])


async def _async_handle_automation_dependencies(call: ServiceCall) -> ServiceResponse:
    """Handle `ontology.automation_dependencies` (contracts/services.md v3 additions)."""
    coordinators = _loaded_coordinators(call.hass)
    if not coordinators:
        return query_tools.not_found_result(
            call.data[ATTR_ENTITY], RESULT_TYPE_AUTOMATION_DEPENDENCIES
        )
    return await query_tools.automation_dependencies(
        coordinators[0].memgraph_client, call.data[ATTR_ENTITY]
    )


async def _async_handle_impact_analysis(call: ServiceCall) -> ServiceResponse:
    """Handle the `ontology.impact_analysis` service call (contracts/services.md v3 additions)."""
    coordinators = _loaded_coordinators(call.hass)
    if not coordinators:
        return query_tools.not_found_result(call.data[ATTR_TARGET], RESULT_TYPE_IMPACT_ANALYSIS)
    return await impact_analysis.analyze(
        coordinators[0].memgraph_client,
        call.data[ATTR_TARGET_TYPE],
        call.data[ATTR_TARGET],
        hass=call.hass,
        entry_id=coordinators[0].entry.entry_id,
    )


async def _async_handle_export_context(call: ServiceCall) -> ServiceResponse:
    """Handle the `ontology.export_context` service call (contracts/services.md v3 additions)."""
    coordinators = _loaded_coordinators(call.hass)
    if not coordinators:
        return query_tools.not_found_result(
            call.data.get(ATTR_TARGET) or "whole_home", RESULT_TYPE_EXPORT_CONTEXT
        )
    return await context_export.export(
        coordinators[0].memgraph_client,
        call.data[ATTR_EXPORT_TYPE],
        call.data.get(ATTR_TARGET),
        hass=call.hass,
        entry_id=coordinators[0].entry.entry_id,
    )


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the ontology services once, regardless of entry count."""
    if hass.services.has_service(DOMAIN, SERVICE_REBUILD):
        return
    hass.services.async_register(DOMAIN, SERVICE_REBUILD, _async_handle_rebuild)
    hass.services.async_register(DOMAIN, SERVICE_RESYNC, _async_handle_resync)
    hass.services.async_register(
        DOMAIN, SERVICE_SYNC_ENTITY, _async_handle_sync_entity, schema=_SYNC_ENTITY_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_VALIDATE, _async_handle_validate)
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_SEMANTICS,
        _async_handle_refresh_semantics,
        schema=_REFRESH_SEMANTICS_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_QUERY,
        _async_handle_query,
        schema=_QUERY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EXPORT_OVERRIDES,
        _async_handle_export_overrides,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_OVERRIDES,
        _async_handle_import_overrides,
        schema=_IMPORT_OVERRIDES_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEARCH,
        _async_handle_search,
        schema=_SEARCH_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_AREA_CONTEXT,
        _async_handle_area_context,
        schema=_AREA_CONTEXT_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DEVICE_CONTEXT,
        _async_handle_device_context,
        schema=_DEVICE_CONTEXT_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ENTITY_CONTEXT,
        _async_handle_entity_context,
        schema=_ENTITY_CONTEXT_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_AUTOMATION_DEPENDENCIES,
        _async_handle_automation_dependencies,
        schema=_AUTOMATION_DEPENDENCIES_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPACT_ANALYSIS,
        _async_handle_impact_analysis,
        schema=_IMPACT_ANALYSIS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EXPORT_CONTEXT,
        _async_handle_export_context,
        schema=_EXPORT_CONTEXT_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


def _async_unregister_services(hass: HomeAssistant) -> None:
    """Remove the ontology services once the last config entry is unloaded."""
    if hass.config_entries.async_entries(DOMAIN):
        return
    for service in (
        SERVICE_REBUILD,
        SERVICE_RESYNC,
        SERVICE_SYNC_ENTITY,
        SERVICE_VALIDATE,
        SERVICE_REFRESH_SEMANTICS,
        SERVICE_QUERY,
        SERVICE_EXPORT_OVERRIDES,
        SERVICE_IMPORT_OVERRIDES,
        SERVICE_SEARCH,
        SERVICE_AREA_CONTEXT,
        SERVICE_DEVICE_CONTEXT,
        SERVICE_ENTITY_CONTEXT,
        SERVICE_AUTOMATION_DEPENDENCIES,
        SERVICE_IMPACT_ANALYSIS,
        SERVICE_EXPORT_CONTEXT,
    ):
        hass.services.async_remove(DOMAIN, service)

