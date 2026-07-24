"""DataUpdateCoordinator for the Ontology integration.

The four explicit sync services (rebuild, resync, single-entity sync,
validate) are serialized through a single lock plus a one-deep pending
queue, rejecting a third+ concurrent request (FR-013a / research.md §8 /
contracts/services.md).

Event-driven incremental updates (registry changes, debounced primary-state
changes) share the same underlying lock so a write is never concurrent with
a full sync, but they wait their turn instead of being rejected: real
installations routinely have many different entities change primary state
within the same few seconds, and treating that as an error only pushed the
same contention into failed_updates for a later retry to re-race (FR-011,
FR-020).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import graph_builder, overrides, query_service, semantic_classifier, validation
from .const import (
    CONF_AUTO_CLASSIFY,
    DEFAULT_AUTO_CLASSIFY,
    DOMAIN,
    HEALTH_ERROR,
    HEALTH_OK,
    HEALTH_UNAVAILABLE,
    SUSTAINED_FAILURE_THRESHOLD,
)
from .memgraph_client import MemgraphClient
from .redact import redact_exception

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass
class PendingUpdate:
    """A single queued incremental-update callable awaiting its turn."""

    kind: str
    func: Any
    args: tuple = ()
    attempts: int = 0


@dataclass
class OntologyState:
    """Observable state surfaced by the health sensors (User Story 6)."""

    health: str = HEALTH_UNAVAILABLE
    node_count: int = 0
    relationship_count: int = 0
    last_sync: str | None = None
    last_error: str | None = None
    schema_version: str | None = None
    consecutive_failures: int = 0
    failed_updates: list[dict[str, Any]] = field(default_factory=list)
    validation_findings: dict[str, int] = field(default_factory=dict)


class OperationInProgress(Exception):
    """Raised when a sync is requested while the single pending slot is
    already occupied (FR-013a, research.md §8)."""


class OntologyCoordinator(DataUpdateCoordinator[OntologyState]):
    """Owns the Memgraph client and serializes all graph-write operations."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: MemgraphClient) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN)
        self.hass = hass
        self.entry = entry
        self.memgraph_client = client
        self.state = OntologyState()
        self._lock = asyncio.Lock()
        self._waiting = False
        # Optional callbacks wired by __init__.py to repairs.py (User Story 9).
        self.on_sustained_failure: Any = None
        self.on_failure_cleared: Any = None

    async def _async_update_data(self) -> OntologyState:
        """Initial full sync: build the graph directly, no clear step (T038)."""
        try:
            await self._execute_full_sync(clear_first=False)
        except Exception as err:  # noqa: BLE001 - convert to UpdateFailed for HA
            raise UpdateFailed(redact_exception(err)) from err
        return self.state

    def _record_success(self) -> None:
        self.state.health = HEALTH_OK
        self.state.last_error = None
        self.state.consecutive_failures = 0
        self.state.last_sync = datetime.now(UTC).isoformat()
        if self.on_failure_cleared:
            self.on_failure_cleared()
        self._notify_state_changed()

    def _record_failure(self, err: Exception) -> None:
        self.state.health = HEALTH_ERROR
        self.state.last_error = redact_exception(err)
        self.state.consecutive_failures += 1
        if (
            self.state.consecutive_failures >= SUSTAINED_FAILURE_THRESHOLD
            and self.on_sustained_failure
        ):
            self.on_sustained_failure()
        self._notify_state_changed()

    def _notify_state_changed(self) -> None:
        """Push the current state to sensor entities.

        This integration never calls ``async_config_entry_first_refresh``/
        ``async_refresh`` (the initial sync runs as a background task per
        T038, and incremental updates bypass the coordinator's own update
        cycle entirely), so ``DataUpdateCoordinator`` would otherwise never
        notify its listeners. Without this, the sensor entities freeze at
        whatever ``self.state`` was when they were first added to hass
        (typically all-zero counts) and never reflect subsequent syncs.
        """
        self.async_set_updated_data(self.state)

    async def _refresh_counts(self) -> None:
        """Refresh the node/relationship count sensors (User Story 6)."""
        node_rows = await self.memgraph_client.run_query("MATCH (n) RETURN count(n) AS c")
        rel_rows = await self.memgraph_client.run_query("MATCH ()-[r]->() RETURN count(r) AS c")
        self.state.node_count = node_rows[0]["c"] if node_rows else 0
        self.state.relationship_count = rel_rows[0]["c"] if rel_rows else 0

    async def _run_serialized(self, func: Any, *args: Any, **kwargs: Any) -> None:
        """Serialize execution through a single lock plus a one-deep pending
        slot: a second concurrent request is queued, a third is rejected
        (FR-013a, research.md §8). Used only by the four explicit sync
        services (rebuild/resync/sync_entity/validate) - see
        `_run_incremental` for event-driven updates."""
        if self._lock.locked():
            if self._waiting:
                raise OperationInProgress("An ontology sync operation is already in progress")
            self._waiting = True
        try:
            async with self._lock:
                self._waiting = False
                await func(*args, **kwargs)
        finally:
            self._waiting = False

    async def _run_incremental(self, func: Any, *args: Any, **kwargs: Any) -> None:
        """Serialize a registry/state-change-driven incremental update through
        the same lock as the heavy sync services, but wait for a turn instead
        of instantly rejecting.

        Unlike `_run_serialized`, this has no one-deep pending-slot limit:
        `asyncio.Lock` is FIFO, so any number of concurrently-arriving
        incremental updates simply queue up and run one at a time, without
        ever raising `OperationInProgress` or starving a pending heavy
        operation.
        """
        async with self._lock:
            await func(*args, **kwargs)

    async def async_run_operation(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run an arbitrary operation through the same single-pending-slot
        serialization as rebuild/resync/sync_entity/validate (FR-013a).

        Generic entry point reused by classify/query/validate/refresh/
        import-export (User Stories 1, 2, 5, 6, 7) so none of them ever run
        concurrently with each other, with rebuild/resync, or with an
        in-flight incremental update (contracts/services.md).
        """
        result_box: dict[str, Any] = {}

        async def _wrapped(*a: Any, **kw: Any) -> None:
            result_box["value"] = await func(*a, **kw)

        await self._run_serialized(_wrapped, *args, **kwargs)
        return result_box.get("value")

    # -- Full-graph operations (User Story 4) -----------------------------

    async def _execute_full_sync(self, *, clear_first: bool) -> None:
        try:
            overrides_payload: dict[str, Any] | None = None
            if clear_first:
                # `clear_generated_graph` deletes every `home_assistant`/
                # `generated` sourced node via DETACH DELETE, which also
                # removes any `source = "user"` override relationship
                # incident to that node (a relationship cannot outlive its
                # endpoints). Round-trip overrides across the clear so
                # rebuild preservation stays unconditional (FR-006, FR-025,
                # Constitution Principle V).
                overrides_payload = await overrides.async_export_overrides(self.memgraph_client)
                await graph_builder.clear_generated_graph(self.memgraph_client)
            auto_classify = self.entry.options.get(CONF_AUTO_CLASSIFY, DEFAULT_AUTO_CLASSIFY)
            await graph_builder.build_full_graph(
                self.hass, self.memgraph_client, auto_classify=auto_classify
            )
            if overrides_payload is not None:
                await overrides.async_import_overrides(self.memgraph_client, overrides_payload)
            self.state.schema_version = await graph_builder.get_schema_version(self.memgraph_client)
            await self._refresh_counts()
        except Exception as err:  # noqa: BLE001
            self._record_failure(err)
            raise
        else:
            self._record_success()

    async def async_rebuild(self) -> None:
        """Clear integration-owned data, then rebuild the full ontology (T038)."""
        await self._run_serialized(self._execute_full_sync, clear_first=True)

    async def async_resync(self) -> None:
        """Re-read HA registries and MERGE in place, without clearing (FR-016)."""
        await self._run_serialized(self._execute_full_sync, clear_first=False)

    # -- Single-entity operations (User Story 5/7) -------------------------

    async def _execute_entity_sync(self, entity_id: str) -> None:
        try:
            await graph_builder.update_entity(self.hass, self.memgraph_client, entity_id)
            await self._refresh_counts()
        except Exception as err:  # noqa: BLE001
            self._record_failure(err)
            raise
        else:
            self._record_success()

    async def async_sync_entity(self, entity_id: str) -> None:
        """Refresh a single entity node/relationships (FR-016).

        Raises ``ValueError`` if the entity does not exist in HA at all
        (contracts/services.md `ontology.sync_entity`).
        """
        registry = er.async_get(self.hass)
        if registry.entities.get(entity_id) is None and self.hass.states.get(entity_id) is None:
            raise ValueError(f"Entity {entity_id} does not exist")
        await self._run_serialized(self._execute_entity_sync, entity_id)

    # -- Validation (User Story 7/8) ---------------------------------------

    async def _execute_validate(self) -> None:
        try:
            await self.memgraph_client.test_connection()
            current_version = await graph_builder.get_schema_version(self.memgraph_client)
            self.state.schema_version = current_version
            self.state.validation_findings = await validation.async_run_validation(
                self.hass, self.memgraph_client
            )
        except Exception as err:  # noqa: BLE001
            self._record_failure(err)
            raise
        else:
            self._record_success()

    async def async_validate(self) -> None:
        """Run the full 9-category validation engine (FR-014, User Story 5).

        Never raises solely due to a schema-version mismatch: `schema_mismatch`
        is now one ordinary finding among nine, not a fatal condition (this
        supersedes v1's connectivity-only check per contracts/services.md).
        """
        await self._run_serialized(self._execute_validate)

    # -- Semantic classification (User Story 1/6) ---------------------------

    async def async_classify(self) -> int:
        """Run a full-graph classification pass (User Story 1)."""
        return await self.async_run_operation(
            semantic_classifier.async_classify_entities, self.hass, self.memgraph_client
        )

    async def async_refresh_semantics(self, entity_id: str | None = None) -> int:
        """Recalculate inferred classifications for one entity or all (User Story 6)."""
        return await self.async_run_operation(
            semantic_classifier.async_refresh_semantics, self.hass, self.memgraph_client, entity_id
        )

    # -- Read-only query service (User Story 2) ------------------------------

    async def async_query(
        self, cypher: str, parameters: dict[str, Any] | None = None, limit: int | None = None
    ) -> dict[str, Any]:
        """Validate and execute a read-only Cypher query (User Story 2)."""
        return await self.async_run_operation(
            query_service.execute_query, self.memgraph_client, cypher, parameters, limit
        )

    # -- User-managed overrides export/import (User Story 7) ----------------

    async def async_export_overrides(self) -> dict[str, Any]:
        """Export every `source = "user"` override relationship (User Story 7)."""
        return await self.async_run_operation(
            overrides.async_export_overrides, self.memgraph_client
        )

    async def async_import_overrides(self, payload: Any) -> int:
        """Validate and import a previously exported overrides payload (User Story 7)."""
        return await self.async_run_operation(
            overrides.async_import_overrides, self.memgraph_client, payload
        )

    # -- Event-driven incremental updates (User Story 5) --------------------

    def _track_failed_update(self, kind: str, target_id: str, err: Exception) -> None:
        """Mark a failed incremental update as failed/pending, never dropped
        (FR-020, T046a)."""
        for item in self.state.failed_updates:
            if item["kind"] == kind and item["id"] == target_id:
                item["attempts"] += 1
                item["error"] = redact_exception(err)
                self._notify_state_changed()
                return
        self.state.failed_updates.append(
            {"kind": kind, "id": target_id, "attempts": 1, "error": redact_exception(err)}
        )
        self._notify_state_changed()

    def _clear_failed_update(self, kind: str, target_id: str) -> None:
        self.state.failed_updates = [
            item
            for item in self.state.failed_updates
            if not (item["kind"] == kind and item["id"] == target_id)
        ]
        self._notify_state_changed()

    async def async_handle_entity_change(self, entity_id: str) -> None:
        """Entry point for debounced `state_changed`/entity-registry events."""
        try:
            await self._run_incremental(self._execute_entity_sync, entity_id)
        except Exception as err:  # noqa: BLE001 - tracked, never dropped (FR-020)
            self._track_failed_update("entity", entity_id, err)
        else:
            self._clear_failed_update("entity", entity_id)

    async def async_handle_device_change(self, device_id: str) -> None:
        """Entry point for device-registry update/remove events."""
        try:
            await self._run_incremental(
                graph_builder.update_device, self.hass, self.memgraph_client, device_id
            )
        except Exception as err:  # noqa: BLE001
            self._track_failed_update("device", device_id, err)
        else:
            self._clear_failed_update("device", device_id)

    async def async_handle_area_change(self, area_id: str) -> None:
        """Entry point for area-registry update/remove events."""
        try:
            await self._run_incremental(
                graph_builder.update_area, self.hass, self.memgraph_client, area_id
            )
        except Exception as err:  # noqa: BLE001
            self._track_failed_update("area", area_id, err)
        else:
            self._clear_failed_update("area", area_id)

    async def async_retry_failed_updates(self) -> None:
        """Retry every tracked failed/pending update (FR-020, T046a)."""
        for item in list(self.state.failed_updates):
            if item["kind"] == "entity":
                await self.async_handle_entity_change(item["id"])
            elif item["kind"] == "device":
                await self.async_handle_device_change(item["id"])
            elif item["kind"] == "area":
                await self.async_handle_area_change(item["id"])
