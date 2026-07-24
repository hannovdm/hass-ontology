# Data Model: Home Assistant Ontology Explorer v2

This document extends [specs/001-ha-ontology-integration/data-model.md](../001-ha-ontology-integration/data-model.md) with the new nodes, relationships, and properties introduced by v2's Key Entities in [spec.md](./spec.md). All conventions from v1 continue to apply: every node/relationship carries `source` and `updated_at`; every write is a `MERGE` keyed on a stable identifier; nodes/relationships with `source = "user"` are never deleted by classification, refresh, rebuild, or resync.

## Common conventions (v2 additions)

- **New `source` value in active use**: `inferred` — used exclusively for semantic classification relationships/nodes created by the rule engine (research.md §5). `generated` continues to mean "derived by integration logic" and is now also used for dashboard/card sync (FR-049). `user` continues to mean "manually added/edited, never touched by any automated operation" (FR-006, FR-025).
- **Semantic node identity**: every semantic asset node (`GasCylinder`, `Vehicle`, `EnergyAsset`, `SecurityDevice`, `OccupancySensor`, `ClimateDevice`, `NetworkDevice`, `BatteryPoweredDevice`) is 1:1 with the `Entity` that produced it — its `ha_id` is derived from the classified entity's `ha_id` plus the semantic type label (e.g., `"sensor.garage_gas_level::GasCylinder"`), so re-running classification `MERGE`s the same node rather than creating duplicates, and two entities describing the same physical asset always get two distinct nodes (per the clarified 1:1 cardinality).
- **`critical` property**: an optional boolean on `Entity`, set by the user (default absent/false), consumed by the `unavailable_critical_entity` validation category (FR-051–FR-056 context; spec Assumptions).

## New Nodes

### SemanticType
- `ha_id`: the semantic type name (e.g., `"GasCylinder"`, `"Vehicle"`) — effectively a shared classification concept node, analogous to `Domain` in v1.
- Properties: `source` (`generated`, created once per known type), `updated_at`.
- Linked from classified `Entity` nodes via `CLASSIFIED_AS`.

### GasCylinder / Vehicle / EnergyAsset / SecurityDevice / OccupancySensor / ClimateDevice / NetworkDevice / BatteryPoweredDevice
- `ha_id`: `"<classified entity ha_id>::<TypeLabel>"` (one node per classified entity — 1:1, never shared/aggregated across entities).
- Properties: `source` (`inferred` from automatic classification, or `user` if manually created/overridden), `confidence` (optional, rule-derived hint, informational only), `updated_at`.
- Relationships: `MEASURED_BY` (GasCylinder/EnergyAsset ← Entity), `OBSERVED_BY` (SecurityDevice/OccupancySensor ← Entity), `LOCATED_IN` (→ Area, where known), plus the classifying `CLASSIFIED_AS` (Entity → this node).
- Validation: may exist with no `LOCATED_IN` relationship if the source entity has no known area (mirrors v1's "missing area is valid, not fatal" pattern).

### Dashboard
- `ha_id`: Lovelace dashboard identifier (URL path / dashboard key).
- Properties: `title` (optional), `source = "generated"`, `updated_at`.
- Present only for dashboards whose configuration was loadable at sync time (FR-050).

### DashboardCard
- `ha_id`: `"<dashboard ha_id>::<view index>::<card index>"` (stable positional identifier within a dashboard's config).
- Properties: `card_type` (e.g., `"entities"`, `"button"`), `source = "generated"`, `updated_at`.
- Preserved even when its config references a deleted/unknown entity (FR-050) — only the `DISPLAYS_ENTITY` relationship is omitted in that case.

### ValidationFinding
- `ha_id`: `"<category>::<affected node ha_id>"` (stable per detected issue, so repeated validation runs `MERGE` the same finding rather than duplicating it).
- Properties: `category` (one of the 9 values below), `severity` (`info`/`warning`/`error`), `status` (`open`/`resolved`), `first_detected_at`, `last_detected_at`, `resolved_at` (optional), `source = "generated"`, `updated_at`.
- Categories: `missing_area`, `missing_device`, `orphan_entity`, `orphan_device`, `duplicate_entity`, `unavailable_critical_entity`, `invalid_relationship`, `schema_mismatch`, `missing_semantic_classification` (detection criteria: research.md §6, FR-011–FR-017, FR-051–FR-056).
- Lifecycle: created/updated (`status = "open"`) when detected; on a subsequent validation run where the same category+target no longer reproduces, `status` is set to `"resolved"` and `resolved_at` is stamped; the node is deleted only after remaining `"resolved"` across one additional validation run, unless the user has taken explicit action on it (per spec Assumptions retention policy).

## New Relationships

| Relationship | From → To | Notes |
|---|---|---|
| `CLASSIFIED_AS` | Entity → SemanticType | One per matched rule; an entity may have multiple (FR-005). |
| `MEASURED_BY` | GasCylinder / EnergyAsset → Entity | Links the semantic asset back to the entity that produced it. |
| `OBSERVED_BY` | SecurityDevice / OccupancySensor → Entity | Links the semantic asset back to the observing entity. |
| `LOCATED_IN` | GasCylinder / Vehicle / SecurityDevice / etc. → Area | Only when the source entity's device/area is known. |
| `CONTAINS_CARD` | Dashboard → DashboardCard | One per card in the dashboard's loaded config. |
| `DISPLAYS_ENTITY` | DashboardCard → Entity | Omitted (not failed) when the card references a deleted/unknown entity (FR-050). |
| `RELATES_TO` | ValidationFinding → Entity / Device / Area | Points at whatever node the finding concerns. |
| `OVERRIDE_OF` *(user-managed)* | Entity/Device/Area → SemanticType-family node | `source = "user"` relationship created by User Story 4's manual override capability; never touched by classification, refresh, rebuild, or resync (FR-006, FR-025). |

All new relationships carry `source` and `updated_at` mirroring the write that created/last touched them, exactly as in v1.

## Validation rules summary (v2 additions)

- Semantic nodes are always 1:1 with their classified `Entity` — classification MUST NOT merge two entities into one shared semantic node, even when they describe the same physical asset (FR-002).
- Classification, refresh, rebuild, and resync MUST NOT create, modify, or delete any node/relationship with `source = "user"` (FR-006, FR-025, extends v1 FR-017a).
- `ontology.query` MUST reject any query containing a disallowed keyword (research.md §3) before it reaches Memgraph, and MUST cap returned rows at the configured limit (FR-018, FR-021, research.md §4).
- Dashboard sync MUST tolerate unloadable dashboards or dangling entity references without failing the overall sync (FR-050).
- `ValidationFinding.ha_id` is stable per (category, affected node) so repeated `ontology.validate` runs update, not duplicate, existing findings.
- Import of overrides MUST validate every entry and fail the entire import closed on an unsupported/mismatched `version`, or on any structurally invalid entry (FR-027, FR-028).
