# Implementation Plan: Interactive Ontology Graph Visualization

**Branch**: `005-ontology-graph-visualization` | **Date**: 2026-08-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-ontology-graph-visualization/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command; its definition describes the execution workflow.

## Summary

Extend the existing Ontology Explorer panel with an area-first Cytoscape.js graph that uses Home Assistant icons, bounded incremental expansion, filtering, details, and live updates. The browser remains inside Home Assistant's authenticated WebSocket boundary and submits named read operations to a `GraphGateway`. The gateway selects an authenticated add-on GraphQL backend when discovered/configured or an equivalent fixed read-only Cypher backend over the integration's existing Memgraph connection. The add-on optionally hosts Memgraph Lab behind Supervisor ingress for administrators; Lab is enabled only when add-on-owned probes verify Enterprise `readonly` authorization.

## Technical Context

**Language/Version**: Python 3.13 in Home Assistant (repository tooling permits 3.11+); browser-native JavaScript ES modules; Node.js 22 LTS for the add-on GraphQL service

**Primary Dependencies**: Home Assistant `websocket_api` and `panel_custom`; `neo4j>=5.0`; an exactly pinned Cytoscape.js 3.x release vendored with the integration; exactly pinned Node `graphql`, `@apollo/server`, and `neo4j-driver` packages; exactly pinned Memgraph 3.12.x and Memgraph Lab image digests verified for amd64/aarch64

**Storage**: Existing Memgraph property graph and `/data` durability volume; graph view state remains browser-session memory only; no second database

**Testing**: `pytest-homeassistant-custom-component` for unit/contract tests; Testcontainers with real Memgraph for integration/performance/security tests; Node test runner for GraphQL resolvers; Playwright for desktop/mobile panel behavior, accessibility, live updates, and nonblank canvas checks; add-on container health/smoke tests where Docker is available

**Target Platform**: Home Assistant OS/Supervised with the project add-on and Home Assistant Container/Core with an externally reachable Memgraph service, targeting an 8 GB host and modern Home Assistant-supported desktop/mobile browsers

**Project Type**: Home Assistant custom integration plus a browser panel and one multi-process Home Assistant add-on

**Performance Goals**: Initial useful graph visible within 3 seconds at p95 for a 5,000-node ontology; 95% of visible changes shown within 5 seconds; 100 changes over 10 seconds converge within 10 seconds while controls remain responsive

**Constraints**: Local-only normal operation; no browser-to-Memgraph or browser-to-GraphQL connection; add-on GraphQL binds to the internal add-on network on port 4000, is never host-published, and requires a locally generated bearer token; direct-backend operations are fixed, bounded, and parameterized; credentials and sensitive properties never reach browser responses; visualization failures cannot block Home Assistant or ontology synchronization; Lab requires verified Enterprise `readonly` authorization and is unavailable otherwise

**Scale/Scope**: One existing Ontology panel, 5,000 ontology nodes, area/device initial view, one-hop expansion, one browser subscription per open panel, one selected backend per config entry, and an optional single add-on deployment containing Memgraph, GraphQL, Lab, and process supervision

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Research Gate

| Principle | Result | Plan Evidence |
|-----------|--------|---------------|
| I. Home Assistant Native Integration First | PASS | Extends `custom_components/ontology`, the existing config entry, panel, and authenticated WebSocket API. |
| II. Local-First and Privacy-Preserving | PASS | All services run on the HA host; gateway responses use a property allowlist and existing redaction rules. |
| III. Memgraph and Cypher Foundation | PASS | Both backends reuse the configured Memgraph database and issue the same fixed parameterized read-only Cypher operations. |
| IV. Async, Non-Blocking Runtime | PASS | Graph calls are bounded async I/O; update bursts are coalesced; component failures degrade the panel only. |
| V. Source Separation | PASS | Visualization does not mutate generated, inferred, or user-managed graph data. |
| VI. Schema Versioning | PASS | No ontology schema mutation is required; presentation contracts are independently versioned. |
| VII. Tests Before Confident Implementation | PASS | Contract, security, integration, performance, browser, and add-on smoke tests are planned. |
| VIII. Observable and Repairable | PASS | Gateway/Lab availability, update revision, reconnect count, latency, truncation, and rejected access are exposed through diagnostics/logging without secrets. |
| IX. Incremental Delivery | PASS | Delivery separates graph contracts, backend gateway, static graph, live updates, add-on GraphQL, and gated Lab. |
| X. Safe Query Surfaces | PASS | Browser operations are named queries; neither backend accepts query text; GraphQL has no mutations/arbitrary Cypher; Lab uses database-enforced `readonly` privileges and fails closed. |
| Compatibility Requirements | PASS | The GraphQL backend is optional; the direct backend preserves Container/Core and externally configured Memgraph support. |

### Post-Design Gate

PASS. The Phase 1 contracts preserve every pre-research gate. Both backends implement one bounded presentation contract, the GraphQL transport is authenticated and internal-only, and Lab secrets/probes remain add-on-owned. The integration consumes only sanitized Lab capability state and fails closed before presenting a launch action.

## Project Structure

### Documentation (this feature)

```text
specs/005-ontology-graph-visualization/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── graphql-schema.graphql
│   ├── backend-transport.md
│   ├── websocket-api.md
│   └── lab-access.md
└── tasks.md
```

### Source Code (repository root)

```text
custom_components/ontology/
├── __init__.py
├── const.py
├── coordinator.py
├── graph_gateway.py
├── graph_backends.py
├── lab_access.py
├── websocket_api.py
└── panel/
    ├── ontology-panel.js
    ├── ontology-graph.js
    ├── ontology-icons.js
    └── vendor/
        └── cytoscape.esm.min.js

memgraph_addon/
├── Dockerfile
├── config.yaml
├── run.sh
├── healthcheck.sh
├── supervisor.conf
└── graphql/
    ├── package.json
    ├── package-lock.json
    ├── schema.graphql
    ├── server.js
    └── resolvers.js

tests/
├── contract/
│   ├── test_graph_gateway_contract.py
│   ├── test_graph_backend_contract.py
│   ├── test_graph_websocket_contract.py
│   └── test_lab_access_contract.py
├── integration/
│   ├── test_graph_visualization_performance.py
│   ├── test_graphql_transport.py
│   ├── test_graph_gateway_lifecycle.py
│   ├── test_addon_secret_lifecycle.py
│   ├── test_graph_live_updates.py
│   └── test_graph_read_only_security.py
├── unit/
│   ├── test_graph_gateway.py
│   └── test_graph_change_batching.py
└── browser/
    └── ontology-graph.spec.js
```

**Structure Decision**: Keep the custom graph, user authorization, gateway, and common backend contract in the existing integration. Use the add-on GraphQL backend when its authenticated endpoint is discovered/configured; otherwise use fixed read-only operations through the existing `MemgraphClient`. Keep GraphQL and Lab optional inside the single project add-on, with no public GraphQL/Lab ports, second database, frontend build system, or standalone application.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations require justification.
