# Contract: Services (`services.yaml`) — v3 additions

Extends [specs/002-ontology-explorer-v2/contracts/services.md](../../002-ontology-explorer-v2/contracts/services.md). All v1/v2 services (`ontology.rebuild`, `ontology.resync`, `ontology.sync_entity`, `ontology.query`, `ontology.refresh_semantics`, `ontology.export_overrides`, `ontology.import_overrides`, `ontology.validate`) are unchanged. `ontology.query` remains the sole bounded read-only Cypher tool (FR-004) and is reused as-is by v3's MCP/Assist/query-tool access channels — v3 adds no second Cypher-execution surface.

Every service below shares the common `ToolResult` shape (data-model.md §2): `{ "target": ..., "result_type": ..., "result": ..., "warnings": [...] }`, is read-only against Memgraph, excludes secrets/tokens/credentials from `result` (FR-006), and returns `result_type: "not_found"` with `result: null` instead of raising when the target cannot be resolved (FR-007).

## `ontology.search`

- **Fields**: `term` (string, required), `limit` (integer, optional; default/max per `DEFAULT_QUERY_LIMIT`/`MAX_QUERY_LIMIT`).
- **Behavior**: Returns ontology nodes whose name/identifier matches `term`, bounded by `limit` (FR-001).
- **Response**: `ToolResult` with `result_type: "search"`, `result: {"matches": [...]}`.

## `ontology.area_context`

- **Fields**: `area` (string, required — id or name).
- **Behavior**: Resolves the area and returns its devices, grouped entities, and known relationships (FR-002, FR-009).
- **Response**: `ToolResult` with `result_type: "area_context"`.

## `ontology.device_context`

- **Fields**: `device` (string, required — id or name).
- **Behavior**: Resolves the device and returns its exposed entities, area, and known relationships (FR-002, FR-011).
- **Response**: `ToolResult` with `result_type: "device_context"`.

## `ontology.entity_context`

- **Fields**: `entity` (string, required — entity_id or name).
- **Behavior**: Resolves the entity and returns device, area, domain, integration, semantic classifications, and direct dependencies where available (FR-002, FR-010).
- **Response**: `ToolResult` with `result_type: "entity_context"`.

## `ontology.automation_dependencies`

- **Fields**: `entity` (string, required — entity_id or name).
- **Behavior**: Returns automations related to the given entity, including a reason for the relationship where available (FR-003, FR-008).
- **Response**: `ToolResult` with `result_type: "automation_dependencies"`.

## `ontology.impact_analysis`

- **Fields**: `target_type` (string, required — one of `entity`, `device`, `area`), `target` (string, required — id or name).
- **Behavior**: Runs the bounded-depth impact-analysis traversal (research.md §5, data-model.md §3) for the given scope; returns an empty-but-present result with `has_dependencies: false` when nothing is found rather than an error (FR-013–FR-018).
- **Response**: `ToolResult` with `result_type: "impact_analysis"`, `result`: `ImpactAnalysisResult` (data-model.md §3).

## `ontology.export_context`

- **Fields**: `export_type` (string, required — one of `area`, `entity`, `device`, `automation`, `impact`, `whole_home`), `target` (string, optional — required for all types except `whole_home`).
- **Behavior**: Builds the allow-list JSON export document for the requested type (research.md §6, data-model.md §4); never includes access tokens, passwords, IP credentials, secrets, or other sensitive configuration (FR-019–FR-022, SC-002).
- **Response**: `ToolResult` with `result_type: "export_context"`, `result`: the export document (data-model.md §4).

## Safety boundary

None of the services above accept or execute arbitrary Cypher — they are fixed-shape, parameterized, bounded operations only (Constitution Principle X). `ontology.query` remains the only Cypher-accepting service, unchanged from v2 and still deny-list-validated.
