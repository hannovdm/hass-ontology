# Home Assistant WebSocket Contract

All commands require an authenticated Home Assistant WebSocket connection. The browser sends operation names and variables, never a GraphQL document, Cypher text, add-on URL, or database credential.

Commands are backend-neutral. `GraphGateway` selects the configured backend described in `backend-transport.md`; response shapes and limits do not reveal which backend served the request.

## `ontology/graph_snapshot`

Returns the area-first initial graph.

Request:

```json
{"type":"ontology/graph_snapshot","limit":500,"cursor":null}
```

Response fields: `nodes`, `relationships`, `truncated`, `next_cursor`, `revision`.

Rules:

- Default/max node limit: 500.
- Includes areas and directly assigned devices only.
- Area-less devices are returned as devices without a parent; the browser creates the presentation-only Unassigned group.

## `ontology/graph_expand`

Returns one-hop neighbors around a stable node ID.

```json
{"type":"ontology/graph_expand","node_id":"Entity:sensor.kitchen","node_limit":100,"edge_limit":250,"cursor":null}
```

Defaults: 100 nodes and 250 edges. Hard maxima: 250 nodes and 500 edges. Unknown IDs return `not_found`; malformed IDs return `invalid_format`.

## `ontology/graph_search`

Searches loaded and unloaded graph nodes by label or stable identifier.

```json
{"type":"ontology/graph_search","term":"kitchen","limit":50}
```

The trimmed term must contain 1-256 characters. Default limit is 50; hard maximum is 100. Response contains `matches`, `truncated`, and `revision`.

## `ontology/graph_detail`

Returns one safe node or relationship plus bounded direct connections.

```json
{"type":"ontology/graph_detail","element_id":"Device:abc123"}
```

Properties are allowlisted and passed through existing redaction rules. Values are bounded as defined in `data-model.md`.

## `ontology/graph_subscribe`

Subscription command for live graph changes.

```json
{"id":42,"type":"ontology/graph_subscribe","from_revision":120}
```

Events:

```json
{
  "id": 42,
  "event": {
    "revision": 121,
    "kind": "upsert",
    "node_ids": ["Entity:sensor.kitchen"],
    "relationship_ids": [],
    "changed_properties": ["state"],
    "occurred_at": "2026-08-19T12:00:00Z"
  }
}
```

Rules:

- Coalesce rapid changes per element over a 250 ms window and retain latest revision/property names.
- Never send changed property values in events.
- Emit `kind: reconcile` when the requested revision cannot be bridged from the bounded in-memory change buffer.
- Unsubscribe on panel disconnect/unload.

## `ontology/lab_status`

Requires an authenticated administrator. Non-administrators receive `unauthorized` without capability details.

```json
{"type":"ontology/lab_status"}
```

Successful response follows the Lab Capability model. `ingress_path` is present only when `available` is true. Direct/external-Memgraph backends return `not_addon_backend` without disclosing connection details.

## Error Contract

Errors use Home Assistant WebSocket error responses with one of:

- `invalid_format`
- `not_found`
- `result_too_large`
- `gateway_unavailable`
- `stale_cursor`
- `unauthorized`
- `lab_unavailable`

Messages are actionable but contain no graph query text, parameters, credentials, tokens, internal hostnames, or stack traces.