# Feature Specification: Home Assistant Ontology Integration v2

**Feature Branch**: `002-ontology-explorer-v2`

**Created**: 2026-07-24

**Status**: Draft

**Input**: User description: "Home Assistant Ontology Integration v2 - Ontology Explorer, Semantic Enrichment, and Validation. Enhance the v1 ontology graph with a user-facing ontology explorer, semantic classification of entities into concepts like gas cylinders, vehicles, energy assets, security devices, and occupancy sensors, user-managed semantic overrides that survive rebuilds, a validation engine for completeness/consistency, a read-only Cypher query service, a semantic refresh service, and import/export of user overrides. Local-first, no cloud dependency, builds on the v1 Home Assistant integration and Memgraph sync."

## Clarifications

### Session 2026-07-24

- Q: The Key Entities section defines `Dashboard`/`DashboardCard` nodes but no Functional Requirement describes how/when they are created or synced. Should dashboards be in v2 scope? → A: Include dashboards in v2 scope — sync Lovelace dashboard/card structure into the graph, tagged `source = "generated"`, with `CONTAINS_CARD` and `DISPLAYS_ENTITY` relationships.
- Q: Does a semantic asset node (e.g., `GasCylinder`, `EnergyAsset`, `SecurityDevice`) represent one physical asset that can aggregate multiple related entities, or does each matching entity get its own semantic node? → A: One node per classified entity — each matching entity gets its own semantic node (1:1), even if multiple entities logically describe the same physical asset.
- Q: Should ontology validation run only when the user calls `ontology.validate`, or should it also run automatically (e.g., after every sync, or on a schedule)? → A: On-demand only — validation runs only when `ontology.validate` is called manually; there is no automatic post-sync or scheduled trigger in v2.
- Q: FR-014 lists 9 validation categories, but only 3 (`missing_area`, `orphan_device`, `unavailable_critical_entity`) have defined detection criteria. Should the remaining 6 be fully specified now? → A: Define detection criteria for all 6 remaining categories now, so every listed category is fully specified.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Classify entities into semantic concepts (Priority: P1)

As a Home Assistant user, I want the integration to classify entities into semantic types so that the ontology understands concepts like gas cylinders, vehicles, energy assets, rooms, security devices, and occupancy sensors instead of just raw Home Assistant metadata.

**Why this priority**: Semantic classification is the foundational capability that turns the v1 metadata graph into a genuine semantic model. Every other v2 capability (explorer, validation, overrides, refresh) depends on the existence of semantic types and the source-tagging convention that distinguishes generated, inferred, and user-managed knowledge.

**Independent Test**: Can be fully tested by running semantic classification against a graph populated with a mix of gas-cylinder, vehicle, energy, and security-related entities, and confirming the expected `SemanticType` nodes and relationships are created and tagged with `source = "inferred"`, without requiring the explorer UI or query service to exist.

**Acceptance Scenarios**:

1. **Given** an entity's name, label, device name, or area indicates a gas cylinder, **When** semantic classification runs, **Then** the integration creates or updates a `GasCylinder` node, links the relevant sensor entity to it, and marks the relationship source as `inferred`.
2. **Given** entities represent solar, battery, grid, gas, water, or power monitoring data, **When** semantic classification runs, **Then** `EnergyAsset` nodes are created or updated with measurement relationships marked as `inferred`.
3. **Given** entities represent cameras, door sensors, motion sensors, locks, or alarms, **When** semantic classification runs, **Then** `SecurityDevice` nodes are created or updated with the relevant entity relationships.
4. **Given** semantic classification is enabled, **When** the user disables automatic classification in integration options, **Then** no new inferred semantic classifications are generated automatically.

---

### User Story 2 - Query the ontology safely with read-only Cypher (Priority: P1)

As an advanced user, I want a read-only Cypher query service so that I can query the ontology from Developer Tools, automations, or scripts without risking damage to the graph.

**Why this priority**: Direct query access is the highest-leverage capability for advanced users and is explicitly called out (ADR-007) as the query capability to deliver first, ahead of any UI. It must be safe by construction since it is the only user-facing surface that accepts arbitrary query text.

**Independent Test**: Can be fully tested by calling the `ontology.query` service with a read-only query (expect JSON results), a write-attempting query (expect rejection and a logged security warning), and a query with no explicit limit (expect the default/maximum result limit enforced) — independent of the explorer UI or semantic classification being present.

**Acceptance Scenarios**:

1. **Given** the user calls `ontology.query` with a read-only query, **When** the service executes, **Then** the result is returned as JSON-compatible data.
2. **Given** the user calls `ontology.query` with a query that attempts to create, update, merge, delete, set, remove, drop, detach, or call an unrestricted procedure, **Then** the integration rejects the query and logs a security warning.
3. **Given** the user calls `ontology.query` with a query that could return many rows, **When** the query executes, **Then** the integration enforces a maximum result limit (default 100, max 1000).

---

### User Story 3 - Provide backend API for the ontology explorer (Priority: P1)

As a frontend component, I want backend API endpoints so that I can retrieve ontology nodes, relationships, and search results from Memgraph safely, without exposing database credentials or unbounded result sets.

**Why this priority**: The backend API is the contract every explorer-facing feature depends on. It can be delivered and independently validated before any frontend panel exists, de-risking the UI work and unblocking automation/testing against a stable API surface.

**Independent Test**: Can be fully tested by requesting area context, entity context, and a search term against a populated graph and confirming bounded, credential-free, validated responses — without a sidebar panel being present.

**Acceptance Scenarios**:

1. **Given** the ontology contains an `Area` node, **When** the frontend requests area context, **Then** the API returns the area, related devices, related entities, and related automations where available.
2. **Given** the ontology contains an `Entity` node, **When** the frontend requests entity context, **Then** the API returns the entity, its device, its area, its semantic classifications, direct dependencies, and any dashboards/cards that display it, where available.
3. **Given** the ontology contains nodes matching a search term, **When** the frontend submits a search request, **Then** the API returns matching nodes with labels, IDs, and summary properties.

---

### User Story 4 - Manage semantic overrides by hand (Priority: P2)

As a Home Assistant user, I want to manually enrich or override semantic classifications so that the ontology matches my actual home context, and so that my manual work is never silently overwritten by automatic classification or resync.

**Why this priority**: Builds directly on User Story 1's semantic layer and the generated/user source-tagging convention (ADR-006). It is essential to trust in the system but depends on the semantic schema already existing.

**Independent Test**: Can be fully tested by creating a user-managed semantic relationship, running a full resync and a rebuild (`ontology.rebuild` always preserves user-managed data), and confirming the relationship survives both, then removing it and confirming it does not reappear.

**Acceptance Scenarios**:

1. **Given** an entity exists in the graph, **When** the user creates a semantic relationship, **Then** the relationship is stored in Memgraph and marked as `source = "user"`.
2. **Given** a user-managed relationship exists, **When** the integration performs a full resync, **Then** the user-managed relationship is preserved.
3. **Given** a user-managed relationship exists, **When** the user runs `ontology.rebuild`, **Then** the user-managed relationship is preserved (preservation is unconditional, not a toggle).
4. **Given** a user-managed relationship exists, **When** the user removes it, **Then** the relationship is deleted and does not reappear unless explicitly recreated.

---

### User Story 5 - Validate ontology completeness and consistency (Priority: P2)

As a Home Assistant administrator, I want validation checks so that I can see where my ontology is incomplete or inconsistent, such as entities missing an area, orphaned devices, or unavailable critical entities.

**Why this priority**: Validation gives administrators actionable insight into graph quality and is most valuable once the semantic layer (User Story 1) exists to validate against, but it does not require the explorer UI or query service to deliver value on its own.

**Independent Test**: Can be fully tested by running validation against a graph containing known issues (an entity with no area, an orphan device, an unavailable entity marked critical) and confirming `ValidationFinding` nodes are created with correct severity, then resolving the issues and confirming findings clear on the next validation run.

**Acceptance Scenarios**:

1. **Given** an `Entity` node has no path to an `Area`, **When** validation runs, **Then** the issue is reported as a warning and a `ValidationFinding` node is created or updated.
2. **Given** a `Device` node has no related `Area` and no exposed `Entity`, **When** validation runs, **Then** the issue is reported and the finding is linked to the `Device` node.
3. **Given** an entity is marked as critical and its state is unavailable, **When** validation runs, **Then** the issue is reported as high severity.
4. **Given** a validation finding exists and the underlying issue has been resolved, **When** validation runs again, **Then** the validation finding is marked as resolved or removed according to retention policy.

---

### User Story 6 - Refresh semantic classifications on demand (Priority: P2)

As a Home Assistant user, I want to refresh semantic classifications without rebuilding the whole graph so that inferred ontology data stays current as my home changes, without disturbing user-managed overrides.

**Why this priority**: A lightweight complement to User Story 1's classification engine, valuable for keeping data fresh but not required for the initial classification capability to exist.

**Independent Test**: Can be fully tested by changing entities/devices that affect classification, calling `ontology.refresh_semantics` (with and without an `entity_id`), and confirming inferred classifications update while user-managed relationships are untouched.

**Acceptance Scenarios**:

1. **Given** the ontology graph exists, **When** the user calls `ontology.refresh_semantics`, **Then** inferred semantic classifications are recalculated and user-managed semantic relationships are preserved.
2. **Given** an entity exists, **When** the user calls `ontology.refresh_semantics` with `entity_id`, **Then** only that entity's semantic classifications are recalculated.

---

### User Story 7 - Export and import user overrides (Priority: P3)

As a Home Assistant administrator, I want to export and import user-managed ontology overrides so that I can back up or migrate my semantic model across installations or after a rebuild.

**Why this priority**: A backup/migration convenience built on top of User Story 4's override mechanism. Valuable for administrators but not required for day-to-day semantic enrichment to function.

**Independent Test**: Can be fully tested by exporting user-managed overrides to a JSON payload, clearing them, importing the payload back, and confirming the overrides are restored identically and that malformed entries are rejected with clear errors.

**Acceptance Scenarios**:

1. **Given** user-managed semantic relationships exist, **When** the user calls `ontology.export_overrides`, **Then** the integration exports a JSON-compatible representation that excludes generated relationships, credentials, and secrets.
2. **Given** the user provides a valid overrides payload, **When** the user calls `ontology.import_overrides`, **Then** user-managed relationships are created or updated and invalid entries are rejected with clear errors.

---

### User Story 8 - Browse the ontology from a sidebar panel (Priority: P3)

As a Home Assistant user, I want a sidebar panel called Ontology so that I can browse the graph visually from the Home Assistant UI instead of relying on Developer Tools or the query service.

**Why this priority**: The panel is the most visible user story but is explicitly allowed to be delivered after the backend API (User Story 3) is stable; it depends entirely on that API and adds no new backend behavior of its own.

**Independent Test**: Can be fully tested by enabling the Ontology panel, confirming it appears in the sidebar, and browsing areas, devices, and search results using the already-validated backend API.

**Acceptance Scenarios**:

1. **Given** the integration is installed and the user enables the Ontology panel, **Then** Home Assistant displays an Ontology item in the sidebar.
2. **Given** the ontology contains areas and entities, **When** the user opens the Ontology panel, **Then** the user can browse areas and see related devices, entities, and automations where available.
3. **Given** the ontology contains devices and exposed entities, **When** the user selects a device, **Then** the panel displays device metadata, exposed entities, and the related area where available.
4. **Given** the ontology contains graph nodes, **When** the user searches for an entity, device, area, automation, scene, script, or semantic type, **Then** matching graph nodes are displayed.

---

### Edge Cases

- What happens when an entity matches more than one semantic classification rule (e.g., a sensor that looks like both a gas cylinder and an energy asset)? The classifier should apply all matching classifications rather than picking one, since an entity may legitimately belong to multiple semantic types.
- How does the system handle a semantic classification rule that would conflict with an existing user-managed classification for the same entity? The user-managed relationship takes precedence and the conflicting inferred relationship is not created or is suppressed.
- What happens when `ontology.query` is called with a syntactically invalid Cypher query? The service returns a clear error without attempting execution.
- What happens when the read-only query service is asked to run a query that only reads but calls a disallowed procedure (e.g., `CALL mg.*`)? The query is rejected under the same rules as write operations.
- How does the system behave when the backend API is asked for context on a node ID that no longer exists (e.g., deleted between graph sync cycles)? The API returns a clear "not found" result rather than an error or partial data.
- What happens when an import payload declares a schema version newer than the integration supports? The import is rejected with a clear version-mismatch error rather than partially applied.
- What happens when a user-managed relationship references an entity or area that has since been deleted from Home Assistant? The relationship is preserved as orphaned data (not deleted) and is surfaced as a validation finding (e.g., `invalid_relationship` or `orphan_entity`) rather than silently dropped.
- How does the system handle very large search result sets in the explorer or query service? Results are truncated to the enforced maximum and the response indicates that results were truncated.

## Requirements *(mandatory)*

### Functional Requirements

**Semantic classification**

- **FR-001**: System MUST classify entities into semantic types (`GasCylinder`, `Vehicle`, `EnergyAsset`, `SecurityDevice`, `OccupancySensor`, `ClimateDevice`, `NetworkDevice`, `BatteryPoweredDevice`) based on entity name, label, device name, or area signals.
- **FR-002**: System MUST create or update exactly one semantic type node per classified entity (a 1:1 relationship between a matching `Entity` and its semantic type node) and MUST create the relationship linking that node to the relevant `Entity`, `Device`, or `Area` nodes when classification runs. System MUST NOT merge multiple entities into a single shared semantic node, even when they logically describe the same physical asset.
- **FR-003**: System MUST mark every automatically-created semantic relationship with `source = "inferred"`.
- **FR-004**: System MUST allow the user to disable automatic semantic classification via an integration option, after which no new inferred classifications are generated until re-enabled.
- **FR-005**: System MUST support an entity matching more than one semantic classification rule by applying all matching classifications.
- **FR-006**: System MUST NOT overwrite or remove a user-managed (`source = "user"`) semantic relationship when generating an inferred classification for the same entity.

**User-managed overrides**

- **FR-007**: System MUST allow a user to create a semantic relationship for an entity, storing it with `source = "user"`, a timestamp, a relationship type, and a target node.
- **FR-008**: System MUST preserve all user-managed relationships across a full resync of generated data.
- **FR-009**: System MUST preserve all user-managed relationships whenever `ontology.rebuild` is invoked; preservation of user-managed data is unconditional (always-on) behavior of `ontology.rebuild`, not a toggleable parameter.
- **FR-010**: System MUST allow a user to remove a user-managed relationship, after which it does not reappear unless explicitly recreated.

**Validation**

- **FR-011**: System MUST detect and report entities with no path to an `Area` as a `missing_area` finding.
- **FR-012**: System MUST detect and report devices with no related `Area` and no exposed `Entity` as an `orphan_device` finding.
- **FR-013**: System MUST detect and report entities marked as critical that are in an unavailable state as a high-severity `unavailable_critical_entity` finding.
- **FR-014**: System MUST support the validation categories: `missing_area`, `missing_device`, `orphan_entity`, `orphan_device`, `duplicate_entity`, `unavailable_critical_entity`, `invalid_relationship`, `schema_mismatch`, `missing_semantic_classification`.
- **FR-015**: System MUST create or update a `ValidationFinding` node for each detected issue, linked to the relevant `Entity`, `Device`, or `Area` node via a `RELATES_TO` relationship.
- **FR-016**: System MUST mark a validation finding as resolved or remove it (per retention policy) when a subsequent validation run no longer detects the underlying issue.
- **FR-017**: System MUST expose an `ontology.validate` service that triggers an on-demand validation run and reports the outcome. Validation MUST NOT run automatically after sync operations or on a schedule in v2; it runs only when explicitly invoked via this service.

**Read-only query service**

- **FR-018**: System MUST expose an `ontology.query` service accepting a Cypher query string and an optional row limit (default 100, maximum 1000).
- **FR-019**: System MUST execute only read-only queries and MUST reject any query containing `CREATE`, `MERGE`, `DELETE`, `DETACH`, `SET`, `REMOVE`, `DROP`, `LOAD CSV`, `CALL dbms`, `CALL mg`, or `CALL algo` (case-insensitive, regardless of position in the query).
- **FR-020**: System MUST log a security warning whenever a query is rejected for containing a disallowed operation.
- **FR-021**: System MUST return query results as JSON-compatible data and MUST enforce the configured row limit even when the query itself could return more rows.
- **FR-022**: System MUST reject syntactically invalid queries with a clear error rather than attempting execution.

**Semantic refresh**

- **FR-023**: System MUST expose an `ontology.refresh_semantics` service that recalculates all inferred semantic classifications without performing a full graph rebuild.
- **FR-024**: System MUST support an optional `entity_id` parameter on `ontology.refresh_semantics` that limits recalculation to a single entity's semantic classifications.
- **FR-025**: System MUST preserve user-managed semantic relationships during any semantic refresh operation.

**Import / export of overrides**

- **FR-026**: System MUST expose an `ontology.export_overrides` service that produces a versioned, JSON-compatible export of user-managed relationships only, excluding generated/inferred relationships, credentials, and secrets.
- **FR-027**: System MUST expose an `ontology.import_overrides` service that validates the payload's schema version and rejects imports with an unsupported or missing version.
- **FR-028**: System MUST validate each entry in an import payload and reject invalid entries individually with a clear error, without failing the entire import unless the overall payload is malformed.
- **FR-029**: System MUST perform imports idempotently, such that importing the same valid payload multiple times produces the same resulting set of user-managed relationships.
- **FR-030**: System MUST NOT delete or replace any existing user-managed override during an import; imports are strictly additive/merge-only, and removing a user-managed override remains possible only via the explicit remove capability in FR-010.

**Backend API for ontology explorer**

- **FR-031**: System MUST provide a read-only backend API to retrieve area context (area, related devices, related entities, related automations where available).
- **FR-032**: System MUST provide a read-only backend API to retrieve entity context (entity, device, area, semantic classifications, direct dependencies, and dashboards/cards displaying the entity, where available).
- **FR-033**: System MUST provide a read-only backend API to search ontology nodes by term, returning matching nodes with labels, IDs, and summary properties.
- **FR-034**: System MUST NOT expose Memgraph credentials through any backend API response.
- **FR-035**: System MUST bound and limit the result size of every backend API response, and MUST indicate when results have been truncated.
- **FR-036**: System MUST validate all input parameters (e.g., node identifiers, search terms) to backend API requests and reject invalid input with a clear error.
- **FR-037**: System MUST return a clear "not found" result when a backend API request references a node ID that does not exist in the graph.

**Sidebar panel**

- **FR-038**: System MUST allow the user to enable a Home Assistant sidebar panel named "Ontology".
- **FR-039**: System MUST allow the panel to browse areas and view related devices, entities, and automations where available.
- **FR-040**: System MUST allow the panel to select a device and view its metadata, exposed entities, and related area where available.
- **FR-041**: System MUST allow the panel to search for entities, devices, areas, automations, scenes, scripts, or semantic types and display matching results.
- **FR-042**: System MAY defer delivery of the sidebar panel until the backend API is stable, in which case the corresponding user story remains partially complete until the panel is added.

**Source tagging (cross-cutting)**

- **FR-043**: System MUST tag every generated, inferred, and user-managed node or relationship introduced by v2 with a `source` property whose value is one of `home_assistant`, `generated`, `inferred`, or `user`.
- **FR-044**: System MUST make it possible to distinguish generated/inferred graph data from user-managed graph data using the `source` property alone.

**Non-functional**

- **FR-045**: System MUST NOT require any cloud service or external network dependency for the ontology explorer, semantic classification, validation, overrides, refresh, or query capabilities.
- **FR-046**: System MUST keep all graph data local to the user's own Memgraph instance.

**Dashboard synchronization**

- **FR-047**: System MUST synchronize Home Assistant dashboard (Lovelace) configuration into the graph, creating or updating `Dashboard` and `DashboardCard` nodes for each configured dashboard and card.
- **FR-048**: System MUST create `CONTAINS_CARD` relationships from a `Dashboard` node to each `DashboardCard` node it contains, and `DISPLAYS_ENTITY` relationships from a `DashboardCard` node to each `Entity` node it displays.
- **FR-049**: System MUST mark all dashboard, card, and display relationships created by dashboard synchronization with `source = "generated"`.
- **FR-050**: System MUST tolerate dashboards or cards that reference deleted or unknown entities by preserving the `DashboardCard` node and omitting the missing `DISPLAYS_ENTITY` relationship, without failing the sync.

**Additional validation category detection criteria**

- **FR-051**: System MUST detect and report `Entity` nodes that lack an associated `Device` node, when the entity's platform typically registers device information, as a `missing_device` finding.
- **FR-052**: System MUST detect and report `Entity` nodes with no relationship to any `Device`, `Area`, automation, scene, or script as an `orphan_entity` finding.
- **FR-053**: System MUST detect and report two or more `Entity` nodes that share the same underlying Home Assistant `entity_id` or `unique_id` as a `duplicate_entity` finding.
- **FR-054**: System MUST detect and report any relationship, including user-managed relationships, whose source or target node no longer exists in the graph as an `invalid_relationship` finding.
- **FR-055**: System MUST detect and report a mismatch between the ontology schema version recorded on the `OntologySchema` node and the version expected by the running integration as a `schema_mismatch` finding, without altering the existing fail-to-load and repair-issue behavior defined for schema mismatches in v1.
- **FR-056**: System MUST detect and report `Entity` nodes matching known semantic classification signals (per FR-001) that have not yet received a corresponding semantic classification relationship, as a `missing_semantic_classification` finding.

### Key Entities *(include if feature involves data)*

- **SemanticType**: A classification concept applied to one or more entities/devices (e.g., "this sensor represents a gas cylinder level"). Linked to `Entity` nodes via `CLASSIFIED_AS`.
- **GasCylinder**: A semantic asset created per classified entity, representing a physical gas cylinder measured by that entity and located in an area where known.
- **Vehicle**: A semantic asset created per classified entity, representing a tracked vehicle, located in an area where known.
- **EnergyAsset**: A semantic asset created per classified entity, representing an energy-related concept (solar, battery, grid, gas, water, power) measured by that entity.
- **SecurityDevice**: A semantic asset created per classified entity, representing a security-related device (camera, door sensor, motion sensor, lock, alarm) observed by that entity.
- **OccupancySensor / ClimateDevice / NetworkDevice / BatteryPoweredDevice**: Additional semantic asset types classifying entities/devices by function.
- **Dashboard / DashboardCard**: Represents a Home Assistant dashboard and the cards it contains, synchronized from Lovelace configuration and tagged `source = "generated"`; cards are linked to their dashboard via `CONTAINS_CARD` and to the entities they display via `DISPLAYS_ENTITY`.
- **ValidationFinding**: Represents a detected completeness or consistency issue, with a category (e.g., `missing_area`, `orphan_device`), a severity, and a relationship to the affected `Entity`, `Device`, or `Area`.
- **Source metadata**: A `source` property (`home_assistant`, `generated`, `inferred`, or `user`) attached to nodes/relationships to distinguish how the data was created and whether it should survive a rebuild or refresh.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An administrator can identify at least the three most common ontology completeness issues (missing area, orphan device, unavailable critical entity) in their installation within 2 minutes of running validation, without writing a single query.
- **SC-002**: A user can classify a home containing gas cylinder, vehicle, energy, and security-related entities such that at least 90% of clearly-named matching entities receive the correct semantic classification without manual intervention.
- **SC-003**: 100% of write-intent Cypher queries (containing any disallowed keyword) submitted to the query service are rejected before execution, with zero write-intent queries reaching the database.
- **SC-004**: A user can back up their entire set of manual semantic overrides and restore them on a fresh installation in under 5 minutes using export/import, with zero data loss for valid entries.
- **SC-005**: Backend API requests for area context, entity context, or search return within 2 seconds on a graph of up to 5,000 nodes on a typical 8 GB local Home Assistant host.
- **SC-006**: A full resync or rebuild with data preservation enabled preserves 100% of user-managed semantic relationships that existed before the operation.
- **SC-007**: Once the sidebar panel is available, a user can locate a specific device and see its area, exposed entities, and semantic classifications within 3 clicks from the Ontology panel.

## Assumptions

- The v1 Home Assistant Ontology Integration (specs/001-ha-ontology-integration) is already installed and syncing core Home Assistant metadata into Memgraph; v2 extends that existing graph rather than replacing it.
- "Automatic classification" is a single integration-level on/off option in v2; per-semantic-type toggles are not required unless a future iteration requests them.
- Validation finding retention policy defaults to: mark a finding resolved when its underlying issue no longer reproduces, and remove resolved findings after they have remained resolved across one subsequent validation run, unless the user has taken an explicit action on the finding.
- The read-only query service (`ontology.query`) is exposed only as a Home Assistant service (for Developer Tools, automations, and scripts) in v2; it is not exposed as a separate authenticated HTTP endpoint for arbitrary external clients.
- The backend API for the ontology explorer (User Story 3) is consumed by the optional sidebar panel and is not intended as a general-purpose public API; it is scoped to the needs of area context, entity context, and search.
- "Critical" entity marking (used for `unavailable_critical_entity` validation) is a property the user or integration sets on select entities; a reasonable default is that no entities are marked critical until the user opts in.
- Import/export payload versioning uses a simple integer or semantic version field; only exact or explicitly-supported version compatibility is accepted, and mismatches fail closed with a clear error.
- The sidebar panel (User Story 8) may ship in a later increment than the backend API; its acceptance scenarios apply once the panel exists, and the user story is considered partially complete (backend-only) until then, consistent with the feature description's own guidance.
- Performance targets assume the same "typical" installation scale established in v1 (up to ~500 entities/devices), extended here to graphs of up to ~5,000 total nodes once semantic types, findings, and dashboard data are included.
