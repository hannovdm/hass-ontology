---

description: "Task list template for feature implementation"
---

# Tasks: Home Assistant Ontology Explorer v2

**Input**: Design documents from `/specs/002-ontology-explorer-v2/`

**Prerequisites**: [plan.md](./plan.md) (required), [spec.md](./spec.md) (required for user stories), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Test tasks are included per Constitution Principle VII ("Tests Before Confident Implementation") and to match the existing v1 test conventions in this repository.

**Organization**: Tasks are grouped by user story (from spec.md) to enable independent implementation and testing of each story. The Dashboard synchronization requirement group (FR-047–FR-050, added via the 2026-07-24 clarification session) is not one of the 8 numbered user stories in spec.md, so its tasks are labeled `[DASH]` instead of `[US#]`; it is independently testable via quickstart.md Scenario F.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US8, or DASH for the dashboard-sync requirement group)
- Paths are relative to the repository root and reference the real files in `custom_components/ontology/` and `tests/` (see [plan.md](./plan.md) Project Structure)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish v2 constants and module scaffolding on top of the existing v1 integration

- [X] T001 Update `custom_components/ontology/const.py`: bump `SCHEMA_VERSION` to `"2.0.0"` (research.md §9); add new node labels (`SemanticType`, `GasCylinder`, `Vehicle`, `EnergyAsset`, `SecurityDevice`, `OccupancySensor`, `ClimateDevice`, `NetworkDevice`, `BatteryPoweredDevice`, `Dashboard`, `DashboardCard`, `ValidationFinding`); new relationship type constants (`CLASSIFIED_AS`, `MEASURED_BY`, `LOCATED_IN`, `OBSERVED_BY`, `CONTAINS_CARD`, `DISPLAYS_ENTITY`, `RELATES_TO`); new service name constants (`SERVICE_QUERY`, `SERVICE_REFRESH_SEMANTICS`, `SERVICE_EXPORT_OVERRIDES`, `SERVICE_IMPORT_OVERRIDES`); the Cypher disallowed-keyword deny-list (`CREATE`, `MERGE`, `DELETE`, `DETACH`, `SET`, `REMOVE`, `DROP`, `LOAD CSV`, `CALL dbms`, `CALL mg`, `CALL algo`); and the 9 validation finding category constants
- [X] T002 [P] Create module skeletons with docstrings for `custom_components/ontology/semantic_classifier.py`, `custom_components/ontology/overrides.py`, `custom_components/ontology/validation.py`, `custom_components/ontology/query_service.py`, `custom_components/ontology/dashboard_sync.py`, `custom_components/ontology/websocket_api.py`, and the `custom_components/ontology/panel/` directory
- [X] T003 [P] Add placeholder entries for the new v2 services/fields to `custom_components/ontology/strings.json` and `custom_components/ontology/translations/en.json`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Extend `OntologyCoordinator` in `custom_components/ontology/coordinator.py` with a generic serialized-operation runner that reuses the existing single-pending-slot lock (v1 FR-013a), usable by classify/query/validate/refresh/import-export operations (depends on T001)
- [X] T005 [P] Add an "automatic semantic classification" on/off option to the options flow in `custom_components/ontology/config_flow.py`, with a default constant in `custom_components/ontology/const.py` (FR-004) (depends on T001)

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Classify entities into semantic concepts (Priority: P1) 🎯 MVP

**Goal**: Automatically classify entities into semantic types (`GasCylinder`, `Vehicle`, `EnergyAsset`, `SecurityDevice`, `OccupancySensor`, `ClimateDevice`, `NetworkDevice`, `BatteryPoweredDevice`) tagged `source = "inferred"`.

**Independent Test**: Run classification against a graph populated with a mix of gas-cylinder, vehicle, energy, and security-related entities and confirm the expected semantic nodes/relationships are created and tagged `inferred`, without the explorer UI or query service existing.

### Tests for User Story 1

- [X] T006 [P] [US1] Unit test: classification rule matching for all 8 semantic types, including an entity matching more than one rule (FR-005) in `tests/unit/test_semantic_classifier.py`
- [X] T007 [P] [US1] Unit test: classification never overwrites an existing user-managed (`source = "user"`) relationship for the same entity (FR-006) in `tests/unit/test_semantic_classifier.py`
- [X] T008 [P] [US1] Integration test: classification results (`source = "inferred"`) survive `ontology.resync` and `ontology.rebuild` in `tests/integration/test_classification_survives_resync.py`

### Implementation for User Story 1

- [X] T009 [US1] Implement the classification rule table (signal predicates per semantic type: entity domain, `device_class`, name/label keyword patterns, area hints) in `custom_components/ontology/semantic_classifier.py` (depends on T002)
- [X] T010 [US1] Implement `async_classify_entities()` — full-graph classification pass, `MERGE` one node per (entity, type) pair, `source = "inferred"`, skipping any pair with an existing user override — in `custom_components/ontology/semantic_classifier.py` (depends on T009)
- [X] T011 [US1] Wire the classification pass into the full sync flow, gated by the automatic-classification option (FR-004), in `custom_components/ontology/graph_builder.py` (depends on T005, T010)
- [X] T012 [US1] Add per-semantic-type classification counts to the redacted diagnostics payload in `custom_components/ontology/diagnostics.py` (depends on T010)

**Checkpoint**: User Story 1 is fully functional and independently testable (SC-002).

---

## Phase 4: User Story 2 - Query the ontology safely with read-only Cypher (Priority: P1)

**Goal**: Expose `ontology.query` as a safe-by-construction, read-only Cypher query service with row-limit enforcement.

**Independent Test**: Call `ontology.query` with a read-only query (expect JSON results), a write-attempting query (expect rejection + logged warning), and an unbounded query (expect the row limit enforced) — independent of classification or the explorer existing.

### Tests for User Story 2

- [X] T013 [P] [US2] Unit test: tokenized keyword scanner rejects every deny-list keyword regardless of case/position, including inside comments, and does not false-positive on string literals containing keyword substrings in `tests/unit/test_query_service_safety.py`
- [X] T014 [P] [US2] Unit test: row-limit enforcement (default 100, max 1000) and the `truncated` response flag in `tests/unit/test_query_service_safety.py`
- [X] T015 [P] [US2] Contract test: `ontology.query` service schema (`cypher`, `parameters`, `limit`) and rejection-response shape in `tests/contract/test_services_contract.py`
- [X] T016 [P] [US2] Integration test: query row-limit enforcement and write-query rejection against a real Memgraph instance in `tests/integration/test_query_row_limit_enforcement.py`
- [X] T061 [P] [US2] Unit test: syntactically invalid Cypher queries are rejected with a clear error before execution, without attempting execution (FR-022) in `tests/unit/test_query_service_safety.py`

### Implementation for User Story 2

- [X] T017 [US2] Implement the tokenized Cypher safety validator (strip comments/string literals, then word-boundary regex match against the deny-list from T001) in `custom_components/ontology/query_service.py` (depends on T002, T001)
- [X] T018 [US2] Implement the bounded read-only query executor (stream results, stop early at the row limit, clear error on syntactically invalid queries per FR-022) in `custom_components/ontology/query_service.py` (depends on T017)
- [X] T019 [US2] Register the `ontology.query` service (schema validation, security-warning log on rejection per FR-020) in `custom_components/ontology/__init__.py` and `custom_components/ontology/services.yaml` (depends on T004, T018)

**Checkpoint**: User Stories 1 and 2 both work independently (SC-003).

---

## Phase 5: User Story 3 - Provide backend API for the ontology explorer (Priority: P1)

**Goal**: Expose read-only `websocket_api` commands for area context, entity context, and search, per [contracts/websocket-api.md](./contracts/websocket-api.md).

**Independent Test**: Request area context, entity context, and a search term against a populated graph and confirm bounded, credential-free, validated responses — without a sidebar panel existing.

### Tests for User Story 3

- [X] T020 [P] [US3] Contract test: `ontology/area_context` command request/response shape, not-found handling for an unknown `area_id` (FR-037), and credential-free response (FR-034) in `tests/contract/test_websocket_api_contract.py`
- [X] T021 [P] [US3] Contract test: `ontology/entity_context` command request/response shape, not-found handling for an unknown `entity_id` (FR-037), and credential-free response (FR-034) in `tests/contract/test_websocket_api_contract.py`
- [X] T022 [P] [US3] Contract test: `ontology/search` command request/response shape, input validation (FR-036), and bounded/credential-free response (FR-034, FR-035) in `tests/contract/test_websocket_api_contract.py`
- [X] T062 [US3] Performance/integration test: `ontology/area_context`, `ontology/entity_context`, and `ontology/search` each respond within 2 seconds on a ~5,000-node fixture graph (SC-005) in `tests/integration/test_websocket_api_performance.py`

### Implementation for User Story 3

- [X] T023 [US3] Implement the `ontology/area_context` command (area + related devices/entities/automations, input validation, not-found handling) in `custom_components/ontology/websocket_api.py` (depends on T002)
- [X] T024 [US3] Implement the `ontology/entity_context` command (entity + device + area + semantic classifications + direct dependencies + dashboards/cards, where available) in `custom_components/ontology/websocket_api.py` (depends on T023)
- [X] T025 [US3] Implement the `ontology/search` command (bounded/truncated results per FR-035) in `custom_components/ontology/websocket_api.py` (depends on T023)
- [X] T026 [US3] Register the websocket_api commands during `async_setup_entry` in `custom_components/ontology/__init__.py` (depends on T023, T024, T025)

**Checkpoint**: All P1 user stories (1, 2, 3) are independently functional — MVP complete.

---

## Phase 6: Dashboard Synchronization (supports User Story 3's dashboard context; Priority: P2)

**Goal**: Best-effort sync of Lovelace dashboard/card structure into the graph (FR-047–FR-050), tagged `source = "generated"`.

**Independent Test**: Sync a dashboard with a card displaying a known entity and a card referencing a deleted entity; confirm `Dashboard`/`DashboardCard` nodes and `CONTAINS_CARD`/`DISPLAYS_ENTITY` relationships are created correctly and the overall sync does not fail (quickstart.md Scenario F).

### Tests for Dashboard Synchronization

- [X] T027 [P] [DASH] Unit test: dashboard/card-to-graph mapping and tolerance for unloadable dashboards / dangling entity references (FR-050) in `tests/unit/test_dashboard_sync.py`
- [X] T028 [P] [DASH] Integration test: dashboard sync does not fail the overall sync when a dashboard is unloadable or a card references a deleted entity in `tests/integration/test_dashboard_sync_tolerance.py`

### Implementation for Dashboard Synchronization

- [X] T029 [DASH] Implement best-effort Lovelace dashboard/card discovery and `Dashboard`/`DashboardCard` `MERGE` (`source = "generated"`) with `CONTAINS_CARD`/`DISPLAYS_ENTITY` relationships in `custom_components/ontology/dashboard_sync.py` (depends on T002, T001)
- [X] T030 [DASH] Wire `dashboard_sync` into the full sync flow in `custom_components/ontology/graph_builder.py`, tolerant of load failures (depends on T029)

---

## Phase 7: User Story 4 - Manage semantic overrides by hand (Priority: P2)

**Goal**: Let users create/remove `source = "user"` semantic relationships that survive resync and rebuild.

**Independent Test**: Create a user-managed relationship, run a full resync and a rebuild, and confirm it survives both; remove it and confirm it does not reappear.

### Tests for User Story 4

- [X] T031 [P] [US4] Unit test: override CRUD helpers create/list/delete `source = "user"` relationships with a timestamp in `tests/unit/test_overrides.py`
- [X] T032 [P] [US4] Integration test: a user-managed relationship survives full `ontology.resync` and `ontology.rebuild` in `tests/integration/test_overrides_survival.py`

### Implementation for User Story 4

- [X] T033 [US4] Implement override CRUD helpers (create/list/delete a `source = "user"` relationship, timestamped) in `custom_components/ontology/overrides.py` (depends on T002)
- [X] T034 [US4] Add guard clauses so rebuild/resync (`custom_components/ontology/graph_builder.py`) and classification (`custom_components/ontology/semantic_classifier.py`) never create, modify, or delete any `source = "user"` node/relationship (depends on T010, T011, T033)

**Checkpoint**: User Story 4 works independently, building on User Story 1's semantic layer.

---

## Phase 8: User Story 5 - Validate ontology completeness and consistency (Priority: P2)

**Goal**: Run on-demand validation across all 9 categories, creating/resolving `ValidationFinding` nodes.

**Independent Test**: Run validation against a graph with known issues (entity with no area, orphan device, unavailable critical entity) and confirm findings are created correctly, then resolve the issues and confirm findings clear on the next run.

### Tests for User Story 5

- [X] T035 [P] [US5] Unit test: each of the 9 validation category detectors (`missing_area`, `missing_device`, `orphan_entity`, `orphan_device`, `duplicate_entity`, `unavailable_critical_entity`, `invalid_relationship`, `schema_mismatch`, `missing_semantic_classification`) in `tests/unit/test_validation_categories.py`
- [X] T036 [P] [US5] Integration test: validation finding lifecycle — created on detection, resolved when fixed, removed after remaining resolved across one subsequent run — in `tests/integration/test_validation_finding_lifecycle.py`
- [X] T037 [P] [US5] Contract test: `ontology.validate` runs only on explicit invocation, never automatically after sync (FR-017) in `tests/contract/test_services_contract.py`

### Implementation for User Story 5

- [X] T038 [US5] Implement all 9 validation category Cypher detectors in `custom_components/ontology/validation.py` (depends on T002, T001)
- [X] T039 [US5] Implement `ValidationFinding` `MERGE` plus resolve/retire lifecycle per the retention policy in `custom_components/ontology/validation.py` (depends on T038)
- [X] T040 [US5] Extend the `ontology.validate` service handler in `custom_components/ontology/__init__.py` to run `validation.py` and report the outcome, replacing v1's connectivity-only check (depends on T004, T039)
- [X] T041 [US5] Add validation finding counts (by category/severity) to the redacted diagnostics payload in `custom_components/ontology/diagnostics.py` (depends on T039)

**Checkpoint**: User Story 5 works independently, given User Story 1's semantic layer exists.

---

## Phase 9: User Story 6 - Refresh semantic classifications on demand (Priority: P2)

**Goal**: Expose `ontology.refresh_semantics` to recalculate inferred classifications without a full rebuild.

**Independent Test**: Change entities/devices affecting classification, call `ontology.refresh_semantics` (with and without `entity_id`), and confirm inferred classifications update while user-managed relationships are untouched.

### Tests for User Story 6

- [X] T042 [P] [US6] Unit test: `refresh_semantics` recalculates all entities or a single `entity_id`, and preserves user-managed relationships in `tests/unit/test_semantic_classifier.py`
- [X] T043 [P] [US6] Contract test: `ontology.refresh_semantics` service schema (optional `entity_id`) in `tests/contract/test_services_contract.py`

### Implementation for User Story 6

- [X] T044 [US6] Implement `async_refresh_semantics(entity_id=None)`, reusing the classification rule table scoped to one entity or all entities, in `custom_components/ontology/semantic_classifier.py` (depends on T009, T010, T033)
- [X] T045 [US6] Register the `ontology.refresh_semantics` service in `custom_components/ontology/__init__.py` and `custom_components/ontology/services.yaml` (depends on T004, T044)

**Checkpoint**: All P1 and P2 user stories are independently functional.

---

## Phase 10: User Story 7 - Export and import user overrides (Priority: P3)

**Goal**: Expose `ontology.export_overrides` / `ontology.import_overrides` for backup/migration of user-managed data.

**Independent Test**: Export user-managed overrides to a JSON payload, clear them, import the payload back, and confirm identical restoration; confirm malformed entries are rejected with clear errors.

### Tests for User Story 7

- [X] T046 [P] [US7] Unit test: export payload includes only `source = "user"` relationships and excludes credentials/secrets in `tests/unit/test_overrides.py`
- [X] T047 [P] [US7] Unit test: import rejects an unsupported/missing version, rejects invalid entries individually without failing a well-formed payload, and is idempotent on repeated import of the same payload in `tests/unit/test_overrides.py`
- [X] T048 [P] [US7] Contract test: `ontology.export_overrides` / `ontology.import_overrides` service schemas in `tests/contract/test_services_contract.py`
- [X] T049 [P] [US7] Integration test: export → clear → import round-trip against real Memgraph, confirming identical restored overrides in `tests/integration/test_overrides_export_import_roundtrip.py`

### Implementation for User Story 7

- [X] T050 [US7] Implement `export_overrides()` (versioned JSON payload, `source = "user"` only, redacted) in `custom_components/ontology/overrides.py` (depends on T033)
- [X] T051 [US7] Implement `import_overrides(payload)` (version check, per-entry validation, idempotent `MERGE` keyed on `relationship_type` + `source_ha_id` + `target_ha_id`) in `custom_components/ontology/overrides.py` (depends on T033)
- [X] T052 [US7] Register `ontology.export_overrides` and `ontology.import_overrides` services in `custom_components/ontology/__init__.py` and `custom_components/ontology/services.yaml` (depends on T004, T050, T051)

---

## Phase 11: User Story 8 - Browse the ontology from a sidebar panel (Priority: P3)

**Goal**: Register an "Ontology" sidebar panel that browses/searches the graph via the User Story 3 backend API.

**Independent Test**: Enable the Ontology panel, confirm it appears in the sidebar, and browse areas/devices/search results using the already-validated backend API.

### Implementation for User Story 8

- [X] T053 [US8] Implement a dependency-free `ontology-panel.js` ES module (browse areas/devices, view entity/device detail, search) consuming the `websocket_api` commands in `custom_components/ontology/panel/ontology-panel.js` (depends on T023, T024, T025)
- [X] T054 [US8] Register the static panel path and a `panel_custom` sidebar panel named "Ontology" in `custom_components/ontology/__init__.py` (depends on T053)
- [ ] T055 [US8] Manual validation: run quickstart.md Scenario G — browse to a device's area/entities/classifications within 3 clicks (SC-007)

**Checkpoint**: All 8 user stories plus dashboard synchronization are independently functional.

---

## Phase 12: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T056 [P] Finalize wording in `custom_components/ontology/strings.json` and `custom_components/ontology/translations/en.json` for all new v2 services and fields
- [X] T057 [P] Update `README.md` with a v2 capability overview (classification, query service, backend API, validation, overrides, dashboard sync, sidebar panel)
- [X] T058 Bump `version` in `custom_components/ontology/manifest.json` for the v2 release
- [ ] T059 Run full `quickstart.md` validation (Scenarios A–G) end-to-end
- [X] T060 [P] Run the full test suite via `.\scripts\test-windows.ps1` and fix any regressions against the existing v1 test suite

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories / Dashboard Sync (Phases 3–11)**: All depend on Foundational phase completion
  - P1 stories (US1, US2, US3) can proceed in parallel once Foundational is done
  - Dashboard Sync (P2) and US4 (P2) depend only on Foundational + their own prerequisites (T002/T001), not on P1 stories, but Dashboard Sync's value is fullest once US3 exists to surface it
  - US5 (P2) depends on User Story 1's semantic layer existing (T010) to validate `missing_semantic_classification`
  - US6 (P2) depends on User Story 1's classification rule table (T009, T010) and User Story 4's override CRUD (T033)
  - US7 (P3) depends on User Story 4's override CRUD (T033)
  - US8 (P3) depends on User Story 3's websocket commands (T023–T025)
- **Polish (Phase 12)**: Depends on all desired user stories being complete

### Within Each User Story

- Tests are written before implementation and MUST fail first
- Rule tables / detectors before the operations that use them
- Operation implementation before service/websocket registration
- Story complete before moving to the next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel (T002, T003)
- Foundational tasks marked [P] can run in parallel (T005, after T004 completes since both touch shared config)
- Once Foundational completes, US1, US2, and US3 can be worked in parallel (different files: `semantic_classifier.py`, `query_service.py`, `websocket_api.py`)
- All test tasks marked [P] within a story can run in parallel (different test files or independent test functions)
- Dashboard Sync, US4, US5, US6 (all P2) can be worked in parallel once their individual prerequisites are met
- US7 and US8 (both P3) can be worked in parallel once their prerequisites are met

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Unit test: classification rule matching for all 8 semantic types in tests/unit/test_semantic_classifier.py"
Task: "Unit test: classification never overwrites a user-managed relationship in tests/unit/test_semantic_classifier.py"
Task: "Integration test: classification survives resync/rebuild in tests/integration/test_classification_survives_resync.py"
```

## Parallel Example: User Stories 1–3 (once Foundational is done)

```bash
# Different files, no cross-story dependencies:
Task: "Implement classification rule table in custom_components/ontology/semantic_classifier.py"      # US1
Task: "Implement tokenized Cypher safety validator in custom_components/ontology/query_service.py"    # US2
Task: "Implement ontology/area_context command in custom_components/ontology/websocket_api.py"        # US3
```

---

## Implementation Strategy

### MVP First (P1 User Stories Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3 (US1), Phase 4 (US2), Phase 5 (US3)
4. **STOP and VALIDATE**: Run quickstart.md Scenarios A–C independently
5. Deploy/demo if ready — this is the MVP (classification + safe query service + backend API)

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add US1 → US2 → US3 → Test independently → Deploy/Demo (MVP!)
3. Add Dashboard Sync, US4, US5, US6 (P2) → Test independently → Deploy/Demo
4. Add US7, US8 (P3) → Test independently → Deploy/Demo
5. Each story adds value without breaking previous stories or v1 behavior

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: US1 (classification) then US6 (refresh, reuses US1's rule table)
   - Developer B: US2 (query service)
   - Developer C: US3 (backend API) then US8 (sidebar panel, reuses US3's commands)
   - Developer D: Dashboard Sync then US4 (overrides) then US5 (validation) then US7 (export/import)
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story (or DASH) for traceability back to spec.md
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
- On Windows, always run tests via `.\scripts\test-windows.ps1 [pytest args]` (see repo memory / README), never plain `pytest`
- No v2 task introduces a new PyPI dependency; `websocket_api`/`frontend` are Home Assistant core components (plan.md Technical Context)
