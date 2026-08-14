# Shared Read Operation Contract

All services, Assist intents, MCP tools, and context projections delegate to the same functions in `query_tools.py`. Transport adapters may render or serialize a result but may not change resolution, thresholds, freshness, bounds, warnings, redaction, or outcome.

## Envelope

```json
{
  "target": "garage motion sensor",
  "result_type": "automation_dependencies",
  "outcome": "ok",
  "result": {},
  "warnings": []
}
```

`outcome` is one of:
- `ok`: a resolved or untargeted operation returned one or more records.
- `empty`: the operation succeeded but no records qualify.
- `not_found`: no eligible target resolved.
- `ambiguous`: more than one eligible exact-name candidate resolved; `result.candidates` is bounded.
- `degraded`: Memgraph or another required local dependency is unavailable.

Existing keys and existing `result_type` meanings remain backward compatible. Errors expose sanitized categories, never raw exception messages.

## Target resolution

Resolution is operation-aware and deterministic:
1. Match an eligible exact stable ID.
2. Otherwise match case-insensitive exact display names among eligible target types.
3. One name match resolves; zero returns `not_found`; multiple return `ambiguous`.

Candidates are ordered by target type, normalized display name, then stable ID and are limited by the configured result bound. No operation selects the first ambiguous match.

## Operations

### `low_battery_areas`

Input:

| Field | Type | Default | Validation |
|---|---|---:|---|
| `threshold_percentage` | number | configured value, initially 20 | 1 through 100 |
| `max_age_hours` | number | configured value, initially 24 | greater than 0 |
| `limit` | integer | configured bound | 1 through configured maximum |

Returns areas ordered by normalized area name and stable ID. A reading qualifies only when available, fresh, and `battery_percentage < threshold_percentage`. Devices appear once while retaining each qualifying measurement. Direct area entities remain visible. Known unavailable or indeterminate measurements contribute to a bounded warning count.

### `active_consumers`

Input:

| Field | Type | Default | Validation |
|---|---|---:|---|
| `threshold_watts` | number | configured value, initially 1 | finite and at least 0 |
| `max_age_hours` | number | configured value, initially 24 | greater than 0 |
| `limit` | integer | configured bound | 1 through configured maximum |

A reading qualifies only when available, fresh, `power_watts > threshold_watts`, and effective energy role is `consumer`. User role overrides inferred role. Devices appear once and retain individual measurement records; overlapping readings are not summed.

The result also includes `known_consumers_without_current_power`: devices with
consumer-role cumulative `energy` entities but no qualifying current power
reading. These records identify known electricity consumers without claiming
that a daily or monthly energy total proves they are active now.

### `automation_dependencies`

Input: `target` string plus optional `limit`.

Eligible targets are Entity and Device. A Device result is the de-duplicated union of automations connected to all its current entities. Each automation includes the stable entity IDs and relationship types establishing the dependency.

### `supplied_targets`

Input: `cylinder` string plus optional `limit`.

Eligible targets are canonical GasCylinder assets. Results include only explicit user-managed `SupplyAssociation` statements whose target currently resolves. An existing cylinder with no associations returns `empty`; unresolved durable associations are reported through warnings and validation rather than fabricated target rows.

### `device_context`

Input: `device` string plus optional `limit`.

Eligible targets are Device nodes. The result includes current area, every associated entity exactly once up to the bound, and the device-level automation dependency union. A resolved device with no associated entities returns `empty`.

## Bounds and ordering

Database queries use fixed-depth parameterized Cypher and fetch at most `effective_limit + 1` rows per bounded stage. The adapter sets `truncated=true` and adds a warning when an extra row proves truncation. Grouped child collections are also bounded. Stable IDs break all display-name ties.

## Redaction

The complete envelope passes once through the existing recursive redactor after result assembly. Target strings, names, warnings, candidates, and nested explanatory fields are covered. Redaction never changes stable envelope keys or numeric measurements.
