# Graph Backend and Transport Contract

## Common Operations

`GraphGateway` exposes only named `initial_graph`, `expand_node`, `search_graph`, `graph_element`, and `graph_health` operations. Both backends return the records and limits in `data-model.md` and never accept arbitrary GraphQL or Cypher text.

## Add-on GraphQL Backend

- GraphQL listens on the add-on network interface at internal port 4000.
- Production add-on configuration MUST NOT publish port 4000 to the host.
- The add-on generates a random bearer token under `/data` with mode `0600`.
- Supervisor discovery includes `graphql_url` and `graphql_token` in the integration discovery payload; manual configuration may provide them as optional advanced fields.
- Every request uses `Authorization: Bearer <token>`, a bounded body size, and a timeout.
- Missing/invalid tokens return an authentication error before GraphQL execution.
- Home Assistant stores connection data in the config entry and never returns it through WebSocket, diagnostics, logs, or panel state.
- Cross-container tests MUST prove Home Assistant can reach the service while browser and unauthenticated requests cannot.

## Direct Memgraph Backend

- Selected when no GraphQL endpoint is configured or when explicitly disabled.
- Uses the config entry's existing `MemgraphClient` and fixed parameterized read-only Cypher owned by the integration.
- Implements exactly the same bounds, stable IDs, redaction, pagination, and errors as the GraphQL backend.
- Does not provide Lab capability; `LabCapability.reason` is `not_addon_backend`.

## Selection and Failure

- Select one backend when the config entry is set up; do not switch silently during a request.
- A GraphQL authentication or availability failure produces `gateway_unavailable` and an actionable repair/reconfigure path.
- Reloading a config entry closes the old backend and constructs the newly configured backend.
- Backend failure never prevents core ontology synchronization through the existing Memgraph client.