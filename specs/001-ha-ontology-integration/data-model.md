# Data Model: Home Assistant Ontology Integration v1

This document defines the graph data model (Memgraph nodes, relationships, and properties) built from the Key Entities in [spec.md](./spec.md). All nodes/relationships created by the integration carry a `source` property per Constitution Principle V, and all writes use `MERGE` on the identifiers below (Constitution Principle VI / FR-008, FR-009).

## Common conventions

- **Stable ID property**: every node has `ha_id` (string) as its `MERGE` key, derived from the corresponding Home Assistant registry identifier (see research.md §4). `ha_id` is unique per label and indexed.
- **`source` property** (all nodes/relationships): one of `home_assistant` (created/updated from HA registry or state data), `generated` (derived by integration logic, e.g., computed groupings), `inferred` (future v2 semantic rules), `user` (manually added/edited, never touched by rebuild/resync — FR-017a).
- **`updated_at` property**: ISO-8601 timestamp of the last write from this integration.
- **Rebuild vs. resync**: rebuild clears and regenerates only nodes/relationships where `source = "home_assistant"` (or `generated` ones the integration owns); resync updates in place without deleting anything the integration did not create. Nodes/relationships with `source = "user"` or `source = "inferred"` are never deleted by either operation.

## Nodes

### Home
- `ha_id`: fixed singleton value (e.g., `"home"`) — one per Memgraph instance / config entry.
- Properties: `name` (from HA instance name/location if available), `source`, `updated_at`.
- Represents the root of the hierarchy; every Area is linked from Home.

### Floor (optional)
- `ha_id`: HA floor registry `floor_id`.
- Properties: `name`, `level` (if provided), `icon` (optional), `source`, `updated_at`.
- Absent entirely if the HA installation/version does not expose floor registry data (FR-006).

### Area
- `ha_id`: HA area registry `area_id`.
- Properties: `name`, `icon` (optional), `source`, `updated_at`.
- Validation: may exist with no linked Floor and no linked Devices (incomplete data is valid, not fatal — FR-006).

### Device
- `ha_id`: HA device registry `device_id`.
- Properties: `name`, `manufacturer` (optional), `model` (optional), `source`, `updated_at`.
- Validation: may exist with no linked Area (FR-006, User Story 3 Acceptance Scenario 3).

### Entity
- `ha_id`: HA `entity_id` (or `unique_id` where `entity_id` is unstable — implementation detail resolved during task planning).
- Properties: `name`, `state` (latest primary state value only — FR-012, FR-012a), `state_updated_at`, `source`, `updated_at`.
- Validation: may exist with no linked Device (directly-provided entities); must always link to exactly one Domain; links to Integration where the providing integration is known.
- State transitions: `state` is overwritten in place on each qualifying `state_changed` event; attribute-only changes without a primary state change do not update this node (FR-012a).

### Domain
- `ha_id`: domain string (e.g., `"light"`, `"sensor"`, `"switch"`).
- Properties: `source`, `updated_at`.
- Effectively a shared classification node; many Entities MAY link to the same Domain node.

### Integration
- `ha_id`: HA integration domain string (e.g., `"hue"`, `"zwave_js"`).
- Properties: `name` (display name if available), `source`, `updated_at`.
- Entities link to Integration only where the source integration is known/available (FR-005).

### Label (optional)
- `ha_id`: HA label registry `label_id`.
- Properties: `name`, `color` (optional), `source`, `updated_at`.
- Absent entirely if the HA installation/version does not expose the label registry (FR-006).

### Automation
- `ha_id`: automation `entity_id` (from the `automation` domain).
- Properties: `name`, `source`, `updated_at`.
- Related to the Entities it references (best-effort extraction from automation config/entity references).

### Scene
- `ha_id`: scene `entity_id` (from the `scene` domain).
- Properties: `name`, `source`, `updated_at`.
- Related to the Entities it controls.

### Script
- `ha_id`: script `entity_id` (from the `script` domain).
- Properties: `name`, `source`, `updated_at`.
- Related to the Entities it references.

### OntologySchema
- `ha_id`: fixed singleton value (e.g., `"home_assistant_ontology"`).
- Properties: `version` (semver string, e.g., `"1.0.0"`), `updated_at`.
- Written once at initial graph creation; read (never silently rewritten) on every subsequent integration startup to detect mismatch (FR-017).

## Relationships

| Relationship | From → To | Notes |
|---|---|---|
| `HAS_AREA` | Home → Area | Every discovered Area is linked to the singleton Home node. |
| `HAS_FLOOR` | Home → Floor | Only when floor registry data exists. |
| `ON_FLOOR` | Area → Floor | Only when the area has an assigned floor. |
| `HAS_DEVICE` | Area → Device | Omitted if the device has no area (FR-006). |
| `HAS_ENTITY` | Device → Entity | Omitted if the entity has no device (directly-provided entities). |
| `IN_DOMAIN` | Entity → Domain | Always present — every entity has a domain. |
| `PROVIDED_BY` | Entity → Integration | Omitted only if the source integration cannot be determined. |
| `HAS_LABEL` | Entity → Label | Zero or more per entity; only when label registry data exists. |
| `REFERENCES` | Automation → Entity | One relationship per entity referenced by the automation's configuration. |
| `CONTROLS` | Scene → Entity | One relationship per entity the scene sets state for. |
| `REFERENCES` | Script → Entity | One relationship per entity referenced by the script's configuration. |

All relationships carry `source` and `updated_at` properties mirroring the write that created/last touched them.

## Validation rules summary

- Every node write is a `MERGE` keyed on `ha_id` within its label — never a blind `CREATE` (Constitution Principle III/VI).
- Missing optional relationships (Area↔Floor, Device↔Area, Entity↔Device, Entity↔Label, Entity↔Integration) are valid end states, not errors (FR-006).
- `OntologySchema.version` is compared, never silently overwritten, on startup (FR-017; see research.md §7).
- Rebuild/resync operations MUST NOT delete or overwrite any node/relationship with `source` other than `home_assistant`/`generated` that the integration itself owns (FR-017a).
