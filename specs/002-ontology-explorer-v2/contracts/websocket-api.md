# Contract: Backend API (`websocket_api` commands)

Defines the backend API contract for the ontology explorer (User Story 3), per FR-031–FR-037. All commands are Home Assistant `websocket_api` commands (research.md §1), authenticated by the existing HA websocket connection — there is no separate HTTP endpoint. All commands are **read-only**: none of them accept or execute Cypher, and none of them mutate graph or Home Assistant state.

## `ontology/area_context`

- **Request fields**:

  | Field | Type | Required | Notes |
  |---|---|---|---|
  | `area_id` | string | yes | The Home Assistant area to look up. |

- **Response**: The `Area` node plus its linked `Device`/`Entity` nodes, their current states (where available), and any semantic classifications on those entities (FR-031).
- **Errors**: a clear "not found" result if `area_id` does not exist in the graph; never a raw Memgraph/driver error or stack trace (redacted per Constitution Principle II).

## `ontology/entity_context`

- **Request fields**:

  | Field | Type | Required | Notes |
  |---|---|---|---|
  | `entity_id` | string | yes | The Home Assistant entity to look up. |

- **Response**: The `Entity` node, its `Device`, its `Area`, its semantic classifications, its direct dependencies (e.g., automations/scenes/scripts referencing it), and any `Dashboard`/`DashboardCard` nodes that display it, where available (FR-032, User Story 3 Acceptance Scenario 2).
- **Errors**: a clear "not found" result if `entity_id` does not exist in the graph.

## `ontology/search`

- **Request fields**:

  | Field | Type | Required | Notes |
  |---|---|---|---|
  | `query` | string | yes | Free-text search term. |
  | `limit` | integer | no | Row cap for results; default 50, maximum matches the query-service cap (FR-018 family). |

- **Response**: Matching `Area`, `Device`, and `Entity` nodes by name/id substring match, each annotated with its type and a direct link/id usable by a follow-up `area_context`/`entity_context` call (FR-033).
- **Behavior**: Read-only; results are capped and streamed the same way as `ontology.query` (research.md §4) to bound response time (SC-005).

## Cross-cutting contract rules

- **Performance**: each command MUST respond within 2 seconds on a graph of up to 5,000 nodes on a typical 8 GB local host (SC-005, FR-037).
- **Security/Privacy**: no command response includes Memgraph connection credentials, HA long-lived tokens, or other secrets (FR-034; reuses `redact.py` conventions from v1).
- **Scope**: this API is scoped to the needs of area context, entity context, and search for the ontology explorer/sidebar panel — it is not a general-purpose public API and is not reachable outside the authenticated HA websocket connection (spec Assumptions).
- **Consumers**: the optional sidebar panel (User Story 8, `panel/ontology-panel.js`) is the primary consumer, but any authenticated HA frontend/websocket client (e.g., Developer Tools > WebSocket, custom Lovelace cards) may call these commands (FR-035, FR-036).
