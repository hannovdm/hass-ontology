# Feature Specification: Interactive Ontology Graph Visualization

**Feature Branch**: `main`

**Created**: 2026-08-19

**Status**: Draft

**Input**: User description: "Visual representation of the ontology by using Memgraph Lab with GraphQL in combination with a custom Cytoscape.js utilizing Home Assistant native icons. The existing memgraph container needs to be used that hosts the memgraph database to include the GraphQL and other required components. This visualization should be part of the Ontology explorer that is already in the HA left side bar. The visualization should be interactive and auto updating."

## Clarifications

### Session 2026-08-19

- Q: Who may access each visualization? → A: All authenticated Home Assistant users may access the custom graph; only Home Assistant administrators may access Memgraph Lab.
- Q: How should the custom graph access GraphQL data? → A: Through a Home Assistant-authenticated GraphQL gateway; direct browser-to-container access is prohibited.
- Q: What should the graph display when first opened? → A: All areas and their directly assigned devices, up to the display limit; entity-level detail loads through expansion.
- Q: How should devices without an assigned area appear initially? → A: Under a clearly marked, presentation-only "Unassigned" group that is never stored in the ontology.
- Q: Which ontology changes should update the open graph automatically? → A: Node and relationship changes plus properties currently visible in the graph or details panel; rapid updates are coalesced.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View the Home Ontology as a Graph (Priority: P1)

As a Home Assistant user, I want to open the existing Ontology Explorer and immediately see my home ontology as a visual graph so that I can understand how areas, devices, entities, automations, dashboards, and semantic concepts relate without writing a query.

**Why this priority**: A clear graph view is the core value of this feature and makes the ontology usable by people who do not know a graph query language.

**Independent Test**: Populate the ontology with representative areas, devices, entities, and relationships, open the Ontology Explorer, and confirm that a labeled, connected graph appears with recognizable Home Assistant iconography and a legend.

**Acceptance Scenarios**:

1. **Given** the ontology contains areas and assigned devices, **When** the user opens the Ontology Explorer graph view, **Then** the view displays all areas and their directly assigned devices with human-readable labels, up to the communicated display limit.
2. **Given** a node represents a Home Assistant object with a known native icon, **When** the node is displayed, **Then** the graph uses that icon and provides a clear fallback for unknown or missing icons.
3. **Given** the graph contains multiple node and relationship types, **When** the view loads, **Then** a visible legend allows the user to distinguish the represented types.
4. **Given** the ontology is empty, **When** the user opens the graph view, **Then** the view presents an empty-state message and a relevant recovery action rather than a blank canvas.

---

### User Story 2 - Explore Relationships Interactively (Priority: P1)

As a Home Assistant user, I want to search, select, expand, filter, and reposition graph elements so that I can investigate a specific object and its neighborhood without being overwhelmed by the entire ontology.

**Why this priority**: Interaction turns a static diagram into a practical troubleshooting and discovery tool, especially as the ontology grows.

**Independent Test**: Open a graph containing at least 100 mixed nodes, locate a known entity through search, inspect its details, expand its neighborhood, apply a type filter, and reset the view without leaving the Ontology Explorer.

**Acceptance Scenarios**:

1. **Given** a graph is visible, **When** the user searches for an object by name or identifier, **Then** matching nodes are shown and selecting a result focuses the corresponding node.
2. **Given** a node is selected, **When** the user requests its details, **Then** the view shows its type, identifier, relevant non-sensitive properties, and directly connected relationships.
3. **Given** a selected node has relationships not yet shown, **When** the user expands the node, **Then** its next bounded set of neighboring nodes and relationships is added without discarding the current view.
4. **Given** the graph contains several object types, **When** the user applies node-type or relationship-type filters, **Then** only matching graph elements remain visible and the filter state is clear.
5. **Given** the user has panned, zoomed, moved nodes, or applied filters, **When** the graph receives an update, **Then** the current selection and viewport are preserved whenever the selected objects still exist.

---

### User Story 3 - See Ontology Changes Automatically (Priority: P1)

As a Home Assistant user, I want the open graph to reflect ontology changes automatically so that the visualization remains trustworthy while devices, states, and relationships change.

**Why this priority**: A stale visualization can lead to incorrect conclusions and would force users to repeatedly reload the panel.

**Independent Test**: Keep the graph view open, create, update, and remove representative ontology objects through normal Home Assistant activity, and confirm the corresponding visual changes appear without a page reload while the user context remains stable.

**Acceptance Scenarios**:

1. **Given** the graph view is open and connected, **When** a node or relationship is added, changed, or removed, or a property currently visible in the graph or details panel changes, **Then** the displayed graph updates automatically within 5 seconds of the ontology recording the change.
2. **Given** the graph view is open, **When** a newly created object matches the current scope and filters, **Then** it appears automatically without a full page reload.
3. **Given** a visible object is removed from the ontology, **When** the update is received, **Then** it is removed from the graph and any now-invalid selection or detail panel is cleared with a concise notice.
4. **Given** live updates are interrupted, **When** the interruption occurs, **Then** the view indicates that data may be stale and automatically attempts to resume updates.
5. **Given** the connection resumes after an interruption, **When** the graph reconciles with the current ontology, **Then** missed changes are reflected and the stale-data indication is removed.

---

### User Story 4 - Use an Advanced Graph Workspace (Priority: P2)

As an advanced Home Assistant administrator, I want to access a Memgraph Lab workspace from the Ontology Explorer so that I can perform deeper visual inspection using the established graph tooling while remaining within the local installation and its safety boundaries.

**Why this priority**: The custom graph serves the common workflow, while the advanced workspace supports expert investigation without requiring a separately managed graph environment.

**Independent Test**: From the Ontology Explorer, open the advanced workspace, inspect the same ontology data shown in the custom graph, run an allowed read-only exploration, and verify that write attempts and unauthenticated access are rejected.

**Acceptance Scenarios**:

1. **Given** the current user is a Home Assistant administrator and the Lab capability check has verified database-enforced read-only access, **When** the user opens the advanced workspace, **Then** it connects to the existing local ontology and does not request separate database credentials.
2. **Given** the advanced workspace is open, **When** the user performs an allowed read-only exploration, **Then** the returned graph reflects the same current ontology used by the custom visualization.
3. **Given** the advanced workspace receives a write-intent request, **When** the request is submitted, **Then** it is rejected before the ontology can be changed.
4. **Given** an authenticated non-administrator, **When** the user attempts to open Memgraph Lab directly or through the Ontology Explorer, **Then** access is denied while the custom graph remains available.
5. **Given** Memgraph Community or a configuration whose read-only capability cannot be verified, **When** an administrator requests the advanced workspace, **Then** the Ontology Explorer reports why Lab is unavailable and continues to provide the custom graph.

### Edge Cases

- When the ontology exceeds the initial display limit, the view loads a bounded, useful starting subgraph, states that more data is available, and lets the user search or expand incrementally.
- Devices without an assigned area appear under a clearly marked, presentation-only "Unassigned" group; the group is not represented or persisted as an ontology node.
- Nodes with identical display names remain distinguishable by type and stable identifier.
- Unknown node labels, relationship types, and icons use visible generic fallbacks instead of being omitted.
- Self-referential relationships and multiple relationships between the same pair of nodes remain selectable and distinguishable.
- Rapid repeated updates are coalesced so that the graph remains interactive and converges to the latest ontology state.
- If the ontology service is unavailable when the panel opens, the user sees an actionable unavailable state and the panel retries without affecting Home Assistant operation.
- If an expanded or selected node disappears during an update, the graph removes it without leaving broken relationships or an invalid details view.
- Sensitive values, credentials, secrets, and redacted diagnostic properties never appear in node details, graph responses, error messages, or the advanced workspace connection flow.
- On narrow screens, the graph remains usable and controls do not overlap the canvas, selected details, or one another.

## Requirements *(mandatory)*

### Functional Requirements

**Integrated graph view**

- **FR-001**: The system MUST add an interactive graph view to the existing Ontology Explorer in the Home Assistant sidebar rather than registering a separate primary sidebar destination.
- **FR-001a**: The custom graph MUST be available to every authenticated Home Assistant user who can access the Ontology Explorer.
- **FR-002**: The graph view MUST visualize ontology nodes and relationships with human-readable labels, directional relationship labels where direction is meaningful, and a visible type legend.
- **FR-003**: The graph view MUST use the corresponding Home Assistant native icon for a represented object when one is available and MUST use a consistent type-specific fallback when it is not.
- **FR-004**: The graph view MUST provide distinct, accessible visual treatment for node types, relationship types, selected elements, search matches, unavailable objects, and validation findings.
- **FR-005**: The graph view MUST provide explicit loading, empty, partial-results, stale-data, unavailable, and error states.

**Interactive exploration**

- **FR-006**: Users MUST be able to pan, zoom, fit, reset, and reposition the graph without those actions changing ontology data.
- **FR-007**: Users MUST be able to search visible and not-yet-loaded ontology objects by name or stable identifier and focus a selected result.
- **FR-008**: Users MUST be able to select a node or relationship and inspect its type, stable identifier, relevant non-sensitive properties, and direct connections.
- **FR-009**: Users MUST be able to expand a selected node by one relationship hop at a time, subject to a clearly communicated per-expansion limit.
- **FR-010**: Users MUST be able to filter the graph by node type and relationship type and clear all active filters in one action.
- **FR-011**: The system MUST preserve the current viewport, filters, and selection across incremental updates whenever the referenced graph elements still exist.
- **FR-012**: The system MUST initially display all `Area` nodes and their directly assigned `Device` nodes up to the configured display limit; entity-level and deeper relationship detail MUST load through incremental expansion rather than being included in the initial graph.
- **FR-012a**: The initial graph MUST place every device without an assigned area under a clearly marked, presentation-only "Unassigned" group and MUST NOT create or persist an ontology node or relationship for that group.
- **FR-013**: The system MUST identify truncated or partial results and provide search or expansion actions that let the user retrieve additional relevant context.

**Automatic updates**

- **FR-014**: The open graph view MUST automatically reflect node and relationship additions, changes, and removals that affect its current scope, plus changes to properties currently visible in the graph or details panel, without requiring a page reload; properties that are neither loaded nor visible MUST NOT be streamed solely for visualization.
- **FR-015**: The system MUST coalesce bursts of topology and visible-property changes and apply the latest values without blocking Home Assistant or making graph controls unresponsive.
- **FR-016**: The graph view MUST visibly indicate when automatic updates are disconnected or delayed and MUST attempt to reconnect automatically.
- **FR-017**: After reconnection, the graph view MUST reconcile its displayed data with the current ontology so that changes missed during the interruption are not permanently omitted.

**Advanced workspace and data access**

- **FR-018**: Home Assistant administrators MUST be able to open an advanced Memgraph Lab workspace from within the Ontology Explorer when the Lab capability check confirms database-enforced read-only access. When that capability is unavailable, administrators MUST receive an actionable reason while the custom graph remains available. Authenticated non-administrators MUST NOT receive Lab access.
- **FR-019**: The advanced workspace and custom graph MUST represent the same ontology stored in the existing local Memgraph database.
- **FR-020**: All graph retrieval surfaces introduced by this feature MUST be read-only and MUST reject graph mutation operations before execution.
- **FR-021**: Access to graph data MUST require Home Assistant authentication, access to Memgraph Lab MUST additionally require Home Assistant administrator privileges, and no surface MUST expose database credentials to the browser or user interface.
- **FR-021a**: The browser MUST access graph data only through the Home Assistant-authenticated gateway. The gateway MUST use the add-on GraphQL adapter when configured and MUST use equivalent fixed, bounded, parameterized read-only Memgraph operations when no GraphQL service is available. The browser MUST NOT connect directly to either backend.
- **FR-022**: Every graph retrieval request MUST enforce a bounded result size and MUST communicate when the result is incomplete.
- **FR-023**: Graph responses and displayed details MUST exclude secrets, credentials, tokens, and properties classified as sensitive by the integration's existing redaction rules.

**Local deployment and resilience**

- **FR-024**: The feature MUST operate locally without requiring a cloud service, cloud account, external telemetry destination, or internet access during normal use.
- **FR-025**: The existing Memgraph add-on/container MUST remain the single graph service deployment managed by the user; this feature MUST NOT require a second database or separately managed visualization container.
- **FR-025a**: The custom graph MUST remain usable when Memgraph is configured as an externally reachable service without Home Assistant Supervisor or the project add-on.
- **FR-026**: Failure or unavailability of any visualization component MUST NOT prevent Home Assistant or the core ontology integration from starting, synchronizing, or unloading.
- **FR-027**: The system MUST provide an actionable unavailable state when graph data or the advanced workspace cannot be reached and MUST recover without requiring a Home Assistant restart.

### Key Entities *(include if feature involves data)*

- **Visual Graph Node**: A safe presentation of an ontology object, including its stable identifier, display label, type, native or fallback icon, selected non-sensitive properties, and current visual state.
- **Visual Graph Relationship**: A safe presentation of a directed or undirected ontology connection, including its type, endpoints, source classification, and selected non-sensitive properties.
- **Graph View State**: The user's current viewport, selection, filters, expanded neighborhoods, result-limit indicators, and update-connection status. It is presentation state and does not modify the ontology.
- **Graph Change**: A notification or reconciliation result indicating that a node or relationship was added, changed, or removed from the ontology.
- **Graph Query Result**: A bounded, read-only collection of nodes, relationships, and metadata indicating whether additional matching data exists.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 90% of first-time users can open the Ontology Explorer, identify an area, and trace it to a related device and entity within 2 minutes without writing a query.
- **SC-002**: For ontologies containing up to 5,000 nodes, the initial useful graph becomes visible within 3 seconds for at least 95% of local test runs on the project's target 8 GB Home Assistant host.
- **SC-003**: At least 95% of node or relationship changes and currently visible property changes affecting the open graph appear within 5 seconds of being recorded, without a page reload.
- **SC-004**: During a burst of 100 ontology changes in 10 seconds, users can continue to pan, zoom, select, and filter the graph, and the display converges to the current ontology within 10 seconds after the burst ends.
- **SC-005**: Users can locate any indexed ontology object by exact name or stable identifier in no more than 3 interactions from the graph view.
- **SC-006**: In security validation, 100% of attempted mutation requests through the custom graph, advanced workspace, and graph data surfaces are rejected without changing the ontology.
- **SC-007**: In resilience testing, loss and restoration of the visualization data connection never interrupts Home Assistant operation, and the graph returns to a current state within 15 seconds after connectivity is restored.
- **SC-008**: In representative desktop and mobile viewport tests, all graph controls, status indicators, and selected-item details remain readable, operable, and free of overlap.

## Assumptions

- The existing Ontology Explorer sidebar panel and its read-only backend capabilities from feature 002 are available and remain the owning user experience for this feature.
- When the project Memgraph add-on is used, it remains the single deployment unit and is extended to include Memgraph Lab, a GraphQL graph data surface, and supporting runtime components. Home Assistant Container/Core installations may continue using an externally reachable Memgraph service without those optional add-on components.
- The custom graph visualization uses Cytoscape.js and Home Assistant native icons as explicit user-mandated delivery constraints; detailed component architecture and package selection belong in the implementation plan.
- The custom graph is the default visualization for common exploration tasks, while Memgraph Lab is an advanced workspace reachable from the Ontology Explorer.
- The custom graph always uses a Home Assistant-authenticated gateway. The gateway uses the internal GraphQL adapter when available and otherwise performs the same fixed, bounded, parameterized read-only operations through the integration's existing Memgraph connection; the browser never connects directly to either backend.
- Memgraph Lab is an optional advanced capability. Its absence on Community or external-Memgraph deployments does not make the custom visualization incomplete.
- The existing ontology schema, stable identifiers, source metadata, and user-managed relationships are authoritative; visualization state never writes to or changes them.
- The initial display limit and per-expansion limit are configurable implementation choices, but defaults must keep the target 8 GB Home Assistant host responsive and must be visible to the user whenever they truncate results.
- The initial graph is an area-first overview: it includes all areas and their directly assigned devices up to the display limit, while entities and deeper relationships load through expansion.
- Automatic updates apply while the graph view is open. Background browser tabs may update when resumed rather than consuming resources continuously.
- Persisting graph layout or personal view preferences across browser sessions is out of scope for the first release; preserving view state during the current open session is required.
- Editing ontology nodes or relationships, controlling Home Assistant devices, and executing unrestricted queries from either visualization are out of scope.