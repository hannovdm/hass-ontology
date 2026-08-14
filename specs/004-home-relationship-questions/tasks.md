# Tasks: Home Relationship Questions

**Input**: Design documents from `/specs/004-home-relationship-questions/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: Required by the feature specification, success criteria, quickstart, and Constitution Principle VII. Write the listed tests first and confirm they fail for the intended behavior before implementation.

**Organization**: Tasks are grouped by user story so each story can be implemented and validated as an independent increment after the shared foundation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with the immediately preceding eligible work because it touches a different file and has no dependency on that work; explicit earlier prerequisites still apply.
- **[Story]**: Maps implementation work to `US1` through `US6` in `spec.md`.
- Every checklist item names the exact file or files it owns.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish shared constants and deterministic fixtures without changing runtime behavior.

- [X] T001 Define schema `3.0.0`, measurement fields/statuses, energy roles, user-knowledge labels/relationships, option defaults, service names, and intent names in `custom_components/ontology/const.py`
- [X] T002 Add reusable battery, power, device/entity ambiguity, automation dependency, and gas-cylinder fixture builders in `tests/conftest.py` after T001 establishes shared constants
- [X] T003 [P] Add reusable Memgraph seed/query helpers for v2 migration and durable statement assertions in `tests/integration/conftest.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add atomic graph evolution, shared measurement ingestion, configuration, and deterministic result semantics needed by multiple stories.

**CRITICAL**: No user story implementation begins until this phase passes its focused tests.

### Tests for Foundational Infrastructure

- [X] T004 [P] Add managed write-transaction commit, rollback, exception-normalization, and cancellation tests in `tests/unit/test_memgraph_client.py`
- [X] T005 [P] Add exact `2.0.0` to `3.0.0`, fresh install, already-current, rollback, rerun, and unsupported-version migration tests in `tests/integration/test_schema_migration_v3.py`
- [X] T006 [P] Add battery/power normalization, strict unit, finite/range, unavailable-transition, and `last_updated` preservation tests in `tests/unit/test_measurement_normalization.py`
- [X] T007 [P] Extend accepted attribute-only, ignored unrelated attribute, retained debounce snapshot, and non-blocking outage tests in `tests/unit/test_state_change_filter.py`
- [X] T008 [P] Add threshold, maximum-age, active-power, and result-bound option validation/contract tests in `tests/contract/test_config_flow_contract.py`
- [X] T009 [P] Add exact-ID precedence, unique-name resolution, bounded ambiguity, stable ordering, and `ToolResult.outcome` compatibility tests in `tests/unit/test_target_resolution.py`

### Implementation for Foundational Infrastructure

- [X] T010 Implement an async managed write-transaction API using driver `session.execute_write` in `custom_components/ontology/memgraph_client.py`
- [X] T011 Implement the idempotent exact-predecessor additive migration with schema-marker-last semantics in `custom_components/ontology/schema_migrations.py`
- [X] T012 Wire migration before schema mismatch rejection and preserve fresh/current/unsupported startup behavior in `custom_components/ontology/__init__.py`
- [X] T013 Implement strict battery percentage and W/kW current-measurement normalization with obsolete numeric-field clearing in `custom_components/ontology/graph_builder.py`
- [X] T014 Update allow-listed state/attribute comparison and retain the accepted per-entity trailing debounce snapshot in `custom_components/ontology/event_listener.py`
- [X] T015 Serialize accepted measurement context and graph writes without replacing Home Assistant `last_updated` with sync time in `custom_components/ontology/coordinator.py`
- [X] T016 Implement low-battery, active-power, and maximum-age options with defaults and validation in `custom_components/ontology/config_flow.py`, `custom_components/ontology/strings.json`, and `custom_components/ontology/translations/en.json`
- [X] T017 Implement the operation-aware deterministic resolver and backward-compatible `ToolResult` outcomes in `custom_components/ontology/query_tools.py`
- [X] T018 Run the focused foundational test set through `scripts/test-windows.ps1` and verify the Phase 2 cases in `specs/004-home-relationship-questions/quickstart.md`

**Checkpoint**: Schema v3 is safe, measurements are current and privacy-bounded, options validate, and all later reads share deterministic resolution/outcome behavior.

---

## Phase 3: User Story 1 - Find Rooms With Low Batteries (Priority: P1) MVP

**Goal**: Return fresh percentage battery readings strictly below the configured threshold, grouped by current room and de-duplicated by device.

**Independent Test**: Populate multiple areas with below/equal/above-threshold, duplicate-device, direct-area, unavailable, malformed, and stale battery readings; verify only qualifying readings are grouped under the correct rooms.

### Tests for User Story 1

- [X] T019 [P] [US1] Add bounded low-battery grouping, strict threshold, freshness cutoff, de-duplication, direct-area, exact unavailable/invalid/unsupported aggregate warning counts, stale-reading exclusion, empty, and truncation tests in `tests/unit/test_low_battery_query.py`
- [X] T020 [P] [US1] Add real-graph measurement synchronization and low-battery area relationship tests in `tests/integration/test_low_battery_areas.py`
- [X] T021 [P] [US1] Add low-battery Home Assistant service schema and response contract tests in `tests/contract/test_services_contract.py`
- [X] T022 [P] [US1] Add low-battery intent sentence and rendering tests in `tests/unit/test_intent_handlers.py`

### Implementation for User Story 1

- [X] T023 [US1] Implement fixed-depth bounded `low_battery_areas` query, Python grouping, explanatory measurements, warnings, and truncation in `custom_components/ontology/query_tools.py`
- [X] T024 [P] [US1] Register the `ontology.low_battery_areas` response service with validated overrides in `custom_components/ontology/__init__.py` and `custom_components/ontology/services.yaml`
- [X] T025 [P] [US1] Implement `OntologyLowBatteryAreas` handling and concise grouped rendering in `custom_components/ontology/intent_handlers.py`
- [X] T026 [US1] Add English low-battery sentence variations and localized empty/degraded/truncated responses in `custom_components/ontology/intents/en.yaml`, `custom_components/ontology/strings.json`, and `custom_components/ontology/translations/en.json`
- [X] T027 [US1] Run the US1 unit, contract, and integration tests through `scripts/test-windows.ps1` and complete Scenario C in `specs/004-home-relationship-questions/quickstart.md`

**Checkpoint**: Low-battery room answers work independently through the shared read core, Home Assistant service, and Assist.

---

## Phase 4: User Story 2 - Find Appliances Currently Consuming Electricity (Priority: P2)

**Goal**: Return only fresh positive consumer-role power readings above the configured threshold, normalized to watts and grouped by device.

**Independent Test**: Populate consumer, producer, storage, grid-flow, unknown-role, zero, negative, stale, unavailable, W, and kW readings; verify only qualifying consumers are returned with explanatory measurements.

### Tests for User Story 2

- [X] T028 [P] [US2] Add deterministic role identity, user-over-inferred precedence, CRUD, and validation tests in `tests/unit/test_energy_roles.py`
- [X] T029 [P] [US2] Add active-consumer threshold, freshness, role filtering, W/kW normalization, device de-duplication, no-sum, empty, and truncation tests in `tests/unit/test_active_consumers_query.py`
- [X] T030 [P] [US2] Add real-graph role binding, rebuild/resync survival, and active-consumer relationship tests in `tests/integration/test_active_consumers.py`
- [X] T031 [P] [US2] Add admin-only role mutation, active-consumer service, and non-admin rejection contract tests in `tests/contract/test_services_contract.py`
- [X] T032 [P] [US2] Add active-consumer Assist sentence, power rendering, empty, warning, and degraded tests in `tests/unit/test_intent_handlers.py`

### Implementation for User Story 2

- [X] T033 [P] [US2] Add conservative inferred energy-role classification with explicit source metadata in `custom_components/ontology/semantic_classifier.py`
- [X] T034 [US2] Implement durable `EnergyRoleAssignment` identity, user CRUD, inferred reconciliation, binding repair, and effective-role precedence in `custom_components/ontology/user_knowledge.py`
- [X] T035 [US2] Serialize role reconciliation with refresh, rebuild, resync, and entity lifecycle processing in `custom_components/ontology/coordinator.py`
- [X] T036 [US2] Register administrator-only `set_energy_role` and `delete_energy_role` services and schemas in `custom_components/ontology/__init__.py` and `custom_components/ontology/services.yaml`
- [X] T037 [US2] Implement fixed-depth bounded `active_consumers` query with effective-role filtering and unsummed explanatory readings in `custom_components/ontology/query_tools.py`
- [X] T038 [P] [US2] Implement active-consumer Assist handling and rendering in `custom_components/ontology/intent_handlers.py` and `custom_components/ontology/intents/en.yaml`
- [X] T039 [US2] Add localized role service fields and active-consumer responses in `custom_components/ontology/strings.json` and `custom_components/ontology/translations/en.json`
- [ ] T040 [US2] Run the US2 unit, contract, and integration tests through `scripts/test-windows.ps1` and complete Scenario D in `specs/004-home-relationship-questions/quickstart.md`

**Checkpoint**: Active-consumer answers work independently and never classify positive generation/storage/grid readings as appliances without an effective consumer role.

---

## Phase 5: User Story 3 - Resolve Automation Dependencies by Entity or Device (Priority: P3)

**Goal**: Resolve entities or devices safely and return the de-duplicated automation dependency union with the entities and relationship types that establish each reason.

**Independent Test**: Create a multi-entity Garage Motion Sensor device referenced by overlapping automations; verify exact IDs and unique names return the complete union, duplicate names disambiguate, and resolved-empty differs from not-found.

### Tests for User Story 3

- [ ] T041 [P] [US3] Extend entity/device resolution, dependency-reason aggregation, de-duplication, empty/not-found, and ambiguity tests in `tests/unit/test_query_tools.py`
- [ ] T042 [P] [US3] Add real-graph device-level automation dependency union and relationship-reason tests in `tests/integration/test_automation_dependencies_device.py`
- [ ] T043 [P] [US3] Add strengthened automation dependency service schema and result contract tests in `tests/contract/test_services_contract.py`
- [ ] T044 [P] [US3] Add “which automations” entity/device Assist sentence, ambiguity, and reason-rendering tests in `tests/unit/test_intent_handlers.py`

### Implementation for User Story 3

- [ ] T045 [US3] Enhance bounded `automation_dependencies` for Entity and Device targets with stable de-duplication and explicit reasons in `custom_components/ontology/query_tools.py`
- [ ] T046 [P] [US3] Update the response service from entity-only input to deterministic `target` resolution while preserving compatibility in `custom_components/ontology/__init__.py` and `custom_components/ontology/services.yaml`
- [ ] T047 [P] [US3] Enhance automation dependency Assist handling and English “which automations” variations in `custom_components/ontology/intent_handlers.py` and `custom_components/ontology/intents/en.yaml`
- [ ] T048 [US3] Run the US3 unit, contract, and integration tests through `scripts/test-windows.ps1` and complete the dependency portion of Scenario E in `specs/004-home-relationship-questions/quickstart.md`

**Checkpoint**: Dependency lookup works independently for entity and device identifiers/names without silent first-match behavior.

---

## Phase 6: User Story 4 - Understand What a Gas Cylinder Supplies (Priority: P4)

**Goal**: Let administrators manage durable gas-cylinder supply statements and let every read channel return currently resolved supplied targets without inferring physical topology.

**Independent Test**: Create associations from a 48kg gas cylinder to a boiler and stove, rebuild/resync, validate unresolved/rebound targets, and verify atomic additive export/import preserves the same knowledge.

### Tests for User Story 4

- [ ] T049 [P] [US4] Add deterministic supply identity, unique endpoint resolution, CRUD, idempotency, and no-partial-write tests in `tests/unit/test_supply_associations.py`
- [ ] T050 [P] [US4] Add version 2 export, legacy version 1 compatibility, additive upsert, omitted-record preservation, duplicate conflict, deterministic-ID validation, and atomic rollback tests in `tests/unit/test_user_knowledge_import.py`
- [ ] T051 [P] [US4] Add real-graph supply binding, rebuild/resync/reclassification survival, unresolved-target, rebound, and delete tests in `tests/integration/test_supply_association_lifecycle.py`
- [ ] T052 [P] [US4] Add real-graph user-knowledge export/import round-trip and transaction rollback tests in `tests/integration/test_user_knowledge_roundtrip.py`
- [ ] T053 [P] [US4] Add admin-only supply CRUD/import and supplied-target read service contract tests in `tests/contract/test_services_contract.py`
- [ ] T054 [P] [US4] Add supplied-target Assist sentences, rendering, empty, ambiguity, and degraded tests in `tests/unit/test_intent_handlers.py`
- [ ] T055 [P] [US4] Extend unresolved supply/role finding lifecycle tests in `tests/integration/test_validation_finding_lifecycle.py`

### Implementation for User Story 4

- [ ] T056 [P] [US4] Preserve canonical gas-cylinder stable identity and source metadata during semantic classification in `custom_components/ontology/semantic_classifier.py`
- [ ] T057 [US4] Implement durable `SupplyAssociation` identity, administrator CRUD, endpoint binding reconciliation, and unresolved record preservation in `custom_components/ontology/user_knowledge.py`
- [ ] T058 [US4] Implement version 2 combined user-knowledge export/import with version 1 override compatibility, full prevalidation, and one atomic additive transaction in `custom_components/ontology/user_knowledge.py` and `custom_components/ontology/overrides.py`
- [ ] T059 [US4] Serialize supply reconciliation/import with delete, refresh, rebuild, resync, and semantic reclassification in `custom_components/ontology/coordinator.py`
- [ ] T060 [US4] Register administrator-only supply CRUD and user-knowledge export/import services with response schemas in `custom_components/ontology/__init__.py` and `custom_components/ontology/services.yaml`
- [ ] T061 [P] [US4] Add unresolved supply source/target and energy-role entity validation findings without automatic deletion in `custom_components/ontology/validation.py`
- [ ] T062 [US4] Implement fixed-depth bounded `supplied_targets` read behavior with resolved-empty, ambiguity, unresolved warnings, areas, and truncation in `custom_components/ontology/query_tools.py`
- [ ] T063 [P] [US4] Implement supplied-target Assist handling and English sentence variations in `custom_components/ontology/intent_handlers.py` and `custom_components/ontology/intents/en.yaml`
- [ ] T064 [US4] Add localized supply/role administration fields and supplied-target responses in `custom_components/ontology/strings.json` and `custom_components/ontology/translations/en.json`
- [ ] T065 [US4] Run the US4 unit, contract, and integration tests through `scripts/test-windows.ps1` and complete Scenarios F and G in `specs/004-home-relationship-questions/quickstart.md`

**Checkpoint**: User-owned supply topology is administrator-managed, atomic, lifecycle-safe, exportable, repairable, and independently queryable.

---

## Phase 7: User Story 5 - List All Entities Associated With a Device (Priority: P5)

**Goal**: Resolve a device and list every current associated entity once with display name, stable entity ID, and current area.

**Independent Test**: Create a Dishwasher device with switch, power, energy, program, and status entities; verify all appear once, area is included, ambiguity is bounded, and a resolved empty device differs from a missing device.

### Tests for User Story 5

- [ ] T066 [P] [US5] Extend device-context entity completeness, de-duplication, ordering, area, empty, not-found, ambiguity, and truncation tests in `tests/unit/test_query_tools.py`
- [ ] T067 [P] [US5] Add real-graph multi-entity device context and current-area movement tests in `tests/integration/test_device_context_entities.py`
- [ ] T068 [P] [US5] Add enhanced device-context service response contract tests in `tests/contract/test_services_contract.py`
- [ ] T069 [P] [US5] Add device-associated-entities Assist sentence and rendering tests in `tests/unit/test_intent_handlers.py`

### Implementation for User Story 5

- [ ] T070 [US5] Enhance bounded `device_context` with complete stable entity records, current area, dependency summary, and deterministic outcomes in `custom_components/ontology/query_tools.py`
- [ ] T071 [P] [US5] Update device-context service schema for optional bounds and response semantics in `custom_components/ontology/__init__.py` and `custom_components/ontology/services.yaml`
- [ ] T072 [P] [US5] Implement device-associated-entities Assist rendering and English sentence variations in `custom_components/ontology/intent_handlers.py` and `custom_components/ontology/intents/en.yaml`
- [ ] T073 [US5] Run the US5 unit, contract, and integration tests through `scripts/test-windows.ps1` and complete the device-context portion of Scenario E in `specs/004-home-relationship-questions/quickstart.md`

**Checkpoint**: Device context answers work independently and expose every bounded current entity exactly once.

---

## Phase 8: User Story 6 - Use the Same Questions Across Supported Read Channels (Priority: P6)

**Goal**: Guarantee service, Assist, MCP, and context-export parity while preserving bounds, redaction, endpoint admission, read-only behavior, and privacy-safe observability.

**Independent Test**: Invoke all five operations through every supported channel against one graph and verify equivalent resolution, result content, warnings, bounds, redaction, empty/not-found/ambiguous/degraded outcomes, and MCP admission behavior.

### Tests for User Story 6

- [ ] T074 [P] [US6] Extend MCP tool-list, JSON schema, dispatch, bounds, and mutation-absence contract tests in `tests/contract/test_mcp_server_contract.py`
- [ ] T075 [P] [US6] Add all-five-operation service/Assist/MCP parity tests in `tests/integration/test_relationship_query_channel_parity.py`
- [ ] T076 [P] [US6] Add sensitive-marker ingestion tests proving arbitrary and secret-bearing Home Assistant attributes are absent from persisted Entity nodes, plus recursive response/export redaction, sanitized audit, and aggregate diagnostics tests in `tests/integration/test_relationship_query_privacy.py`
- [ ] T077 [P] [US6] Extend MCP disabled, unauthorized, non-local, read-only listing, and degraded endpoint tests in `tests/integration/test_mcp_endpoint_e2e.py`
- [ ] T078 [P] [US6] Add under-three-second latency, row-bound, candidate-bound, child-bound, and truncation-warning tests using at least 5,000 entities, 1,000 devices, and 500 pre-bound qualifying rows in `tests/integration/test_query_tools_performance.py`
- [ ] T079 [P] [US6] Extend allow-listed measurement, effective-role, and resolved-supply context export tests in `tests/unit/test_context_export.py`
- [ ] T080 [P] [US6] Extend privacy-safe operation/outcome/count/truncation/error-category audit and diagnostic tests in `tests/unit/test_agent_audit.py` and `tests/unit/test_diagnostics_redaction.py`

### Implementation for User Story 6

- [ ] T081 [US6] Advertise and dispatch `low_battery_areas`, `active_consumers`, `automation_dependencies`, `supplied_targets`, and `device_context` as bounded read-only MCP tools in `custom_components/ontology/mcp_server.py`
- [ ] T082 [US6] Align all Home Assistant read service adapters with the shared `ToolResult` envelope, validation, and bounds in `custom_components/ontology/__init__.py`
- [ ] T083 [P] [US6] Export only allow-listed normalized measurements, effective roles, and relevant resolved supply knowledge in `custom_components/ontology/context_export.py`
- [ ] T084 [P] [US6] Record operation, channel, outcome, count, truncation, timestamp, and sanitized category without targets, utterances, measurements, payloads, or exceptions in `custom_components/ontology/agent_audit.py`
- [ ] T085 [US6] Expose aggregate measurement/role/supply health and operation outcomes without raw identifiers or values in `custom_components/ontology/diagnostics.py`
- [ ] T086 [US6] Apply the recursive redaction boundary to every new nested result, warning, candidate, export, and error path in `custom_components/ontology/redact.py`
- [ ] T087 [US6] Run US6 contract, privacy, admission, parity, and performance tests through `scripts/test-windows.ps1` and complete Scenario H in `specs/004-home-relationship-questions/quickstart.md`

**Checkpoint**: All five questions have one safe behavior across every supported read channel, and MCP remains disabled by default, authenticated, local, bounded, audited, and read-only.

---

## Phase 9: Polish & Cross-Cutting Validation

**Purpose**: Prove backward compatibility, lifecycle resilience, privacy, and complete requirement coverage across the delivered stories.

- [ ] T088 [P] Verify the integration release version in `custom_components/ontology/manifest.json` independently of graph schema `3.0.0`, and document the migration, options, services, intents, and MCP tools in `README.md`
- [ ] T089 [P] Add setup/reload/unload and Memgraph-outage regression coverage plus explicit backward-compatibility checks for existing area, device, entity, search, impact-analysis, context-export, automation-dependency, Assist, and MCP reads in `tests/integration/test_relationship_questions_lifecycle.py`
- [ ] T090 Run the complete Windows test suite through `scripts/test-windows.ps1` and record any environment-specific exceptions in `specs/004-home-relationship-questions/quickstart.md`
- [ ] T091 Run Ruff against `custom_components/ontology/` and `tests/`, fix only feature-related findings, and verify commands documented in `specs/004-home-relationship-questions/quickstart.md`
- [ ] T092 Execute every quickstart scenario and verify SC-001 through SC-012 plus FR-001 through FR-046 against `specs/004-home-relationship-questions/spec.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**: Starts immediately.
- **Phase 2 Foundational**: Depends on Phase 1 and blocks every user story.
- **US1-US6**: Depend on Phase 2. Priority order is the default delivery sequence.
- **Phase 9 Polish**: Depends on every story selected for release; full sign-off depends on US1-US6.

### User Story Dependencies

- **US1 (P1)**: No dependency on another story after Foundation; this is the MVP.
- **US2 (P2)**: No behavioral dependency on US1; shares normalized measurement infrastructure.
- **US3 (P3)**: No behavioral dependency on US1/US2; shares deterministic resolution.
- **US4 (P4)**: No behavioral dependency on earlier stories; modifies `user_knowledge.py` alongside US2, so schedule file ownership serially if implemented in parallel.
- **US5 (P5)**: No behavioral dependency on earlier stories; shares deterministic resolution.
- **US6 (P6)**: Integration phase depends on completed read operations from US1-US5 because it proves cross-channel parity for all five.

### Within Each User Story

1. Write the story's tests and verify the expected failures.
2. Implement graph/model behavior before query behavior.
3. Implement shared query behavior before service, Assist, or MCP adapters.
4. Run the focused story test set and its quickstart scenario.
5. Do not use a transport adapter to duplicate shared resolution or query logic.

## Parallel Opportunities

- Setup fixture tasks T002-T003 can proceed in parallel after T001 establishes constants.
- Foundational tests T004-T009 can be authored in parallel; implementation then follows their local dependency order.
- After Phase 2, US1, US2, US3, US4, and US5 are behaviorally independent, though shared-file ownership must be coordinated.
- Contract, unit, and integration tests marked `[P]` within each story can be authored concurrently.
- US6 test files T074-T080 can be authored concurrently after the five shared operations are specified.
- Documentation and lifecycle regression work T088-T089 can proceed in parallel after story implementation.

## Parallel Examples by User Story

### User Story 1

```text
T019 tests/unit/test_low_battery_query.py
T020 tests/integration/test_low_battery_areas.py
T021 tests/contract/test_services_contract.py
T022 tests/unit/test_intent_handlers.py
```

### User Story 2

```text
T028 tests/unit/test_energy_roles.py
T029 tests/unit/test_active_consumers_query.py
T030 tests/integration/test_active_consumers.py
T031 tests/contract/test_services_contract.py
```

### User Story 3

```text
T041 tests/unit/test_query_tools.py
T042 tests/integration/test_automation_dependencies_device.py
T043 tests/contract/test_services_contract.py
T044 tests/unit/test_intent_handlers.py
```

### User Story 4

```text
T049 tests/unit/test_supply_associations.py
T050 tests/unit/test_user_knowledge_import.py
T051 tests/integration/test_supply_association_lifecycle.py
T052 tests/integration/test_user_knowledge_roundtrip.py
```

### User Story 5

```text
T066 tests/unit/test_query_tools.py
T067 tests/integration/test_device_context_entities.py
T068 tests/contract/test_services_contract.py
T069 tests/unit/test_intent_handlers.py
```

### User Story 6

```text
T074 tests/contract/test_mcp_server_contract.py
T075 tests/integration/test_relationship_query_channel_parity.py
T076 tests/integration/test_relationship_query_privacy.py
T078 tests/integration/test_query_tools_performance.py
```

## Implementation Strategy

### MVP First: User Story 1

1. Complete Setup and Foundation.
2. Implement US1 measurement-to-query-to-service/Assist behavior.
3. Stop and validate US1 independently with T027.
4. Demo low-battery room answers before adding energy roles or user-managed supply topology.

### Incremental Delivery

1. **Foundation**: Atomic schema v3, current measurements, options, and deterministic result semantics.
2. **US1**: Low-battery rooms, independently useful MVP.
3. **US2**: Role-aware active consumers.
4. **US3**: Entity/device automation dependency aggregation.
5. **US4**: Durable administrator-managed gas supply knowledge and atomic import/export.
6. **US5**: Complete device entity context.
7. **US6**: MCP/export/observability parity and cross-channel hardening.
8. **Polish**: Full lifecycle, privacy, performance, lint, and requirements sign-off.

### Parallel Team Strategy

After Foundation:
- Developer A can own US1 and US5 measurement/context reads.
- Developer B can own US2 energy roles.
- Developer C can own US3 dependency resolution.
- Developer D can own US4 durable supply knowledge.
- Integrate US1-US5 before assigning US6 parity and final hardening.

## Notes

- `[P]` means different-file work with no incomplete local dependency; shared existing files still require merge coordination across stories.
- Tests precede implementation and must demonstrate the intended failure before production changes.
- Stable Home Assistant identifiers, never display names or Memgraph element IDs, define durable identity.
- Every graph read remains parameterized, fixed-depth, and bounded; fetch `effective_limit + 1` only to prove truncation.
- Assist and MCP remain read-only. Only native Home Assistant administrator services mutate user knowledge.
- Rebuild/resync may recreate generated bindings but must never delete durable user statements.
