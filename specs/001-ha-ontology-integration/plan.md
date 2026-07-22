# Implementation Plan: Home Assistant Ontology Integration v1

**Branch**: `001-ha-ontology-integration` | **Date**: 2026-07-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-ha-ontology-integration/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command; its definition describes the execution workflow.

## Summary

Build a Home Assistant custom integration (`custom_components/ontology`) configured through Devices & Services that discovers Home Assistant registry metadata (areas, floors, devices, entities, domains, integrations, labels, automations, scenes, scripts) and synchronizes it into a local Memgraph graph database as an idempotent, versioned ontology. The integration validates connectivity at setup, performs an async full sync on first load, applies debounced incremental updates from registry/state-change events afterward, exposes health/diagnostics/services/repair issues, and enforces schema-version safety (fail-to-load + repair issue on mismatch) — all without any cloud dependency, per the project constitution.

## Technical Context

**Language/Version**: Python 3.13 (current Home Assistant core minimum supported runtime; integration code must stay within whatever Python version ships with the target HA core release)

**Primary Dependencies**: `homeassistant` core (custom integration APIs: config entries, config flow, coordinator, diagnostics, repairs, entity platforms); `neo4j` Python driver (Bolt protocol client, used to connect to Memgraph since Memgraph is Bolt-wire-compatible and this avoids adding an OGM dependency); Home Assistant's built-in `voluptuous` for config flow / service schemas

**Storage**: Memgraph (external, locally-hosted graph database reached over Bolt; current-state-only, no time-series/history stored in the graph)

**Testing**: `pytest` + `pytest-asyncio` + `pytest-homeassistant-custom-component` for unit/contract tests against a mocked HA core and mocked Memgraph client; `testcontainers-python` (Memgraph container) for integration tests that need a real Bolt-speaking database (idempotency, schema versioning, sync behavior)

**Target Platform**: Home Assistant OS / Supervised / Core, deployed as a `custom_components` integration; primary reference host is an 8 GB x86_64 Home Assistant machine reaching a separate local Memgraph container over the network

**Project Type**: Single project — Home Assistant custom integration + companion test suite (no separate frontend/backend split; this is a backend-only HA add-on)

**Performance Goals**: Initial full synchronization completes in under 5 minutes for a medium installation (~500 entities/devices, per SC-001); incremental updates are reflected in the graph within a few seconds of the triggering HA event (SC-003); state-change processing is debounced/throttled (few-second window) so it never degrades the HA event loop

**Constraints**: Async-only I/O against Memgraph with connection timeouts; Home Assistant startup/shutdown/event loop must never block on graph activity; Memgraph unavailability must degrade gracefully (health sensor + repair issue), not crash HA; credentials/secrets must be redacted from all logs, diagnostics, and error messages; sync operations are serialized (queue-or-reject, never concurrent); no external/cloud services of any kind

**Scale/Scope**: Up to ~500 entities/devices for the "typical" sizing target (SC-001); single config entry (single Memgraph target) per Home Assistant instance for v1

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. HA Native Integration First | PASS | Implemented under `custom_components/ontology` with `manifest.json`, `config_flow.py`, config entries, services, entity platforms, diagnostics, repairs — no AppDaemon/standalone script path considered. |
| II. Local-First & Privacy-Preserving | PASS | Memgraph runs locally over Bolt; no cloud dependency in any chosen dependency; diagnostics/log redaction is an explicit design requirement (FR-004, FR-018). |
| III. Memgraph & Cypher Are the Graph Foundation | PASS | `neo4j` Bolt driver targets Memgraph exclusively; no second graph database, RDF, or SPARQL introduced. Current-state-only storage, no history in graph. |
| IV. Asynchronous, Non-Blocking Runtime | PASS | All Memgraph I/O is async with timeouts; debounce/throttle for state-change events; serialized sync operations (FR-013a) prevent overlapping graph writes from blocking the loop. |
| V. Generated/Inferred/User Data Separated | PASS | Data model (Phase 1) tags every node/relationship with `source` (`home_assistant`/`generated`/`inferred`/`user`); rebuild/resync logic must preserve non-`home_assistant`-sourced data (FR-017a). |
| VI. Schema Versioning & Idempotent Migration | PASS | `OntologySchema` node design carried into data-model.md; mismatch triggers fail-to-load + repair issue (FR-017), never silent migration. All writes use `MERGE` with stable IDs (FR-008, FR-009). |
| VII. Tests Before Confident Implementation | PASS | Testing strategy covers all required v1 categories: config flow success/failure, Memgraph connection success/failure, full-sync idempotency, entity/device/area/state update behavior, service execution, diagnostics redaction, setup/unload/reload, outage handling. |
| VIII. Observable, Diagnosable, Repairable | PASS | Plan includes the exact sensor/button/service surface named in the constitution (`sensor.ontology_*`, `button.ontology_*`, `ontology.*` services) as contracts (Phase 1). |
| IX. Small, Incremental Delivery | PASS | This plan scopes only v1 (config flow → connection validation → schema node → initial sync → diagnostics/services → incremental updates → validation/repair); no v2/v3 semantic or AI features included. |
| X. Explicit Safety Boundaries for AI/Query Surfaces | PASS | v1 exposes no arbitrary Cypher execution surface; only the four fixed services (`rebuild`, `resync`, `sync_entity`, `validate`) are exposed, matching the constitution's v1 restriction. |

No violations identified; Complexity Tracking section is not required.

**Post-Phase-1 re-check**: The completed Phase 1 artifacts ([data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)) were reviewed against the table above after design — the `source`-tagging model, fixed (non-arbitrary) service contract, `OntologySchema` versioning/fail-fast behavior, and redaction rules in the contracts all match the Constitution Check gates with no new violations introduced.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
custom_components/
└── ontology/
    ├── __init__.py          # async_setup_entry / async_unload_entry / async_reload_entry
    ├── manifest.json         # domain, version, config_flow: true, iot_class: local_push
    ├── config_flow.py        # Devices & Services UI: connection form + validation + options flow
    ├── const.py               # domain string, defaults, schema version constant
    ├── coordinator.py         # DataUpdateCoordinator: serializes sync ops (single pending-slot queue)
    ├── memgraph_client.py     # async Bolt (neo4j driver) wrapper: connect, retry/backoff, timeouts
    ├── graph_builder.py       # maps HA registries -> idempotent MERGE Cypher (nodes/relationships)
    ├── event_listener.py      # registry + debounced state_changed listeners -> coordinator update requests
    ├── redact.py              # strips passwords/secrets from logs, diagnostics, and error/exception text
    ├── services.yaml          # ontology.rebuild / resync / sync_entity / validate schemas
    ├── sensor.py               # sensor.ontology_health/nodes/relationships/last_sync/last_error/schema_version
    ├── button.py               # button.ontology_rebuild/validate/resync
    ├── diagnostics.py          # redacted diagnostics payload
    ├── repairs.py              # schema-mismatch and sustained-outage repair issues
    ├── strings.json
    └── translations/
        └── en.json

tests/
├── contract/       # config_flow, services.yaml schema, diagnostics payload shape
├── integration/    # real Memgraph (testcontainers) sync/idempotency/schema-version tests
└── unit/           # graph_builder mapping logic, debounce/throttle, retry/backoff, redaction
```

**Structure Decision**: Single project — this is a Home Assistant custom integration, not a client/server or mobile app, so the repository-mandated `custom_components/ontology/` layout (per the constitution's Repository Standards) is used directly, with a parallel `tests/` tree split into contract, integration (real Memgraph via testcontainers), and unit tests per Principle VII.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No Constitution Check violations were identified; this section is not applicable.
