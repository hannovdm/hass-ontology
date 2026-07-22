---

description: "Task list template for feature implementation"
---

# Tasks: Home Assistant Ontology Integration v1

**Input**: Design documents from `/specs/001-ha-ontology-integration/`

**Prerequisites**: [plan.md](./plan.md) (required), [spec.md](./spec.md) (required for user stories), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Included. The project constitution (Principle VII) mandates specific v1 test categories (config flow success/failure, Memgraph connection success/failure, full-sync idempotency, entity/device/area/state update behavior, service execution, diagnostics redaction, setup/unload/reload, outage handling) for this feature, so test tasks are generated alongside implementation tasks.

**Organization**: Tasks are grouped by user story (from spec.md) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Single project — Home Assistant custom integration under `custom_components/ontology/`, with tests under `tests/{unit,integration,contract}/`, per [plan.md](./plan.md) Project Structure.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic package/test scaffolding

- [X] T001 Create `custom_components/ontology/` package directory with stub Python modules: `__init__.py`, `config_flow.py`, `const.py`, `coordinator.py`, `memgraph_client.py`, `graph_builder.py`, `event_listener.py`, `sensor.py`, `button.py`, `diagnostics.py`, `repairs.py`
- [X] T002 [P] Create `custom_components/ontology/manifest.json` with `domain: "ontology"`, `name`, `version: "1.0.0"`, `config_flow: true`, `iot_class: "local_push"`, `requirements: ["neo4j>=5.0"]`, `codeowners`
- [X] T003 [P] Create `custom_components/ontology/strings.json` and `custom_components/ontology/translations/en.json` skeletons for config flow, error, and repair strings
- [X] T004 [P] Create `custom_components/ontology/services.yaml` skeleton with empty stubs for `rebuild`, `resync`, `sync_entity`, `validate` (filled in during Phase 9)
- [X] T005 [P] Create `pyproject.toml` declaring runtime dependency `neo4j` and dev/test dependencies (`pytest`, `pytest-asyncio`, `pytest-homeassistant-custom-component`, `testcontainers`), plus `ruff`/`black` lint/format configuration per Constitution Python Standards
- [X] T006 [P] Create `tests/unit/`, `tests/integration/`, `tests/contract/` directories with `__init__.py` files and pytest configuration (`[tool.pytest.ini_options]` in `pyproject.toml`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T007 Implement `custom_components/ontology/const.py`: `DOMAIN`, `CONF_HOST`/`CONF_PORT`/`CONF_USERNAME`/`CONF_PASSWORD`/`CONF_DATABASE`/`CONF_ENCRYPTED`, `DEFAULT_PORT`, `SCHEMA_VERSION`, debounce window (research.md §5) and retry/backoff constants (research.md §6)
- [X] T008 Implement `custom_components/ontology/memgraph_client.py`: async Bolt client wrapper (`neo4j.AsyncGraphDatabase`) with `connect()`, `close()`, `run_query()`, a basic bounded-timeout `test_connection()` (connectivity check consumed by config flow validation in US1), connection timeouts, and an exponential-backoff retry helper (1s→60s cap, max 5 attempts) per research.md §2 and §6
- [X] T009 [P] Implement `custom_components/ontology/redact.py`: shared helper that strips `password`/secret fields from log records, diagnostics payloads, and error/exception text (FR-004)
- [X] T010 [P] Implement generic `merge_node()` / `merge_relationship()` helpers in `custom_components/ontology/graph_builder.py` that `MERGE` on the `ha_id` key and set `source`/`updated_at` properties per data-model.md conventions
- [X] T011 Implement `custom_components/ontology/coordinator.py` skeleton: `OntologyCoordinator(DataUpdateCoordinator)` holding the `memgraph_client`, an `asyncio.Lock` plus single-pending-slot queue enforcing serialized sync operations (FR-013a), with placeholder `async_rebuild`/`async_resync`/`async_sync_entity`/`async_validate` methods
- [X] T012 [P] Create `tests/conftest.py`: shared fixtures for a mocked `hass`, mocked config entry, and mocked `memgraph_client` (via `pytest-homeassistant-custom-component`)
- [X] T013 [P] Create `tests/integration/conftest.py`: `testcontainers`-based fixture that starts a real Memgraph container and yields a connected `memgraph_client` (research.md §3)

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Configure the connection to the local graph database (Priority: P1) 🎯 MVP

**Goal**: Let an administrator configure the Memgraph connection entirely through Devices & Services, with validation and redacted credentials.

**Independent Test**: Add the integration through Settings > Devices & Services, enter connection details for a running local Memgraph, and confirm it loads successfully (or reports a clear error when it cannot connect).

### Tests for User Story 1 ⚠️

- [X] T014 [P] [US1] Contract test verifying the config flow schema/steps match [contracts/config-flow.md](./contracts/config-flow.md) in `tests/contract/test_config_flow_contract.py`
- [X] T015 [P] [US1] Test: config flow succeeds against a reachable Memgraph and creates a config entry in `tests/unit/test_config_flow_success.py`
- [X] T016 [P] [US1] Test: config flow fails clearly against an unreachable Memgraph and does not create a config entry in `tests/unit/test_config_flow_failure.py`

### Implementation for User Story 1

- [X] T017 [US1] Implement the `user` step schema and submit handler in `custom_components/ontology/config_flow.py` (host/port/username/password/database/encrypted per contracts/config-flow.md), invoking `memgraph_client` connection validation
- [X] T018 [US1] Implement the reconfigure/options flow in `custom_components/ontology/config_flow.py` to update and re-validate an existing connection without requiring a manual restart (FR-003)
- [X] T019 [US1] Implement `custom_components/ontology/__init__.py` `async_setup_entry`, `async_unload_entry`, `async_reload_entry` wiring the coordinator/memgraph_client lifecycle to the config entry
- [X] T020 [US1] Add config-flow error keys (`cannot_connect`, `invalid_auth`) and form labels to `custom_components/ontology/strings.json` and `custom_components/ontology/translations/en.json`
- [X] T021 [US1] Verify password/secret redaction across config-flow logs and error messages using `redact.py` (FR-004, SC-007)

**Checkpoint**: User Story 1 is independently functional and testable (add/update the integration through the UI)

---

## Phase 4: User Story 2 - Confirm the graph database connection is healthy (Priority: P1)

**Goal**: Actively verify Memgraph connectivity so misconfigurations are caught immediately, without ever destabilizing Home Assistant.

**Independent Test**: Point the integration at a reachable database (expect success) and then at an unreachable one (expect a clear failure) without affecting Home Assistant's own stability.

### Tests for User Story 2 ⚠️

- [X] T022 [P] [US2] Integration test **(validated: PASSED against real Docker/Memgraph container, `TC_HOST=127.0.0.1` + Bolt-port readiness fix in `tests/integration/conftest.py`)**: `memgraph_client.test_connection()` succeeds against a real reachable Memgraph container in `tests/integration/test_connection_health.py`
- [X] T023 [P] [US2] Test: `async_setup_entry` raises `ConfigEntryNotReady` (not an unhandled exception) and never blocks HA startup when Memgraph is unavailable, in `tests/unit/test_setup_entry_unavailable.py`

### Implementation for User Story 2

- [X] T024 [US2] Enhance the `test_connection()` helper (introduced in T008) in `custom_components/ontology/memgraph_client.py` to distinguish `cannot_connect` vs `invalid_auth` failure modes for use by ongoing health checks
- [X] T025 [US2] Wire `custom_components/ontology/__init__.py` `async_setup_entry` to raise `ConfigEntryNotReady` on transient connection failure so HA startup remains stable and reload is retried through HA's normal mechanism
- [X] T026 [US2] Record connection health state (`healthy`/`error`) on `custom_components/ontology/coordinator.py` for later consumption by the health sensors (User Story 6)

**Checkpoint**: Connection validation is reliable and Home Assistant stability is proven under both success and failure conditions

---

## Phase 5: User Story 3 - Discover the full smart home structure (Priority: P1)

**Goal**: Discover areas, floors, devices, entities, automations, scenes, scripts, domains, integrations, and labels from Home Assistant.

**Independent Test**: Run discovery against a Home Assistant instance containing a mix of fully-configured and partially-configured entities/devices, and confirm all supported metadata types are read without the process failing.

### Tests for User Story 3 ⚠️

- [X] T027 [P] [US3] Test: discovery reads area/device/entity/floor/label registries and captures each entity's domain and source integration in `tests/unit/test_discovery_full.py`
- [X] T028 [P] [US3] Test: discovery still captures entities/devices with missing relationships (no device, no area) as incomplete data rather than failing in `tests/unit/test_discovery_partial.py`

### Implementation for User Story 3

- [X] T029 [US3] Implement `collect_areas`, `collect_floors`, `collect_devices`, `collect_entities`, `collect_labels` in `custom_components/ontology/graph_builder.py`, reading HA area/device/entity/floor/label registries (floor/label optional per FR-006)
- [X] T030 [US3] Implement `collect_automations`, `collect_scenes`, `collect_scripts` in `custom_components/ontology/graph_builder.py`, reading HA `automation`/`scene`/`script` domain entities and their referenced entity IDs
- [X] T031 [US3] Implement `collect_domains` and `collect_integrations` derivation from discovered entities in `custom_components/ontology/graph_builder.py`
- [X] T032 [US3] Handle and log (without raising) missing optional relationships during discovery — entity with no device, device with no area — per FR-006

**Checkpoint**: Full discovery runs cleanly against realistic (including partial) Home Assistant registry data

---

## Phase 6: User Story 4 - Build a queryable ontology from discovered data (Priority: P1) 🎯 MVP

**Goal**: Build the initial Memgraph ontology from discovered Home Assistant metadata, idempotently.

**Independent Test**: Run a full synchronization against a configured Home Assistant instance and confirm the resulting graph contains the expected structural elements and relationships, and that re-running the synchronization does not create duplicates.

### Tests for User Story 4 ⚠️

- [X] T033 [P] [US4] Integration test: full initial **(validated: PASSED against real Docker/Memgraph container)** synchronization against a real Memgraph container produces Home/Area/Device/Entity/Domain/Integration/Automation/Scene/Script/OntologySchema nodes and expected relationships in `tests/integration/test_initial_sync.py`
- [X] T034 [P] [US4] Integration test: running full **(validated: PASSED against real Docker/Memgraph container)** synchronization twice does not create duplicate nodes/relationships in `tests/integration/test_sync_idempotency.py`
- [X] T035 [P] [US4] Test: `MERGE` query construction for each node/relationship type uses `ha_id` as key and sets `source`/`updated_at` in `tests/unit/test_graph_builder_merge.py`
- [X] T035a [P] [US4] Integration test: `ontology.rebuild` **(validated: PASSED against real Docker/Memgraph container)** clears existing `source = "home_assistant"`/`"generated"` nodes/relationships before regenerating, while `source = "user"`/`"inferred"` elements survive untouched (FR-017a, Constitution Principle V) in `tests/integration/test_rebuild_preserves_user_data.py`

### Implementation for User Story 4

- [X] T036 [US4] Implement `build_full_graph(hass, memgraph_client)` orchestration in `custom_components/ontology/graph_builder.py`: runs all `collect_*` functions from User Story 3 and writes all nodes + relationships (data-model.md) via `merge_node`/`merge_relationship`
- [X] T037 [US4] Implement `OntologySchema` node creation on first successful full sync in `custom_components/ontology/graph_builder.py`, writing `version = SCHEMA_VERSION` (Constitution Principle VI)
- [X] T037a [US4] Implement `clear_generated_graph(memgraph_client)` in `custom_components/ontology/graph_builder.py`: deletes only nodes/relationships where `source` is `"home_assistant"` or `"generated"`, never touching `source = "user"`/`"inferred"` elements (FR-017a, data-model.md "Rebuild vs. resync")
- [X] T038 [US4] Wire `coordinator.async_rebuild` in `custom_components/ontology/coordinator.py` to call `clear_generated_graph` followed by `build_full_graph`, and wire the initial `async_config_entry_first_refresh` to call `build_full_graph` directly (no clear step on first sync) — both asynchronously without blocking HA setup (FR-013)
- [X] T039 [US4] Record last-sync timestamp and node/relationship counts on `custom_components/ontology/coordinator.py` after each full sync (for User Story 6 sensors)

**Checkpoint**: The MVP is complete — configuration (US1), validated connectivity (US2), discovery (US3), and an idempotent initial ontology (US4) all work together

---

## Phase 7: User Story 5 - Keep the ontology current as Home Assistant changes (Priority: P2)

**Goal**: Apply debounced, incremental graph updates in response to Home Assistant registry and primary-state-change events.

**Independent Test**: Make a live change in Home Assistant (e.g., renaming an area, moving a device, changing an entity's state) and confirm only the affected part of the graph updates without a full rebuild.

### Tests for User Story 5 ⚠️

- [X] T040 [P] [US5] Test: state-change debounce batches rapid successive changes for the same entity into a single update within the ~3s window (research.md §5) in `tests/unit/test_debounce.py`
- [X] T041 [P] [US5] Test: only primary state changes trigger a sync; attribute-only changes (e.g., battery %, signal strength) are filtered out (FR-012a) in `tests/unit/test_state_change_filter.py`
- [X] T042 [P] [US5] Integration test: renaming **(validated: PASSED against real Docker/Memgraph container, 3 tests)** an area / moving a device / adding-removing-renaming an entity updates only the affected node(s)/relationship(s) without a full rebuild in `tests/integration/test_incremental_updates.py`
- [X] T042a [P] [US5] Test: an incremental update that keeps failing after retries is marked failed/pending rather than silently dropped, and is retried on the next coordinator cycle (FR-020) in `tests/unit/test_failed_update_tracking.py`
- [X] T042b [P] [US5] Integration test: an entity/device/area is deleted **(validated: PASSED against real Docker/Memgraph container, 3 tests)** in Home Assistant while a full sync or another incremental update is already in flight; the queued update is handled as a removal without corrupting the graph or crashing the coordinator (edge case, spec.md Edge Cases) in `tests/integration/test_delete_during_sync.py`

### Implementation for User Story 5

- [X] T043 [US5] Implement `custom_components/ontology/event_listener.py`: registry update listeners (area/device/entity add/remove/update) forwarding change requests to the coordinator
- [X] T044 [US5] Implement the `state_changed` listener in `custom_components/ontology/event_listener.py`, filtering to primary-state changes only (FR-012a) with a per-entity debounce/throttle (research.md §5, FR-011)
- [X] T045 [US5] Implement single-element update functions (`update_entity`, `update_device`, `update_area`) in `custom_components/ontology/graph_builder.py` that `MERGE` only the affected node and its direct relationships
- [X] T045a [US5] Handle the race condition where the underlying HA registry element no longer exists by the time a queued update is processed in `update_entity`/`update_device`/`update_area` (`custom_components/ontology/graph_builder.py`): treat it as a removal instead of raising (edge case, spec.md Edge Cases)
- [X] T046 [US5] Route `event_listener` requests through the coordinator's serialized update path (FR-013a) in `custom_components/ontology/coordinator.py`, ensuring incremental updates never run concurrently with a full rebuild/resync
- [X] T046a [US5] Implement failed/pending-update tracking in `custom_components/ontology/coordinator.py`: an incremental update that exhausts retries is marked failed/pending (not dropped), surfaced via `sensor.ontology_last_error`, and retried on the next coordinator cycle (FR-020)

**Checkpoint**: The ontology stays current automatically without requiring manual rebuilds, high-frequency events are throttled, and failed updates are never silently lost

---

## Phase 8: User Story 6 - Monitor integration health from within Home Assistant (Priority: P2)

**Goal**: Expose health, counts, timing, error, and schema-version indicators plus manual rebuild/validate/resync controls.

**Independent Test**: Load the integration and confirm health, count, timing, and error indicators appear and update correctly, and that manual control actions are available and functional.

### Tests for User Story 6 ⚠️

- [X] T047 [P] [US6] Test: `sensor.ontology_health`/`_nodes`/`_relationships`/`_last_sync`/`_last_error`/`_schema_version` reflect coordinator data in `tests/unit/test_sensors.py`
- [X] T048 [P] [US6] Test: the health sensor transitions to an error state with a redacted `last_error` summary when a sync fails in `tests/unit/test_sensor_error_state.py`

### Implementation for User Story 6

- [X] T049 [US6] Implement `custom_components/ontology/sensor.py`: the six diagnostic sensors per [contracts/diagnostics.md](./contracts/diagnostics.md), reading from the coordinator
- [X] T050 [US6] Implement `custom_components/ontology/button.py`: `button.ontology_rebuild`/`_validate`/`_resync`, each invoking the corresponding coordinator method

**Checkpoint**: Operational visibility and manual control are available directly in the Home Assistant UI

---

## Phase 9: User Story 7 - Trigger ontology operations on demand (Priority: P2)

**Goal**: Expose `ontology.rebuild`/`resync`/`sync_entity`/`validate` as callable services for automations.

**Independent Test**: Invoke each operation independently and confirm the expected scope of change (full rebuild, refresh, single-entity refresh, or validation-only) occurs.

### Tests for User Story 7 ⚠️

- [X] T051 [P] [US7] Contract test verifying `custom_components/ontology/services.yaml` matches the service field/behavior contract in [contracts/services.md](./contracts/services.md), in `tests/contract/test_services_contract.py`
- [X] T052 [P] [US7] Test: each of `ontology.rebuild`/`resync`/`sync_entity`/`validate` invokes the correct coordinator method, and a service call made while another operation is running is queued/rejected per FR-013a, in `tests/unit/test_services.py`

### Implementation for User Story 7

- [X] T053 [US7] Fill in `custom_components/ontology/services.yaml` field schemas for `rebuild`, `resync`, `sync_entity` (`entity_id` field), and `validate` per contracts/services.md
- [X] T054 [US7] Register/unregister the four services in `custom_components/ontology/__init__.py`, routing each to `coordinator.async_rebuild`/`async_resync`/`async_sync_entity`/`async_validate`, with `sync_entity` validating the target entity exists

**Checkpoint**: All four operations are independently callable from automations/scripts with correct scoping and serialization

---

## Phase 10: User Story 8 - Protect against unsafe schema changes (Priority: P3)

**Goal**: Track the ontology schema version and fail safely (no silent mutation) on mismatch.

**Independent Test**: Build the initial graph, confirm a schema version is recorded, and then simulate a mismatched version to confirm the integration reports the mismatch instead of proceeding silently.

### Tests for User Story 8 ⚠️

- [X] T055 [P] [US8] Integration test: startup **(validated: PASSED against real Docker/Memgraph container)** with a mismatched `OntologySchema.version` in Memgraph fails to load, performs no graph writes, and creates a `schema_version_mismatch` repair issue, in `tests/integration/test_schema_mismatch.py`

### Implementation for User Story 8

- [X] T056 [US8] Implement the schema-version check in `custom_components/ontology/__init__.py` `async_setup_entry`: read `OntologySchema.version`, compare to `const.SCHEMA_VERSION`; proceed on match, abort setup without writing on mismatch (FR-017)
- [X] T057 [US8] Implement `schema_version_mismatch` repair issue creation in `custom_components/ontology/repairs.py` per [contracts/diagnostics.md](./contracts/diagnostics.md), directing the administrator to resolve manually

**Checkpoint**: Schema drift is detected and blocks unsafe automatic changes, with clear repair guidance

---

## Phase 11: User Story 9 - Diagnose and recover from connectivity problems (Priority: P3)

**Goal**: Provide redacted diagnostics and repair notifications for sustained Memgraph connectivity problems.

**Independent Test**: Download integration diagnostics (expect redacted, informative output) and simulate a sustained outage (expect a repair notification to appear).

### Tests for User Story 9 ⚠️

- [X] T058 [P] [US9] Test: diagnostics payload includes connection status/element counts/schema version and never includes password/secrets, in `tests/unit/test_diagnostics_redaction.py`
- [X] T059 [P] [US9] Test: after 3 consecutive failed sync attempts a `sustained_connection_failure` repair issue is created, and it clears once a subsequent sync succeeds, in `tests/unit/test_repair_sustained_outage.py`

### Implementation for User Story 9

- [X] T060 [US9] Implement `custom_components/ontology/diagnostics.py` `async_get_config_entry_diagnostics` producing the redacted payload per [contracts/diagnostics.md](./contracts/diagnostics.md)
- [X] T061 [US9] Implement consecutive-failure tracking and exponential-backoff retry (research.md §6, using the T008 retry helper) in `custom_components/ontology/coordinator.py`, triggering `sustained_connection_failure` repair issue creation/clearing in `custom_components/ontology/repairs.py`

**Checkpoint**: Administrators can self-diagnose and receive repair guidance without reading raw logs

---

## Phase 12: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation and hardening across all user stories

- [ ] T062 [P] Run all quickstart.md **(BLOCKED: requires a live, running Home Assistant instance with the integration installed via its UI — Docker/Memgraph alone is not sufficient for this manual scenario walkthrough; not available in this dev environment)** validation scenarios (A–D) end-to-end against a real Memgraph instance and record results
- [X] T062a [P] Integration test: first-run synchronization **(validated: PASSED against real Docker/Memgraph container)** against a Memgraph instance that already contains unrelated, non-ontology data only creates/touches the integration's own `ha_id`-keyed nodes/relationships and leaves the unrelated data untouched (edge case, spec.md Edge Cases) in `tests/integration/test_first_run_unrelated_data.py`
- [X] T063 [P] Performance validation **(validated: PASSED in ~15s against real Docker/Memgraph container for a 500-entity/100-device/10-area fixture, well under the 5-minute SC-001 budget, in `tests/integration/test_performance_initial_sync.py`)**: confirm initial full sync completes in under 5 minutes for a ~500 entity/device fixture (SC-001)
- [X] T064 [P] Security/redaction audit: verify logs, diagnostics output, and repair issue text across all modules never contain plaintext credentials (FR-004, SC-007)
- [X] T064a [P] Cloud-dependency audit: verify `custom_components/ontology/` imports no cloud SDKs and makes no outbound network calls other than the configured local Memgraph Bolt connection (SC-008)
- [X] T065 Code cleanup pass: finalize type hints and lint/format compliance across `custom_components/ontology/` per Constitution Python Standards

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational only
- **User Story 2 (Phase 4)**: Depends on Foundational (the base `test_connection()` check from T008 is already available) and on US1's `__init__.py` `async_setup_entry` (T019) to wire `ConfigEntryNotReady` handling
- **User Story 3 (Phase 5)**: Depends on Foundational only (discovery is independent of connection UI details)
- **User Story 4 (Phase 6)**: Depends on Foundational, and consumes US3's `collect_*` functions to build the graph — the MVP (US1+US2+US3+US4) is complete after this phase
- **User Story 5 (Phase 7)**: Depends on Foundational and US4's `graph_builder`/`coordinator` sync machinery
- **User Story 6 (Phase 8)**: Depends on Foundational and the coordinator state populated by US2/US4/US5
- **User Story 7 (Phase 9)**: Depends on Foundational and the coordinator methods established in US4/US5/US6
- **User Story 8 (Phase 10)**: Depends on Foundational and US4's `OntologySchema` node creation
- **User Story 9 (Phase 11)**: Depends on Foundational, US2's health-state recording, and US4's sync machinery
- **Polish (Phase 12)**: Depends on all desired user stories being complete

### Within Each User Story

- Tests MUST be written first and FAIL before implementation
- Discovery/data functions before graph-write orchestration
- Graph-write orchestration before coordinator wiring
- Coordinator wiring before UI-facing surfaces (sensors/buttons/services)
- Story complete before moving to next priority (in solo/sequential execution)

### Parallel Opportunities

- All Setup tasks marked [P] (T002-T006) can run in parallel after T001
- Foundational tasks marked [P] (T009, T010, T012, T013) can run in parallel once T007/T008/T011 land
- Once Foundational completes, US1 and US3 can start in parallel (no shared files); US2 should follow US1 (shares `config_flow.py`/`__init__.py`); US4 should follow US3 (consumes `collect_*`)
- All [P]-marked test tasks within a story can run in parallel with each other
- Different user stories can be worked on in parallel by different team members once Foundational is done, respecting the file-sharing dependencies noted above

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Contract test for config flow in tests/contract/test_config_flow_contract.py"
Task: "Test: config flow succeeds against reachable Memgraph in tests/unit/test_config_flow_success.py"
Task: "Test: config flow fails against unreachable Memgraph in tests/unit/test_config_flow_failure.py"
```

## Parallel Example: User Story 4

```bash
# Launch all tests for User Story 4 together:
Task: "Integration test: full initial sync in tests/integration/test_initial_sync.py"
Task: "Integration test: sync idempotency in tests/integration/test_sync_idempotency.py"
Task: "Test: MERGE query construction in tests/unit/test_graph_builder_merge.py"
Task: "Integration test: rebuild preserves user/inferred data in tests/integration/test_rebuild_preserves_user_data.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1–4 together)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3 (US1: configure connection), Phase 4 (US2: confirm connection healthy), Phase 5 (US3: discover structure), Phase 6 (US4: build queryable ontology)
4. **STOP and VALIDATE**: Run quickstart.md Scenario A — this is the MVP per spec.md (User Story 4's own rationale: "the minimum viable product once configuration, validation, and discovery are in place")
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add US1 → US2 → US3 → US4 → Test independently → Deploy/Demo (MVP!)
3. Add US5 (incremental updates) → Test independently → Deploy/Demo
4. Add US6 (health monitoring) + US7 (on-demand services) → Test independently → Deploy/Demo
5. Add US8 (schema safety) + US9 (diagnostics/repair) → Test independently → Deploy/Demo
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: US1 → US2 (connection/config lifecycle)
   - Developer B: US3 → US4 (discovery/graph build)
   - Developer C (after US4 lands): US5 (incremental updates)
   - Developer D: US6 + US7 (observability/services), then US8 + US9 (safety/diagnostics)
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
