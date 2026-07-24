# Contract: Services (`services.yaml`) — v2 additions

Extends [specs/001-ha-ontology-integration/contracts/services.md](../001-ha-ontology-integration/contracts/services.md). The v1 services (`ontology.rebuild`, `ontology.resync`, `ontology.sync_entity`) are unchanged. `ontology.validate` is extended in place (behavior below supersedes v1's description). All services below join the same single-flight serialization group as v1's services (FR-013a) — none run concurrently with each other, with rebuild/resync, or with an in-flight incremental update.

## `ontology.query`

- **Fields**:

  | Field | Type | Required | Notes |
  |---|---|---|---|
  | `cypher` | string | yes | A read-only Cypher query. |
  | `parameters` | mapping | no | Named query parameters (never string-interpolated into `cypher`). |
  | `limit` | integer | no | Row cap for this call; default 100, maximum 1000 (FR-018, FR-021). |

- **Behavior**: Validates `cypher` with the tokenized safety scanner (research.md §3) before execution; rejects the call (no execution) if any disallowed keyword (`CREATE`, `MERGE`, `DELETE`, `DETACH`, `SET`, `REMOVE`, `DROP`, `LOAD CSV`, `CALL dbms`, `CALL mg`, `CALL algo`) is found (FR-019). Executes the query read-only against Memgraph, streaming results and stopping at `limit` rows (research.md §4).
- **Response**: `{ "rows": [...], "truncated": <bool>, "row_count": <int> }` on success; a clear rejection error (no partial execution) when the safety check fails (FR-020).
- **Errors**: rejected query (safety violation), Memgraph timeout/unavailable (degrades per Constitution Principle IV — does not crash HA).

## `ontology.refresh_semantics`

- **Fields**:

  | Field | Type | Required | Notes |
  |---|---|---|---|
  | `entity_id` | string | no | If provided, re-run classification for only this entity; if omitted, re-run for all entities (FR-023, FR-024). |

- **Behavior**: Re-evaluates the classification rule table (research.md §5) for the given scope, creating/updating `source = "inferred"` semantic nodes/relationships via `MERGE`. Never creates, modifies, or deletes any `source = "user"` node/relationship (FR-025).
- **Response**: none (fire-and-forget); result observable via diagnostics (classification counts) and the graph itself.

## `ontology.export_overrides`

- **Fields**: none.
- **Behavior**: Reads every `source = "user"` relationship in the graph and returns them as the versioned JSON payload described in research.md §7 (FR-026). Excludes any Memgraph credentials or HA secrets.
- **Response**: `{ "version": <int>, "exported_at": <iso8601>, "overrides": [...] }`.

## `ontology.import_overrides`

- **Fields**:

  | Field | Type | Required | Notes |
  |---|---|---|---|
  | `payload` | mapping | yes | A payload previously produced by `ontology.export_overrides` (or hand-authored in the same shape). |

- **Behavior**: Validates `payload.version` against the integration's supported import version and validates every entry's shape before writing anything; if either check fails, the entire import is rejected with no partial writes (FR-027, FR-028). On success, each entry is `MERGE`d keyed on `(relationship_type, source_ha_id, target_ha_id)`, so re-importing the same payload is a no-op after the first successful import (FR-029).
- **Response**: `{ "imported_count": <int> }` on success; a clear rejection error (fail closed, no partial writes) on any validation failure.

## `ontology.validate` (extended)

- **Fields**: none (unchanged from v1).
- **Behavior**: Runs **only** when explicitly invoked via this service — there is no automatic post-sync or scheduled trigger in v2 (FR-017, per the clarified on-demand-only decision). Evaluates all 9 validation categories (research.md §6, data-model.md `ValidationFinding`) and `MERGE`s a `ValidationFinding` node per detected issue; findings not re-detected are marked resolved per the retention policy in the spec's Assumptions. Does not modify any other data.
- **Response**: none (fire-and-forget); result observable via the graph's `ValidationFinding` nodes and diagnostics finding counts.

## Safety boundary

`ontology.query` is the only v2 service that accepts a Cypher string, and it is the only one bound by the deny-list safety check (Constitution Principle X). No other v2 or v1 service accepts or executes arbitrary Cypher.
