# Phase 0 Research: Home Assistant Ontology Integration v1

## 1. Python / Home Assistant core version target

- **Decision**: Target the Python version bundled with the current Home Assistant core release (Python 3.13 as of the 2025.x/2026.x HA core line), with type hints and async-first code throughout.
- **Rationale**: The constitution requires "Python compatible with current supported Home Assistant versions" rather than pinning an independent version. Custom integrations run inside the HA core process, so the runtime is dictated by whatever HA core ships, not by the integration itself.
- **Alternatives considered**: Pinning an older Python (e.g., 3.11) for broader compatibility — rejected because HA core itself enforces a minimum version floor per release and custom integrations cannot run on an older interpreter than HA core requires.

## 2. Memgraph client library

- **Decision**: Use the official `neo4j` Python driver (Bolt protocol) for all Memgraph connectivity, wrapped in `memgraph_client.py`.
- **Rationale**: Memgraph implements the Bolt protocol and is wire-compatible with the Neo4j Python driver, which is lightweight, actively maintained, fully async-capable (`neo4j.AsyncGraphDatabase`), and does not impose an object-graph-mapping layer. This keeps the dependency surface small and keeps all Cypher construction explicit and auditable, which matters for the idempotent-`MERGE` and safety-boundary requirements in the constitution.
- **Alternatives considered**: `gqlalchemy` (Memgraph's official OGM) — rejected for v1 because its object-mapping abstractions add indirection that makes it harder to guarantee exact, auditable `MERGE` semantics and to keep the "no arbitrary Cypher execution" safety boundary explicit; it remains a candidate for v2+ if modeling complexity grows.

## 3. Testing strategy and frameworks

- **Decision**: Use `pytest` + `pytest-asyncio` + `pytest-homeassistant-custom-component` for unit and contract tests (mocked HA core, mocked Memgraph client), and `testcontainers-python` to spin up a real Memgraph container for integration tests that validate idempotency, schema versioning, and end-to-end sync behavior.
- **Rationale**: `pytest-homeassistant-custom-component` is the de facto standard harness for testing HA custom integrations (provides fixtures for `hass`, config entries, and registries). Real-Memgraph integration tests are necessary because idempotent `MERGE` behavior and schema-version detection are core correctness guarantees that mocks cannot fully validate.
- **Alternatives considered**: Testing exclusively against mocks — rejected because it cannot verify actual Cypher correctness against Memgraph's Bolt implementation; a fully manual Memgraph test instance — rejected in favor of `testcontainers` for reproducibility and CI compatibility.

## 4. Stable identifier derivation

- **Decision**: Derive every graph node's stable identifier directly from the corresponding Home Assistant registry ID (`area_id`, `device_id`, `entity_id`/`unique_id`, automation/scene/script `entity_id`), stored as a dedicated indexed property (e.g., `ha_id`) used as the `MERGE` key.
- **Rationale**: FR-009 requires durable identifiers derived from HA registry IDs so identity survives restarts and repeated syncs; using HA's own registry identifiers avoids inventing a parallel ID scheme that could drift out of sync.
- **Alternatives considered**: Generating synthetic UUIDs per node — rejected because it would require an additional persistent mapping table and adds a reconciliation failure mode that HA's own stable IDs avoid.

## 5. Debounce / throttle window for state-change events

- **Decision**: Default debounce window of 3 seconds per entity (configurable internally as a constant), batching rapid successive `state_changed` events for the same entity into a single graph write.
- **Rationale**: The spec's Assumptions section calls for "a reasonable default debounce/throttle window (on the order of a few seconds)"; 3 seconds balances near-real-time feel (SC-003) against protecting the HA event loop and Memgraph from high-frequency sensor updates (FR-011).
- **Alternatives considered**: Sub-second debounce — rejected, insufficient protection against chatty sensors (e.g., power/energy monitors); 10+ second debounce — rejected as it would noticeably harm the "near-real-time" perception in SC-003.

## 6. Retry / backoff policy for Memgraph operations

- **Decision**: Exponential backoff starting at 1 second, doubling up to a capped maximum of 60 seconds, with a maximum of 5 attempts per operation before marking the update as failed/pending and surfacing it via the health/last-error sensor; a repair issue is created after 3 consecutive full-sync failures.
- **Rationale**: FR-020 requires retry with backoff rather than silently dropping failed writes; the spec's Assumptions call for "a small number of consecutive failed synchronization attempts" before raising a repair notification to avoid noisy false alarms.
- **Alternatives considered**: Unlimited retries — rejected, risks unbounded background load during sustained outages; single-attempt (no retry) — rejected, contradicts FR-020 directly.

## 7. Schema-version mismatch handling

- **Decision**: On integration setup, read the `OntologySchema.version` property from Memgraph (if present) and compare it to the integration's `const.py`-defined expected version. On mismatch, `async_setup_entry` raises `ConfigEntryNotReady`/fails setup (integration does not load), no Cypher writes are issued, and a Home Assistant repair issue is created describing the mismatch and directing the administrator to resolve it manually (e.g., via backup/restore or manual migration).
- **Rationale**: Directly implements the clarified decision (spec Clarifications, Session 2026-07-22) and FR-017: fail-to-load, no silent structural changes, repair issue guidance.
- **Alternatives considered**: Auto-migrating the schema in place — explicitly rejected by the clarification; degraded/read-only mode — explicitly rejected by the clarification in favor of hard failure.

## 8. Sync operation serialization mechanism

- **Decision**: Implement a single `asyncio.Lock` (or equivalent single-flight guard) inside the coordinator; if a sync/rebuild/resync/validate/single-entity operation is requested while the lock is held, the request is queued (FIFO, single pending slot per operation type) or rejected with a clear "sync already in progress" result, per FR-013a.
- **Rationale**: The clarification session selected "serialize — queue or reject" over concurrent execution; a single coordinator-owned lock is the simplest mechanism consistent with Home Assistant's `DataUpdateCoordinator` pattern and avoids races against Memgraph.
- **Alternatives considered**: Allowing concurrent syncs with optimistic conflict resolution — rejected, contradicts the clarified requirement and significantly increases complexity/risk of duplicate or conflicting writes.

## Outstanding NEEDS CLARIFICATION

None — all technical unknowns identified from the Technical Context have been resolved above; the functional/behavioral clarifications were already resolved in the spec's Clarifications section.
