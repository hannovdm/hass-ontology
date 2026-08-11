# Quickstart: Validating the Home Assistant Ontology Integration v3

This guide describes how to validate v3's Assist, MCP, impact-analysis, and local-AI-readiness capabilities end-to-end on top of an already-installed v1/v2 integration. It intentionally does not include implementation code — see [data-model.md](./data-model.md) for record/export shapes and [contracts/](./contracts/) for exact service/intent/MCP contracts.

## Prerequisites

- v1 (`specs/001-ha-ontology-integration`) and v2 (`specs/002-ontology-explorer-v2`) already installed, configured, and synced at least once.
- The updated `custom_components/ontology` (v3) copied over the existing installation, then Home Assistant restarted.
- Confirm `sensor.ontology_schema_version` is **unchanged** after the restart (v3 introduces no schema bump — FR-035) and `sensor.ontology_health` is healthy before proceeding.

## Scenario A — Predefined safe query tools (validates User Story 1)

1. From Developer Tools → Services, call `ontology.search` with a partial name. **Expected**: matching nodes are returned and the count does not exceed the configured limit (FR-001).
2. Call `ontology.area_context` with a known area. **Expected**: devices, entities, and known relationships for the area are returned (FR-002).
3. Call `ontology.automation_dependencies` with a known entity. **Expected**: related automations are returned (FR-003).
4. Call `ontology.query` (the existing v2 bounded read-only tool) with a write-intent Cypher query, e.g. `MATCH (e:Entity) SET e.hacked = true`. **Expected**: rejected before execution, no data modified (FR-004, SC-004).
5. Inspect any of the responses above. **Expected**: each includes a target identifier and a result type, and excludes any secret/token/password value (FR-005, FR-006).
6. Call `ontology.entity_context` with an entity identifier that does not exist. **Expected**: a clear "not found" result, no broad/unbounded query is executed (FR-007, SC-006).

## Scenario B — Ask Assist about the ontology (validates User Story 2)

1. Open the Assist conversation UI and ask: "what automations depend on `<a known entity's friendly name>`?". **Expected**: the entity resolves, related automations are listed, with a reason where available (FR-008, US2 Scenario 1).
2. Ask: "what devices are in `<a known area>`?". **Expected**: devices are returned, entities grouped by device where possible (FR-009, US2 Scenario 2).
3. Ask: "what is `<a known entity>` connected to?". **Expected**: device, area, domain, integration, semantic classifications, and dependencies are returned where available (FR-010, US2 Scenario 3).
4. Ask about an entity/device/area name that does not exist. **Expected**: a clear "not found" conversational response, not an error or a hang (FR-012, SC-006).

## Scenario C — Entity impact analysis (validates User Story 3)

1. Call `ontology.impact_analysis` with `target_type: entity` for an entity known to have automations/scripts/scenes/dashboards referencing it. **Expected**: all of those are returned, plus semantic assets where available (FR-013, US3 Scenario 1).
2. Repeat for an entity with no downstream dependencies. **Expected**: an empty dependency list with a clear "no known dependencies found" explanation, not an error (FR-016, US3 Scenario 3).
3. Repeat with a target entity id that does not exist. **Expected**: a clear "not found" response (FR-017).

## Scenario D — Device and area impact analysis (validates User Story 4, User Story 5)

1. Call `ontology.impact_analysis` with `target_type: device` for a device exposing multiple entities. **Expected**: all exposed entities, their downstream dependencies, and related semantic objects are aggregated (FR-014, US4 Scenario 1).
2. Move the device to a different area (via the HA device registry), resync, then repeat. **Expected**: the analysis reflects the device's current area relationship (FR-014, US4 Scenario 2).
3. Call `ontology.impact_analysis` with `target_type: area` for an area containing devices and entities. **Expected**: affected devices, affected entities, and related automations/scripts/scenes/dashboards are returned where available (FR-015, US5 Scenario 1).
4. Repeat for an area with no known devices/entities. **Expected**: an empty result with a clear explanation (FR-016, US5 Scenario 2).
5. Time each call in Scenarios C and D against a graph with several thousand nodes. **Expected**: every call returns within 3 seconds without degrading Home Assistant's own responsiveness (SC-005).

## Scenario E — Local AI context export (validates User Story 6)

1. Call `ontology.export_context` with `export_type: area` for a known area. **Expected**: a structured JSON document with devices, entities, automations, semantic assets, and validation findings where available (FR-019, FR-021, US6 Scenario 1).
2. Call `ontology.export_context` with `export_type: entity` for a known entity. **Expected**: a JSON document with direct graph relationships, excluding secrets/credentials (FR-019, FR-022, US6 Scenario 2).
3. Call `ontology.export_context` with `export_type: whole_home`. **Expected**: a compact JSON summary excluding secrets, tokens, credentials, and sensitive configuration (FR-019, US6 Scenario 3).
4. Inspect every export produced above against a known set of test sensitive values injected into the graph beforehand (e.g., a node property containing a fake token string). **Expected**: zero secrets/tokens/passwords/credentials appear in any export, 100% of the time (FR-020, SC-002, US6 Scenario 4).

## Scenario F — Local MCP-compatible endpoint (validates User Story 7)

1. On a fresh install/upgrade, without changing any option, attempt to reach the MCP endpoint (`POST /api/ontology/mcp`). **Expected**: HTTP 404 — no endpoint is exposed (FR-023, SC-003, US7 Scenario 2).
2. In the integration's options, enable MCP support. **Expected**: a local access token is generated and surfaced once via a persistent notification (research.md §3); the endpoint becomes reachable locally.
3. Using a local MCP client (or a raw HTTP client) with the generated token, call `initialize` then `tools/list`. **Expected**: only read-only tools are listed (FR-025).
4. Call `tools/call` for `entity_context` on a known entity. **Expected**: structured JSON context is returned (US7 Scenario 3).
5. Call `tools/call` for `query` with a write-intent Cypher payload. **Expected**: the request is rejected and the rejection is recorded in diagnostics (FR-026, US7 Scenario 4).
6. Repeat step 4 with an invalid/missing token. **Expected**: HTTP 401, no tool executes, the rejection is recorded in diagnostics (FR-034).
7. Repeat step 4 from a host outside the configured local network boundary (if testable in your environment). **Expected**: rejected as not locally-bound (FR-024).

## Scenario G — Audit and diagnostics for agent access (validates User Story 8)

1. After performing Scenarios B and F above, open the integration's diagnostics download. **Expected**: it includes redacted counts of Assist queries and MCP tool invocations (by tool/status), with no secrets or full prompts/utterances present (FR-028, FR-029, US8 Scenario 1 and 3).
2. Confirm the rejected write attempt from Scenario F step 5 appears as a distinct diagnostic entry (rejected operation type only, no credentials) (FR-030, US8 Scenario 2).
3. Wait past (or simulate) the 30-day retention window for a test record. **Expected**: the record is no longer present in diagnostics after the window elapses (FR-036).

## Scenario H — No external AI runtime required (validates FR-031, FR-032, SC-007)

1. With no external local LLM/AI runtime running anywhere on the network, restart Home Assistant with v3 installed. **Expected**: startup succeeds with zero failures attributable to v3 (SC-007).
2. Repeat Scenarios A–G above with no external AI runtime reachable. **Expected**: every capability (Assist intents, impact analysis, context export, MCP endpoint) continues to function normally — none of them depend on any external AI runtime being reachable (FR-031, FR-032).
