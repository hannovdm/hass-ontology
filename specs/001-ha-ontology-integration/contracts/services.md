# Contract: Services (`services.yaml`)

Defines the callable service contract, per FR-015, FR-016, FR-013a, Constitution Principle VIII and X.

All four services below are mutually serialized: if any one of them (or an in-flight event-driven update) is already running, a newly invoked service call is queued (single pending slot) or fails immediately with a "sync already in progress" error, per FR-013a — never executed concurrently.

## `ontology.rebuild`

- **Fields**: none.
- **Behavior**: Clears all `source = "home_assistant"` (and integration-owned `generated`) nodes/relationships, then performs a full discovery + graph build from current HA registries (per the "rebuild policy" in data-model.md). Never deletes `source = "user"` or `source = "inferred"` data (FR-017a).
- **Response**: none (fire-and-forget); result observable via `sensor.ontology_health` / `sensor.ontology_last_sync` / `sensor.ontology_last_error`.

## `ontology.resync`

- **Fields**: none.
- **Behavior**: Re-reads current HA registries and updates/creates corresponding graph elements in place using `MERGE`, without deleting any existing data the integration does not manage (FR-016).
- **Response**: none (fire-and-forget); result observable via the same sensors as above.

## `ontology.sync_entity`

- **Fields**:

  | Field | Type | Required | Notes |
  |---|---|---|---|
  | `entity_id` | string | yes | The Home Assistant entity to refresh. |

- **Behavior**: Refreshes only the specified Entity node and its direct relationships (Domain, Integration, Device, Labels) — no full-graph rebuild or resync (FR-016, User Story 7 Acceptance Scenario 3).
- **Errors**: fails with a clear error if `entity_id` does not exist in Home Assistant.

## `ontology.validate`

- **Fields**: none.
- **Behavior**: Checks graph consistency (e.g., orphaned/missing expected relationships, schema version match) without modifying data; reports outcome through the health indicators (FR-016, User Story 7 Acceptance Scenario 4).
- **Response**: none (fire-and-forget); result observable via `sensor.ontology_health` / `sensor.ontology_last_error`.

## Safety boundary

None of these services accept or execute arbitrary Cypher; there is no service or parameter that allows passing a raw query string, consistent with Constitution Principle X (v1 exposes no arbitrary Cypher execution surface).
