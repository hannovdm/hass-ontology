# Feature Specification: Home Assistant Ontology Integration v1

**Feature Branch**: `001-ha-ontology-integration`

**Created**: 2026-07-22

**Status**: Draft

**Input**: User description: "Home Assistant Ontology Integration v1 - Build a first-class Home Assistant custom integration that discovers Home Assistant metadata (areas, floors, devices, entities, automations, scenes, scripts, domains, integrations, labels) and synchronizes it into a local Memgraph graph database as a queryable ontology, using a Devices & Services configuration flow, incremental event-driven updates, diagnostics, services, and schema versioning. Local-first with no cloud dependency."

## Clarifications

### Session 2026-07-22

- Q: When a sync operation is already running and a new one is requested, how should the system handle it? → A: Serialize — queue or reject the new request until the current operation finishes.
- Q: When the integration starts and finds the graph's recorded schema version does not match what the integration expects, what should happen? → A: Integration fails to load and creates a repair issue directing the user to resolve it manually.
- Q: Success Criteria SC-001 targets "under 5 minutes on a typical local installation" — what scale should "typical" represent for sizing and performance validation? → A: Medium: up to ~500 entities/devices.
- Q: Should all entity state changes (including attribute-only changes like signal strength or battery %, not just the primary state value) be synchronized to the ontology, or only certain categories? → A: Only primary entity state changes trigger sync; attribute-only changes (e.g., battery %, signal strength) are out of scope for v1.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure the connection to the local graph database (Priority: P1)

As a Home Assistant administrator, I want to configure the Ontology integration through Devices & Services so that I can connect my smart home to a local graph database without editing YAML files.

**Why this priority**: Nothing else in this feature can function without a working, user-configured connection. This is the entry point for every other capability.

**Independent Test**: Can be fully tested by adding the integration through Settings > Devices & Services, entering connection details for a running local graph database, and confirming the integration loads successfully (or reports a clear error when it cannot connect).

**Acceptance Scenarios**:

1. **Given** a local graph database is running and reachable, **When** the administrator adds the Ontology integration and supplies host, port, username, password, and database options, **Then** the integration validates the connection, creates a config entry, and shows as loaded.
2. **Given** the graph database is unreachable, **When** the administrator submits the configuration form, **Then** the integration displays a clear connection error and does not create a config entry.
3. **Given** the integration is already configured, **When** the administrator updates the host, port, username, or password, **Then** the integration validates the new connection and reloads without requiring manual file edits.
4. **Given** credentials are entered during setup, **When** logs or diagnostics are generated, **Then** the password is never shown in plain text.

---

### User Story 2 - Confirm the graph database connection is healthy (Priority: P1)

As a Home Assistant administrator, I want the integration to actively verify connectivity to the graph database so that misconfigurations are caught immediately rather than surfacing later as silent failures.

**Why this priority**: Reliable, early connection validation is required for Story 1 to give trustworthy feedback and is foundational to every sync operation that follows.

**Independent Test**: Can be fully tested by pointing the integration at a reachable database (expect success) and then at an unreachable one (expect a clear failure) without affecting Home Assistant's own stability.

**Acceptance Scenarios**:

1. **Given** the graph database is reachable, **When** the integration tests the connection, **Then** the connection succeeds and the integration records the database as healthy.
2. **Given** the graph database is not reachable, **When** the integration tests the connection, **Then** the connection attempt fails, the error clearly identifies that the database is unreachable, and Home Assistant startup remains stable and unaffected.

---

### User Story 3 - Discover the full smart home structure (Priority: P1)

As a Home Assistant user, I want the integration to discover areas, floors, devices, entities, automations, scenes, scripts, integrations, domains, and labels so that the ontology accurately reflects my Home Assistant installation.

**Why this priority**: Discovery is the data-gathering step that every graph-building and update capability depends on; without it, there is nothing to synchronize.

**Independent Test**: Can be fully tested by running discovery against a Home Assistant instance containing a mix of fully-configured and partially-configured entities/devices, and confirming all supported metadata types are read without the process failing.

**Acceptance Scenarios**:

1. **Given** the integration is loaded, **When** the initial synchronization starts, **Then** it reads area, device, entity, floor (where supported), and label (where supported) registry data.
2. **Given** Home Assistant contains entities, **When** discovery runs, **Then** each entity is captured along with its domain and, where available, its source integration.
3. **Given** an entity has no related device, or a device has no related area, **When** discovery runs, **Then** the entity or device is still captured and the missing relationship is treated as incomplete data rather than a fatal error.

---

### User Story 4 - Build a queryable ontology from discovered data (Priority: P1)

As a Home Assistant user, I want the integration to build an initial ontology representing my smart home so that I can explore and query my home's structure and relationships.

**Why this priority**: This is the core value delivery of v1 — turning raw Home Assistant metadata into a structured, queryable representation. It is the minimum viable product once configuration, validation, and discovery are in place.

**Independent Test**: Can be fully tested by running a full synchronization against a configured Home Assistant instance and confirming the resulting graph contains the expected structural elements and relationships, and that re-running the synchronization does not create duplicates.

**Acceptance Scenarios**:

1. **Given** the integration is configured and the graph database is reachable, **When** the initial synchronization runs, **Then** the graph contains representations of the home, areas, devices, entities, domains, integrations, automations, scenes, scripts, and a schema record.
2. **Given** Home Assistant metadata contains areas, devices, and entities, **When** the initial synchronization runs, **Then** the home is linked to its areas, areas to their devices, devices to their entities, and entities to their domains and integrations where available.
3. **Given** the graph already exists, **When** a full synchronization runs again, **Then** no duplicate elements are created and existing elements are updated in place using stable identifiers.

---

### User Story 5 - Keep the ontology current as Home Assistant changes (Priority: P2)

As a Home Assistant user, I want ontology updates to happen automatically when devices, entities, areas, or states change so that the graph stays current without requiring a full rebuild.

**Why this priority**: Builds on the MVP (Story 4) by keeping the graph accurate over time, which is important for ongoing usefulness but not required for the very first successful sync.

**Independent Test**: Can be fully tested by making a live change in Home Assistant (e.g., renaming an area, moving a device, changing an entity's state) and confirming only the affected part of the graph updates without a full rebuild.

**Acceptance Scenarios**:

1. **Given** an entity is added, removed, renamed, disabled, or otherwise updated, **When** Home Assistant reports the change, **Then** only the affected entity representation and its direct relationships are updated.
2. **Given** a device is created, removed, renamed, or moved to a different area, **When** Home Assistant reports the change, **Then** only the affected device representation and related area/entity relationships are updated.
3. **Given** an area is created, renamed, or deleted, **When** Home Assistant reports the change, **Then** the corresponding area representation is updated and overall graph consistency is preserved.
4. **Given** an entity's primary state changes, **When** Home Assistant reports the state change, **Then** the entity's latest state is updated and no historical time-series record is created by default; attribute-only changes (e.g., signal strength, battery percentage) with no primary state change are not synchronized in v1.
5. **Given** state changes occur very frequently, **When** the integration processes them, **Then** updates are throttled so they do not overwhelm the graph database or the Home Assistant event loop.

---

### User Story 6 - Monitor integration health from within Home Assistant (Priority: P2)

As a Home Assistant administrator, I want visibility into the integration's health so that I can monitor and control ontology synchronization from the Home Assistant UI.

**Why this priority**: Operational visibility and manual control matter once the integration is running continuously, but are secondary to getting the core sync working.

**Independent Test**: Can be fully tested by loading the integration and confirming health, count, timing, and error indicators appear and update correctly, and that manual control actions are available and functional.

**Acceptance Scenarios**:

1. **Given** the integration is loaded, **Then** indicators for ontology health, element counts, last synchronization time, last error, and schema version are available.
2. **Given** the integration is loaded, **Then** controls for rebuilding, validating, and resynchronizing the graph are available.
3. **Given** the graph database becomes unavailable, **When** a synchronization operation fails, **Then** the health indicator changes to an error state and the last-error indicator shows a redacted summary.

---

### User Story 7 - Trigger ontology operations on demand (Priority: P2)

As an advanced Home Assistant user, I want to trigger ontology operations programmatically so that I can incorporate them into my own automations and routines.

**Why this priority**: Extends control beyond the UI for power users and automation authors; valuable but not required for the base synchronization experience.

**Independent Test**: Can be fully tested by invoking each operation independently and confirming the expected scope of change (full rebuild, refresh, single-entity refresh, or validation-only) occurs.

**Acceptance Scenarios**:

1. **Given** the integration is configured, **When** a full rebuild is triggered, **Then** the graph is cleared according to the integration's rebuild policy and a full synchronization is executed.
2. **Given** the integration is configured, **When** a resynchronization is triggered, **Then** the graph is refreshed without deleting data the integration does not manage.
3. **Given** the integration is configured, **When** a single-entity synchronization is triggered with an entity identifier, **Then** only that entity and its direct relationships are refreshed.
4. **Given** the integration is configured, **When** a validation is triggered, **Then** graph consistency is checked and the result is reported through the health indicators.

---

### User Story 8 - Protect against unsafe schema changes (Priority: P3)

As a developer or advanced user, I want the ontology's structural version to be tracked so that future updates can evolve the graph structure safely instead of silently corrupting it.

**Why this priority**: Important for long-term safety and future upgrades, but does not affect the functional value delivered by the first release.

**Independent Test**: Can be fully tested by building the initial graph, confirming a schema version is recorded, and then simulating a mismatched version to confirm the integration reports the mismatch instead of proceeding silently.

**Acceptance Scenarios**:

1. **Given** the initial graph is created, **Then** the graph contains a record of the current ontology schema version.
2. **Given** the integration expects a specific schema version and the graph contains a different one, **When** the integration starts, **Then** it fails to load, does not silently modify the graph structure, and creates a repair issue directing the administrator to resolve the mismatch manually.

---

### User Story 9 - Diagnose and recover from connectivity problems (Priority: P3)

As a Home Assistant administrator, I want built-in diagnostics and repair guidance so that I can resolve graph database connectivity and schema issues without having to read raw logs.

**Why this priority**: Improves supportability and troubleshooting experience; useful once the integration is deployed and running, but not required for initial functional value.

**Independent Test**: Can be fully tested by downloading integration diagnostics (expect redacted, informative output) and by simulating a sustained outage (expect a repair notification to appear).

**Acceptance Scenarios**:

1. **Given** the integration is configured, **When** diagnostics are downloaded, **Then** credentials are redacted, and connection status, element counts, and schema version are included.
2. **Given** the graph database is unreachable across repeated synchronization attempts, **When** the integration detects the sustained failure, **Then** a repair notification is created explaining that the database is unreachable.

---

### Edge Cases

- What happens when an entity, device, or area is deleted in Home Assistant while the integration is mid-synchronization?
- How does the system handle a graph database that becomes unreachable partway through a synchronization operation?
- What happens when Home Assistant contains entities with no domain or integration information available?
- How does the system behave on first startup if the graph database already contains unrelated, non-ontology data?
- What happens when the configured credentials become invalid after initial setup (e.g., password changed on the database side)?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow administrators to configure the connection to the local graph database entirely through the Home Assistant Devices & Services UI, without requiring manual configuration file edits.
- **FR-002**: The system MUST validate the graph database connection at configuration time and reject setup with a clear error message if the connection cannot be established.
- **FR-003**: The system MUST allow administrators to update connection details for an existing configuration and re-validate before applying changes.
- **FR-004**: The system MUST redact credentials and other secrets from all logs, diagnostics output, and error messages.
- **FR-005**: The system MUST discover and represent areas, floors (where supported), devices, entities, domains, source integrations, labels (where supported), automations, scenes, and scripts from the Home Assistant installation.
- **FR-006**: The system MUST continue discovery and synchronization when optional relationships are missing (e.g., a device with no area, an entity with no device), representing the available data without treating the gap as a fatal error.
- **FR-007**: The system MUST build a graph representation linking the home to its areas, areas to their devices, devices to their entities, and entities to their domains and source integrations.
- **FR-008**: The system MUST ensure that repeated full synchronizations are idempotent: existing elements are identified and updated using stable identifiers rather than duplicated.
- **FR-009**: The system MUST use stable, durable identifiers for every represented element, derived from the corresponding Home Assistant registry identifiers (area, device, entity, automation, scene, script) so that identity is preserved across syncs and restarts.
- **FR-010**: The system MUST update only the affected part of the graph in response to individual Home Assistant registry or state change events, without requiring a full rebuild.
- **FR-011**: The system MUST throttle processing of high-frequency state change events so that synchronization activity does not degrade Home Assistant responsiveness.
- **FR-012**: The system MUST store only the current state of each entity by default, not a historical time-series of past states.
- **FR-012a**: The system MUST synchronize an entity's primary state value on change; attribute-only changes (e.g., battery percentage, signal strength) that do not change the primary state value are out of scope for synchronization in v1.
- **FR-013**: The system MUST perform synchronization work asynchronously so that Home Assistant startup and normal operation are never blocked by graph database activity.
- **FR-014**: The system MUST expose health status, element counts (nodes and relationships), last synchronization time, last error, and schema version as monitorable indicators within Home Assistant.
- **FR-013a**: The system MUST serialize ontology synchronization operations: if an operation (event-driven update, rebuild, resync, single-entity sync, or validation) is already in progress, a newly requested operation MUST be queued or rejected until the in-progress operation completes, rather than executed concurrently.
- **FR-015**: The system MUST provide user-triggerable controls to rebuild, validate, and resynchronize the ontology from within Home Assistant.
- **FR-016**: The system MUST provide callable operations to: rebuild the full ontology, resynchronize without deleting data the integration does not manage, synchronize a single specified entity, and validate graph consistency.
- **FR-017**: The system MUST record a structural schema version alongside the ontology data and detect when the expected version does not match what is present. On mismatch, the system MUST fail to load (rather than proceeding in a degraded or read-only mode), MUST NOT silently alter the existing structure, and MUST create a Home Assistant repair issue directing the administrator to resolve the mismatch manually.
- **FR-017a**: The system MUST distinguish elements it generated from Home Assistant metadata from any elements added or modified by a user or by inference, and MUST NOT delete or overwrite user-added or inferred elements during a rebuild or resync unless the user explicitly requests destructive behavior.
- **FR-018**: The system MUST provide downloadable diagnostics that include redacted connection information, connection status, element counts, and schema version.
- **FR-019**: The system MUST create a Home Assistant repair notification when the graph database remains unreachable across repeated synchronization attempts, with an explanation of the condition.
- **FR-020**: The system MUST retry failed graph database operations using a backoff strategy and mark affected updates as failed or pending rather than losing them silently.
- **FR-021**: The system MUST operate entirely with locally-hosted components; no functionality in this release may depend on an external cloud service.
- **FR-022**: The system MUST be manageable as a standard Home Assistant integration lifecycle object (install, configure, reload, unload) consistent with Home Assistant's Devices & Services model.

### Key Entities

- **Home**: The root representation of the Home Assistant installation itself; the top of the structural hierarchy.
- **Floor**: An optional grouping of areas, mirrored from Home Assistant's floor registry where supported.
- **Area**: A physical or logical location within the home that contains devices; mirrored from Home Assistant's area registry.
- **Device**: A physical device registered in Home Assistant, associated with an area and exposing one or more entities.
- **Entity**: An individual controllable or observable point (sensor, switch, etc.) exposed by a device or directly by an integration; carries a domain, a source integration, optional labels, and its latest known state.
- **Domain**: The category of an entity (e.g., light, sensor, switch), used to group entities by type.
- **Integration**: The Home Assistant integration that provides a given entity.
- **Automation**: A configured Home Assistant automation, related to the entities it references.
- **Scene**: A configured Home Assistant scene, related to the entities it controls.
- **Script**: A configured Home Assistant script, related to the entities it references.
- **Label**: A user-defined tag that can be applied to entities for grouping and classification.
- **Schema Record**: A version marker describing the current structural version of the ontology, used to detect and prevent unsafe structural drift between releases.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An administrator can go from an unconfigured integration to a fully synchronized, queryable ontology of their smart home in under 5 minutes on a typical local installation (up to ~500 entities/devices).
- **SC-002**: 100% of areas, devices, and entities present in a Home Assistant installation are represented in the ontology after the first successful synchronization, including those missing optional relationships.
- **SC-003**: A change made in Home Assistant (e.g., renaming a device, moving it to a new area, or changing an entity's state) is reflected in the ontology within a reasonable, near-real-time window without requiring a manual rebuild.
- **SC-004**: Running a full synchronization multiple times in a row never increases the count of represented elements beyond what actually exists in Home Assistant (i.e., zero duplicate creation).
- **SC-005**: When the graph database is temporarily unreachable, Home Assistant itself remains fully responsive and stable, with no restart or startup delay attributable to the integration.
- **SC-006**: An administrator can determine, from within Home Assistant alone (no external logs), whether the ontology is healthy, when it last synchronized, and what the last error (if any) was.
- **SC-007**: Diagnostics downloaded by an administrator never expose plaintext credentials or secrets.
- **SC-008**: Zero ontology functionality in this release requires internet connectivity or an external cloud account.

## Assumptions

- A "typical local installation" for sizing and performance validation purposes (per SC-001) is assumed to be a medium-scale installation of up to approximately 500 entities/devices; larger installations may take proportionally longer to synchronize.
- The Home Assistant installation runs on hardware capable of hosting or reaching a local graph database instance over the network; the graph database itself runs as a separate local service (e.g., in a local container) rather than embedded inside Home Assistant.
- "Rebuild" is assumed to clear and regenerate only the elements the integration itself manages (per the schema record), while "resync" is assumed to preserve any additional data present in the graph database that the integration did not create.
- A reasonable default debounce/throttle window (on the order of a few seconds) is used for high-frequency state change events; the exact interval is an implementation detail left to the design phase.
- A reasonable default retry/backoff policy (e.g., exponential backoff with a capped maximum) is used for transient graph database failures; exact timing is an implementation detail.
- A repair notification is assumed to be raised after a small number of consecutive failed synchronization attempts (rather than after a single transient failure), to avoid noisy false alarms.
- Floor and label registry data are treated as optional inputs since not all Home Assistant installations or versions expose them identically; their absence does not block synchronization of the rest of the ontology.
- Only one administrator-facing configuration entry per Home Assistant instance is assumed for v1 (i.e., connecting to a single graph database target).
