# Contract: Local MCP-compatible endpoint (`mcp_server.py`)

A `homeassistant.components.http.HomeAssistantView` mounted at `POST /api/ontology/mcp`, registered **only** when the user has enabled the MCP option (default disabled — FR-023, SC-003). Implements the subset of the MCP JSON-RPC-over-HTTP ("Streamable HTTP", non-streaming JSON response mode) protocol described in research.md §2.

## Enablement and binding

- **Disabled by default**: on fresh install and on upgrade from v1/v2, the view is not registered and the endpoint returns HTTP 404 (FR-023, SC-003).
- **Local-only**: when enabled, the view rejects (HTTP 403) any request whose `request.remote` is not loopback or within the local network range Home Assistant itself is configured to serve, as defense-in-depth alongside network-level local-only expectations (FR-024).
- **Token-gated**: every request MUST include a valid bearer token (the generated local access token, research.md §3) in an `Authorization: Bearer <token>` header. Missing/invalid tokens are rejected with HTTP 401 **and** recorded as an `AgentQueryRecord` with `event: "mcp_auth_rejected"` (FR-034, FR-030).

## `initialize`

- **Request**: standard MCP `initialize` JSON-RPC request.
- **Response**: capability negotiation response declaring `tools` support only (no `resources`, `prompts`, or streaming capability in this release).

## `tools/list`

- **Response**: the fixed list of read-only tools — `search`, `entity_context`, `area_context`, `device_context`, `automation_dependencies`, `impact_analysis`, `query` (bounded read-only Cypher), `export_context` — each with a JSON-schema `inputSchema` matching the corresponding service's fields (contracts/services.md) (FR-025).

## `tools/call`

- **Request**: `{"name": <tool name from tools/list>, "arguments": {...}}`.
- **Behavior**: Dispatches to the same shared functions used by services/Assist intents (research.md §7); applies the same redaction and result-limit rules as the predefined query tools and context export (FR-027). If `name` is `query` and the supplied Cypher contains any data-modifying keyword (reusing v2's `query_service.py` deny-list) — or any tool call otherwise resembles a write/mutation — the call is rejected before execution (FR-026, FR-033) and no data is modified.
- **Response on success**: `{"content": [{"type": "text", "text": <JSON-encoded ToolResult>}]}`.
- **Response on write-attempt rejection**: a JSON-RPC error response; the rejection is recorded as an `AgentQueryRecord` with `event: "mcp_write_rejected"`, including the rejected operation/tool name but excluding credentials (FR-026, FR-030, US7 Scenario 4, US8 Scenario 2).

## Diagnostics contract

Every successful `tools/call` records an `AgentQueryRecord` with `event: "mcp_tool_call"` (tool name, status, result count, timestamp — no secrets, no full request body, FR-028, FR-029, US8 Scenario 1).

## Ambiguous/mixed read+write requests (Edge Case)

Any Cypher payload submitted to the `query` tool that contains **both** read and write clauses is treated as a write attempt and rejected in full — the deny-list scan (reused from v2's `query_service.py`) triggers on the presence of any disallowed keyword regardless of any read clauses also present, so no partial/ambiguous execution is possible (FR-004, FR-026).
