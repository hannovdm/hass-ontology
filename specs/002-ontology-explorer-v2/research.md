# Phase 0 Research: Home Assistant Ontology Integration v2

## 1. Backend API transport mechanism for the ontology explorer (User Story 3)

- **Decision**: Implement the area/entity/search context endpoints as Home Assistant **`websocket_api`** commands (e.g., `ontology/area_context`, `ontology/entity_context`, `ontology/search`), registered via `homeassistant.components.websocket_api.async_register_command` during `async_setup_entry`.
- **Rationale**: `websocket_api` reuses Home Assistant's existing authenticated websocket connection (no new credential surface, no new HTTP view to secure), is the idiomatic mechanism other HA custom integrations use for frontend/backend data exchange, and keeps the API "not a separate authenticated HTTP endpoint for arbitrary external clients" as required by the spec's Assumptions. It also composes cleanly with `voluptuous` schemas for input validation (FR-036).
- **Alternatives considered**: A custom `HomeAssistantView` (REST endpoint) — rejected because it would require its own auth wiring and would read as a "separate authenticated HTTP endpoint," which the spec's Assumptions explicitly say to avoid; GraphQL layer — rejected as unnecessary complexity for three bounded, purpose-built queries.

## 2. Sidebar panel implementation approach (User Story 8)

- **Decision**: Register a custom panel via `homeassistant.components.frontend.async_register_built_in_panel` (`panel_custom` style), backed by a small, dependency-free JS module (a single ES module, no build step / bundler / framework) served as a static path from `custom_components/ontology/panel/`. The panel communicates exclusively through the websocket_api commands from research item 1.
- **Rationale**: Keeps the panel inside the same integration package (Constitution Principle I — no separate frontend project), avoids introducing a JS build toolchain this repository does not currently have, and matches FR-042's allowance that the panel may ship after the backend API is stable — the panel is additive and isolated from all other v2 capabilities.
- **Alternatives considered**: A full frontend framework (Lit/React) with a build pipeline — rejected for v2 as disproportionate to a single browse/search panel and inconsistent with Constitution Principle IX (small, incremental delivery); an iframe-hosted external page — rejected, adds a network-facing surface with no benefit for a local-first integration.

## 3. Read-only Cypher query safety validation (User Story 2)

- **Decision**: Validate queries with a **tokenized keyword scan**, not a naive substring match: strip Cypher comments (`//...` and `/* ... */`) and string literals first, uppercase the remainder, then match the disallowed keywords (`CREATE`, `MERGE`, `DELETE`, `DETACH`, `SET`, `REMOVE`, `DROP`, `LOAD CSV`, `CALL DBMS`, `CALL MG`, `CALL ALGO`) using word-boundary regular expressions. A query is rejected if any match is found anywhere in the (comment/string-stripped) text, regardless of clause position (FR-019).
- **Rationale**: A naive substring check would both over-reject (e.g., a string literal containing the word "created") and under-reject (e.g., a disallowed keyword hidden inside a `//` comment intended to confuse a naive scanner, or mixed case). Stripping comments/literals and using word boundaries closes both gaps while remaining simple enough to audit, matching Constitution Principle X's "safe by construction" requirement.
- **Alternatives considered**: A full openCypher parser/AST allow-list — rejected for v2 as excess complexity relative to the fixed, well-known deny-list already mandated by the constitution; naive `in` substring check (as a v0 sketch) — rejected for the false-positive/false-negative reasons above.

## 4. Query result row-limit enforcement (User Story 2)

- **Decision**: Enforce the row limit (default 100, max 1000; FR-018, FR-021) by streaming the Bolt result and stopping consumption once the limit is reached (`AsyncResult.records()` iteration with an early break), rather than injecting a `LIMIT` clause into arbitrary user Cypher text. The response indicates `truncated: true` when the cap was hit before the underlying result was exhausted.
- **Rationale**: Injecting a `LIMIT` clause into arbitrary, unparsed Cypher text is unreliable (subqueries, `UNION`, existing `LIMIT`/`ORDER BY` clauses) and could silently change query semantics. Streaming and cutting off consumption at the driver level is transport-agnostic and always safe, regardless of query shape.
- **Alternatives considered**: String-injecting/replacing `LIMIT` — rejected as fragile and semantically risky for arbitrary queries; rejecting any query that returns more than the limit outright — rejected, contradicts FR-021's requirement to still return the first N rows with a truncation indicator.

## 5. Semantic classification rule engine design (User Story 1, User Story 6)

- **Decision**: Implement classification as a small, declarative rule table in `semantic_classifier.py` — each rule maps a semantic type (`GasCylinder`, `Vehicle`, `EnergyAsset`, `SecurityDevice`, `OccupancySensor`, `ClimateDevice`, `NetworkDevice`, `BatteryPoweredDevice`) to a set of signal predicates (entity domain, `device_class`, name/label keyword patterns, area hints). Classification iterates all matching entities against all rules per run (supporting FR-005's "apply all matching classifications"), creating one semantic node per (entity, matched type) pair (per the confirmed 1:1 cardinality) tagged `source = "inferred"`, and skips node creation for any (entity, type) pair that already has a `source = "user"` relationship (FR-006).
- **Rationale**: A declarative rule table keeps the matching logic auditable and independently unit-testable per rule/signal, and evaluating "all rules against all entities" directly satisfies FR-005 without needing a priority/first-match system. Refreshing (User Story 6) re-runs the same rule table scoped to one entity or all entities, reusing the identical matching function.
- **Alternatives considered**: An ML/embedding-based classifier — rejected, disproportionate for keyword/domain-based rules and contradicts local-first simplicity; a first-match (stop on first rule) engine — rejected because it violates FR-005 (an entity may match more than one type).

## 6. Detection approach for the 9 validation categories (User Story 5)

- **Decision**: Implement each category in `validation.py` as an independent, idempotent Cypher read + `ValidationFinding` `MERGE` pass, run in sequence by `ontology.validate`:
  - `missing_area`: `Entity` with no path to `Area` (graph traversal absence).
  - `missing_device`: `Entity` on a device-backed platform with no `HAS_ENTITY` incoming relationship from any `Device`.
  - `orphan_entity`: `Entity` with no relationship to `Device`, `Area`, `Automation`, `Scene`, or `Script`.
  - `orphan_device`: `Device` with no `Area` and no exposed `Entity`.
  - `duplicate_entity`: two or more `Entity` nodes sharing the same `ha_id` root (registry-level duplicate, e.g. leftover from a prior identifier scheme).
  - `unavailable_critical_entity`: `Entity` with `critical = true` and `state = "unavailable"`.
  - `invalid_relationship`: any relationship whose start or end node is absent (defensive Cypher check; guards against future partial-delete bugs) or that references a deleted HA object.
  - `schema_mismatch`: `OntologySchema.version` present but not equal to the integration's expected version (re-check of the same condition v1 already treats as fatal on startup, additionally surfaced here as an ordinary finding for visibility without changing v1's fail-to-load behavior).
  - `missing_semantic_classification`: `Entity` whose domain/name matches a classification rule signal (research item 5) but has no `CLASSIFIED_AS`/type relationship at all.
  Each pass creates/updates a `ValidationFinding` node linked via `RELATES_TO`; a finding not re-detected on the next run is marked resolved and removed after remaining resolved across one subsequent run (per the spec's documented retention policy), unless the user acted on it.
- **Rationale**: Each category maps to a narrow, independently testable Cypher query, keeping detection logic auditable and letting new categories be added without touching existing ones.
- **Alternatives considered**: A single generic "graph health" heuristic scoring pass — rejected, it would not produce the specific, actionable categories FR-014 requires.

## 7. Import/export payload format and idempotency (User Story 7)

- **Decision**: Export/import payloads are a JSON document `{"version": <int>, "exported_at": <iso8601>, "overrides": [ {relationship_type, source_ha_id, target_ha_id, properties...} ] }` containing only `source = "user"` relationships. Import performs one `MERGE` per entry keyed on `(relationship_type, source_ha_id, target_ha_id)`, so re-importing the same payload is a no-op after the first successful import (FR-029). `version` is checked for exact match against the integration's supported import version; any other value fails the whole import closed (FR-027).
- **Rationale**: A flat, versioned JSON array keyed on stable HA identifiers (consistent with the `ha_id` convention from v1's data model) is simple to validate entry-by-entry (FR-028) and trivially idempotent via `MERGE`.
- **Alternatives considered**: A binary/graph-native dump (e.g., raw Cypher `CREATE` script) — rejected, harder to validate per-entry and reintroduces raw write-Cypher into a user-facing surface, contradicting Constitution Principle X.

## 8. Dashboard (Lovelace) configuration access (Dashboard synchronization FRs)

- **Decision**: Read dashboard/card structure best-effort from Home Assistant's Lovelace config objects available via `hass.data["lovelace"]` (dashboard collection, each exposing an `async_load()`-able config of views/cards), synchronizing only dashboards whose configuration is currently loadable. Dashboards/cards that fail to load or reference deleted entities are skipped/tolerated per FR-050, never failing the overall sync.
- **Rationale**: This is the same internal data structure other community integrations already rely on for dashboard introspection; treating it as best-effort (not a hard dependency) is consistent with FR-050 and avoids coupling the integration to Lovelace internals changing between HA core releases.
- **Alternatives considered**: Requiring users to manually declare dashboard structure — rejected, defeats the purpose of automatic sync; parsing raw YAML dashboard files directly from disk — rejected, does not cover UI/storage-mode dashboards and duplicates logic HA core already exposes in memory.

## 9. Schema version bump strategy for v2

- **Decision**: Bump `SCHEMA_VERSION` (in `const.py`) from `"1.0.0"` to `"2.0.0"` when v2 ships. Because v2 only *adds* new labels/relationships/properties (semantic types, `ValidationFinding`, `Dashboard`/`DashboardCard`, `source = "inferred"`) without altering the meaning or shape of any v1 label/relationship, existing v1 installations upgrading in place are compatible; the version bump exists purely to make the new minimum-expected-schema explicit and to keep v1.x integration code (which does not know about v2 labels) from silently running against a v2-shaped graph, per Constitution Principle VI.
- **Rationale**: A major bump communicates "new capabilities present" without implying any breaking change to v1 data; the existing fail-to-load-on-mismatch behavior (v1 FR-017) means a v1 binary talking to a v2-tagged graph — or vice versa — fails safely rather than silently.
- **Alternatives considered**: A minor bump (`1.1.0`) — considered but rejected in favor of a major bump to make the schema-version repair-issue message clearer to administrators that a substantial new capability set is present.

## 10. Frontend/panel test strategy

- **Decision**: No new JS/frontend automated test tooling is introduced in v2. The sidebar panel (User Story 8) is verified manually via `quickstart.md` steps (load panel, browse, search) since this repository has no existing JS test harness and the panel's logic is a thin, stateless client over already-tested websocket_api commands.
- **Rationale**: Consistent with Constitution Principle IX (small, incremental delivery — no unrelated infrastructure introduced in one step) and the spec's own allowance (FR-042) that the panel may lag the backend API; all business logic the panel depends on is already covered by backend contract/unit/integration tests.
- **Alternatives considered**: Introducing Playwright/Jest for the panel — rejected for v2 as disproportionate to a single thin browse/search view; may be revisited in a future increment if the panel grows in complexity.

## Outstanding NEEDS CLARIFICATION

None — all technical unknowns identified from the Technical Context have been resolved above; functional/behavioral ambiguities were already resolved in the spec's Clarifications section (`/speckit.clarify`, session 2026-07-24).
