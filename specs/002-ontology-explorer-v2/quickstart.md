# Quickstart: Validating the Home Assistant Ontology Explorer v2

This guide describes how to validate v2's semantic layer end-to-end on top of an already-installed v1 integration. It intentionally does not include implementation code — see [data-model.md](./data-model.md) for the graph schema and [contracts/](./contracts/) for the exact service/websocket-API contracts.

## Prerequisites

- v1 (`specs/001-ha-ontology-integration`) already installed, configured, and synced at least once (see [v1 quickstart.md](../001-ha-ontology-integration/quickstart.md) Scenario A) — v2 extends the existing graph rather than replacing it.
- The updated `custom_components/ontology` (v2) copied over the existing installation, then Home Assistant restarted.
- After restart, confirm `sensor.ontology_schema_version` reads `2.0.0` (research.md §9) and `sensor.ontology_health` is healthy before proceeding.

## Scenario A — Automatic semantic classification (validates User Story 1, User Story 6)

1. Ensure your Home Assistant instance has at least one entity whose name/domain/`device_class` matches a known semantic signal (e.g., a `sensor` entity named containing "gas cylinder", a `device_tracker` entity for a vehicle, an energy/solar sensor, a camera or door/motion sensor).
2. Trigger a resync (`ontology.resync` or wait for the next scheduled classification pass, per your installation).
3. **Expected**: for each matching entity, a semantic asset node (`GasCylinder`/`Vehicle`/`EnergyAsset`/`SecurityDevice`/etc.) is created in Memgraph, `CLASSIFIED_AS`-linked to the entity, tagged `source = "inferred"` (FR-001–FR-004, SC-002). Each matching entity gets its own node — verify two entities describing the same physical asset produce two distinct semantic nodes, not one shared node (FR-002).
4. Call `ontology.refresh_semantics` with a specific `entity_id`. **Expected**: only that entity's classifications are re-evaluated (FR-023, FR-024).
5. Manually add a `source = "user"` override relationship on a classified entity (e.g., via `mgconsole`), then call `ontology.refresh_semantics` again. **Expected**: the user-managed relationship is untouched (FR-006, FR-025).

## Scenario B — Read-only query service (validates User Story 2)

1. From Developer Tools → Services, call `ontology.query` with a simple read query, e.g. `MATCH (e:Entity) RETURN e LIMIT 5`. **Expected**: rows are returned, `row_count` and `truncated` are present per [contracts/services.md](./contracts/services.md).
2. Call `ontology.query` with a write-intent query, e.g. `MATCH (e:Entity) SET e.hacked = true`. **Expected**: the call is rejected before execution — no data is modified (SC-003, FR-019, FR-020).
3. Call `ontology.query` with a query that would return more than the default row cap, e.g. `MATCH (e:Entity) RETURN e` on a graph with >100 entities. **Expected**: exactly the capped number of rows is returned with `truncated: true` (FR-018, FR-021).

## Scenario C — Backend API for the ontology explorer (validates User Story 3)

1. Using Developer Tools → WebSocket (or an authenticated websocket client), send an `ontology/area_context` command for a known `area_id`. **Expected**: the response includes the area's devices/entities, their current states, and semantic classifications (FR-031).
2. Send an `ontology/entity_context` command for a known `entity_id`. **Expected**: the response includes the entity's device, area, semantic classifications, dependencies, and any dashboards/cards displaying it, per [contracts/websocket-api.md](./contracts/websocket-api.md).
3. Send an `ontology/search` command with a partial name. **Expected**: matching areas/devices/entities are returned within 2 seconds (SC-005).

## Scenario D — Validation (validates User Story 5)

1. Introduce a known issue (e.g., remove an area from a device, mark an entity `critical` and set it unavailable).
2. Call `ontology.validate`. **Expected**: a `ValidationFinding` node is created for the corresponding category (`missing_area`, `unavailable_critical_entity`, etc. — data-model.md, research.md §6) — administrators can identify the issue within 2 minutes without writing a query (SC-001).
3. Confirm validation does **not** run automatically after a resync/rebuild — only `ontology.validate` calls produce findings (FR-017).
4. Fix the underlying issue, call `ontology.validate` again. **Expected**: the finding's `status` becomes `resolved`; after one further validation run without recurrence, the finding is removed (per the retention policy in spec.md's Assumptions).

## Scenario E — Override export/import (validates User Story 4, User Story 7)

1. Create at least one manual `source = "user"` override relationship (e.g., manually classify an entity).
2. Call `ontology.export_overrides`. **Expected**: the response contains only `source = "user"` data, in the versioned JSON shape from research.md §7 (FR-026).
3. On a fresh/second installation (or after clearing user data), call `ontology.import_overrides` with the exported payload. **Expected**: the override(s) are recreated within 5 minutes with zero data loss (SC-004, FR-029).
4. Call `ontology.import_overrides` again with a payload whose `version` field is altered to an unsupported value. **Expected**: the entire import is rejected with no partial writes (FR-027, FR-028).

## Scenario F — Dashboard synchronization (validates the Dashboard synchronization requirements)

1. Ensure at least one Lovelace dashboard exists with a card displaying a known entity, and (optionally) one card referencing a deleted/unknown entity.
2. Trigger a resync. **Expected**: `Dashboard` and `DashboardCard` nodes appear in Memgraph, linked via `CONTAINS_CARD`, with `DISPLAYS_ENTITY` links to the entities they show, all tagged `source = "generated"` (FR-047–FR-049).
3. **Expected**: the card referencing a deleted/unknown entity still has its `DashboardCard` node preserved, simply without a `DISPLAYS_ENTITY` relationship — the overall sync does not fail (FR-050).

## Scenario G — Sidebar panel (validates User Story 8, once shipped)

1. Confirm the "Ontology" panel appears in the Home Assistant sidebar.
2. Open the panel and browse to a device. **Expected**: its area, exposed entities, and semantic classifications are visible within 3 clicks (SC-007).
3. This scenario is optional/deferred if the panel has not yet shipped in your installation (FR-042, spec Assumptions) — Scenarios A–F fully validate the backend independent of the panel.
