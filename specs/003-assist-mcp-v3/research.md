# Phase 0 Research: Home Assistant Ontology Integration v3

**Input**: [spec.md](./spec.md), [plan.md](./plan.md) Technical Context, [.specify/memory/constitution.md](../../.specify/memory/constitution.md)

This document resolves every technical unknown left open by the Technical Context and records the decision, rationale, and rejected alternatives for each, per the `/speckit.plan` Phase 0 workflow.

---

## §1. Assist ontology query intents

**Decision**: Implement each Assist-invocable query (automation dependencies, area contents, entity context, device context, impact analysis, general search) as a native Home Assistant **intent**: a `homeassistant.helpers.intent.IntentHandler` subclass registered via `intent.async_register(hass, handler)` in `intent_handlers.py`, paired with a bundled sentence file at `custom_components/ontology/intents/en.yaml` using the `hassil` sentence-template format HA core integrations already use for their own shipped intents (e.g. `todo`, `cover`). Home Assistant's default conversation agent auto-loads an integration's `intents/<language>.yaml` file when the integration is set up — no extra registration call is needed beyond defining the file and registering the matching handler.

**Rationale**: This works with HA's default, non-LLM, sentence-trigger conversation agent, which every Assist-enabled installation has out of the box. It requires no cloud service and no user-configured LLM conversation agent, keeping v3's Assist experience local-first by default (Constitution II, FR-031) and consistent with v1/v2's "no new required dependency" precedent.

**Alternatives considered**:
- *LLM Tool API* (`homeassistant.helpers.llm.Tool` registered via a custom `llm.API`): would let any LLM-backed conversation agent (and, incidentally, HA core's own `mcp_server` integration) call the same functions with more flexible natural-language matching. Rejected as the *primary* mechanism because it only activates for users who have configured an LLM conversation agent (e.g. OpenAI/Ollama/Google Generative AI), which is not guaranteed and is out of scope per the spec's Assumptions ("this specification only covers what the ontology integration exposes... not any AI model behavior"). Not added in v3 to avoid unrequested scope growth (Constitution IX); may be revisited in a future release if a dedicated user story asks for it.
- *Reusing HA core's built-in `mcp_server` integration* to expose intents automatically as MCP tools: rejected for the Assist access path specifically because it conflates two independent, differently-gated access channels (Assist is always available if Assist is enabled; the ontology MCP endpoint must default to disabled per FR-023) and because core's `mcp_server` uses long-lived-access-token/OAuth auth, not the config-entry-scoped local token this integration must generate/enforce itself (FR-034).

## §2. Local MCP-compatible endpoint transport

**Decision**: Mount the MCP endpoint as a `homeassistant.components.http.HomeAssistantView` (`mcp_server.py`), registered only when the user enables the MCP option (FR-023), served on HA's existing HTTP server (same host/port as the frontend) rather than a second process or port. The view implements a minimal, hand-rolled JSON-RPC-over-HTTP handler covering the subset of the MCP spec actually needed for v3: `initialize`, `tools/list`, and `tools/call`, returning a single JSON response per POST request (the MCP "Streamable HTTP" transport's non-streaming JSON response mode). No Server-Sent-Events streaming and no session resumability are implemented in this release.

**Rationale**: HA already runs an aiohttp-based HTTP server; mounting on it avoids a second listening port, a second TLS/reverse-proxy story, and an added ASGI server dependency — consistent with the 8 GB host Performance Requirements and Constitution I (HA-native). Every v3 MCP tool call is a quick, bounded read (SC-005: <3s), so a request/response JSON transport (no streaming) is sufficient; adding SSE/streaming support now would be speculative complexity with no current user story requiring it (Constitution IX).

**Alternatives considered**:
- *Official `mcp` Python SDK* (`mcp.server.Server` / `FastMCP`) running its own ASGI app (uvicorn) on a dedicated local port: gives spec-complete transport support (SSE, resumability) but adds a new PyPI dependency and a second local server process/port to manage inside an already-constrained 8 GB host, for capability (streaming, session resumability) no v3 user story needs. Rejected for this release; can be reconsidered if a future spec needs long-running/streaming MCP operations.
- *Reusing HA core's `mcp_server` integration*: see §1 — rejected because it cannot enforce this integration's own disabled-by-default toggle and generated local access token (FR-023, FR-034) independently of HA core's own MCP auth model.

## §3. MCP local access token generation and storage

**Decision**: Generate the local access token with `secrets.token_urlsafe(32)` the first time the user enables MCP support (config-entry options-flow toggle, default `False`), and persist it in a `homeassistant.helpers.storage.Store` file scoped to the config entry (`.storage/ontology_mcp_token_<entry_id>`). The token is never displayed in the UI/dashboard after initial generation; it is surfaced once via a Home Assistant persistent notification at generation time and can be regenerated on demand via a new `button.ontology_regenerate_mcp_token` control entity (consistent with Constitution VIII's existing button-entity pattern), which immediately invalidates the previous token. Diagnostics report only whether a token is configured (boolean), never the value — mirroring the existing `password`/secret non-exposure convention in `redact.py`/`diagnostics.py`.

**Rationale**: `Store` is the standard HA mechanism for small local JSON state (already how HA core stores its own auth tokens); it is local-only, requires no new dependency, and keeps the token out of the config entry's `options` dict (which diagnostics/exports partially serialize elsewhere in this integration, so keeping the token in a dedicated store avoids it ever being an accidental diagnostics field to remember to redact).

**Alternatives considered**: Storing the token directly in the config entry's `options`/`data` — rejected because it would require every future config-entry diagnostics/export code path to remember to exclude it, versus a dedicated store that is simply never read by diagnostics/export code at all.

## §4. Assist/MCP diagnostic and audit record storage + retention

**Decision**: Record every Assist ontology-query invocation, every MCP tool call, and every rejected MCP write/authentication attempt as a small redacted dict (request type, tool name, result status, result count, error category, timestamp — FR-028) appended to a bounded, `homeassistant.helpers.storage.Store`-backed JSON log (`agent_audit.py`), scoped per config entry. On every append, and additionally on the existing periodic sweep pattern already used for `FAILED_UPDATE_RETRY_INTERVAL_SECONDS` (`async_track_time_interval`), entries older than a fixed 30-day retention window are pruned (FR-036). `diagnostics.py` is extended to include a redacted summary (counts by tool/status) drawn from this log, never raw entries containing prompts.

**Rationale**: Per the Clarifications, these are explicitly non-graph diagnostic records — Memgraph must not gain a new label/relationship or a schema-version bump for this. HA's own `Store` helper is the natural local-storage mechanism already used elsewhere in HA core for bounded, versioned JSON state, and reusing the existing periodic-sweep pattern (`async_track_time_interval`) avoids introducing a second scheduling mechanism.

**Alternatives considered**: Using Home Assistant's built-in `logbook`/`recorder` for these events — rejected because those are general-purpose, long-retention HA subsystems not scoped to this integration, would be harder to guarantee a strict 30-day prune against, and would require additional recorder-specific integration code disproportionate to the need for a small, self-contained audit log.

## §5. Entity/device/area impact-analysis traversal bounding

**Decision**: Implement impact analysis (`impact_analysis.py`) as bounded-depth Cypher traversals from the target node, following `REFERENCES`, `CONTROLS`, `CLASSIFIED_AS`, `DISPLAYS_ENTITY`, `HAS_DEVICE`, and `HAS_ENTITY` relationships up to a small fixed hop limit (2 hops for entity-level; aggregated per-entity for device/area scopes), executed via `MemgraphClient.run_query_limited` with the existing `DEFAULT_QUERY_LIMIT`/`MAX_QUERY_LIMIT` constants (FR-018). Device-level impact analysis aggregates entity-level results across all of a device's currently-exposed entities (via the device's live `HAS_ENTITY` edges, so a device moved to a new area always reflects its current `HAS_AREA`/`HAS_DEVICE` relationship — Acceptance Scenario 2 of US4); area-level impact analysis aggregates device-level results across the area's current devices and directly-related entities.

**Rationale**: A small fixed hop limit plus the existing row-limit machinery is what makes SC-005's <3s target achievable on a several-thousand-node graph without introducing a new traversal-depth configuration surface; "current relationship" aggregation (rather than caching stale device/area membership) is what satisfies the device-moved and area-remodel acceptance scenarios (US4 Scenario 2) correctly by construction, with no extra invalidation logic needed.

**Alternatives considered**: An unbounded/variable-depth traversal — rejected outright, it directly conflicts with FR-018 and SC-005 and with the constitution's "Avoid unbounded traversals in services or diagnostics" standard.

## §6. Local AI context export redaction model

**Decision**: `context_export.py` builds every exported JSON document using an explicit **allow-list** field projection per node type (e.g. an `Entity` projection includes only `ha_id`, `name`, `domain`, `area_id`, `device_id`, `unit_of_measurement`, `device_class`, `source`; a `Device` projection includes only `ha_id`, `name`, `manufacturer`, `model`, `area_id`; and so on) rather than passing whole node dicts through the existing block-list `redact.py` helper.

**Rationale**: The constitution's Security and Privacy Requirements explicitly state "The integration must prefer allow-list export models over block-list export models for v3 AI context" — this is a hard constraint, not a style preference. An allow-list is also strictly stronger for SC-002 (100% of exported documents contain zero secrets/tokens/credentials): a never-anticipated future node property (e.g. a raw config value accidentally written into a node by a future v4 feature) cannot leak through an allow-list projection, whereas a block-list would need to be kept in lockstep with every future property added anywhere in the schema.

**Alternatives considered**: Reusing `redact.py`'s `redact_mapping` (block-list) for context export, matching how `diagnostics.py` already redacts — rejected specifically for context export because the constitution singles this export path out for the stricter allow-list model; `redact.py`'s block-list approach remains correct and unchanged for diagnostics/config redaction, which is a different, already-bounded surface (connection info only).

## §7. Predefined query tools as a shared, transport-agnostic layer

**Decision**: Implement `query_tools.py` (search, area/device/entity context, automation dependencies) as plain async functions operating on a `MemgraphClient`, independent of any calling transport. Home Assistant services (`ontology.search`, `ontology.area_context`, etc.), Assist intent handlers (§1), and the MCP endpoint (§2) all call the same functions and share one JSON-compatible result shape: `{"target": ..., "result_type": ..., "result": ..., "warnings": [...]}"` (FR-005). The existing v2 bounded read-only query service (`query_service.py`, `ontology.query`) is reused unchanged as the "bounded read-only query" tool required by FR-004/US1 — v3 does not reimplement Cypher-safety validation.

**Rationale**: This directly satisfies the spec's own Assumption ("Assist, MCP, and the predefined query tools... are different access channels over the same bounded operations, not separate implementations of ontology logic") and avoids triplicating query logic across three transports, which would otherwise triple the surface area needing FR-006/FR-020 redaction and result-limit review.

**Alternatives considered**: Extending v2's `websocket_api.py` handlers directly for v3's tool functions — rejected to keep the v2 explorer panel's backend API untouched (lower regression risk, Constitution IX) since it serves a different consumer (the frontend panel) with slightly different response shapes than FR-005 requires.

## §8. Options-flow default and MCP enable/disable

**Decision**: Add a single new options-flow boolean, `CONF_MCP_ENABLED` (default `False`), alongside the existing v2 `CONF_AUTO_CLASSIFY` option in `config_flow.py`. Enabling it triggers first-time token generation (§3) and registers the MCP `HomeAssistantView`; disabling it unregisters the view on next reload (HA views are registered per `async_setup_entry` call, so a config-entry reload after an options change is sufficient — the existing options-update-listener pattern in `__init__.py`/`coordinator.py` already triggers a reload on options change).

**Rationale**: A single boolean is the minimum surface needed to satisfy FR-023 (disabled by default) and SC-003 (100% of installs/upgrades start disabled); reusing the existing options-update-listener/reload pattern means no new lifecycle code is needed to react to the toggle.

**Alternatives considered**: A separate config entry/sub-entry just for MCP — rejected as disproportionate; a single option on the existing entry matches how `CONF_AUTO_CLASSIFY` was already added in v2.

## §9. Verifying SC-005 (<3s) and SC-007 (no startup failure without external AI)

**Decision**: `tests/integration/test_query_tools_performance.py` builds a fixture graph of several thousand nodes (reusing the same fixture-generation approach as v2's `test_websocket_api_performance.py`) and asserts every predefined query-tool call and every impact-analysis call completes in under 3 seconds. `tests/integration/test_first_run_unrelated_data.py`'s existing pattern (and a new startup test) confirms `async_setup_entry` never depends on reachability of any external local AI runtime — no v3 module imports or calls out to any AI runtime; the "external local AI runtime" referenced in the spec's business goal is entirely a consumer of context export/MCP output, never a dependency the integration calls into itself.

**Rationale**: Reusing v2's existing performance-test fixture pattern keeps the new tests consistent with established conventions; confirming no code path references an external AI runtime at all is the simplest possible way to satisfy FR-032/SC-007 by construction rather than by defensive error handling around a dependency that structurally does not exist.

**Alternatives considered**: None — this is a verification-only decision, not an architectural one.
