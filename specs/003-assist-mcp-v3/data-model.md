# Data Model: Home Assistant Ontology Integration v3

**Input**: [spec.md](./spec.md) Key Entities, [research.md](./research.md)

Per the Clarifications, v3 introduces **zero new Memgraph node labels, relationship types, or a `SCHEMA_VERSION` bump**. This document therefore has two parts: (1) the existing v1/v2 graph entities/relationships that v3's new read paths traverse (unchanged), and (2) the new **non-graph** Python-level record shapes v3 introduces for diagnostics/audit, context export, and impact-analysis results.

## 1. Existing graph entities traversed by v3 (no changes)

All read-only; sourced from `custom_components/ontology/const.py`. No new `LABEL_*`/`REL_*` constants are added by this feature.

| Label | Traversed by |
|---|---|
| `Home`, `Floor`, `Area` | area context, area impact analysis, whole-home context export |
| `Device` | device context, device impact analysis |
| `Entity` | entity context, entity impact analysis, automation dependencies, search |
| `Domain`, `Integration`, `Label` | entity context ("domain, integration" per FR-010) |
| `Automation`, `Scene`, `Script` | impact analysis (US3-US5), automation-dependencies tool (FR-003, FR-008) |
| `Dashboard`, `DashboardCard` | impact analysis "dashboards (where available)" (FR-013/FR-014/FR-015), whole-home/area context export |
| `SemanticType` + the 8 semantic asset labels (`GasCylinder`, `Vehicle`, `EnergyAsset`, `SecurityDevice`, `OccupancySensor`, `ClimateDevice`, `NetworkDevice`, `BatteryPoweredDevice`) | impact analysis "semantic assets (where available)" (FR-013/FR-014), context export |
| `ValidationFinding` | area/whole-home context export ("validation findings where available", FR-021) |

| Relationship | Traversed by |
|---|---|
| `HAS_AREA`, `HAS_FLOOR`, `ON_FLOOR`, `HAS_DEVICE`, `HAS_ENTITY` | area/device context and impact analysis, "current area relationship" (FR-014 Scenario 2) |
| `IN_DOMAIN`, `PROVIDED_BY`, `HAS_LABEL` | entity context (domain/integration/labels, FR-010) |
| `REFERENCES`, `CONTROLS` | automation-dependency resolution and entity/device/area impact analysis (automations/scripts/scenes that reference or control the target) |
| `CLASSIFIED_AS` | semantic-asset lookups for impact analysis and context export |
| `DISPLAYS_ENTITY`, `CONTAINS_CARD` | dashboard-dependency lookups for impact analysis and context export |
| `MEASURED_BY`, `LOCATED_IN`, `OBSERVED_BY` | supplementary semantic-asset relationships surfaced when present in impact analysis/context export ("where available") |

No new labels/relationships are added; no existing node/relationship gains a new property as a result of this feature (v3 is read-only against the graph).

## 2. Shared tool-result shape (Python-level, not persisted)

Every predefined query tool (`query_tools.py`), impact-analysis call (`impact_analysis.py`), Assist intent response, and MCP tool-call response is built from one common, transport-agnostic result shape (FR-005, FR-006):

```text
ToolResult
├── target: str                  # resolved identifier of the area/device/entity/automation queried, or the raw
│                                 #   search term; REQUIRED
├── result_type: str              # one of: "search" | "area_context" | "device_context" | "entity_context" |
│                                 #   "automation_dependencies" | "impact_analysis" | "query" | "not_found"
├── result: dict | list | None    # the bounded payload (already redacted); None when result_type == "not_found"
└── warnings: list[str]           # e.g. "relationship X unavailable", "result truncated to N rows"; MAY be empty
```

**Validation rules**:
- `target` and `result_type` are always present, even for a "not found" result (FR-007, FR-012, FR-017, SC-006).
- `result` and any nested dict/list MUST NOT contain any key matching the existing `SECRET_KEYS`/`_SECRET_PATTERN` definitions in `redact.py`, nor any raw access token/password/credential value (FR-006).
- `result` size is always bounded by `DEFAULT_QUERY_LIMIT`/`MAX_QUERY_LIMIT` (existing v2 constants) or an equivalent impact-analysis-specific limit (FR-018).

## 3. Impact-analysis result shape

Extends `ToolResult` (`result_type == "impact_analysis"`); `result` is:

```text
ImpactAnalysisResult
├── scope: str                       # "entity" | "device" | "area"
├── affected_entities: list[str]     # device/area scope only (FR-014, FR-015)
├── affected_devices: list[str]      # area scope only (FR-015)
├── automations: list[dict]          # each: {entity_id/automation_id, name, reason?}
├── scripts: list[dict]
├── scenes: list[dict]
├── dashboards: list[dict]           # where available (FR-013-FR-015)
├── semantic_assets: list[dict]      # where available (FR-013, FR-014)
└── has_dependencies: bool           # False → "no known dependencies found" explanation (FR-016)
```

`has_dependencies == False` MUST still be returned as a normal (not error) result with all list fields present but empty (US3 Acceptance Scenario 3, FR-016).

## 4. Context export documents (allow-list projections, not persisted as records)

Per research.md §6, every export uses an explicit allow-list of fields per node type — this table is the authoritative allow-list (extending it requires updating both `context_export.py` and this table):

| Export node type | Allow-listed fields |
|---|---|
| `Area` | `ha_id`, `name`, `floor_id` |
| `Device` | `ha_id`, `name`, `manufacturer`, `model`, `area_id` |
| `Entity` | `ha_id`, `name`, `domain`, `device_class`, `unit_of_measurement`, `area_id`, `device_id`, `source` |
| `Automation` | `ha_id`, `name`, `mode` |
| `Scene` / `Script` | `ha_id`, `name` |
| `SemanticType` asset labels | `ha_id`, `asset_type`, `entity_id` |
| `ValidationFinding` | `finding_type`, `severity`, `target_id`, `message` |
| `Dashboard` / `DashboardCard` | `ha_id`, `title` |

Fields not listed here (including any field containing "token", "password", "secret", "key", "credential", or a bare IP/host+credential pair) are never included, regardless of whether they exist on the underlying node (FR-020, SC-002).

**Export document top-level shapes**:

```text
AreaContextExport / WholeHomeContextExport
├── devices: list[Device projection]
├── entities: list[Entity projection]
├── automations: list[Automation projection]
├── semantic_assets: list[SemanticType projection]
└── validation_findings: list[ValidationFinding projection]   # FR-021

EntityContextExport / DeviceContextExport / AutomationContextExport
└── relationships: list[{type: str, target: <allow-listed projection>}]   # FR-022 "direct graph relationships"

ImpactContextExport
└── <ImpactAnalysisResult, §3, with all nested dicts passed through the allow-list projections above>
```

## 5. Diagnostic/audit records (non-graph, `homeassistant.helpers.storage.Store`)

Per Clarifications and FR-035, these are **not** Memgraph nodes. Each is a JSON-serializable dict appended to the per-config-entry audit log (`agent_audit.py`), pruned after 30 days (FR-036).

### AssistQueryRecord (FR-028, FR-029)

```text
AssistQueryRecord
├── event: "assist_query"
├── intent: str              # e.g. "OntologyAutomationDependencies" — the intent name, not the raw utterance
├── status: str               # "resolved" | "not_found" | "error"
├── result_count: int
├── error_category: str | None
└── timestamp: str            # ISO-8601 UTC
```
No raw user utterance/prompt is ever stored (FR-029).

### AgentQueryRecord (MCP tool invocation; FR-028-FR-030)

```text
AgentQueryRecord
├── event: "mcp_tool_call" | "mcp_write_rejected" | "mcp_auth_rejected"
├── tool: str | None                # tool name for mcp_tool_call/mcp_write_rejected; None for auth failures
├── client_id: str                  # opaque per-connection identifier (not a credential), for correlation only
├── status: str                     # "ok" | "rejected" | "error"
├── result_count: int | None
├── error_category: str | None      # e.g. "write_intent_detected", "invalid_token"
└── timestamp: str
```
Never includes the token value, request body, or any credential (FR-030).

### ImpactAnalysisRecord / ContextExportRecord (audit trail, not the result payload itself)

```text
ImpactAnalysisRecord
├── event: "impact_analysis"
├── scope: "entity" | "device" | "area"
├── status: "ok" | "not_found" | "error"
├── has_dependencies: bool | None
└── timestamp: str

ContextExportRecord
├── event: "context_export"
├── export_type: "area" | "entity" | "device" | "automation" | "impact" | "whole_home"
├── status: "ok" | "not_found" | "error"
└── timestamp: str
```

**Retention**: every record above carries a `timestamp`; `agent_audit.py` prunes any record with `timestamp` older than 30 days, both on each append and via the existing periodic-sweep pattern (research.md §4). No record type is retained indefinitely (FR-036).

### McpAccessToken (not an audit record — the single per-entry credential)

```text
McpAccessToken
├── entry_id: str
├── token: str            # secrets.token_urlsafe(32); never logged, never included in diagnostics payload
└── created_at: str
```
Stored in its own `Store` file (research.md §3), separate from the audit log, so it can never accidentally appear in an audit-log/diagnostics dump.
