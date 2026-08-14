# Feature Specification: Home Relationship Questions

**Feature Branch**: `004-home-relationship-questions`

**Created**: 2026-08-12

**Status**: Draft

**Input**: User description: "Allow Home Assistant Ontology to answer questions such as: Which rooms have devices with low batteries? What appliances currently consume electricity? Which automations depend on the garage motion sensor? What is powered by my 48kg gas cylinder? Show all entities associated with the dishwasher. Implement the graph data, user-managed relationships, safe shared queries, Assist support, services, MCP access, exports, migration, and tests required to answer all five questions reliably."

## Clarifications

### Session 2026-08-12

- Q: Which timestamp determines measurement freshness? → A: Home Assistant `last_updated` from the latest accepted measurement-relevant change.
- Q: Who may mutate user-managed supply associations and energy-role assignments? → A: Home Assistant administrators only.
- Q: How must imports interact with existing user-managed knowledge? → A: Merge/upsert imported records and preserve unmentioned existing records.
- Q: What write behavior is acceptable for attribute-only measurement events? → A: An accepted debounced measurement update produces at most one entity write; an event changing only non-allow-listed attributes produces zero graph writes and does not restart the debounce timer.
- Q: What benchmark dataset defines "several thousand entities"? → A: At least 5,000 entities across at least 1,000 devices, with at least 500 qualifying rows before result bounds are applied.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Find Rooms With Low Batteries (Priority: P1)

As a Home Assistant user, I want to ask which rooms contain devices with low batteries so that I can replace batteries before devices stop working.

**Why this priority**: Low-battery awareness is actionable, broadly useful, and depends only on current Home Assistant state and existing area/device relationships.

**Independent Test**: Populate multiple areas with devices exposing battery percentages above, below, and exactly at the configured threshold, ask the question through a supported query channel, and verify that only qualifying devices are grouped under their current rooms.

**Acceptance Scenarios**:

1. **Given** battery-powered devices in multiple rooms and at least one current battery percentage below the low-battery threshold, **When** the user asks which rooms have devices with low batteries, **Then** the answer lists each matching room and its low-battery devices with current percentages.
2. **Given** a device has several battery entities, **When** more than one reports a low value, **Then** the device appears once and the answer identifies the readings that caused it to qualify.
3. **Given** no current battery reading is below the threshold, **When** the question is asked, **Then** the answer clearly states that no low batteries are known.
4. **Given** a low-battery entity is assigned directly to an area without a device, **When** the question is asked, **Then** the entity is included under that area.
5. **Given** a battery reading is unavailable, unknown, nonnumeric, or stale, **When** the question is answered, **Then** that reading is excluded and the result warns that some battery status is unavailable.

---

### User Story 2 - Find Appliances Currently Consuming Electricity (Priority: P2)

As a Home Assistant user, I want to ask which appliances currently consume electricity so that I can understand live household demand.

**Why this priority**: Live consumption is valuable for energy awareness but requires the system to distinguish consumers from producers, storage, and grid-flow measurements.

**Independent Test**: Populate consumer and non-consumer devices with current positive, zero, negative, stale, and unavailable power readings, then verify that only active consumers are returned with normalized power and location.

**Acceptance Scenarios**:

1. **Given** appliances classified as electricity consumers with fresh positive power readings above the active threshold, **When** the user asks what appliances currently consume electricity, **Then** the answer lists each appliance, its room where known, its current normalized power, and the measuring entity.
2. **Given** solar generation, battery storage, grid import, or grid export sensors report positive values, **When** the question is answered, **Then** they are not described as appliances consuming electricity unless the user explicitly classifies them as consumers.
3. **Given** a consumer reports zero, negative, unavailable, unknown, nonnumeric, or stale power, **When** the question is answered, **Then** it is excluded from the active-consumer list.
4. **Given** power measurements use watts or kilowatts, **When** results are compared and presented, **Then** values are normalized to a common unit without changing their meaning.
5. **Given** no appliance has a qualifying current power reading, **When** the question is asked, **Then** the answer clearly states that no active electricity consumers are known.

---

### User Story 3 - Resolve Automation Dependencies by Entity or Device (Priority: P3)

As a Home Assistant user, I want to ask which automations depend on a named sensor or device so that I can understand the effect of changing or removing it.

**Why this priority**: Entity-level automation dependency lookup already exists; extending resolution to natural device names closes a common mismatch between how people name hardware and how automations reference entities.

**Independent Test**: Create a device named "Garage Motion Sensor" with multiple entities referenced by different automations and verify that one question returns the de-duplicated union with relationship reasons.

**Acceptance Scenarios**:

1. **Given** an exact entity identifier or unique entity name, **When** the user asks which automations depend on it, **Then** matching automations and relationship reasons are returned.
2. **Given** a unique device name whose entities are referenced by automations, **When** the same question is asked using the device name, **Then** dependencies across all current device entities are aggregated and de-duplicated.
3. **Given** an automation references multiple entities belonging to the same device, **When** dependencies are aggregated, **Then** the automation appears once and the relevant entities are identified.
4. **Given** a name matches multiple entities or devices, **When** the question is asked, **Then** the system returns a bounded disambiguation response rather than silently choosing a target.
5. **Given** the target resolves but no automations depend on it, **When** the question is asked, **Then** the answer clearly states that no known automations depend on the target.

---

### User Story 4 - Understand What a Gas Cylinder Supplies (Priority: P4)

As a Home Assistant user, I want to record and ask what is powered by a named gas cylinder so that I can understand which appliances are affected when that cylinder is empty, disconnected, or replaced.

**Why this priority**: Home Assistant cannot reliably infer physical fuel-supply topology, so this valuable question requires explicit user-owned knowledge and safe lifecycle behavior.

**Independent Test**: Create a user-managed supply association from "48kg Gas Cylinder" to a boiler and stove, rebuild and resync the graph, and verify that the same two supplied targets are returned afterward.

**Acceptance Scenarios**:

1. **Given** a named gas cylinder has user-managed supply associations, **When** the user asks what it powers, **Then** the answer lists the supplied devices and entities with their rooms where known.
2. **Given** a supply association is created, **When** generated data is refreshed, rebuilt, or resynchronized, **Then** the user-managed association remains intact.
3. **Given** a user removes a supply association, **When** the cylinder is queried again, **Then** the removed target is no longer returned and unrelated associations remain unchanged.
4. **Given** a cylinder exists but has no recorded supply associations, **When** the question is asked, **Then** the answer explains that no supplied appliances have been recorded rather than inferring unsupported relationships.
5. **Given** a requested source or supplied target does not resolve uniquely, **When** a user attempts to create an association, **Then** the request is rejected without a partial graph change and provides bounded candidate information.
6. **Given** user-managed associations are exported and imported, **When** the import is valid, **Then** imported records are merged idempotently by stable identity and existing records absent from the import are preserved; when any entry is invalid, the import is rejected without partial changes.

---

### User Story 5 - List All Entities Associated With a Device (Priority: P5)

As a Home Assistant user, I want to ask for all entities associated with a named appliance such as the dishwasher so that I can see every control, sensor, diagnostic, and status entity it exposes.

**Why this priority**: The underlying device-to-entity relationships already exist, but users need direct natural-language access and a useful rendered answer.

**Independent Test**: Create a dishwasher device exposing switch, power, energy, program, and status entities, ask for associated entities, and verify every current graph relationship appears once.

**Acceptance Scenarios**:

1. **Given** a unique device name or identifier, **When** the user asks to show all associated entities, **Then** every current entity linked to the device is listed once with its display name and entity identifier.
2. **Given** the device has an area, **When** the answer is returned, **Then** the current area is included.
3. **Given** a device exists but exposes no entities, **When** the question is asked, **Then** the answer clearly states that no associated entities are known.
4. **Given** the device name is ambiguous, **When** the question is asked, **Then** the system requests disambiguation and returns bounded candidates.

---

### User Story 6 - Use the Same Questions Across Supported Read Channels (Priority: P6)

As an automation author or local AI user, I want these relationship questions available through the integration's structured read channels so that Assist, Home Assistant services, and authorized local clients produce consistent answers.

**Why this priority**: A single shared behavior prevents channel-specific data and safety differences.

**Independent Test**: Invoke every new operation through each supported channel and verify equivalent target resolution, result content, warnings, bounds, redaction, and not-found behavior.

**Acceptance Scenarios**:

1. **Given** the same populated ontology, **When** a question is invoked through Assist, a Home Assistant service, or an enabled authenticated local tool endpoint, **Then** each channel uses the same shared result semantics.
2. **Given** a result contains more items than the configured result bound, **When** it is returned through any channel, **Then** the result is truncated consistently and includes a warning.
3. **Given** a query or association includes sensitive-looking values, **When** a read result, export, diagnostic record, or error is produced, **Then** secrets and credentials are absent.
4. **Given** the local tool endpoint is disabled or a client is unauthorized, **When** it attempts any new operation, **Then** existing endpoint admission and audit protections still apply.

### Edge Cases

- A battery value equals the low-battery threshold exactly; it is not considered low because "low" means strictly below the threshold.
- A battery value is reported as a decimal fraction, percentage text, voltage, enum, or another non-percentage representation; only unambiguous percentage readings qualify automatically.
- Multiple battery or power sensors map to one device; the device is returned once while retaining the qualifying measurements.
- An entity moves between devices or areas while a query is running; the completed synchronization state is used and no cross-area duplicate is returned.
- A power sensor changes only an attribute while its primary state remains constant; relevant normalized metadata still refreshes.
- An unrelated attribute changes without changing battery or power state or allow-listed measurement metadata; the event is ignored and does not refresh the stored measurement timestamp.
- A power reading is positive but its energy role is unknown; it is excluded from the definitive consumer answer and surfaced as unresolved where warnings are supported.
- A device has both consuming and generating behavior; each measurement's role is evaluated independently.
- A target name differs only by case or matches both a device and an entity; exact identifiers take precedence, while ambiguous names require disambiguation.
- A user-managed supply target is deleted from Home Assistant; the association remains distinguishable as user knowledge but validation reports the missing target until the user removes or repairs it.
- An import contains a record that already exists and omits another local record; the existing record is updated idempotently and the omitted local record is preserved.
- Memgraph is unavailable during state synchronization, association management, or a question; Home Assistant remains operational and the request returns a safe degraded/error response without losing user-managed data.
- Large homes contain thousands of entities and hundreds of qualifying results; all lookups, candidate lists, and answers remain bounded.

## Requirements *(mandatory)*

### Functional Requirements

**Current state and semantic metadata**

- **FR-001**: The system MUST maintain the current, queryable battery percentage for entities that unambiguously report percentage-based battery state.
- **FR-002**: The system MUST maintain the current, queryable power value for entities that unambiguously report power and MUST normalize supported watt and kilowatt readings to watts.
- **FR-003**: The system MUST retain the source measurement's display unit, device class, Home Assistant `last_updated` timestamp from the latest accepted measurement-relevant state or allow-listed attribute change, device association, and area association needed to explain battery and power answers.
- **FR-004**: The system MUST treat unavailable, unknown, nonnumeric, malformed, or unsupported-unit measurements as unavailable rather than coercing them into numeric results.
- **FR-005**: The system MUST update queryable battery and power metadata when either the primary state or a relevant allow-listed state attribute changes, while continuing to ignore unrelated attribute-only churn.
- **FR-006**: The system MUST copy only explicitly allow-listed state metadata into the ontology and MUST NOT copy arbitrary state attributes, credentials, tokens, or secret values.
- **FR-007**: Current-state synchronization MUST remain debounced, asynchronous, and non-blocking, and Memgraph unavailability MUST NOT destabilize Home Assistant.

**Low-battery room query**

- **FR-008**: The system MUST provide a read operation that returns areas containing percentage-based battery readings strictly below a low-battery threshold, grouped by area and device where possible.
- **FR-009**: The default low-battery threshold MUST be 20 percent and users MUST be able to configure a threshold from 1 through 100 percent without changing graph data.
- **FR-010**: Low-battery results MUST include the area, device or direct entity, measuring entity, current percentage, and measurement timestamp where available.
- **FR-011**: Low-battery results MUST de-duplicate devices, include directly area-assigned entities, exclude unavailable or stale readings, and return an aggregate warning count for battery-class entities whose current measurement status is `unavailable`, `invalid_value`, or `unsupported_unit`; stale otherwise-valid readings are excluded without contributing to that unavailable count.
- **FR-012**: The maximum acceptable measurement age MUST be configurable, MUST default to 24 hours, and MUST be evaluated at query time against the stored Home Assistant `last_updated` timestamp; synchronization alone MUST NOT refresh that timestamp.

**Active electricity-consumer query**

- **FR-013**: The system MUST provide a read operation that returns devices currently consuming electricity based on fresh positive power measurements above an active-power threshold.
- **FR-014**: The default active-power threshold MUST be 1 watt and users MUST be able to configure a nonnegative threshold without rewriting graph data.
- **FR-015**: Active-consumer results MUST include the device, area where known, normalized power in watts, measuring entity, source unit, and measurement timestamp.
- **FR-016**: The system MUST distinguish at least the energy roles consumer, producer, storage, grid import, and grid export, and MUST exclude non-consumer and unknown-role measurements from definitive appliance-consumption results.
- **FR-017**: The system MAY infer an energy role from unambiguous Home Assistant metadata but MUST allow a Home Assistant administrator to override or supply the role, MUST identify inferred versus user-managed roles, and MUST give user-managed roles precedence.
- **FR-018**: User-managed energy roles MUST survive refresh, rebuild, resynchronization, export, and idempotent import.
- **FR-019**: A device with multiple qualifying consumer measurements MUST appear once while retaining each measurement needed to explain its total or individual readings; the system MUST NOT sum measurements unless they are explicitly identified as non-overlapping.

**Dependency and device-context resolution**

- **FR-020**: Automation dependency lookup MUST resolve exact entity identifiers, unique entity names, exact device identifiers, and unique device names.
- **FR-021**: When dependency lookup resolves a device, the system MUST aggregate and de-duplicate automations across all entities currently associated with that device and MUST identify the entities establishing each dependency.
- **FR-022**: Device context lookup MUST return all entities currently associated with the resolved device, with both display names and stable entity identifiers, plus the current area where known.
- **FR-023**: Exact stable identifiers MUST take precedence over names; a name matching multiple eligible targets MUST produce a bounded disambiguation result and MUST NOT silently select the first match.
- **FR-024**: Resolved targets with no dependencies or associated entities MUST return a successful empty result with a clear explanation; unresolved targets MUST return a distinct not-found result.

**Gas-cylinder supply knowledge**

- **FR-025**: The ontology schema MUST represent a directional supply association from a gas-cylinder semantic asset to a supplied device or entity, with source ownership metadata.
- **FR-026**: The schema version MUST be incremented for the new supply association and migration MUST be idempotent, preserve all existing generated and user-managed graph data, and be safe to rerun.
- **FR-027**: Home Assistant administrators MUST be able to create, list, and delete supply associations through authenticated Home Assistant administration surfaces; non-administrator users, Assist, and local AI read channels MUST NOT create or delete them.
- **FR-028**: Creation of a supply association MUST require one uniquely resolved gas-cylinder source and one uniquely resolved device or entity target and MUST reject invalid or ambiguous requests without partial changes.
- **FR-029**: Supply associations MUST be marked as user-managed and MUST survive generated-data refresh, rebuild, resynchronization, and semantic reclassification.
- **FR-030**: The system MUST provide a read operation that returns all devices and entities supplied by a resolved gas cylinder, including their current areas where known.
- **FR-031**: A resolved cylinder with no supply associations MUST return a successful empty result explaining that no supplied targets are recorded; an unresolved or ambiguous cylinder MUST return not-found or disambiguation respectively.
- **FR-032**: User-managed supply associations and energy-role assignments MUST be included in a versioned export and import format; restoration by import MUST be restricted to Home Assistant administrators, fully validated before writing, and atomic from the caller's perspective. A valid import MUST merge or update records by stable identity, MUST be idempotent, and MUST preserve existing user-managed records not present in the import.
- **FR-033**: Validation MUST report supply associations whose source or target no longer resolves, without deleting user-managed knowledge automatically.

**Assist and structured access channels**

- **FR-034**: Assist MUST recognize at least two English sentence patterns for each of the five requested questions, including both "which automations depend on {target}" and "what automations use {target}" wording, without requiring users to know entity identifiers.
- **FR-035**: Assist responses MUST render low batteries grouped by room, active consumers with power, automation dependencies with reasons, cylinder-supplied targets, and device-associated entities as spoken and textual answers bounded by the configured result limit; when truncation occurs, the response MUST state that additional results were omitted.
- **FR-036**: The system MUST expose shared structured read operations for low-battery areas, active power consumers, automation dependencies, supplied targets, and device context through Home Assistant services and the enabled authenticated local tool endpoint.
- **FR-037**: Every access channel MUST delegate to the same shared read behavior and return consistent target resolution, result semantics, warnings, redaction, and limits.
- **FR-038**: The enabled local tool endpoint MUST advertise schemas for every new read operation and retain all existing opt-in, network-admission, access-token, read-only, and audit controls.
- **FR-039**: Existing context exports MUST include normalized battery/power metadata only where permitted by an explicit privacy allow-list and MUST include user-managed supply and energy-role relationships when relevant to the requested target.
- **FR-040**: Diagnostic records MUST identify the operation, status, result count, and sanitized error category without storing raw utterances, measurement histories, access tokens, credentials, or exception messages.

**Bounds, freshness, compatibility, and safety**

- **FR-041**: Every result and disambiguation candidate list MUST enforce the integration's configured result bounds and state when truncation occurred.
- **FR-042**: All five questions MUST produce an answer, empty result, disambiguation, not-found response, or safe degraded response without executing an unbounded traversal.
- **FR-043**: The system MUST store only current battery and power state in the ontology; historical measurements remain outside this feature.
- **FR-044**: Existing area, device, entity, search, impact-analysis, context-export, automation-dependency, Assist, and local tool behaviors MUST remain backward compatible unless this specification explicitly strengthens ambiguity handling.
- **FR-045**: All new read capabilities MUST work locally without a cloud service and MUST NOT permit mutation of Home Assistant or generated ontology data through Assist or local AI tools.
- **FR-046**: User-facing names and measurements MUST pass through the existing recursive redaction boundary before being returned or recorded.

### Key Entities *(include if feature involves data)*

- **Current Measurement**: The latest usable battery or power observation for an entity, including normalized numeric value, source unit, device class, and Home Assistant `last_updated` timestamp from the latest accepted measurement-relevant change. It is current state, not history.
- **Energy Role Assignment**: A classification stating whether a measurement represents a consumer, producer, storage system, grid import, or grid export. It records whether the role is inferred or user-managed, with user-managed knowledge taking precedence.
- **Supply Association**: A directional, user-managed statement that a named gas-cylinder semantic asset supplies a device or entity. It survives generated graph lifecycle operations and may become temporarily unresolved if its target disappears.
- **Low-Battery Area Result**: A bounded grouping of qualifying battery measurements by current area and device, including threshold and freshness context.
- **Active Consumer Result**: A bounded collection of consumer devices with fresh qualifying power measurements, normalized power, measuring entities, and current areas.
- **Disambiguation Result**: A bounded list of candidate entities, devices, or semantic assets returned when a human-readable name does not uniquely identify a target.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can obtain a correct answer to each of the five example questions in one conversational turn when the target is unique and required data or user-managed associations exist.
- **SC-002**: Across a representative dataset, 100% of percentage battery readings below the configured threshold are returned under the correct current area, while readings at or above the threshold and unusable readings are excluded.
- **SC-003**: Across consumer, producer, storage, grid-flow, zero, negative, stale, and unavailable examples, 100% of definitive active-consumer results contain only fresh consumer-role readings above the configured threshold.
- **SC-004**: Device-name dependency lookup returns the complete de-duplicated union of automations referencing any current entity on that device in 100% of integration test cases.
- **SC-005**: User-managed gas supply associations and energy-role assignments remain unchanged after refresh, rebuild, resynchronization, semantic reclassification, and an export/import round trip.
- **SC-006**: Device context returns 100% of currently associated entities exactly once for devices exposing up to the supported result bound.
- **SC-007**: Ambiguous names produce a bounded disambiguation response and never silently select a target in 100% of ambiguity test cases.
- **SC-008**: Each new query returns within 3 seconds on a benchmark graph containing at least 5,000 entities across at least 1,000 devices and at least 500 qualifying rows before bounds are applied, and returns an explicit truncation warning when its result bound is exceeded.
- **SC-009**: Automated inspection of all new read responses, exports, diagnostics, and errors finds zero access tokens, passwords, credentials, secret values, raw Assist utterances, or raw exception messages.
- **SC-010**: An accepted attribute-only battery or power metadata change becomes queryable within the configured synchronization debounce interval and produces at most one entity write after debouncing; an event changing only non-allow-listed attributes produces zero graph writes and does not restart an already scheduled debounce timer.
- **SC-011**: Home Assistant setup, operation, unload, and reload remain successful when Memgraph is unavailable; new capabilities report degraded behavior instead of causing a Home Assistant failure.
- **SC-012**: Existing automated contract, unit, and integration tests continue to pass, and each new question has both deterministic behavior tests and real-graph relationship coverage.

## Assumptions

- "Low battery" means a percentage strictly below a configurable threshold that defaults to 20 percent.
- A measurement is fresh for these questions when it is no older than a configurable duration that defaults to 24 hours.
- "Currently consuming electricity" means a fresh consumer-role power measurement strictly above a configurable threshold that defaults to 1 watt; energy consumption accumulated over time is not a substitute for current power.
- Positive power alone is insufficient evidence that something is an appliance consumer. Unknown-role measurements are excluded from definitive answers until safely inferred or assigned by the user.
- Watt and kilowatt power readings are supported initially. Unsupported units are preserved for diagnostics where safe but are not converted speculatively.
- Home Assistant generally cannot infer physical fuel-supply topology. Gas-cylinder supply associations are therefore user-managed knowledge and are never inferred from proximity, naming, or a measuring relationship alone.
- The existing gas-cylinder semantic classification remains the way a source is identified; users may rely on existing semantic override mechanisms when automatic classification is insufficient.
- New user-managed supply and energy-role knowledge is administered through authenticated Home Assistant controls, not through conversational or local AI write operations.
- The existing local tool endpoint remains disabled by default and all current authentication, network, redaction, result-bound, and audit requirements remain in force.
- This feature stores current measurements only. Trends, history, forecasts, cost calculations, and automatic control of appliances are outside scope.
- English sentence coverage is required for the initial release; additional languages can be added through the existing translation process without changing query semantics.
