# Implementation Plan: Home Assistant Ontology Explorer v2

**Branch**: `002-ontology-explorer-v2` | **Date**: 2026-07-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-ontology-explorer-v2/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command; its definition describes the execution workflow.

## Summary

Extend the existing Home Assistant Ontology Integration (`custom_components/ontology`, v1) with a semantic layer over the graph it already builds: automatic classification of entities into domain-specific semantic types (gas cylinder, vehicle, energy asset, security device, occupancy/climate/network/battery devices) tagged `source = "inferred"`; a read-only, write-rejecting Cypher query service (`ontology.query`) with row-limit enforcement; a backend API (Home Assistant `websocket_api` commands) that serves area/entity context and search for an ontology explorer; user-managed semantic overrides with export/import; an on-demand validation service covering nine completeness/consistency categories; and best-effort synchronization of Lovelace dashboard/card structure into the graph. All new capability is delivered inside the existing `custom_components/ontology` package, reusing v1's Memgraph client, coordinator serialization, and `source`-tagging conventions, and adding an optional, thin sidebar panel once the backend API is stable.

## Technical Context

**Language/Version**: Python 3.13 (unchanged from v1 — the Python version bundled with the current Home Assistant core release)

**Primary Dependencies**: Existing `homeassistant` core custom-integration APIs (config entries, `DataUpdateCoordinator`, diagnostics, repairs, entity platforms) and the existing `neo4j>=5.0` Bolt driver (unchanged — all new Cypher for classification, validation, query, refresh, and import/export reuses `memgraph_client.py`). New for v2, but already part of Home Assistant core (no new PyPI dependency): `homeassistant.components.websocket_api` (backend API commands, research.md §1) and `homeassistant.components.frontend` panel registration (sidebar panel, research.md §2).

**Storage**: Memgraph (unchanged — external, locally-hosted graph database reached over Bolt; v2 adds new labels/relationships to the same graph, current-state-only, no time-series history)

**Testing**: Unchanged `pytest` + `pytest-asyncio` + `pytest-homeassistant-custom-component` + `testcontainers-python` (real Memgraph container) stack, extended with: contract tests for the new/extended services (`ontology.query`, `ontology.refresh_semantics`, `ontology.export_overrides`, `ontology.import_overrides`, extended `ontology.validate`) and the new websocket_api commands; unit tests for the classification rule engine, the tokenized Cypher safety validator (including rejection of syntactically invalid queries per FR-022), and each of the 9 validation-category detectors; integration tests (real Memgraph) for classification-survives-rebuild/resync, validation finding lifecycle, query row-limit enforcement, user-managed override survival across resync/rebuild, override export/import round-trips, and websocket_api backend API response time against a ~5,000-node fixture graph (SC-005). No new JS/frontend test tooling is introduced (research.md §10) — the sidebar panel is verified manually via `quickstart.md`.

**Target Platform**: Unchanged — Home Assistant OS/Supervised/Core, deployed as the `custom_components/ontology` integration; primary reference host is an 8 GB x86_64 Home Assistant machine reaching a separate local Memgraph container over Bolt.

**Project Type**: Single project — v2 remains a Home Assistant custom integration. The "backend API" (websocket_api commands) and optional "sidebar panel" (static JS module + `panel_custom` registration) are both delivered inside the same `custom_components/ontology` package rather than as a separate frontend/backend deployable split.

**Performance Goals**: Backend API requests (area context, entity context, search) return within 2 seconds on graphs of up to 5,000 nodes on a typical 8 GB local host (SC-005); classification and validation passes over a ~500-entity/device installation complete in the same order of magnitude as v1's full sync; query-service row-limit enforcement adds no perceptible overhead versus an unbounded read.

**Constraints**: The read-only query service must reject 100% of write-intent Cypher before execution, with zero write-intent queries reaching the database (SC-003); all v2 writes use `MERGE` and are idempotent; classification, validation, refresh, dashboard sync, and rebuild/resync must never delete or overwrite `source = "user"` data (extends v1 FR-017a); the backend API/websocket commands must never leak Memgraph credentials or secrets in responses; import fails closed on any unsupported/mismatched version; dashboard sync tolerates missing/unloadable Lovelace config or dangling entity references without failing the overall sync (FR-050); sync/classification/validation/refresh/query/import-export operations reuse v1's single-flight serialization (coordinator lock) so they never run concurrently with each other or with v1's rebuild/resync.

**Scale/Scope**: Up to ~5,000 total nodes once semantic types, validation findings, and dashboard data are included (extends v1's ~500 entity/device baseline); single config entry (single Memgraph target) per Home Assistant instance, unchanged from v1.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. HA Native Integration First | PASS | All v2 capability (classification, query service, validation, overrides, dashboard sync, backend API, panel) is delivered inside `custom_components/ontology` via config-entry-scoped services, `websocket_api` commands, and an optional `panel_custom` registration — no standalone script or separate deployable. |
| II. Local-First & Privacy-Preserving | PASS | No cloud dependency introduced (FR-045, FR-046); export/import and backend API responses carry no Memgraph credentials or HA secrets; diagnostics redaction (v1 `redact.py`) is reused unchanged. |
| III. Memgraph & Cypher Are the Graph Foundation | PASS | All new reads/writes go through the existing `neo4j` Bolt client against Memgraph; no second graph database, RDF, or SPARQL surface is introduced. |
| IV. Asynchronous, Non-Blocking Runtime | PASS | Classification, validation, query, refresh, and import/export are async operations serialized through the existing coordinator lock (single-flight, per v1 FR-013a), so none can block the HA event loop or race v1's rebuild/resync. |
| V. Generated/Inferred/User Data Separated | PASS | Classification results are tagged `source = "inferred"` (FR-003); user overrides are tagged `source = "user"` and are never touched by classification, refresh, rebuild, or resync (FR-006, FR-025); dashboard sync is tagged `source = "generated"` (FR-049). |
| VI. Schema Versioning & Idempotent Migration | PASS | `SCHEMA_VERSION` bumps to `"2.0.0"` (research.md §9) to reflect the new additive labels/relationships; all writes remain `MERGE`-based; existing fail-to-load + repair-issue behavior on mismatch is unchanged (FR-055 explicitly preserves it). |
| VII. Tests Before Confident Implementation | PASS | Test plan (Technical Context, above) covers every new capability: classification rules, query safety/row-limits, all 9 validation categories, override export/import round-trip, dashboard sync tolerance, and websocket_api contract shape. |
| VIII. Observable, Diagnosable, Repairable by Design | PASS | v2 reuses v1's diagnostic sensors/buttons/services surface; `ontology.validate` (already an existing v1 service/button) is extended in place rather than duplicated; no new sensor entities are mandated by the spec, so none are speculatively added. |
| IX. Small, Incremental Delivery Over Big-Bang Features | PASS | User Story priorities (P1: classification, query, backend API; P2: overrides, validation, refresh; P3: import/export, sidebar panel) allow each capability to ship and be verified independently, consistent with "v2 semantic features are added only after v1 is stable." |
| X. Explicit Safety Boundaries for AI and Query Surfaces | PASS | `ontology.query` rejects exactly the constitution's deny-list (`CREATE`, `MERGE`, `DELETE`, `DETACH`, `SET`, `REMOVE`, `DROP`, `LOAD CSV`, `CALL dbms`, `CALL mg`, `CALL algo`) via a tokenized scanner (research.md §3), with zero write-intent queries reaching Memgraph (SC-003). |

No violations identified; Complexity Tracking section is not required.

**Post-Phase-1 re-check**: The completed Phase 1 artifacts ([data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)) were reviewed against the table above after design — the new labels/relationships and their `source` tagging, the websocket_api command contracts, the query-safety/row-limit contract, and the validation-finding lifecycle all match the Constitution Check gates above with no new violations introduced.

## Project Structure

### Documentation (this feature)

```text
specs/002-ontology-explorer-v2/
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
    ├── __init__.py            # EXTEND: register websocket_api commands + optional panel in async_setup_entry
    ├── manifest.json          # unchanged (no new PyPI requirement; websocket_api/frontend are HA core)
    ├── config_flow.py         # unchanged
    ├── const.py               # EXTEND: new labels/relationships/services/finding categories, SCHEMA_VERSION -> "2.0.0"
    ├── coordinator.py         # EXTEND: new serialized operations (classify, validate*, query, refresh, export/import)
    ├── memgraph_client.py     # unchanged (reused as-is by all new modules)
    ├── graph_builder.py       # EXTEND: invoke dashboard_sync during full sync; unchanged core HA metadata mapping
    ├── semantic_classifier.py # NEW: classification rule table + refresh_semantics (US1, US6)
    ├── overrides.py           # NEW: user-managed override CRUD + export/import (US4, US7)
    ├── validation.py          # NEW: on-demand validation engine, all 9 finding categories (US5)
    ├── query_service.py       # NEW: tokenized Cypher safety validator + bounded read-only executor (US2)
    ├── dashboard_sync.py      # NEW: best-effort Lovelace dashboard/card sync (Dashboard synchronization FRs)
    ├── websocket_api.py       # NEW: backend API commands (area/entity context, search) (US3)
    ├── panel/                 # NEW: static frontend assets for the optional sidebar panel (US8)
    │   └── ontology-panel.js  # dependency-free ES module, no build step
    ├── event_listener.py      # unchanged
    ├── redact.py              # unchanged (reused by diagnostics/export)
    ├── repairs.py              # unchanged (schema-mismatch/outage repairs still apply)
    ├── services.yaml          # EXTEND: query, refresh_semantics, export_overrides, import_overrides
    ├── sensor.py               # unchanged
    ├── button.py               # unchanged
    ├── diagnostics.py          # EXTEND: include validation finding counts (redacted payload)
    ├── strings.json           # EXTEND: new service/field strings
    └── translations/
        └── en.json            # EXTEND: mirrors strings.json additions

tests/
├── contract/
│   ├── test_services_contract.py        # EXTEND: new/extended services
│   └── test_websocket_api_contract.py   # NEW: area/entity/search command shapes
├── integration/
│   ├── test_classification_survives_resync.py    # NEW
│   ├── test_validation_finding_lifecycle.py       # NEW
│   ├── test_query_row_limit_enforcement.py        # NEW
│   ├── test_overrides_survival.py                 # NEW
│   ├── test_overrides_export_import_roundtrip.py  # NEW
│   ├── test_dashboard_sync_tolerance.py           # NEW
│   └── test_websocket_api_performance.py          # NEW
└── unit/
    ├── test_semantic_classifier.py   # NEW
    ├── test_query_service_safety.py  # NEW
    ├── test_validation_categories.py # NEW
    ├── test_overrides.py             # NEW
    └── test_dashboard_sync.py        # NEW
```

**Structure Decision**: Single project — v2 extends the existing repository-mandated `custom_components/ontology/` layout (per the constitution's Repository Standards) rather than introducing a separate frontend/backend split; the backend API and sidebar panel are additive modules/assets within the same package, and the `tests/` tree keeps the existing contract/integration/unit split with new files per new module.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No Constitution Check violations were identified; this section is not applicable.
