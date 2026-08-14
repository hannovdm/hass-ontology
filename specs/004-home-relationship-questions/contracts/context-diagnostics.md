# Context Export, Validation, Audit, and Diagnostics Contract

## Context export

Existing export types remain compatible. Device, entity, and whole-home projections may include only these new allow-listed fields where relevant:

- `measurement_kind`
- `measurement_status`
- `battery_percentage`
- `power_watts`
- `device_class`
- `unit_of_measurement`
- `measurement_last_updated`
- effective `energy_role` and `energy_role_source`
- resolved user-managed supply associations

Exports do not include arbitrary Home Assistant attributes, historical readings, raw statement timestamps unless needed for administration, credentials, tokens, or raw exceptions. The fully assembled structure passes through recursive redaction.

## Validation

Validation adds these stable finding types:

| Finding | Trigger | Target |
|---|---|---|
| `unresolved_supply_source` | Association has no current GasCylinder binding. | SupplyAssociation ID |
| `unresolved_supply_target` | Association has no current Device/Entity binding. | SupplyAssociation ID |
| `unresolved_energy_role_entity` | Assignment has no current Entity binding. | EnergyRoleAssignment ID |

Validation never deletes durable user knowledge. A later endpoint return and reconciliation clears the corresponding finding.

## Audit

For each read or administrator mutation, audit may retain:
- operation name
- channel (`service`, `assist`, `mcp`, or internal administration)
- outcome
- bounded result count
- truncation flag
- UTC timestamp
- sanitized error category

Audit must not retain raw utterances, target names/IDs, measurement values, access tokens, credentials, arbitrary state attributes, payload bodies, or exception messages.

## Diagnostics

Diagnostics may expose aggregate counts for:
- measurement kind and status
- fresh/stale measurements by kind
- effective role and unresolved-role status
- supply association resolved/unresolved status
- operation and outcome
- sanitized error category

Diagnostics exclude individual measurements, names, stable target IDs, import/export payloads, raw queries, and exception messages. Existing endpoint enabled/authentication health and Memgraph connection health remain available in their current aggregate form.
