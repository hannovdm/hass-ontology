# Implementation Plan: Home Assistant Ontology Integration v3

**Branch**: `003-assist-mcp-v3` | **Date**: 2026-08-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-assist-mcp-v3/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command; its definition describes the execution workflow.

## Summary

Extend the existing Home Assistant Ontology Integration (`custom_components/ontology`, v1+v2) with consumer-facing access to the ontology graph already built by v1/v2: a shared set of predefined, bounded, safe query/impact-analysis/context-export functions; Home Assistant Assist intents that let users ask natural-language ontology questions through the default (non-LLM) conversation agent; entity/device/area impact analysis; an allow-listed local-AI context export; an opt-in, local-only, token-authenticated MCP-compatible read-only endpoint; and redacted, time-pruned diagnostics/audit records for all agent access. Per clarification, none of this introduces new Memgraph node labels, relationships, or a schema version bump — every new capability is a read path over the existing v1/v2 graph, delivered as new modules inside the existing `custom_components/ontology` package, reusing v1's `MemgraphClient`/coordinator serialization and v2's `query_service.py` safety validator and `redact.py` helpers.

## Technical Context

**Language/Version**: Python 3.13 (unchanged from v1/v2 — the Python version bundled with the current Home Assistant core release; local dev/test tooling remains relaxed to `>=3.11` per `pyproject.toml`).

**Primary Dependencies**: Existing `homeassistant` core custom-integration APIs (config entries, options flow, `DataUpdateCoordinator`, diagnostics, repairs, `homeassistant.helpers.storage.Store`) and the existing `neo4j>=5.0` Bolt driver (unchanged — all new impact-analysis/context-export/query-tool Cypher reuses `memgraph_client.py`). New for v3, but already part of Home Assistant core (no new PyPI dependency): `homeassistant.helpers.intent` (Assist `IntentHandler` registration) plus a bundled `intents/en.yaml` sentence file (research.md §1); `homeassistant.components.http` (`HomeAssistantView`) to mount the opt-in local MCP endpoint on HA's existing web server instead of a second port (research.md §2). No `mcp` SDK or ASGI server dependency is added — the MCP transport is a minimal hand-rolled JSON-RPC-over-HTTP handler (research.md §2).

**Storage**: Memgraph (unchanged — external, locally-hosted graph database reached over Bolt; v3 adds zero new labels/relationships/schema-version bump per Clarifications). New: a small local `homeassistant.helpers.storage.Store`-backed JSON file per config entry holding the Assist/MCP diagnostic-and-audit log (redacted metadata only, pruned after 30 days, research.md §4) and the generated MCP local access token (research.md §3) — both are Home Assistant local storage, not Memgraph, consistent with FR-035.

**Testing**: Unchanged `pytest` + `pytest-asyncio` + `pytest-homeassistant-custom-component` + `testcontainers-python` (real Memgraph container) stack, extended with: contract tests for the new services (`ontology.search`, `ontology.area_context`, `ontology.device_context`, `ontology.entity_context`, `ontology.automation_dependencies`, `ontology.impact_analysis`, `ontology.export_context`) and the new MCP HTTP endpoint (`initialize`/`tools/list`/`tools/call` request/response shapes, auth-token rejection, write-rejection); unit tests for each Assist `IntentHandler` (mocked graph), the allow-list context-export field projections (per node/export type), MCP token generation/validation, and the audit-log append/prune logic (30-day retention, FR-036); integration tests (real Memgraph) for entity/device/area impact analysis correctness, context export end-to-end (zero secrets, SC-002), Assist intent "not found" handling (SC-006), MCP end-to-end tool-call round trip with and without a valid token, audit record lifecycle across the 30-day window, and impact-analysis/query-tool response time against a several-thousand-node fixture graph (SC-005, <3s). Windows dev runs continue to use `.\scripts\test-windows.ps1` (repo memory: `windows-test-environment.md`).

**Target Platform**: Unchanged — Home Assistant OS/Supervised/Core, deployed as the `custom_components/ontology` integration; primary reference host is an 8 GB x86_64 Home Assistant machine reaching a separate local Memgraph container over Bolt. The MCP endpoint, when enabled, is served from HA's own HTTP server (same host/port as the HA frontend), not a standalone process.

**Project Type**: Single project — v3 remains a Home Assistant custom integration. Assist intents, the MCP endpoint, impact analysis, and context export are all delivered inside the same `custom_components/ontology` package rather than as a separate frontend/backend/service deployable.

**Performance Goals**: Impact analysis (entity/device/area) and every predefined query-tool call return a result — including "no dependencies found" or "not found" — within 3 seconds on a graph containing several thousand nodes, without degrading Home Assistant's own responsiveness (SC-005); MCP tool-call dispatch and Assist intent resolution add no material overhead beyond the underlying bounded Cypher call.

**Constraints**: Zero new Memgraph node labels, relationship types, or `SCHEMA_VERSION` bump (Clarifications, FR-035); the bounded read-only query operation (reusing v2's `query_service.py`) must reject 100% of write-intent Cypher before execution (SC-004, unchanged from v2 SC-003); every predefined query/impact-analysis/context-export result must exclude secrets, tokens, passwords, and credentials (FR-006, FR-020, SC-002) using an **allow-list** field-projection model for context export specifically (Constitution "Security and Privacy Requirements" — distinct from the existing block-list `redact.py` used for diagnostics/config); the MCP endpoint MUST remain disabled by default (FR-023, SC-003), MUST bind/operate local-only (FR-024), and MUST require a generated local access token before any tool call (FR-034); MCP write/mutation attempts and unauthenticated requests MUST be rejected and recorded in diagnostics (FR-026, FR-030); Assist/MCP diagnostic and audit records MUST NOT include secrets or full user prompts/queries (FR-029) and MUST be automatically pruned after a fixed 30-day retention window (FR-036); all v3 capability must keep functioning with zero Home Assistant startup failures when no external local AI runtime is reachable (FR-032, SC-007).

**Scale/Scope**: Same graph scale as v2 (up to several thousand total nodes including v1 metadata and v2 semantic/validation/dashboard data); single config entry (single Memgraph target) per Home Assistant instance, unchanged from v1/v2; the MCP endpoint serves a single local access token per config entry (no multi-client/multi-token management in this release, per Assumptions).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. HA Native Integration First | PASS | Assist intents use `homeassistant.helpers.intent` + a bundled `intents/en.yaml` sentence file (native Assist mechanism, research.md §1); the MCP endpoint is a `HomeAssistantView` mounted on HA's existing HTTP server (research.md §2), not a standalone process/port; new query/impact-analysis/export capability is exposed as config-entry-scoped HA services, matching v1/v2's pattern. |
| II. Local-First & Privacy-Preserving | PASS | No cloud dependency introduced (FR-031); Assist intents work with HA's default (non-LLM) conversation agent, so no external/cloud conversation agent is required (research.md §1); the MCP endpoint is opt-in, disabled by default (FR-023), local-only (FR-024), and token-gated (FR-034); context export uses an allow-list projection so unknown/future node fields can never leak by default (Security and Privacy Requirements). |
| III. Memgraph & Cypher Are the Graph Foundation | PASS | All new reads (search, area/device/entity context, automation dependencies, impact analysis) go through the existing `neo4j` Bolt client against Memgraph, reusing v2's `query_service.py` safety validator for the bounded read-only query tool; no second graph database or query language is introduced. |
| IV. Asynchronous, Non-Blocking Runtime | PASS | Intent handlers, MCP tool dispatch, and the new services are async and reuse v1's coordinator-serialized Memgraph client; the MCP HTTP view and audit-log `Store` writes are non-blocking and do not hold the coordinator's single-flight lock (they are pure reads plus local JSON-file appends). |
| V. Generated/Inferred/User Data Separated | N/A (this feature) | v3 introduces no new graph writes or `source`-tagged data — it is a pure read/query/diagnostics layer over data v1/v2 already write and tag. |
| VI. Schema Versioning & Idempotent Migration | PASS | Per Clarifications, v3 adds zero new Memgraph labels/relationships; `SCHEMA_VERSION` stays unchanged (no bump) and no migration is required. |
| VII. Tests Before Confident Implementation | PASS | Test plan (Technical Context, above) covers every new capability: predefined query tools, Assist intents (including not-found handling), entity/device/area impact analysis, allow-list context export (zero-secret audit), MCP endpoint auth/write-rejection/tool-call contract, and audit-log append/prune lifecycle. |
| VIII. Observable, Diagnosable, Repairable by Design | PASS | `diagnostics.py` is extended with a redacted summary of recent Assist/MCP audit activity (counts by tool/status, no prompts/secrets); no new sensor/button entities are mandated by the spec, so none are speculatively added, consistent with v2's precedent. |
| IX. Small, Incremental Delivery Over Big-Bang Features | PASS | User Story priorities (P1: predefined query tools; P2: Assist; P3-P5: entity/device/area impact analysis; P6: context export; P7: MCP endpoint; P8: audit/diagnostics) allow each capability to ship and be verified independently, and P1's shared query/impact/export functions are a prerequisite every later story reuses rather than reimplementing. |
| X. Explicit Safety Boundaries for AI and Query Surfaces | PASS | The MCP endpoint exposes read-only tools only (FR-025), rejects any write-intent request via the same deny-list validator as v2's `ontology.query` (FR-026), is disabled by default (FR-023), and requires a local access token (FR-034); Assist intents and context export never expose raw Cypher execution to the end user or an AI runtime; no v3 access path can trigger autonomous/unattended writes to HA or Memgraph (FR-033). |

No violations identified; Complexity Tracking section is not required.

**Post-Phase-1 re-check**: The completed Phase 1 artifacts ([data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)) were reviewed against the table above after design — the shared query/impact-analysis/export function contracts, the MCP tool/auth contract, the intent/sentence contract, and the audit-record lifecycle all match the Constitution Check gates above with no new violations introduced.

## Project Structure

### Documentation (this feature)

```text
specs/003-assist-mcp-v3/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
custom_components/
└── ontology/
    ├── __init__.py            # EXTEND: register new services, conditional MCP view, intents, audit pruning
    ├── manifest.json          # unchanged (no new PyPI requirement)
    ├── config_flow.py         # EXTEND: options-flow toggle for MCP support (default disabled, FR-023)
    ├── const.py                # EXTEND: new services/intents, MCP option/token keys, retention constants
    ├── coordinator.py          # unchanged (v3 reads do not require coordinator serialization)
    ├── memgraph_client.py      # unchanged (reused as-is by all new modules)
    ├── query_service.py        # unchanged (v2 read-only safety validator, reused by query_tools.py)
    ├── query_tools.py          # NEW: shared search/area/device/entity/automation-dependencies functions (US1)
    ├── impact_analysis.py      # NEW: entity/device/area impact-analysis traversal + aggregation (US3-US5)
    ├── context_export.py       # NEW: allow-list JSON context export (area/entity/device/automation/whole-home) (US6)
    ├── intent_handlers.py      # NEW: Assist `IntentHandler` registration + response building (US2)
    ├── intents/
    │   └── en.yaml              # NEW: bundled Assist sentence definitions for the new intents (US2)
    ├── mcp_server.py            # NEW: opt-in local-only, token-authenticated MCP HTTP view (US7)
    ├── agent_audit.py           # NEW: redacted Assist/MCP diagnostic-and-audit log, 30-day pruning (US8)
    ├── websocket_api.py         # unchanged (v2 explorer backend API, not reused by v3 to limit diff risk)
    ├── graph_builder.py         # unchanged
    ├── semantic_classifier.py   # unchanged
    ├── overrides.py             # unchanged
    ├── validation.py            # unchanged
    ├── dashboard_sync.py        # unchanged
    ├── event_listener.py        # unchanged
    ├── redact.py                # unchanged (block-list redaction, still used by diagnostics/config; NOT used
    │                             #   by context_export.py, which uses an allow-list projection instead)
    ├── repairs.py                # unchanged
    ├── services.yaml             # EXTEND: search, area_context, device_context, entity_context,
    │                              #   automation_dependencies, impact_analysis, export_context
    ├── sensor.py                 # unchanged
    ├── button.py                 # unchanged
    ├── diagnostics.py            # EXTEND: redacted Assist/MCP audit summary (counts by tool/status)
    ├── strings.json              # EXTEND: new service/field/options-flow strings
    └── translations/
        └── en.json                # EXTEND: mirrors strings.json additions

tests/
├── contract/
│   ├── test_services_contract.py     # EXTEND: new query/impact-analysis/export services
│   └── test_mcp_server_contract.py   # NEW: initialize/tools-list/tools-call request/response shapes
├── integration/
│   ├── test_impact_analysis_entity.py     # NEW
│   ├── test_impact_analysis_device.py     # NEW
│   ├── test_impact_analysis_area.py       # NEW
│   ├── test_context_export_redaction.py   # NEW (SC-002: zero secrets)
│   ├── test_assist_intent_not_found.py    # NEW (SC-006)
│   ├── test_mcp_endpoint_e2e.py           # NEW (token auth, write-rejection, tool call)
│   ├── test_agent_audit_lifecycle.py      # NEW (append + 30-day prune, FR-036)
│   └── test_query_tools_performance.py    # NEW (SC-005: <3s on several-thousand-node fixture)
└── unit/
    ├── test_query_tools.py        # NEW
    ├── test_impact_analysis.py    # NEW
    ├── test_context_export.py     # NEW (allow-list field projections per export type)
    ├── test_intent_handlers.py    # NEW
    ├── test_mcp_server_auth.py    # NEW (token validation, local-binding guard, write-intent rejection)
    └── test_agent_audit.py        # NEW (redaction, pruning logic)
```

**Structure Decision**: Single project — v3 extends the existing repository-mandated `custom_components/ontology/` layout (per the constitution's Repository Standards) rather than introducing a separate frontend/backend split or a second process/port. All new capability (query tools, impact analysis, context export, Assist intents, the MCP endpoint, and audit logging) is delivered as new, single-responsibility modules inside the same package; the `tests/` tree keeps the existing contract/integration/unit split with new files per new module.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No Constitution Check violations were identified; this section is not applicable.
