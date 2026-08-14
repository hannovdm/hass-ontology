# Data Model: Home Relationship Questions

**Input**: [spec.md](./spec.md), [research.md](./research.md)  
**Schema transition**: `2.0.0` to `3.0.0`

## 1. Existing graph entities extended by this feature

### Entity

Existing Home Assistant entity node. Feature 004 adds allow-listed current-measurement properties.

| Field | Type | Rules |
|---|---|---|
| `ha_id` | string | Existing stable entity identifier; required. |
| `measurement_kind` | enum | `battery` or `power`; absent when entity is not a supported measurement. |
| `measurement_status` | enum | `available`, `unavailable`, `invalid_value`, or `unsupported_unit`. |
| `battery_percentage` | float | Present only for an available battery reading; finite and 0 through 100. |
| `power_watts` | float | Present only for an available power reading; finite; may be negative or zero. |
| `device_class` | string | Existing exact Home Assistant source value. |
| `unit_of_measurement` | string | Existing exact Home Assistant display/source unit. |
| `measurement_last_updated` | string | UTC ISO-8601 serialization of Home Assistant `State.last_updated` for the accepted measurement-relevant change. |
| `measurement_last_updated_epoch` | float | UTC epoch seconds for bounded freshness predicates. |

**Validation and clearing rules**:
- Battery requires `device_class=battery`, unit `%`, finite numeric state, and range 0-100.
- Power requires `device_class=power`, unit `W` or `kW`, and finite numeric state. `kW` is normalized to watts.
- `unknown`, `unavailable`, malformed, nonfinite, out-of-range, or unsupported-unit readings cannot retain an old normalized numeric property.
- A resync or rebuild writes the Home Assistant timestamp; graph synchronization time never substitutes for measurement freshness.
- Historical measurements are not retained.

### GasCylinder

Existing canonical semantic asset associated with an entity. Its stable `ha_id` remains `<entity_id>::GasCylinder`. A source may originate from inference or an existing user semantic override, but supply knowledge is never inferred.

### Device and Area

Existing generated nodes and `HAS_ENTITY`, `HAS_DEVICE`, and direct area relationships remain authoritative for current topology. Device and area display names are not stable identities.

## 2. New durable statement entities

### SupplyAssociation

A user-owned directional statement that one gas-cylinder asset supplies one Device or Entity.

| Field | Type | Rules |
|---|---|---|
| `ha_id` | string | Deterministic UUIDv5/canonical hash from `(source_asset_id, target_kind, target_id)`; required and immutable. |
| `source_asset_id` | string | Stable canonical GasCylinder ID; required. |
| `target_kind` | enum | `device` or `entity`. |
| `target_id` | string | Stable Home Assistant device or entity identifier; required. |
| `source` | string | Always `user`. |
| `created_at` | string | UTC ISO-8601; retained on idempotent upsert. |
| `updated_at` | string | UTC ISO-8601; advances when the statement is reaffirmed or changed. |

**Identity and uniqueness**:
- Exactly one record may exist for a source/target pair.
- Display names, area names, and Memgraph element IDs never participate in identity.
- An imported `ha_id` must equal the ID recomputed from the record fields.

**Relationships**:

```text
(:SupplyAssociation)-[:SUPPLY_SOURCE {source: "generated"}]->(:GasCylinder)
(:SupplyAssociation)-[:SUPPLIES {source: "generated"}]->(:Device|Entity)
```

The statement node is durable; binding relationships are projections and may be absent while either endpoint is unresolved. Reconciliation recreates bindings when endpoints return.

### EnergyRoleAssignment

A classification of a power-measurement Entity.

| Field | Type | Rules |
|---|---|---|
| `ha_id` | string | Deterministic from `(assignment_source, measurement_entity_id)`; required and immutable. |
| `measurement_entity_id` | string | Stable Entity ID; required. |
| `role` | enum | `consumer`, `producer`, `storage`, `grid_import`, or `grid_export`. |
| `source` | enum | `user` or `inferred`. |
| `created_at` | string | UTC ISO-8601; retained on upsert. |
| `updated_at` | string | UTC ISO-8601; advances when role changes. |

**Identity and precedence**:
- At most one assignment exists per `(source, measurement_entity_id)`.
- `role` is mutable and is not part of identity.
- Effective role is the user assignment when present, otherwise the inferred assignment; absent assignments produce `unknown` at query time.

**Relationship**:

```text
(:EnergyRoleAssignment)-[:ASSIGNS_ROLE_TO {source: "generated"}]->(:Entity)
```

The durable assignment survives an unresolved entity; reconciliation restores the binding later.

## 3. Schema state and migration

### OntologySchema

The existing singleton advances to:

| Field | Value |
|---|---|
| `name` | `home_assistant_ontology` |
| `version` | `3.0.0` |
| `previous_version` | `2.0.0` after upgrade; absent on fresh install |
| `migrated_at` | UTC migration completion timestamp after upgrade |
| `updated_at` | UTC schema write timestamp |

**State transitions**:

```text
No schema node --fresh install--> 3.0.0
2.0.0 --atomic additive migration--> 3.0.0
3.0.0 --startup/retry--> 3.0.0 (no-op)
Any other version --startup--> mismatch repair + setup refusal
```

The version marker is the final operation in the migration transaction.

## 4. Current Measurement state transitions

```text
unsupported/non-measurement
  -> accepted battery or power event
available

available
  -> unknown/unavailable state
unavailable (numeric value removed)

available
  -> malformed/nonfinite/out-of-range state
invalid_value (numeric value removed)

available
  -> unsupported/missing unit
unsupported_unit (numeric value removed)

any status
  -> unrelated attribute-only event
unchanged (no write, timestamp unchanged)
```

Staleness is not a stored state. At query time a measurement is fresh when:

$$measurement\_last\_updated\_epoch \ge now_{UTC} - max\_age$$

A reading exactly at the cutoff is fresh.

## 5. Shared operation records

### TargetCandidate

| Field | Type | Rules |
|---|---|---|
| `target_type` | enum | Operation-eligible type such as `entity`, `device`, or `gas_cylinder`. |
| `target_id` | string | Stable identifier. |
| `name` | string | Redacted display name. |
| `area_name` | string/null | Redacted area name when useful. |

Candidates are bounded and ordered by target type, normalized name, then stable ID.

### ToolResult

The v3 result envelope gains `outcome` while preserving existing keys.

```text
ToolResult
├── target: string
├── result_type: string
├── outcome: ok | empty | not_found | ambiguous | degraded
├── result: object | list | null
└── warnings: list[string]
```

- `empty` means the target resolved and no qualifying relationships/readings exist.
- `not_found` means no eligible target resolved.
- `ambiguous` returns bounded `TargetCandidate` records.
- `degraded` means a dependency such as Memgraph was unavailable; no raw exception is returned.
- Every collection is bounded and reports truncation through warnings and payload metadata.

## 6. Query result entities

### LowBatteryAreaResult

```text
LowBatteryAreaResult
├── threshold_percentage: float
├── max_age_hours: float
├── areas: list[
│   ├── area_id: string | null
│   ├── area_name: string
│   └── items: list[
│       ├── device_id: string | null
│       ├── entity_id: string
│       ├── name: string
│       └── measurements: list[{entity_id, name, percentage, measured_at}]
│   ]
│ ]
├── unavailable_count: integer
└── truncated: boolean
```

Devices are de-duplicated by stable ID; direct area entities fall back to entity identity. Every qualifying measurement remains available for explanation.

### ActiveConsumerResult

```text
ActiveConsumerResult
├── threshold_watts: float
├── max_age_hours: float
├── consumers: list[
│   ├── device_id: string
│   ├── name: string
│   ├── area_id: string | null
│   ├── area_name: string | null
│   └── measurements: list[{entity_id, name, watts, source_unit, role, role_source, measured_at}]
│ ]
├── known_consumers_without_current_power: list[
│   ├── device_id: string
│   ├── name: string
│   ├── area_id: string | null
│   ├── area_name: string | null
│   └── energy_entities: list[{entity_id, name}]
│ ]
├── unresolved_role_count: integer
└── truncated: boolean
```

Measurements are not summed unless later metadata explicitly marks them non-overlapping.
Cumulative energy entities establish that a device is a known consumer but do
not establish current activity; they are returned separately without watts.

### AutomationDependencyResult

```text
AutomationDependencyResult
├── target: TargetCandidate summary
├── automations: list[
│   ├── automation_id: string
│   ├── name: string
│   └── reasons: list[{entity_id, relationship_type}]
│ ]
└── truncated: boolean
```

A device target aggregates dependencies through every current associated entity and de-duplicates by automation stable ID.

### SuppliedTargetsResult

```text
SuppliedTargetsResult
├── cylinder: TargetCandidate summary
├── targets: list[{target_type, target_id, name, area_id, area_name}]
└── truncated: boolean
```

Only explicit user-managed associations qualify.

### DeviceContextResult

```text
DeviceContextResult
├── device: TargetCandidate summary
├── area: {area_id, area_name} | null
├── entities: list[{entity_id, name, domain, device_class, unit_of_measurement}]
├── automation_dependencies: list[AutomationDependencyResult item]
└── truncated: boolean
```

Every currently associated entity appears once.

## 7. User-knowledge export document

Version 2 extends the existing override export:

```json
{
  "version": 2,
  "exported_at": "UTC ISO-8601",
  "overrides": [],
  "supply_associations": [],
  "energy_role_assignments": []
}
```

**Import rules**:
- Version 1 legacy override documents remain accepted.
- Unknown fields/types/versions, malformed IDs, invalid roles/kinds, conflicting duplicate IDs, or duplicate user roles for one entity reject the entire payload.
- Validation completes before the write transaction starts.
- Valid records merge/upsert by stable identity; omitted local records remain unchanged.
- Temporarily unresolved endpoint references are retained as durable statements.

## 8. Validation and diagnostics

New validation finding types:
- `unresolved_supply_source`
- `unresolved_supply_target`
- `unresolved_energy_role_entity`

Findings target durable statement IDs, never nonexistent endpoint IDs. Diagnostics expose only aggregate counts by measurement status, unresolved role, association state, operation, outcome, and sanitized error category. They exclude raw measurements, stable target IDs, names, utterances, credentials, tokens, and exception messages.
