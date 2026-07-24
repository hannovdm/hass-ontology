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
from homeassistant.components import panel_custom
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

from . import websocket_api
from .const import (
    ATTR_CYPHER,
    ATTR_ENTITY_ID,
    ATTR_LIMIT,
    ATTR_PARAMETERS,
    ATTR_PAYLOAD,
    CONF_DATABASE,
    CONF_ENCRYPTED,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    DEFAULT_ENCRYPTED,
    DOMAIN,
    FAILED_UPDATE_RETRY_INTERVAL_SECONDS,
    PLATFORMS,
    SCHEMA_VERSION,
    SERVICE_EXPORT_OVERRIDES,
    SERVICE_IMPORT_OVERRIDES,
    SERVICE_QUERY,
    SERVICE_REBUILD,
    SERVICE_REFRESH_SEMANTICS,
    SERVICE_RESYNC,
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

    _async_register_services(hass)
    websocket_api.async_register_commands(hass)
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
    ):
        hass.services.async_remove(DOMAIN, service)

