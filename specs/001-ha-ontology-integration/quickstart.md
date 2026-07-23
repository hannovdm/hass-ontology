# Quickstart: Validating the Home Assistant Ontology Integration v1

This guide describes how to stand up the prerequisites and validate the feature end-to-end. It intentionally does not include implementation code — see [data-model.md](./data-model.md) for the graph schema and [contracts/](./contracts/) for the exact service/config-flow/diagnostics contracts.

## Prerequisites

- A running Home Assistant instance (OS/Supervised/Core) with access to install a `custom_components` integration.
- A local Memgraph instance reachable over Bolt from the Home Assistant host. Two supported options:
  - **Home Assistant OS / Supervised**: install the [Memgraph add-on](../../memgraph_addon/) shipped in this repo (add `https://github.com/hannovdm/hass-ontology` as an add-on repository under **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, then install and start **Memgraph**). See [memgraph_addon/README.md](../../memgraph_addon/README.md).
  - **Home Assistant Container / Core**, or any other setup: run Memgraph yourself, e.g. `docker run -p 7687:7687 memgraph/memgraph-platform`.
- The `ontology` custom component copied into `<config>/custom_components/ontology/`, then Home Assistant restarted (or reloaded if HA supports hot-reload for new custom components).

## Scenario A — First-time setup and initial sync (validates User Stories 1–4)

1. In Home Assistant, go to **Settings → Devices & Services → Add Integration**, search for "Ontology".
2. Enter the Memgraph `host`, `port`, and credentials (if configured) per [contracts/config-flow.md](./contracts/config-flow.md).
3. **Expected**: the config entry is created and shows as loaded; if Memgraph is unreachable, the form instead shows a connection error and no entry is created.
4. Wait for the initial full synchronization to complete (bounded by SC-001: under 5 minutes for ~500 entities/devices).
5. **Expected**: `sensor.ontology_health` reports healthy, `sensor.ontology_nodes` / `sensor.ontology_relationships` are non-zero, `sensor.ontology_last_sync` reflects a recent timestamp, and `sensor.ontology_schema_version` matches the version recorded in [data-model.md](./data-model.md)'s `OntologySchema` node.
6. Query Memgraph directly (e.g., via `mgconsole` or Memgraph Lab) to confirm the graph contains the Home → Area → Device → Entity chain and Entity → Domain/Integration links described in data-model.md.
7. Re-trigger a full sync (`button.ontology_rebuild` or the `ontology.rebuild` service). **Expected**: node/relationship counts do not increase beyond what actually exists in HA (idempotency — SC-004, FR-008).

## Scenario B — Incremental updates (validates User Story 5)

1. In Home Assistant, rename an Area, move a Device to a different Area, or change an entity's primary state.
2. **Expected**: within a few seconds, only the affected node(s)/relationship(s) in Memgraph reflect the change — no full rebuild occurs (SC-003, FR-010).
3. Trigger several rapid state changes on the same entity in quick succession.
4. **Expected**: the graph write is debounced/throttled (research.md §5) rather than issuing one write per event, and Home Assistant's UI/event loop remains responsive (FR-011).

## Scenario C — Health, services, and diagnostics (validates User Stories 6–7, 9)

1. From Developer Tools → Services, call `ontology.validate`. **Expected**: no data is modified; `sensor.ontology_health` / `sensor.ontology_last_error` reflect the validation outcome per [contracts/services.md](./contracts/services.md).
2. Call `ontology.sync_entity` with a specific `entity_id`. **Expected**: only that entity and its direct relationships refresh.
3. Stop the Memgraph container to simulate an outage, then trigger a sync.
4. **Expected**: Home Assistant remains fully responsive (SC-005); `sensor.ontology_health` moves to an error state; after the configured consecutive-failure threshold (research.md §6), a repair issue (`sustained_connection_failure`) appears under **Settings → Repairs**, per [contracts/diagnostics.md](./contracts/diagnostics.md).
5. Download diagnostics for the integration. **Expected**: connection status, element counts, and schema version are present; `password`/secrets are never present in the output (SC-007).
6. Restart Memgraph, wait for a subsequent sync attempt to succeed. **Expected**: the repair issue clears automatically.

## Scenario D — Schema version safety (validates User Story 8)

1. With the integration already set up and synced once, manually change the `OntologySchema.version` property in Memgraph to a value different from the integration's expected version (e.g., via `mgconsole`).
2. Restart Home Assistant (or reload the config entry).
3. **Expected**: the integration fails to load (does not silently proceed or modify graph structure), and a `schema_version_mismatch` repair issue appears explaining the discrepancy and directing manual resolution, per [contracts/diagnostics.md](./contracts/diagnostics.md) and FR-017.
