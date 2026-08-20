# Research: Interactive Ontology Graph Visualization

## 1. Browser Trust Boundary

**Decision**: Keep the browser on Home Assistant's authenticated WebSocket API. The panel sends named operations and variables to a `GraphGateway`, which selects an add-on GraphQL backend when configured or a fixed read-only direct Memgraph backend otherwise. The browser never receives backend locations or credentials.

**Rationale**: The existing panel already uses `hass.callWS`, and Home Assistant supplies user identity and lifecycle handling there. This satisfies the clarified gateway requirement without adding browser-managed credentials or exposing an add-on port.

**Alternatives considered**:

- Direct browser-to-GraphQL access: rejected because it bypasses Home Assistant authorization and exposes an internal service.
- Direct browser-to-Bolt access: rejected because it exposes database connectivity and cannot satisfy the credential boundary.
- A new public HTTP API: rejected because it duplicates Home Assistant authentication and increases attack surface.
- Requiring the add-on GraphQL service: rejected because the constitution requires Container/Core and externally reachable Memgraph compatibility.

## 2. Backend Contract and GraphQL Shape

**Decision**: Define one `GraphBackend` contract for snapshot, expansion, search, detail, and health operations. `AddonGraphQLBackend` maps those operations to a small Query-only GraphQL schema; `DirectMemgraphBackend` executes equivalent fixed, bounded, parameterized Cypher through the existing client. Neither accepts caller-provided GraphQL or Cypher text.

**Rationale**: The shared contract keeps behavior identical across installation types. A custom query-only GraphQL adapter avoids generated mutations, while the direct adapter preserves constitution-required compatibility when no add-on service exists.

**Alternatives considered**:

- Generated Neo4j GraphQL schema: rejected because generated mutations and broad filtering exceed the feature's read-only needs.
- GraphQL in Home Assistant Core: rejected because GraphQL belongs in the project add-on while Core needs only the common gateway and direct compatibility adapter.
- REST endpoints: rejected because GraphQL is an explicit feature constraint.

## 3. Automatic Update Transport

**Decision**: Publish sanitized graph-change envelopes from the coordinator only after successful ontology writes. A Home Assistant WebSocket subscription coalesces envelopes per open panel. The panel applies topology changes incrementally and refetches only currently visible properties through named gateway operations. Reconnection compares a monotonic in-memory revision and requests a bounded snapshot when revisions cannot be bridged.

**Rationale**: Home Assistant already owns the change signals that write the graph. Reusing them avoids polling and database change-data-capture complexity while preserving the clarified visible-property boundary.

**Alternatives considered**:

- Polling GraphQL: rejected because it wastes resources and weakens the five-second freshness target.
- Memgraph triggers or CDC: rejected because they add schema/runtime coupling and do not carry Home Assistant user context.
- Streaming every changed property: rejected because unloaded property churn is explicitly out of scope.

## 4. Cytoscape.js Integration

**Decision**: Vendor a pinned Cytoscape.js 3.x ES module under the integration's static panel directory. Use `cy.add`, collection data updates, and `cy.remove` inside batched operations. Preserve positions for existing nodes, lay out only newly expanded nodes, and restore selection/viewport after reconciliation.

**Rationale**: Cytoscape supports incremental element operations, interaction events, layouts, selection, and background images without requiring a frontend build system. Vendoring preserves local-only operation and deterministic HACS packaging.

**Alternatives considered**:

- CDN import: rejected because normal operation must not require internet access.
- A new npm frontend build: rejected because the existing panel is a dependency-free ES module and the added pipeline is unnecessary.
- Full graph replacement per update: rejected because it loses user context and becomes expensive at scale.

## 5. Initial Graph and Expansion Limits

**Decision**: The initial operation returns all areas and directly assigned devices up to 500 nodes and 1,000 edges. Devices without an area are attached to a client-created `presentation:unassigned` compound/group node that is never returned to or persisted in Memgraph. One-hop expansion defaults to 100 new nodes and 250 edges, with hard maxima of 250 nodes and 500 edges per request. Search defaults to 50 and has a hard maximum of 100.

**Rationale**: These limits bound memory and layout work on the target 8 GB host, while the area-first view remains immediately useful. Every response includes truncation metadata and a continuation cursor where applicable.

**Alternatives considered**:

- Load all 5,000 nodes initially: rejected because layout and rendering would undermine the three-second target.
- Empty initial canvas: rejected by clarification.
- Persist an `Unassigned` area: rejected because it would falsify ontology data.

## 6. Home Assistant Icons and Accessibility

**Decision**: Resolve icon names from safe node properties and current Home Assistant entity metadata, then render the corresponding bundled Material Design icon path in Cytoscape. Use deterministic type fallbacks. Do not encode type or status by color alone; expose a synchronized keyboard-operable result/tree list and textual details alongside the canvas.

**Rationale**: Canvas graph nodes are not sufficient as the only accessible representation. A synchronized semantic list preserves keyboard and screen-reader access while native icons make the graph familiar.

**Alternatives considered**:

- Remote icon images: rejected by local-only and reliability constraints.
- Text initials only: rejected because native icons are an explicit requirement.
- Canvas-only interaction: rejected because it leaves critical journeys inaccessible.

## 7. Add-on Process Model

**Decision**: Preserve one Home Assistant add-on deployment and one Memgraph database. Build a pinned multi-stage image that contains Memgraph, the Node GraphQL service, Memgraph Lab runtime, and a lightweight process supervisor. Persist only Memgraph data and required generated secrets under `/data`; do not expose GraphQL or Lab host ports. Provide an aggregate health check while keeping Memgraph startup independent of optional visualization services.

**Rationale**: The existing `run.sh` uses `exec` for one process, so three services require explicit child supervision, signal forwarding, and failure policy. GraphQL/Lab failure must not terminate Memgraph or block Home Assistant.

**Alternatives considered**:

- Separate add-ons/containers: rejected by the single-deployment requirement.
- Background shell jobs without supervision: rejected because failures and shutdown would be unreliable.
- Replace the database with another graph platform: prohibited by the constitution.

## 7a. Authenticated GraphQL Transport

**Decision**: Bind GraphQL to the add-on network interface on internal port 4000 without a host port mapping. Generate a random bearer token under `/data` with owner-only permissions. Extend Supervisor discovery with the internal URL and token; manual configuration may provide optional GraphQL connection values. Every request requires the bearer token and a timeout. Missing/invalid authentication is rejected and never falls back within the GraphQL process.

**Rationale**: Home Assistant Core and the add-on are separate network peers, so loopback cannot connect them. Internal networking plus application authentication gives Core a reachable backend without exposing it to browsers or the host network.

**Alternatives considered**:

- Loopback-only GraphQL: rejected because Home Assistant Core runs outside the add-on container.
- Publish port 4000 on the host: rejected because it increases attack surface and bypasses the intended internal boundary.
- Trust add-on-network location without a token: rejected because network placement alone is not authentication.

## 8. Memgraph Lab Read-only Enforcement

**Decision**: Keep the dedicated Lab credential and all Enterprise/read/write/sentinel probes inside the add-on. Expose only sanitized `LabCapability` state through authenticated internal GraphQL. If checks fail, Lab remains stopped or inaccessible and the custom graph remains available.

**Rationale**: Official Memgraph documentation states that Community supports user authentication but not authorization, while clause privileges and the `readonly` role are Enterprise capabilities. Lab is a full Bolt query console and can execute writes. Query-text filtering or admin-only UI visibility cannot provide the constitution's database-enforced read-only guarantee.

**Alternatives considered**:

- Run Lab against Community with no credentials: rejected because all writes are allowed.
- Filter Cypher strings in a reverse proxy: rejected because Bolt/Cypher parsing and procedure behavior make this incomplete and unsafe.
- Allow administrators to write: rejected by FR-020 and Constitution Principle X.
- Add a read-only replica: rejected because it adds a second database process and operational complexity.

## 9. Lab Presentation and Authorization

**Decision**: Serve Lab through Supervisor ingress with admin-only metadata and no published host port. The integration's `lab_access.py` consumes only sanitized capability state from `AddonGraphQLBackend`; it never reads add-on `/data` or receives the Lab password. The Explorer renders the launch action only for administrators after a ready capability result.

**Rationale**: Supervisor ingress handles local routing, Home Assistant authentication, base paths, HTTP, and WebSockets. Backend admin checks and database authorization remain authoritative; frontend visibility is convenience only.

**Alternatives considered**:

- Expose Lab port 3000: rejected because it bypasses Home Assistant access control.
- Embed an unauthenticated Lab iframe: rejected because direct access could be shared or guessed.
- Implement a second custom advanced workspace: rejected because Memgraph Lab is explicitly required.

## 10. Observability and Failure Recovery

**Decision**: Track GraphQL health/latency, Lab capability state, current graph revision, active graph subscriptions, coalesced update counts, reconnect/reconcile counts, truncated response counts, and rejected Lab access. Log only operation names, counts, durations, and error categories. Surface unavailable/stale states in the panel and include sanitized status in diagnostics.

**Rationale**: The feature spans three processes and a browser connection. Operators need to distinguish database, gateway, Lab, and subscription failures without exposing graph data or credentials.

**Alternatives considered**:

- Container logs only: rejected because the constitution requires Home Assistant-native diagnostics.
- Raw GraphQL/Cypher logging: rejected because queries and parameters may expose home metadata.

## Resolved Unknowns

All Technical Context unknowns are resolved. Exact package/image versions, digests, licenses, and amd64/aarch64 availability must be recorded during setup before implementation dependencies are accepted.