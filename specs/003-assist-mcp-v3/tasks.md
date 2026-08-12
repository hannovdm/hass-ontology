---

description: "Task list template for feature implementation"
---

# Tasks: Home Assistant Ontology Integration v3 — Assist, MCP, Impact Analysis, and Local AI Readiness

**Input**: Design documents from `/specs/003-assist-mcp-v3/`

**Prerequisites**: [plan.md](./plan.md) (required), [spec.md](./spec.md) (required for user stories), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Test tasks are included per Constitution Principle VII ("Tests Before Confident Implementation") and to match the existing v1/v2 test conventions in this repository.

**Organization**: Tasks are grouped by user story (from spec.md, US1–US8) to enable independent implementation and testing of each story, in the same style as [specs/002-ontology-explorer-v2/tasks.md](../002-ontology-explorer-v2/tasks.md). A small number of tasks verify global non-functional requirements (FR-031, FR-032, FR-035, SC-007) with no single owning user story — these are labeled `[NFR]`, mirroring v2 tasks.md's `[DASH]` precedent for cross-cutting, non-story-specific work.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US8), or `[NFR]` for cross-cutting non-functional verification not owned by a single story
- Paths are relative to the repository root and reference the real files in `custom_components/ontology/` and `tests/` (see [plan.md](./plan.md) Project Structure)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish v3 constants and module scaffolding on top of the existing v1/v2 integration

- [X] T001 Update `custom_components/ontology/const.py`: add new service name constants (`SERVICE_SEARCH`, `SERVICE_AREA_CONTEXT`, `SERVICE_DEVICE_CONTEXT`, `SERVICE_ENTITY_CONTEXT`, `SERVICE_AUTOMATION_DEPENDENCIES`, `SERVICE_IMPACT_ANALYSIS`, `SERVICE_EXPORT_CONTEXT`); the `CONF_MCP_ENABLED` option key (default `False`, research.md §8); the MCP token/audit `Store` key prefixes (research.md §3, §4); the 30-day retention constant (`AGENT_AUDIT_RETENTION_DAYS = 30`, FR-036); impact-analysis hop-limit constant (research.md §5); and the context-export allow-list field table (data-model.md §4) as a Python constant structure
- [X] T002 [P] Create module skeletons with docstrings for `custom_components/ontology/query_tools.py`, `custom_components/ontology/impact_analysis.py`, `custom_components/ontology/context_export.py`, `custom_components/ontology/intent_handlers.py`, `custom_components/ontology/mcp_server.py`, and `custom_components/ontology/agent_audit.py`, plus the `custom_components/ontology/intents/` directory with a placeholder `en.yaml`
- [X] T003 [P] Add placeholder entries for the new v3 services, options-flow field, and intents to `custom_components/ontology/strings.json` and `custom_components/ontology/translations/en.json`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Add the `CONF_MCP_ENABLED` options-flow toggle (default `False`) to `custom_components/ontology/config_flow.py`, wired to the existing options-update-listener/reload pattern in `custom_components/ontology/__init__.py`/`custom_components/ontology/coordinator.py` (research.md §8, FR-023) (depends on T001)
- [X] T005 [P] Implement the redacted, `Store`-backed audit log foundation in `custom_components/ontology/agent_audit.py`: `async_append_record()`, the 30-day prune-on-append logic, and a periodic sweep registered via `async_track_time_interval` alongside the existing `FAILED_UPDATE_RETRY_INTERVAL_SECONDS` pattern (research.md §4, FR-036) (depends on T001, T002)

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Predefined safe ontology query tools (Priority: P1) 🎯 MVP

**Goal**: Provide the shared, transport-agnostic `query_tools.py` layer (search, area/device/entity context, automation dependencies) that every other v3 capability (Assist, impact analysis, context export, MCP) is built on top of, plus the `ToolResult` envelope (data-model.md §2).

**Independent Test**: Invoke each new `ontology.*` service directly (Developer Tools → Services) against a populated graph and confirm correct, bounded, JSON-compatible `ToolResult` responses — without Assist or MCP existing yet (quickstart.md Scenario A).

### Tests for User Story 1

- [X] T006 [P] [US1] Unit test: `query_tools.search()` bounds results by `limit`/`DEFAULT_QUERY_LIMIT`/`MAX_QUERY_LIMIT` (FR-001) in `tests/unit/test_query_tools.py`
- [X] T007 [P] [US1] Unit test: `query_tools.area_context()`/`device_context()`/`entity_context()`/`automation_dependencies()` each return the common `ToolResult` shape with `target`, `result_type`, `result`, `warnings` (FR-002, FR-003, FR-005) in `tests/unit/test_query_tools.py`
- [X] T008 [P] [US1] Unit test: every `query_tools` function returns `result_type: "not_found"` with `result: None` for an unresolvable identifier, without executing an unbounded query (FR-007, SC-006) in `tests/unit/test_query_tools.py`
- [X] T009 [P] [US1] Unit test: `query_tools` results never contain a key matching `redact.py`'s `SECRET_KEYS`/`_SECRET_PATTERN` (FR-006) in `tests/unit/test_query_tools.py`
- [X] T010 [P] [US1] Contract test: `ontology.search`, `ontology.area_context`, `ontology.device_context`, `ontology.entity_context`, `ontology.automation_dependencies` service schemas and `ToolResult` response shape (contracts/services.md) in `tests/contract/test_services_contract.py`
- [X] T011 [P] [US1] Integration test: `ontology.query` (existing v2 bounded read-only tool) rejects a write-intent Cypher query before execution, no data modified (FR-004, SC-004) in `tests/integration/test_query_row_limit_enforcement.py`

### Implementation for User Story 1

- [X] T012 [US1] Implement `query_tools.search(term, limit=None)` (bounded name/identifier match) in `custom_components/ontology/query_tools.py` (depends on T002, T001)
- [X] T013 [US1] Implement `query_tools.area_context(area)` (area's devices, entities, known relationships) in `custom_components/ontology/query_tools.py` (depends on T012)
- [X] T014 [US1] Implement `query_tools.device_context(device)` (device's exposed entities, area, known relationships) in `custom_components/ontology/query_tools.py` (depends on T012)
- [X] T015 [US1] Implement `query_tools.entity_context(entity)` (device, area, domain, integration, semantic classifications, direct dependencies where available) in `custom_components/ontology/query_tools.py` (depends on T012)
- [X] T016 [US1] Implement `query_tools.automation_dependencies(entity)` (related automations with reason where available) in `custom_components/ontology/query_tools.py` (depends on T012)
- [X] T017 [US1] Implement the shared `ToolResult` construction/redaction-check helper (data-model.md §2) reused by every function above and by later Assist/MCP/context-export call sites in `custom_components/ontology/query_tools.py` (depends on T013, T014, T015, T016)
- [X] T018 [US1] Register `ontology.search`, `ontology.area_context`, `ontology.device_context`, `ontology.entity_context`, `ontology.automation_dependencies` services in `custom_components/ontology/__init__.py` and `custom_components/ontology/services.yaml` (depends on T017; sequenced after T004 only because both edit `__init__.py`, not a feature dependency on the MCP toggle)

**Checkpoint**: User Story 1 is fully functional and independently testable (quickstart.md Scenario A) — this is the MVP shared layer every later story reuses.

---

## Phase 4: User Story 2 - Ask Home Assistant Assist about the ontology (Priority: P2)

**Goal**: Register native Assist intents (`intent_handlers.py` + `intents/en.yaml`) that let users ask conversational ontology questions via HA's default (non-LLM) conversation agent, delegating to User Story 1's `query_tools.py`.

**Independent Test**: Issue supported Assist queries (automation dependencies, area contents, entity context) against a populated graph and confirm correct resolved answers or a clear "not found" response (quickstart.md Scenario B).

### Tests for User Story 2

- [X] T019 [P] [US2] Unit test: `OntologyAutomationDependencies`, `OntologyAreaContents`, `OntologyEntityContext` intent handlers call the correct `query_tools` function and translate `ToolResult` into an `IntentResponse` (FR-008, FR-009, FR-010) in `tests/unit/test_intent_handlers.py`
- [X] T020 [P] [US2] Unit test: `OntologyDeviceContext`, `OntologyImpactAnalysis`, `OntologySearch` thin wrapper intents delegate correctly (FR-011) in `tests/unit/test_intent_handlers.py`
- [X] T021 [P] [US2] Integration test: an unresolvable entity/device/area reference through Assist returns a clear "not found" conversational response without running an unbounded query (FR-012, SC-006) in `tests/integration/test_assist_intent_not_found.py`

### Implementation for User Story 2

- [X] T022 [US2] Implement the `OntologyAutomationDependencies`, `OntologyAreaContents`, `OntologyEntityContext` `IntentHandler` subclasses (slot resolution, not-found handling) in `custom_components/ontology/intent_handlers.py` (depends on T016, T013, T015)
- [X] T023 [US2] Implement the `OntologyDeviceContext`, `OntologyImpactAnalysis`, `OntologySearch` thin wrapper `IntentHandler` subclasses in `custom_components/ontology/intent_handlers.py` (depends on T022, T014, T012)
- [X] T024 [US2] Author the bundled sentence definitions for all 6 intents in `custom_components/ontology/intents/en.yaml` (research.md §1) (depends on T022, T023)
- [X] T025 [US2] Register all 6 `IntentHandler`s via `intent.async_register(hass, handler)` during `async_setup_entry` in `custom_components/ontology/__init__.py` (depends on T022, T023, T024)

**Checkpoint**: User Story 2 works independently, building on User Story 1's query tools (quickstart.md Scenario B).

---

## Phase 5: User Story 3 - Entity impact analysis (Priority: P3)

**Goal**: Provide entity-level impact analysis (`impact_analysis.py`), returning related automations, scripts, scenes, dashboards, and semantic assets for a target entity.

**Independent Test**: Request impact analysis for a known entity and confirm the returned dependency lists match the graph's actual relationships, including the "no dependencies" and "not found" cases (quickstart.md Scenario C).

### Tests for User Story 3

- [X] T026 [P] [US3] Unit test: `impact_analysis.analyze(scope="entity", target=...)` returns the `ImpactAnalysisResult` shape (data-model.md §3) with all list fields present (FR-013) in `tests/unit/test_impact_analysis.py`
- [X] T027 [P] [US3] Unit test: `has_dependencies == False` returns a normal (non-error) empty-but-present result (FR-016) in `tests/unit/test_impact_analysis.py`
- [X] T028 [P] [US3] Integration test: entity impact analysis correctness against a real Memgraph fixture (automations/scripts/scenes/dashboards/semantic assets that reference the entity) (FR-013, US3 Scenario 1) in `tests/integration/test_impact_analysis_entity.py`
- [X] T029 [P] [US3] Integration test: entity with no downstream dependencies returns an empty list with a clear explanation, and an unresolvable entity id returns "not found" (FR-016, FR-017, US3 Scenario 3) in `tests/integration/test_impact_analysis_entity.py`

### Implementation for User Story 3

- [X] T030 [US3] Implement the bounded 2-hop entity-level impact-analysis Cypher traversal (`REFERENCES`, `CONTROLS`, `CLASSIFIED_AS`, `DISPLAYS_ENTITY`) via `MemgraphClient.run_query_limited` in `custom_components/ontology/impact_analysis.py` (research.md §5) (depends on T002, T017)
- [X] T031 [US3] Implement `impact_analysis.analyze(scope, target)` dispatch entry point and the `ImpactAnalysisResult` construction (data-model.md §3) for `scope="entity"` in `custom_components/ontology/impact_analysis.py` (depends on T030)
- [X] T032 [US3] Register the `ontology.impact_analysis` service in `custom_components/ontology/__init__.py` and `custom_components/ontology/services.yaml` (depends on T031; sequenced after T004 only because both edit `__init__.py`, not a feature dependency on the MCP toggle)

**Checkpoint**: User Story 3 works independently, given User Story 1's query/traversal foundation (quickstart.md Scenario C).

---

## Phase 6: User Story 4 - Device impact analysis (Priority: P4)

**Goal**: Aggregate entity-level impact analysis across all of a device's currently-exposed entities, using the device's current area relationship.

**Independent Test**: Request impact analysis for a known device with multiple exposed entities and confirm all entities and their downstream dependencies are aggregated correctly, including after the device moves area (quickstart.md Scenario D, steps 1-2).

### Tests for User Story 4

- [X] T033 [P] [US4] Integration test: device impact analysis aggregates all exposed entities, their dependencies, and related semantic objects (FR-014, US4 Scenario 1) in `tests/integration/test_impact_analysis_device.py`
- [X] T034 [P] [US4] Integration test: after a device is moved to another area and resynced, impact analysis reflects the device's current area relationship (FR-014, US4 Scenario 2) in `tests/integration/test_impact_analysis_device.py`
- [X] T035 [P] [US4] Integration test: an unresolvable device target returns "not found" (FR-017, US4 Scenario 3) in `tests/integration/test_impact_analysis_device.py`

### Implementation for User Story 4

- [X] T036 [US4] Implement `scope="device"` in `impact_analysis.analyze()` — aggregate entity-level impact analysis (T030/T031) across the device's live `HAS_ENTITY` edges, using current `HAS_AREA`/`HAS_DEVICE` relationships (research.md §5) in `custom_components/ontology/impact_analysis.py` (depends on T031)

**Checkpoint**: User Story 4 works independently, building on User Story 3's entity-level traversal (quickstart.md Scenario D steps 1-2).

---

## Phase 7: User Story 5 - Area impact analysis (Priority: P5)

**Goal**: Aggregate device-level impact analysis across an area's current devices and directly-related entities.

**Independent Test**: Request impact analysis for a known area containing devices and entities and confirm the aggregated result includes all affected devices, entities, and related automations/scripts/scenes/dashboards (quickstart.md Scenario D, steps 3-5).

### Tests for User Story 5

- [X] T037 [P] [US5] Integration test: area impact analysis returns affected devices, affected entities, and related automations/scripts/scenes/dashboards where available (FR-015, US5 Scenario 1) in `tests/integration/test_impact_analysis_area.py`
- [X] T038 [P] [US5] Integration test: an area with no known devices/entities returns an empty result with a clear explanation (FR-016, US5 Scenario 2) in `tests/integration/test_impact_analysis_area.py`
- [X] T039 [P] [US5] Performance/integration test: entity, device, and area impact-analysis calls and every predefined query-tool call each complete within 3 seconds on a several-thousand-node fixture graph (SC-005) in `tests/integration/test_query_tools_performance.py`

### Implementation for User Story 5

- [X] T040 [US5] Implement `scope="area"` in `impact_analysis.analyze()` — aggregate device-level impact analysis (T036) across the area's current devices and directly-related entities (research.md §5) in `custom_components/ontology/impact_analysis.py` (depends on T036)

**Checkpoint**: All impact-analysis scopes (US3-US5) are independently functional (quickstart.md Scenario D complete).

---

## Phase 8: User Story 6 - Local AI context export (Priority: P6)

**Goal**: Export allow-listed JSON context documents (area, entity, device, automation, impact, whole-home) for local AI agents, per the allow-list field table (data-model.md §4, research.md §6).

**Independent Test**: Request each export type against a populated graph and confirm well-formed JSON with zero secrets/tokens/passwords/credentials present, audited against known sensitive test values (quickstart.md Scenario E).

### Tests for User Story 6

- [X] T041 [P] [US6] Unit test: allow-list field projections for each node type (`Area`, `Device`, `Entity`, `Automation`, `Scene`/`Script`, `SemanticType`, `ValidationFinding`, `Dashboard`/`DashboardCard`) include only the fields listed in data-model.md §4 (FR-020) in `tests/unit/test_context_export.py`
- [X] T042 [P] [US6] Unit test: a node property containing "token"/"password"/"secret"/"key"/"credential" is never present in any projection, even if it exists on the underlying node (FR-020, SC-002) in `tests/unit/test_context_export.py`
- [X] T043 [P] [US6] Contract test: `ontology.export_context` service schema (`export_type`, `target`) and response shape (contracts/services.md) in `tests/contract/test_services_contract.py`
- [X] T044 [P] [US6] Integration test: area/entity/whole-home export documents against a real Memgraph fixture seeded with known fake sensitive values — confirm zero secrets/tokens/credentials appear in any export (FR-019, FR-020, FR-021, FR-022, SC-002, US6 Scenarios 1-4) in `tests/integration/test_context_export_redaction.py`

### Implementation for User Story 6

- [X] T045 [US6] Implement the allow-list field-projection table and per-node-type projection helper (data-model.md §4) in `custom_components/ontology/context_export.py` (depends on T002, T001)
- [X] T046 [US6] Implement `context_export.export(export_type="area"|"whole_home", target=None)` (devices, entities, automations, semantic assets, validation findings where available, FR-021) in `custom_components/ontology/context_export.py` (depends on T045, T013)
- [X] T047 [US6] Implement `context_export.export(export_type="entity"|"device"|"automation", target)` (direct graph relationships only, FR-022) in `custom_components/ontology/context_export.py` (depends on T045, T014, T015)
- [X] T048 [US6] Implement `context_export.export(export_type="impact", target)` (pass `ImpactAnalysisResult` nested dicts through the allow-list projections, data-model.md §4) in `custom_components/ontology/context_export.py` (depends on T045, T040)
- [X] T049 [US6] Register the `ontology.export_context` service in `custom_components/ontology/__init__.py` and `custom_components/ontology/services.yaml` (depends on T046, T047, T048; sequenced after T004 only because both edit `__init__.py`, not a feature dependency on the MCP toggle)

**Checkpoint**: User Story 6 works independently, given User Story 1's context functions and User Story 3-5's impact analysis (quickstart.md Scenario E).

---

## Phase 9: User Story 7 - Local MCP-compatible read-only endpoint (Priority: P7)

**Goal**: Expose an opt-in, local-only, token-authenticated MCP-compatible JSON-RPC endpoint (`mcp_server.py`) dispatching to the same shared `query_tools`/`impact_analysis`/`context_export` functions.

**Independent Test**: Enable MCP support, connect a local client, invoke a read-only tool, and confirm structured results; separately confirm no endpoint is exposed when MCP support is left disabled (quickstart.md Scenario F).

### Tests for User Story 7

- [X] T050 [P] [US7] Unit test: MCP local access token generation (`secrets.token_urlsafe(32)`), `Store` persistence, and regeneration invalidates the previous token (research.md §3) in `tests/unit/test_mcp_server_auth.py`
- [X] T051 [P] [US7] Unit test: local-binding guard rejects a non-loopback/non-local-network `request.remote` with HTTP 403 (FR-024) in `tests/unit/test_mcp_server_auth.py`
- [X] T052 [P] [US7] Unit test: missing/invalid bearer token is rejected with HTTP 401 and no tool executes (FR-034) in `tests/unit/test_mcp_server_auth.py`
- [X] T053 [P] [US7] Unit test: a `tools/call` for `query` (or any tool) containing a data-modifying Cypher keyword — including mixed read+write payloads — is rejected in full before execution, reusing v2's `query_service.py` deny-list (FR-026, FR-033, Edge Case) in `tests/unit/test_mcp_server_auth.py`
- [X] T054 [P] [US7] Contract test: `initialize`, `tools/list` (8 read-only tools with `inputSchema`), and `tools/call` request/response JSON-RPC shapes (contracts/mcp-endpoint.md) in `tests/contract/test_mcp_server_contract.py`
- [X] T055 [P] [US7] Integration test: on fresh install/upgrade with MCP left disabled, `POST /api/ontology/mcp` returns HTTP 404 (FR-023, SC-003, US7 Scenario 2) in `tests/integration/test_mcp_endpoint_e2e.py`
- [X] T056 [P] [US7] Integration test: with MCP enabled and a valid token, `initialize` → `tools/list` → `tools/call` (`entity_context`) end-to-end round trip returns structured JSON context (US7 Scenario 1, 3) in `tests/integration/test_mcp_endpoint_e2e.py`

### Implementation for User Story 7

- [X] T057 [US7] Implement MCP local access token generation/storage (`secrets.token_urlsafe(32)`, dedicated `Store` file per config entry) and the `button.ontology_regenerate_mcp_token` control entity in `custom_components/ontology/mcp_server.py` and `custom_components/ontology/button.py` (research.md §3) (depends on T004)
- [X] T058 [US7] Implement the `HomeAssistantView` at `POST /api/ontology/mcp` — enablement gate (404 when disabled), local-only binding check (403), and bearer-token validation (401) — in `custom_components/ontology/mcp_server.py` (depends on T057)
- [X] T059 [US7] Implement `initialize` and `tools/list` (8 read-only tools with `inputSchema` matching contracts/services.md) in `custom_components/ontology/mcp_server.py` (depends on T058)
- [X] T060 [US7] Implement `tools/call` dispatch to `query_tools`/`impact_analysis`/`context_export`/`query_service` functions, including write-intent rejection (reusing v2's deny-list) for mixed read+write payloads (FR-026, FR-027, FR-033) in `custom_components/ontology/mcp_server.py` (depends on T059, T017, T031, T040, T049)
- [X] T061 [US7] Conditionally register the `mcp_server.py` view during `async_setup_entry`, gated by `CONF_MCP_ENABLED` (FR-023) in `custom_components/ontology/__init__.py` (depends on T060)

**Checkpoint**: User Story 7 works independently, reusing every prior story's shared functions (quickstart.md Scenario F).

---

## Phase 10: User Story 8 - Audit and diagnostics for agent access (Priority: P8)

**Goal**: Wire redacted `AssistQueryRecord`/`AgentQueryRecord`/`ImpactAnalysisRecord`/`ContextExportRecord` audit entries (data-model.md §5) into every Assist intent (US2) and MCP endpoint (US7) call site, and surface a redacted summary in diagnostics.

**Independent Test**: Invoke ontology queries through Assist and MCP and confirm diagnostic metadata is recorded without secrets or full prompts, and that rejected write/auth attempts are separately recorded (quickstart.md Scenario G).

### Tests for User Story 8

- [X] T062 [P] [US8] Unit test: `agent_audit.py` record redaction — no raw utterance, no token/credential value, ever appears in any record type (FR-029, FR-030) in `tests/unit/test_agent_audit.py`
- [X] T063 [P] [US8] Unit test: records older than 30 days are pruned on append and via the periodic sweep (FR-036) in `tests/unit/test_agent_audit.py`
- [X] T064 [P] [US8] Integration test: an Assist ontology query records exactly one `AssistQueryRecord`, an MCP tool call records an `AgentQueryRecord` (`mcp_tool_call`), a rejected MCP write records `mcp_write_rejected`, and a rejected/missing token records `mcp_auth_rejected` (FR-028, FR-029, FR-030, US8 Scenarios 1-3) in `tests/integration/test_agent_audit_lifecycle.py`
- [X] T065 [P] [US8] Integration test: a record older than the 30-day retention window is no longer present in diagnostics after the window elapses (FR-036) in `tests/integration/test_agent_audit_lifecycle.py`

### Implementation for User Story 8

- [X] T066 [US8] Add `AssistQueryRecord` append calls (intent name, status, result count, timestamp — no raw utterance) to every `IntentHandler` in `custom_components/ontology/intent_handlers.py` (depends on T005, T025)
- [X] T067 [US8] Add `AgentQueryRecord` append calls (`mcp_tool_call`, `mcp_write_rejected`, `mcp_auth_rejected`) to the MCP view's token-validation, local-binding, and `tools/call` dispatch paths in `custom_components/ontology/mcp_server.py` (depends on T005, T061)
- [X] T068 [US8] Add `ImpactAnalysisRecord`/`ContextExportRecord` append calls to `impact_analysis.analyze()` and `context_export.export()` in `custom_components/ontology/impact_analysis.py` and `custom_components/ontology/context_export.py` (depends on T005, T040, T049)
- [X] T069 [US8] Extend `custom_components/ontology/diagnostics.py` with a redacted Assist/MCP audit summary (counts by tool/status, drawn from `agent_audit.py`, never raw entries) (depends on T066, T067, T068)

**Checkpoint**: All 8 user stories are independently functional (quickstart.md Scenario G).

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories, plus v3-wide non-functional verification (FR-031, FR-032, SC-007)

- [X] T070 [P] [NFR] Integration test: `async_setup_entry` never depends on reachability of any external local AI runtime, and Home Assistant startup succeeds with zero failures attributable to v3 with no external AI runtime running (FR-031, FR-032, SC-007) in `tests/integration/test_first_run_unrelated_data.py`
- [X] T071 [P] Finalize wording in `custom_components/ontology/strings.json` and `custom_components/ontology/translations/en.json` for all new v3 services, options-flow field, and intents
- [X] T072 [P] Update `README.md` with a v3 capability overview (predefined query tools, Assist intents, impact analysis, context export, MCP endpoint, audit/diagnostics)
- [X] T073 Bump `version` in `custom_components/ontology/manifest.json` for the v3 release
- [ ] T074 Run full `quickstart.md` validation (Scenarios A-H) end-to-end
- [X] T075 [P] Run the full test suite via `.\scripts\test-windows.ps1` and fix any regressions against the existing v1/v2 test suite
- [X] T076 [P] [NFR] Unit test: `SCHEMA_VERSION` and the set of `LABEL_*`/`REL_*` constants in `custom_components/ontology/const.py` are unchanged from the v2 baseline — v3 introduces zero new Memgraph node labels/relationship types/schema version bump (FR-035, data-model.md §1) in `tests/unit/test_query_tools.py`
- [X] T077 [P] [US7] Integration test: calling the same target via a direct service (`ontology.entity_context`) and via MCP `tools/call` (`entity_context`) produces identical redaction/result-limit behavior, confirming FR-027 parity between access channels in `tests/integration/test_mcp_endpoint_e2e.py` (depends on T018, T060)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phases 3-10)**: All depend on Foundational phase completion
  - US1 (Phase 3) has no dependency on other stories — it is the shared foundation every later story reuses
  - US2 (Phase 4) depends on US1's `query_tools.py` functions (T012-T017)
  - US3 (Phase 5) depends on US1's `ToolResult` helper (T017) and `MemgraphClient` access
  - US4 (Phase 6) depends on US3's entity-level traversal (T030, T031)
  - US5 (Phase 7) depends on US4's device-level aggregation (T036)
  - US6 (Phase 8) depends on US1's context functions (T013-T015) and US5's area-level impact analysis (T040)
  - US7 (Phase 9) depends on US1 (T017), US3-US5 (T031, T036, T040), and US6 (T049) — it dispatches to all of them
  - US8 (Phase 10) depends on US2 (T025) and US7 (T061) already emitting the events it records, plus US3-US6's `analyze()`/`export()` entry points
- **Polish (Phase 11)**: Depends on all desired user stories being complete

### Within Each User Story

- Tests are written before implementation and MUST fail first
- Shared/lower-level functions before the operations/handlers that call them
- Function implementation before service/intent/endpoint registration
- Story complete before moving to the next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel (T002, T003)
- Foundational task T005 can run in parallel with T004 (different files)
- All test tasks marked [P] within a story can run in parallel (different test files or independent test functions)
- Within US1, T013-T016 touch the same file (`query_tools.py`) so are sequenced, not [P]; test tasks T006-T011 are [P] (different assertions/files)
- US3, US4, US5 must proceed sequentially (each aggregates the previous scope's result) — not parallelizable across stories
- US2 and US3 (once US1 is done) can be worked in parallel by different developers (different files: `intent_handlers.py` vs `impact_analysis.py`)
- US6 can start once US1 and US5 are done, in parallel with continued US7 test-writing
- US8's test tasks (T062-T065) can be written in parallel with US7 implementation, but US8 implementation tasks (T066-T069) must wait for US2/US7 to exist

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Unit test: query_tools.search() bounds results by limit in tests/unit/test_query_tools.py"
Task: "Unit test: area/device/entity/automation-dependency functions return the common ToolResult shape in tests/unit/test_query_tools.py"
Task: "Unit test: not_found handling for unresolvable identifiers in tests/unit/test_query_tools.py"
Task: "Unit test: no secret keys ever appear in query_tools results in tests/unit/test_query_tools.py"
Task: "Contract test: new service schemas and ToolResult response shape in tests/contract/test_services_contract.py"
Task: "Integration test: ontology.query rejects write-intent Cypher in tests/integration/test_query_row_limit_enforcement.py"
```

## Parallel Example: User Stories 2 and 3 (once User Story 1 is done)

```bash
# Different files, no cross-story dependencies:
Task: "Implement OntologyAutomationDependencies/OntologyAreaContents/OntologyEntityContext intent handlers in custom_components/ontology/intent_handlers.py"   # US2
Task: "Implement the bounded 2-hop entity-level impact-analysis traversal in custom_components/ontology/impact_analysis.py"                                    # US3
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3 (US1)
4. **STOP and VALIDATE**: Run quickstart.md Scenario A independently
5. Deploy/demo if ready — this is the MVP (shared, safe, bounded query tools that every later capability builds on)

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add US1 → Test independently → Deploy/Demo (MVP!)
3. Add US2 (Assist) → Test independently → Deploy/Demo
4. Add US3 → US4 → US5 (impact analysis, entity → device → area) → Test independently after each → Deploy/Demo
5. Add US6 (context export) → Test independently → Deploy/Demo
6. Add US7 (MCP endpoint, opt-in/disabled by default) → Test independently → Deploy/Demo
7. Add US8 (audit/diagnostics) → Test independently → Deploy/Demo
8. Each story adds value without breaking previous stories or v1/v2 behavior

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once US1 is done:
   - Developer A: US2 (Assist intents)
   - Developer B: US3 → US4 → US5 (impact analysis, sequential — each scope builds on the previous)
   - Developer C: starts US7's auth/token/transport scaffolding (T057-T059) once US1 exists, then joins US6/US7 dispatch wiring once US5/US6 land
3. US6 starts once US1 and US5 are both done
4. US7 starts once US1, US3-US5, and US6 are all done (it dispatches to all of them)
5. US8 starts once US2 and US7 are both done (it instruments their call sites)
6. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story (US1-US8) for traceability back to spec.md
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
- On Windows, always run tests via `.\scripts\test-windows.ps1 [pytest args]` (see repo memory / README), never plain `pytest`
- No v3 task introduces a new PyPI dependency; `homeassistant.helpers.intent` and `homeassistant.components.http` are Home Assistant core components (plan.md Technical Context, research.md §1-§2)
- v3 introduces zero new Memgraph node labels, relationship types, or a `SCHEMA_VERSION` bump — every graph-touching task above is read-only (data-model.md §1)
- T074 remains unchecked: it requires manually walking through quickstart.md Scenarios A-H against a live Home Assistant instance with the integration installed via its UI (Developer Tools service calls, the Assist conversation UI, a real MCP client) - the same "needs a live running Home Assistant instance" limitation recorded for v1/v2's equivalent manual-validation task. Every scenario's underlying behavior is otherwise covered by automated unit/contract/integration tests (each test file's docstring cross-references its quickstart Scenario letter).

## Phase 12: Convergence

- [X] T078 CRITICAL enforce recursive key-pattern and value redaction across query-tool results, MCP responses, context-export projections, and raw-query target metadata, with hostile secret-value tests, per Constitution II, FR-006, FR-020, FR-027, and SC-002 (partial)
- [X] T079 CRITICAL enforce an allow-listed and recursively redacted storage boundary in `custom_components/ontology/agent_audit.py`, with tests that submit raw utterances, credentials, and secret-looking values, per Constitution II, FR-029, and SC-002 (partial)
- [X] T080 Enforce the current MCP enablement option for every request and cover enabled-to-disabled config-entry reload so a previously registered route cannot serve tools per FR-023, SC-003, and plan: MCP toggle (contradicts)
- [X] T081 Bound every predefined context and dependency collection, propagate truncation warnings, and test high-fanout payload limits per FR-006 and US1/AC5 (partial)
- [X] T082 Report specific incomplete or unavailable relationship warnings from area, device, entity, and automation-dependency query operations per FR-005 and US1/AC5 (partial)
- [X] T083 Include automation relationship reasons, area entities grouped by device, and device, area, domain, integration, classifications, and direct dependencies in Assist responses per FR-008, FR-009, FR-010, and US2/AC1-3 (partial)
- [X] T084 Replace unbounded impact collections and sequential device/area fan-out with bounded aggregate traversal plus truncation metadata, and verify the three-second responsiveness budget under high fan-out per FR-018 and SC-005 (partial)
- [X] T085 Resolve and incorporate each device's current area relationship in device impact analysis, including an area-move regression test, per FR-014 and US4/AC2 (partial)
- [X] T086 Synchronize direct entity area overrides as `Entity-[:HAS_AREA]->Area` relationships and cover them in area context and impact analysis per FR-002, FR-015, and plan: direct area entities (partial)
- [X] T087 Export all available direct entity, device, and automation relationships, including entity domain, integration, and semantic classifications, with allow-listed projections per FR-022 and US6/AC2 (partial)
- [X] T088 Restrict MCP requests to an explicitly configured local network boundary using trusted-proxy-aware client resolution, with proxied external-client rejection tests, per FR-024 (partial)
- [X] T089 Complete audit coverage for Assist queries, all MCP success/rejection/error paths, impact analysis, and context export, recording accurate status, count, error category, and rejected operation type per FR-028, FR-030, US8/AC1-3, and T068 (partial)
- [X] T090 Add real-Memgraph integration coverage proving scripts, scenes, dashboards, and semantic assets for entity, device, and area impact results per FR-013, FR-014, FR-015, Constitution VII, T028, T033, and T037 (missing)
- [X] T091 Implement a compact, bounded whole-home context summary with truncation metadata and high-cardinality tests per US6/AC3 and plan: compact whole-home export (partial)
- [X] T092 Replace fixed-path Assist sentence overwrites with a collision-safe managed installation strategy that preserves user-authored custom sentences per plan: bundled Assist sentences and delivery boundary (unrequested)
