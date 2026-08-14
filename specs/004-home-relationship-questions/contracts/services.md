# Home Assistant Service Contract

Service responses use the [shared read operation contract](./read-operations.md). Existing services remain available; `device_context` and `automation_dependencies` gain deterministic ambiguity handling.

## Read services

| Service | Required fields | Optional fields |
|---|---|---|
| `ontology.low_battery_areas` | none | `threshold_percentage`, `max_age_hours`, `limit` |
| `ontology.active_consumers` | none | `threshold_watts`, `max_age_hours`, `limit` |
| `ontology.automation_dependencies` | `target` | `limit` |
| `ontology.supplied_targets` | `cylinder` | `limit` |
| `ontology.device_context` | `device` | `limit` |

Read services are authenticated and return response data. Threshold and age overrides are validated before query execution and do not alter integration options or graph data.

## Administrator mutation services

The integration registers these with Home Assistant's native administrator-service helper. A non-administrator call is rejected before any graph write.

### `ontology.create_supply_association`

Fields:

| Field | Type | Rules |
|---|---|---|
| `cylinder` | string | Required; uniquely resolves to one GasCylinder. |
| `target_type` | enum | Required; `device` or `entity`. |
| `target` | string | Required; uniquely resolves within `target_type`. |

Returns the durable statement. Repeating the same source/target upserts the same stable identity. Not-found or ambiguous input performs no write.

### `ontology.list_supply_associations`

Optional `limit`. Returns durable statements, including `resolved_source` and `resolved_target` flags. This administration response may expose stable IDs required for repair.

### `ontology.delete_supply_association`

Requires `association_id`. Deleting an unknown ID returns `not_found`; deletion is idempotent from the graph's perspective and removes the durable statement and generated bindings atomically.

### `ontology.set_energy_role`

Requires `entity` and `role`. `entity` must uniquely resolve to a power-measurement entity; `role` is one of `consumer`, `producer`, `storage`, `grid_import`, or `grid_export`. The service upserts the user assignment and returns the effective role.

### `ontology.delete_energy_role`

Requires `entity`. Deletes only the user assignment. Any inferred assignment becomes effective after reconciliation.

### `ontology.export_user_knowledge`

No required fields. Returns version 2 of [the user-knowledge schema](./user-managed-knowledge.schema.json), including semantic overrides, supply associations, and energy-role assignments.

### `ontology.import_user_knowledge`

Requires object `payload`. Accepts version 2 and legacy override-only version 1. It validates the entire document, then atomically merge/upserts supplied records while preserving omitted local records. Any validation or write failure changes nothing and returns a sanitized category.

## Failure behavior

Every service returns or raises an existing Home Assistant service error category suitable for the call. User-visible text may distinguish invalid input, not found, ambiguity, unauthorized, and unavailable dependency. It never includes credentials, tokens, arbitrary state attributes, or raw exception text.
