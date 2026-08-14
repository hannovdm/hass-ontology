# Research: Home Relationship Questions

**Feature**: [spec.md](./spec.md)  
**Date**: 2026-08-12

All Technical Context unknowns are resolved. This research extends the existing v1-v3 architecture and introduces no new runtime dependency.

## 1. Ontology schema migration

**Decision**: Advance the graph schema from `2.0.0` to `3.0.0` through a managed write transaction. Startup accepts a fresh graph, an already-current `3.0.0` graph, or exactly `2.0.0`; it migrates only the exact predecessor and updates the `OntologySchema` marker last.

**Rationale**: The feature adds persisted labels, relationships, properties, and migration behavior. Updating the version last prevents a failed migration from advertising success. The migration is additive, so existing generated, inferred, and user-managed data remains intact and reruns are harmless.

**Alternatives considered**:
- Keep schema `2.0.0`: rejected because new persisted semantics require explicit versioning under Constitution Principle VI.
- Use `2.1.0`: rejected because the new durable concepts and automatic migration are a major graph-semantic change.
- Clear and rebuild the graph: rejected because it risks user knowledge and is unnecessary for an additive migration.

## 2. Transaction boundary

**Decision**: Add one managed write-transaction API to `MemgraphClient` and use transaction-local Cypher for schema migration and user-knowledge import.

**Rationale**: Existing helper calls open independent sessions. Full prevalidation followed by one transaction is required to guarantee that a failed import or migration leaves no partial writes.

**Alternatives considered**:
- Sequential autocommit writes: rejected because a mid-operation failure can leave partial data.
- Compensating deletes: rejected because rollback logic is more complex and less reliable than a database transaction.

## 3. Current measurement representation

**Decision**: Store normalized current measurement properties directly on `Entity` nodes: `measurement_kind`, `measurement_status`, `battery_percentage` or `power_watts`, `device_class`, `unit_of_measurement`, `measurement_last_updated`, and `measurement_last_updated_epoch`. Explicitly remove obsolete numeric fields when a reading becomes unusable or changes kind.

**Rationale**: Each entity contributes at most one current observation, and the feature intentionally excludes history. Entity-local properties minimize graph expansion and support fixed-depth bounded queries. Separate battery and power fields prevent unit confusion.

**Alternatives considered**:
- Create `CurrentMeasurement` nodes: rejected because they add identity and traversal cost without historical or multi-observation value.
- Store one generic numeric field: rejected because it weakens validation and can mix incompatible units.
- Omit invalid status: rejected because stale numeric properties could remain queryable after an unavailable or malformed transition.

## 4. Unit and value normalization

**Decision**: Battery normalization requires device class `battery`, exact unit `%`, a finite numeric state, and range 0 through 100. Power normalization requires device class `power`, exact unit `W` or `kW`, and a finite numeric state; kilowatts are multiplied by 1000. Zero and negative power remain valid current measurements but do not qualify as active consumption.

**Rationale**: This implements only unambiguous conversions promised by the specification. Home Assistant constants define accepted values, while unsupported units remain unavailable rather than being guessed.

**Alternatives considered**:
- Parse percentage strings, fractions, voltage, or integration-specific attributes: rejected as speculative and outside scope.
- Use a broad unit converter: rejected because it silently expands support beyond the specified watt and kilowatt contract.

## 5. Freshness and event filtering

**Decision**: Freshness uses Home Assistant `State.last_updated` from the latest accepted measurement-relevant change, never graph write time or `last_changed`. State changes and changes to allow-listed `friendly_name`, `device_class`, or `unit_of_measurement` attributes synchronize; only device class and unit changes advance measurement freshness. Unrelated attributes neither schedule nor restart the existing trailing-edge per-entity debounce.

**Rationale**: `last_updated` captures state or attribute changes, including relevant attribute-only updates. Retaining the accepted event snapshot through the debounce prevents later unrelated churn from supplying a newer timestamp. Query-time age evaluation keeps rebuilds from making old data fresh.

**Alternatives considered**:
- Use ontology synchronization time: rejected because resync would falsely rejuvenate old readings.
- Use `last_changed`: rejected because it does not advance for attribute-only changes.
- Accept every attribute change: rejected because it increases write load and broadens the privacy surface.
- Use `last_reported`: rejected because repeated unchanged reports are not measurement changes for this feature.

## 6. Energy-role semantics

**Decision**: Represent roles as durable `EnergyRoleAssignment` statement nodes targeted at power-measurement entities. Valid roles are `consumer`, `producer`, `storage`, `grid_import`, and `grid_export`; role is mutable and excluded from stable identity. User assignments override inferred assignments.

**Rationale**: Positive power is not sufficient evidence of consumption. A statement record can carry identity, ownership, provenance, and lifecycle independently of a generated entity binding.

**Alternatives considered**:
- Store one role property on the entity: rejected because it cannot cleanly preserve inferred and user-owned values simultaneously.
- Infer consumer from positive power: rejected because generation, storage, and grid-flow sensors can also be positive.

## 7. Gas supply knowledge

**Decision**: Model each durable user statement as a `SupplyAssociation` node, bound directionally to a canonical gas-cylinder asset and a `Device` or `Entity` target. Stable identity is derived deterministically from source asset ID, target kind, and target stable ID. Generated binding relationships are reconciled whenever endpoints appear, disappear, rebuild, resync, or reclassify.

**Rationale**: A direct edge cannot survive deletion of a generated endpoint. The statement node preserves user knowledge while validation reports unresolved sources or targets, and bindings can be recreated later.

**Alternatives considered**:
- Reuse `MEASURED_BY`: rejected because measurement does not imply physical supply.
- Use only `GasCylinder-[:SUPPLIES]->Target`: rejected because deleting either endpoint destroys the user-owned statement.
- Infer supply from names or proximity: rejected because Home Assistant lacks reliable physical fuel topology.

## 8. User-knowledge export and import

**Decision**: Introduce version 2 of the existing user-knowledge payload with `overrides`, `supply_associations`, and `energy_role_assignments`; continue accepting legacy override payload version 1. Validate all records and deterministic IDs before writing, reject conflicting duplicates, then merge/upsert in one transaction. Never delete records omitted from an import.

**Rationale**: This preserves backward compatibility and implements the clarified additive, idempotent, atomic behavior. Stable references permit temporarily unresolved records to round-trip without data loss.

**Alternatives considered**:
- Treat import as replacement: rejected because omission would silently destroy local knowledge.
- Reject all conflicts with existing records: rejected because idempotent restoration must update the same stable statement.
- Require live endpoints during import: rejected because backups must preserve knowledge about temporarily absent devices.

## 9. Authorization and channel boundaries

**Decision**: Register supply CRUD, energy-role CRUD, and user-knowledge import with Home Assistant's native administrator-service helper. Keep all Assist and MCP operations read-only. Export/list behavior remains available through authenticated Home Assistant administration surfaces and existing read channels only where the specification permits.

**Rationale**: Persistent shared ontology mutations affect every user and survive rebuilds. Native admin registration provides the established Home Assistant authorization behavior without custom role logic.

**Alternatives considered**:
- Allow every authenticated user to mutate: rejected because the changes are global and durable.
- Add a custom delegated-user ACL: rejected as unnecessary scope and a new security surface.
- Add MCP or Assist mutation tools: rejected by the specification and Constitution Principle X.

## 10. Shared target resolution and result semantics

**Decision**: Add one operation-aware resolver that gives exact stable IDs precedence, otherwise requires exactly one case-insensitive exact name match, and returns bounded deterministic candidates for ambiguity. Extend the existing transport-neutral `ToolResult` with `outcome: ok | empty | not_found | ambiguous | degraded` while retaining existing keys and result-type meanings.

**Rationale**: Current `OR ... LIMIT 1` patterns can silently pick duplicate names. A shared resolver and explicit outcome preserve parity across services, Assist, MCP, exports, and audit categories while distinguishing a successful empty answer from failure.

**Alternatives considered**:
- Keep transport-specific resolution: rejected because channels would diverge.
- Pick the first name match: rejected because it is nondeterministic and unsafe.
- Encode every outcome as `result_type`: rejected because operation payload type and execution outcome are independent concerns.

## 11. Bounded read queries

**Decision**: Add `low_battery_areas`, `active_consumers`, enhanced device/entity automation dependencies, `supplied_targets`, and enhanced `device_context` to `query_tools.py`. Use fixed-depth parameterized Cypher, fetch `effective_limit + 1`, group/de-duplicate in Python by stable ID, retain explanatory measurements/reasons, and never sum power readings unless explicitly marked non-overlapping.

**Rationale**: One shared read core guarantees consistent thresholds, freshness, ambiguity, truncation, warnings, and redaction across all channels. Row-wise bounded queries avoid unbounded `collect()` allocations.

**Alternatives considered**:
- Build separate queries per transport: rejected because safety and result semantics would drift.
- Sum all measurements for a device: rejected because sensors may overlap or report the same load at different scopes.
- Use variable-length traversals: rejected because all required relationships are known and fixed-depth.

## 12. Configuration, privacy, and observability

**Decision**: Add options for low-battery threshold (default 20%, range 1-100), active-power threshold (default 1 W, nonnegative), and maximum measurement age (default 24 hours). Services and MCP may provide validated per-call overrides. Context export allow-lists only approved normalized measurement and user-knowledge fields. Audit records store operation, outcome, count, truncation, channel, timestamp, and sanitized category only; diagnostics expose aggregates, not raw measurements or identifiers.

**Rationale**: Query-time options avoid rewriting graph data. Explicit allow-lists remain safe when the graph evolves, and aggregate observability supports diagnosis without creating a sensitive activity log.

**Alternatives considered**:
- Persist threshold classifications in Memgraph: rejected because changing an option would require graph rewrites.
- Export arbitrary node properties then redact: rejected because unknown future fields would leak by default.
- Record raw targets or utterances: rejected by the privacy requirements.
