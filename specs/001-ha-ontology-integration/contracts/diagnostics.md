# Contract: Diagnostics & Health Surfaces

Defines the observability contract, per FR-014, FR-018, FR-019, Constitution Principle VIII.

## Entities (sensor platform)

| Entity | Type | Values / Notes |
|---|---|---|
| `sensor.ontology_health` | enum/state sensor | e.g., `ok`, `error`, `unavailable` — reflects last operation outcome and current Memgraph reachability. |
| `sensor.ontology_nodes` | numeric sensor | Total node count currently represented in the graph (as last measured). |
| `sensor.ontology_relationships` | numeric sensor | Total relationship count currently represented in the graph. |
| `sensor.ontology_last_sync` | timestamp sensor | Timestamp of the last completed synchronization (any type). |
| `sensor.ontology_last_error` | text sensor | Redacted summary of the most recent error, if any; empty/`none` when healthy. |
| `sensor.ontology_schema_version` | text sensor | Current `OntologySchema.version` value as recorded in the graph. |

## Entities (button platform)

| Entity | Action |
|---|---|
| `button.ontology_rebuild` | Invokes `ontology.rebuild`. |
| `button.ontology_validate` | Invokes `ontology.validate`. |
| `button.ontology_resync` | Invokes `ontology.resync`. |

## Diagnostics download payload (`diagnostics.py`)

**Included** (per FR-018):
- Connection status (reachable/unreachable, last check time).
- Element counts (nodes, relationships) — same values as the sensors above.
- Schema version.
- Redacted connection info: `host`, `port`, `username` (present/absent only, not value if considered sensitive by policy), `database`, `encrypted` flag.

**Always excluded** (redacted, per FR-004, SC-007):
- `password` / any secret field — never included, not even masked with partial characters.
- Any Home Assistant long-lived access tokens or API keys, if ever incidentally referenced.

## Repair issues (`repairs.py`)

| Issue | Trigger | Guidance shown to user |
|---|---|---|
| `schema_version_mismatch` | Startup detects `OntologySchema.version` in Memgraph ≠ expected version (research.md §7) | Explains the mismatch (expected vs. found version) and directs the administrator to manually resolve it (e.g., restore backup, run a documented migration) before the integration will load. |
| `sustained_connection_failure` | Repeated (≥3 consecutive, research.md §6) synchronization attempts fail due to Memgraph unreachability | Explains that the graph database is unreachable across repeated attempts and to check that the local Memgraph service is running/reachable. |

Both repair issues are cleared automatically once the underlying condition is resolved and detected on a subsequent check.
