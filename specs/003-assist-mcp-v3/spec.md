# Feature Specification: Home Assistant Ontology Integration v3

**Feature Branch**: `003-assist-mcp-v3`

**Created**: 2026-08-11

**Status**: Draft

**Input**: User description: "Home Assistant Ontology Integration v3 - Assist, MCP, Impact Analysis, and Local AI Readiness. Adds natural-language-ready ontology query intents for Home Assistant Assist, a local read-only MCP-compatible endpoint (disabled by default), entity/device/area impact analysis, local AI context export with secret redaction, predefined safe query tools (search, context, dependencies, bounded read-only Cypher), and audit/diagnostics for agent access. Local-first, no cloud dependency, external/optional AI runtime, builds on the v1/v2 ontology graph in Memgraph."

## Clarifications

### Session 2026-08-11

- Q: Should Assist/MCP diagnostic events and impact-analysis/context-export records be persisted as new Memgraph graph nodes (extending the ontology schema, e.g. `AssistQuery`/`AgentQuery`/`ImpactAnalysis`/`ContextExport` labels), or purely as non-graph diagnostic/log records? → A: Diagnostics-only records, reusing the existing v1/v2 diagnostics mechanism — no new graph schema or schema version bump.
- Q: What responsiveness target should impact analysis and query-tool calls meet on a several-thousand-node graph (for SC-005)? → A: Under 3 seconds.
- Q: Beyond local-only binding, does the MCP endpoint require an additional auth mechanism? → A: Yes — a generated local access token is required before any tool call is accepted.
- Q: What retention policy should apply to Assist/MCP diagnostic and audit records? → A: Time-based expiry — records are automatically pruned after a fixed retention window (30 days).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Predefined safe ontology query tools (Priority: P1)

As an integration consumer (an automation, a script, Assist, or an MCP client), I want a set of predefined, safe query operations — search, area context, entity context, device context, automation dependencies, and a strictly bounded read-only query — so that I can retrieve ontology knowledge without writing or being exposed to raw graph query syntax, and without risking unbounded or destructive queries.

**Why this priority**: This is the foundational service layer that every other v3 capability (Assist intents, MCP tools, impact analysis, context export) is built on top of. Without deterministic, bounded, safe query tools, none of the higher-level consumer-facing features can be delivered safely.

**Independent Test**: Can be fully tested by invoking each predefined query operation directly (e.g., as a Home Assistant service call) against a populated ontology graph and confirming correct, bounded, JSON-compatible results — without requiring Assist or MCP to exist yet.

**Acceptance Scenarios**:

1. **Given** a search term is provided, **When** the ontology search operation is invoked, **Then** matching nodes are returned and the result count does not exceed the configured limit.
2. **Given** a valid area identifier or name, **When** the area context operation is invoked, **Then** the area's devices, entities, and known relationships are returned.
3. **Given** a valid entity identifier, **When** the automation dependencies operation is invoked, **Then** automations related to that entity are returned.
4. **Given** the bounded read-only query operation is invoked with a query that attempts to create, update, or delete data, **When** the operation is evaluated, **Then** the request is rejected before execution and no data is modified.
5. **Given** any predefined query operation is invoked, **When** the result is returned, **Then** it includes a target identifier, a result type, and any warnings about incomplete relationships, and excludes sensitive values.

---

### User Story 2 - Ask Home Assistant Assist about the ontology (Priority: P2)

As a Home Assistant user, I want to ask Home Assistant Assist questions about my home ontology so that I can understand relationships, dependencies, and impact using natural conversation instead of a dashboard or raw query tool.

**Why this priority**: This is the primary, most visible way most users will experience v3 — conversational access to ontology knowledge is the core business goal of this release.

**Independent Test**: Can be fully tested by issuing supported Assist queries (about automation dependencies, area contents, or entity context) against a populated ontology graph and confirming Assist returns correct, resolved answers or a clear "not found" response for unresolved references.

**Acceptance Scenarios**:

1. **Given** the ontology contains automations and entities, **When** the user asks which automations depend on a specific entity, **Then** the integration resolves the entity, returns matching automations, and includes why each automation is related where that information is available.
2. **Given** the ontology contains areas, devices, and entities, **When** the user asks what devices are in an area, **Then** the integration returns devices related to that area and groups related entities by device where possible.
3. **Given** the ontology contains an entity, **When** the user asks what an entity is connected to, **Then** the integration returns its device, area, domain, integration, semantic classifications, and direct dependencies where available.
4. **Given** the user asks about an entity, device, or area that cannot be resolved, **When** Assist invokes the ontology query, **Then** the integration returns a clear "not found" response and does not run a broad, unbounded query.

---

### User Story 3 - Entity impact analysis (Priority: P3)

As a Home Assistant user, I want to understand what depends on a specific entity so that I can troubleshoot failures and plan changes safely.

**Why this priority**: Impact analysis at the entity level is the most granular and most frequently needed troubleshooting capability (e.g., "what breaks if this sensor goes unavailable?").

**Independent Test**: Can be fully tested by requesting impact analysis for a known entity in a populated graph and confirming the returned dependency lists (automations, scripts, scenes, dashboards, semantic assets) match the graph's actual relationships.

**Acceptance Scenarios**:

1. **Given** an entity exists in the graph, **When** the user requests impact analysis for the entity, **Then** the integration returns related automations, scripts, scenes, dashboards (where available), and semantic assets (where available).
2. **Given** an entity's state is unavailable, **When** the user requests impact analysis, **Then** the integration identifies downstream automations, scripts, scenes, dashboards, and semantic assets that may be affected.
3. **Given** an entity exists with no downstream dependencies, **When** impact analysis runs, **Then** the integration returns an empty dependency list and explains that no known graph dependencies were found.

---

### User Story 4 - Device impact analysis (Priority: P4)

As a Home Assistant user, I want to understand what depends on a device so that I can safely replace, move, rename, or troubleshoot hardware.

**Why this priority**: Device-level analysis aggregates entity-level impact across all of a device's exposed entities, supporting hardware-level maintenance decisions; it builds naturally on entity impact analysis.

**Independent Test**: Can be fully tested by requesting impact analysis for a known device with multiple exposed entities and confirming all entities and their downstream dependencies are aggregated correctly.

**Acceptance Scenarios**:

1. **Given** a device exposes multiple entities, **When** the user requests impact analysis for the device, **Then** the integration returns all exposed entities, downstream dependencies for each entity, and related semantic objects.
2. **Given** a device has been moved to another area, **When** impact analysis runs, **Then** the analysis uses the current area relationship.
3. **Given** the target device cannot be resolved, **When** impact analysis is requested, **Then** the integration returns a "not found" response.

---

### User Story 5 - Area impact analysis (Priority: P5)

As a Home Assistant user, I want to understand what depends on an area so that I can troubleshoot or remodel a room without breaking automations and dashboards.

**Why this priority**: Area-level analysis is the broadest and least frequently needed impact scope, aggregating device- and entity-level impact for planning larger changes (remodels, area reassignments).

**Independent Test**: Can be fully tested by requesting impact analysis for a known area containing devices and entities and confirming the aggregated result includes all affected devices, entities, and related automations, scripts, scenes, and dashboards.

**Acceptance Scenarios**:

1. **Given** an area contains devices and entities, **When** the user requests impact analysis for the area, **Then** the integration returns affected devices, affected entities, related automations, related scripts, related scenes, and related dashboards where available.
2. **Given** an area contains no known devices or entities, **When** impact analysis runs, **Then** the integration returns an empty result with a clear explanation.

---

### User Story 6 - Local AI context export (Priority: P6)

As an advanced user, I want to export ontology context for local AI agents so that my local LLM can reason over my smart home without direct access to Home Assistant internals or exposure to secrets.

**Why this priority**: Context export enables offline/batch local-AI use cases distinct from live conversational (Assist) or live tool-call (MCP) access, and depends on impact analysis and query tooling already being available.

**Independent Test**: Can be fully tested by requesting each export type (area, entity, device, automation, impact, whole-home summary) against a populated graph and confirming the output is well-formed JSON with no secrets, tokens, passwords, or credentials present.

**Acceptance Scenarios**:

1. **Given** the ontology contains area relationships, **When** the user exports context for an area, **Then** the integration returns a structured JSON document including devices, entities, automations, semantic assets, and validation findings where available.
2. **Given** the ontology contains an entity, **When** the user exports context for the entity, **Then** the integration returns a structured JSON document including direct graph relationships and excluding secrets and credentials.
3. **Given** the ontology graph exists, **When** the user requests a whole-home summary export, **Then** the integration produces a compact JSON representation that excludes secrets, tokens, credentials, and sensitive configuration.
4. **Given** exported nodes contain attributes, **When** context export runs, **Then** access tokens, passwords, IP credentials, and secrets are excluded from the output.

---

### User Story 7 - Local MCP-compatible read-only endpoint (Priority: P7)

As an advanced user, I want a local MCP-compatible endpoint so that local agents can query the Home Assistant ontology without cloud dependencies.

**Why this priority**: The MCP endpoint is an additional, opt-in access channel layered on top of the same safe query tools already delivered for Assist and context export; it is valuable but targets a narrower, more advanced audience and must be off by default for safety.

**Independent Test**: Can be fully tested by enabling MCP support, connecting a local client, invoking a read-only tool, and confirming structured results are returned; and separately, by confirming no endpoint is exposed when MCP support is left at its default (disabled) setting.

**Acceptance Scenarios**:

1. **Given** the user enables MCP support, **When** the integration starts, **Then** a local MCP-compatible endpoint is exposed and the endpoint provides read-only ontology tools.
2. **Given** the integration is installed, **When** the user has not enabled MCP support, **Then** no MCP endpoint is exposed.
3. **Given** an MCP client connects locally, **When** it invokes the entity context tool, **Then** the integration returns structured JSON context for that entity.
4. **Given** an MCP client attempts a write operation, **When** the request is evaluated, **Then** the integration rejects the request and records the event in diagnostics.

---

### User Story 8 - Audit and diagnostics for agent access (Priority: P8)

As a Home Assistant administrator, I want diagnostics for Assist and MCP access so that I can understand how the ontology is being used and detect misuse.

**Why this priority**: Diagnostics are cross-cutting oversight for all other v3 capabilities; they are important for trust and troubleshooting but depend on the other access paths (Assist, MCP, query tools) existing first to have something to record.

**Independent Test**: Can be fully tested by invoking ontology queries through Assist and MCP and confirming diagnostic metadata (request type, tool, status, count, timestamp) is recorded without secrets or full prompts, and that rejected write attempts are separately recorded.

**Acceptance Scenarios**:

1. **Given** MCP support is enabled, **When** an MCP client invokes an ontology tool, **Then** the integration records diagnostic metadata and does not record secrets or full prompts by default.
2. **Given** an MCP client attempts a write operation, **When** the operation is rejected, **Then** the integration records the rejected operation type and updates diagnostics.
3. **Given** Assist invokes an ontology query intent, **When** the query completes, **Then** the integration records that an Assist query occurred and stores only redacted diagnostic metadata by default.

---

### Edge Cases

- What happens when Assist or an MCP client asks about an entity, device, or area that exists in Home Assistant but has not yet been synced into the ontology graph?
- How does the system handle impact analysis or context export requests against a graph with tens of thousands of nodes, where a full unbounded traversal would be too slow or resource-intensive?
- What happens when the external local AI runtime referenced by a user's own tooling is unreachable or not running — do ontology intents, MCP tools, impact analysis, and context export still function?
- How does the system respond when an MCP client sends a request that resembles a write operation but is ambiguous (e.g., a query that includes both read and write clauses)?
- What happens when a context export or diagnostics record would otherwise include a value that looks like a secret (e.g., a long alphanumeric string) but cannot be definitively classified as one?
- What happens when the same entity, device, or area name matches multiple nodes in the graph (ambiguous reference)?

## Requirements *(mandatory)*

### Functional Requirements

**Predefined safe query tools**

- **FR-001**: System MUST provide a search operation that returns matching ontology nodes for a given search term, with the number of returned results bounded by a configurable limit.
- **FR-002**: System MUST provide operations to retrieve structured context for an area, a device, and an entity by identifier or name.
- **FR-003**: System MUST provide an operation that returns automations related to a given entity.
- **FR-004**: System MUST provide a bounded, read-only query operation that accepts a query and rejects it before execution if it contains any data-modifying (create, update, delete) operation.
- **FR-005**: Every predefined query operation's result MUST include a target identifier, a result type, and warnings when related information is incomplete or unavailable.
- **FR-006**: Every predefined query operation's result MUST exclude secrets, tokens, passwords, and credentials, and MUST enforce a result count limit.
- **FR-007**: System MUST return a clear "not found" response when a requested entity, device, or area reference cannot be resolved, without executing an unbounded query.

**Assist ontology query intents**

- **FR-008**: System MUST support an Assist-invocable query for automation dependencies of a given entity, including a reason for the relationship where available.
- **FR-009**: System MUST support an Assist-invocable query for the contents of an area (devices, grouped by device where possible, with related entities).
- **FR-010**: System MUST support an Assist-invocable query for entity context, including device, area, domain, integration, semantic classifications, and direct dependencies where available.
- **FR-011**: System MUST support Assist-invocable queries for device context, impact analysis, and a general ontology search.
- **FR-012**: System MUST return a clear "not found" response through Assist when a referenced entity, device, or area cannot be resolved.

**Impact analysis**

- **FR-013**: System MUST provide entity-level impact analysis that returns related automations, scripts, scenes, dashboards (where available), and semantic assets (where available).
- **FR-014**: System MUST provide device-level impact analysis that aggregates all of a device's exposed entities, their downstream dependencies, and related semantic objects, using the device's current area relationship.
- **FR-015**: System MUST provide area-level impact analysis that returns affected devices, affected entities, and related automations, scripts, scenes, and dashboards where available.
- **FR-016**: System MUST return an empty result with a clear explanation when impact analysis finds no known dependencies, rather than an error.
- **FR-017**: System MUST return a "not found" response when the target entity, device, or area of an impact analysis request cannot be resolved.
- **FR-018**: System MUST bound impact analysis traversal depth and result count so that analysis remains responsive on graphs containing thousands of nodes.

**Local AI context export**

- **FR-019**: System MUST support exporting structured JSON context for an area, entity, device, automation, and impact scope, and a whole-home summary export.
- **FR-020**: System MUST exclude access tokens, passwords, IP credentials, secrets, and other sensitive configuration values from every exported context document.
- **FR-021**: Area and whole-home context exports MUST include devices, entities, automations, semantic assets, and validation findings where that information is available.
- **FR-022**: Entity, device, and automation context exports MUST include direct graph relationships for the target.

**MCP-compatible local endpoint**

- **FR-023**: System MUST NOT expose an MCP-compatible endpoint unless the user has explicitly enabled MCP support; it MUST remain disabled by default on install and upgrade.
- **FR-024**: When enabled, the MCP endpoint MUST bind locally only and MUST NOT be reachable from outside the local host/network boundary the user configures.
- **FR-025**: The MCP endpoint MUST expose only read-only ontology tools in this release: search, entity context, area context, device context, automation dependencies, impact analysis, bounded read-only query, and context export.
- **FR-026**: The MCP endpoint MUST reject any write/mutation request from a connected client and MUST record the rejected attempt in diagnostics without including credentials.
- **FR-027**: The MCP endpoint MUST apply the same redaction and result-limit rules as the predefined query tools and context export to all responses.
- **FR-034**: The MCP endpoint MUST require a client to present a generated local access token before accepting any tool invocation, in addition to local-only network binding; requests without a valid token MUST be rejected and recorded in diagnostics.

**Audit and diagnostics**

- **FR-028**: System MUST record diagnostic metadata for each Assist ontology query and each MCP tool invocation, including request type, requested tool, result status, result count, error category (when applicable), and timestamp.
- **FR-029**: System MUST NOT record secrets or full user prompts/queries in diagnostic metadata by default.
- **FR-030**: System MUST record rejected write attempts from MCP clients as a distinct diagnostic entry, including the rejected operation type but excluding credentials.
- **FR-035**: Diagnostic and audit records for Assist queries, MCP tool invocations, and rejected write/authentication attempts MUST be stored using the existing Home Assistant diagnostics/logging mechanism; this capability MUST NOT introduce new Memgraph node labels, relationships, or a schema version bump.
- **FR-036**: Diagnostic and audit records MUST be automatically pruned after a fixed retention window of 30 days rather than retained indefinitely.

**Non-functional**

- **FR-031**: All v3 capabilities (Assist intents, query tools, impact analysis, context export, MCP endpoint) MUST function without any cloud service dependency; all ontology data MUST remain on the local network/host.
- **FR-032**: System MUST continue to operate (Assist intents, impact analysis, context export) when an external local AI runtime referenced by the user's own tooling is unavailable, and MUST NOT fail Home Assistant startup because of it.
- **FR-033**: System MUST NOT allow autonomous or unattended write/change execution to Home Assistant or the ontology graph through any v3 access path (Assist, MCP, query tools).

### Key Entities *(include if feature involves data)*

Note: per clarification, these are non-graph diagnostic/log concepts held in the existing Home Assistant diagnostics mechanism — none of them are new Memgraph node labels, and v3 does not bump the ontology schema version.

- **ImpactAnalysis**: A single impact-analysis request/result for a target entity, device, or area, captured as a diagnostic record; references the analyzed target and the automations, scripts, scenes, or dashboards found as dependencies.
- **ContextExport**: A diagnostic record of a generated local-AI context export for an area, device, or entity; tracks what export type ran and when, and excludes sensitive values.
- **AssistQuery**: A single Home Assistant Assist ontology query event, used for diagnostics; stores redacted metadata about the query intent and outcome, not the raw user utterance. Pruned after 30 days.
- **AgentQuery / McpClient**: A query made by an external agent through the MCP endpoint, and the connecting client's identity, used for diagnostics and to enforce read-only, token-authenticated access; stores redacted metadata about the tool invoked and outcome, not credentials or tokens. Pruned after 30 days.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can get an answer to a supported ontology question through Assist (automation dependency, area contents, or entity context) in a single conversational turn, without needing to open a dashboard or write a query.
- **SC-002**: 100% of exported context documents and diagnostic records contain zero secrets, tokens, passwords, or credentials when audited against a test dataset containing known sensitive values.
- **SC-003**: 100% of fresh installs and upgrades have the MCP endpoint disabled until the user explicitly enables it.
- **SC-004**: 100% of write/mutation attempts made through the MCP endpoint or the bounded read-only query tool are rejected before any data changes, across a representative test suite of write-attempt patterns.
- **SC-005**: Impact analysis for an entity, device, or area, and any predefined query-tool call, returns a result (including "no dependencies found" or "not found") within 3 seconds on a graph containing several thousand nodes, without degrading Home Assistant's own responsiveness.
- **SC-006**: 100% of unresolved entity/device/area references across Assist, MCP, and query tools return a clear "not found" response rather than an error or an unbounded query.
- **SC-007**: All v3 capabilities remain fully operational (excluding any user-provided external AI runtime features) when no external AI runtime is reachable, with zero Home Assistant startup failures attributable to v3.

## Assumptions

- Assist, MCP, and the predefined query tools all share the same underlying safe query/impact-analysis/export capabilities; they are different access channels over the same bounded operations, not separate implementations of ontology logic.
- Reasonable default numeric bounds (result count limits and graph traversal depth) will be applied to search, impact analysis, and read-only queries; exact default values are an implementation decision made during planning, not a scoping concern for this specification.
- "Local-only binding" for the MCP endpoint means the endpoint is reachable only from the local host or local network the user configures, consistent with the existing local-first design of v1/v2; it does not require a specific transport or protocol choice to be fixed at the specification stage. It is additionally protected by a required local access token per FR-034.
- Entity/device/area name resolution for Assist and MCP reuses the existing entity/device/area registry and graph data already established by v1/v2; no new naming or aliasing system is introduced by v3.
- The exact mechanism for generating, storing, and rotating the MCP local access token (FR-034) is an implementation decision made during planning, not a scoping concern for this specification.
- The "external local AI runtime" referenced in the business goal is entirely outside this integration's control and responsibility; this specification only covers what the ontology integration exposes (context, tools), not any AI model behavior.
- Semantic assets referenced in impact analysis and context export are those already produced by the v2 semantic classification capability; v3 does not introduce new semantic classification types.
