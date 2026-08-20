# Data Model: Interactive Ontology Graph Visualization

## Scope

This feature does not add persisted ontology labels or relationships. It defines versioned presentation records derived from the existing Memgraph graph plus ephemeral browser state.

## Graph Backend

One config-entry-scoped interface implemented by:

- **AddonGraphQLBackend**: authenticated calls to the discovered/configured internal GraphQL endpoint.
- **DirectMemgraphBackend**: the same fixed operations over the existing `MemgraphClient` when GraphQL is absent or explicitly disabled.

Both return identical Graph Slice records and enforce the same bounds, stable IDs, allowlists, redaction, and error categories. Backend selection is configuration-driven; request failures do not silently switch backends mid-request.

## Graph Node

Represents one persisted ontology node safe for visualization.

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| `id` | string | yes | Stable presentation ID composed from canonical label and `ha_id`; never use a transient internal database ID as the sole identity. |
| `haId` | string | yes | Existing stable Home Assistant/ontology identifier. |
| `type` | enum | yes | Canonical node type such as `Area`, `Device`, `Entity`, `Automation`, `Dashboard`, `SemanticType`, or `ValidationFinding`. Unknown labels map to `Other`. |
| `label` | string | yes | Human-readable display value; falls back to `haId`. Maximum 256 characters. |
| `icon` | string | no | Valid Home Assistant icon name from safe graph/entity metadata; invalid values are omitted and resolved to a type fallback. |
| `state` | string | no | Current visible state only when requested and safe. Maximum 256 characters. |
| `unavailable` | boolean | yes | Indicates unavailable/unknown current state. |
| `findingSeverity` | enum | no | `info`, `warning`, `error`, or `critical` for validation findings. |
| `properties` | list of Graph Property | yes | Allowlisted, redacted display properties only. |

### Validation

- Reject IDs or labels containing control characters.
- Exclude credentials, tokens, passwords, secrets, connection fields, and properties rejected by existing redaction rules.
- Bound property count to 25 per node and serialized response values to 2 KiB each.

## Graph Relationship

Represents one persisted ontology relationship safe for visualization.

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| `id` | string | yes | Deterministic from relationship type, endpoints, and stable discriminator where parallel edges exist. |
| `type` | string | yes | Existing relationship type; maximum 128 characters. |
| `source` | string | yes | Graph Node `id`. |
| `target` | string | yes | Graph Node `id`. |
| `directed` | boolean | yes | True when ontology direction carries meaning. |
| `sourceClass` | enum | no | `home_assistant`, `generated`, `inferred`, or `user`. |
| `properties` | list of Graph Property | yes | Allowlisted, redacted relationship properties. |

### Validation

- Both endpoints must occur in the same Graph Slice response or already exist in the client's loaded graph.
- Unknown relationship types remain visible with a generic style.
- Self-references and parallel relationships remain distinct.

## Graph Property

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| `name` | string | yes | Allowlisted property name. |
| `value` | scalar string/number/boolean/null | yes | JSON-compatible and redacted. |
| `displayValue` | string | yes | Localized-safe string representation bounded to 2 KiB. |

## Graph Slice

Bounded response for initial load, search context, expansion, detail, or reconciliation.

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| `nodes` | list of Graph Node | yes | Deduplicated by `id`. |
| `relationships` | list of Graph Relationship | yes | Deduplicated by `id`. |
| `truncated` | boolean | yes | True when additional matching records exist. |
| `nextCursor` | string | no | Opaque continuation token; expires with revision changes. |
| `revision` | non-negative integer | yes | Current integration graph revision. |

## Graph Change Envelope

Sanitized notification emitted after successful graph writes.

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| `revision` | non-negative integer | yes | Strictly increases within one integration runtime. |
| `kind` | enum | yes | `upsert`, `remove`, or `reconcile`. |
| `nodeIds` | list of string | yes | Stable IDs affected by topology or currently visible properties. |
| `relationshipIds` | list of string | yes | Stable relationship IDs affected. |
| `changedProperties` | list of string | yes | Property names only; no values. |
| `occurredAt` | timestamp | yes | UTC event time. |

### State Transitions

```text
connected/current -> change received -> applying -> connected/current
connected/current -> transport lost -> stale/reconnecting
stale/reconnecting -> revision bridge available -> applying -> connected/current
stale/reconnecting -> bridge unavailable -> reconciling snapshot -> connected/current
any state -> gateway unavailable -> unavailable/retrying
```

## Graph View State

Ephemeral browser-session state; never persisted in Memgraph.

| Field | Type | Rules |
|-------|------|-------|
| `viewport` | pan/zoom tuple | Preserve across incremental updates. |
| `selectedId` | string/null | Clear with notice when removed. |
| `nodeTypes` | set | Active node filters. |
| `relationshipTypes` | set | Active relationship filters. |
| `expandedNodeIds` | set | Loaded one-hop neighborhoods. |
| `revision` | integer | Last fully applied revision. |
| `connectionState` | enum | `loading`, `current`, `stale`, `reconciling`, `unavailable`. |

## Presentation-only Unassigned Group

The client creates one synthetic group with ID `presentation:unassigned` when at least one initial device has no area.

- It is visually and textually marked as presentation-only.
- It is never returned as a persisted Graph Node by GraphQL.
- It is never sent to a mutation surface, because no mutation surface exists.
- Synthetic membership edges exist only in Graph View State and never in Memgraph.

## Lab Capability

| Field | Type | Required | Rules |
|-------|------|----------|-------|
| `available` | boolean | yes | True only after all capability probes pass. |
| `reason` | enum | yes | `ready`, `not_addon_backend`, `transport_unavailable`, `lab_unhealthy`, `enterprise_required`, `readonly_user_missing`, or `write_probe_succeeded`. Non-administrators are rejected by the Home Assistant WebSocket authorization layer before this model is returned. |
| `ingressPath` | string | no | Returned only to an authenticated Home Assistant administrator when available. |
| `checkedAt` | timestamp | yes | UTC capability-check time. |

### Capability State Transitions

```text
unknown -> probing -> ready
unknown -> probing -> unavailable
ready -> health/auth failure -> unavailable
unavailable -> scheduled/admin retry -> probing
```

The add-on owns credential and probe state. Home Assistant receives this model only through authenticated GraphQL and never receives the Lab password.