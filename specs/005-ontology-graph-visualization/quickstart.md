# Quickstart: Validate Interactive Ontology Graph Visualization

## Prerequisites

- Home Assistant development environment with the Ontology integration configured.
- Existing Memgraph add-on or a local Memgraph 3.12.x test container.
- Python environment restored from `pyproject.toml`.
- Node.js 22 for GraphQL contract tests.
- Docker for real add-on and Memgraph integration tests.
- Playwright browser dependencies for UI validation.
- Memgraph Enterprise authorization and a test license only for the positive Lab scenario; Community is expected to exercise the fail-closed scenario.

See [data-model.md](data-model.md), [backend-transport.md](contracts/backend-transport.md), [graphql-schema.graphql](contracts/graphql-schema.graphql), [websocket-api.md](contracts/websocket-api.md), and [lab-access.md](contracts/lab-access.md) for expected shapes and limits.

## 1. Run Existing Regression Tests

```powershell
.\scripts\test-windows.ps1 tests\contract\test_websocket_api_contract.py tests\integration\test_websocket_api_performance.py
```

Expected: existing Ontology Explorer contracts and the 5,000-node performance baseline still pass.

## 2. Validate Graph Contracts and Security

```powershell
.\scripts\test-windows.ps1 tests\unit\test_graph_gateway.py tests\unit\test_graph_change_batching.py tests\contract\test_graph_gateway_contract.py tests\contract\test_graph_websocket_contract.py tests\contract\test_lab_access_contract.py
```

Expected:

- Named operations map to fixed GraphQL documents.
- Limits and input validation are enforced.
- Responses contain no credentials or sensitive properties.
- Non-admin Lab requests are denied.
- No GraphQL mutation or arbitrary Cypher field is available.

## 3. Validate the Internal GraphQL Service

```powershell
Push-Location memgraph_addon\graphql
npm ci
npm test
Pop-Location
```

Expected: schema tests prove there is no `Mutation` root, resolver tests use parameterized read-only Cypher, and all page limits are bounded.

## 3a. Validate Both Backend Modes

```powershell
.\scripts\test-windows.ps1 tests\contract\test_graph_backend_contract.py tests\integration\test_graphql_transport.py tests\integration\test_graph_gateway_lifecycle.py
```

Expected: GraphQL and direct Memgraph backends return equivalent bounded records; cross-container GraphQL requires its bearer token; direct/external Memgraph works without Supervisor; setup, reload, unload, and unavailable behavior do not interrupt ontology sync.

## 4. Run Real Memgraph Integration Tests

```powershell
.\scripts\test-windows.ps1 tests\integration\test_graph_visualization_performance.py tests\integration\test_graph_live_updates.py tests\integration\test_graph_read_only_security.py
```

Expected:

- Initial area/device graph meets the 3-second p95 target on the 5,000-node fixture.
- Visible updates arrive within 5 seconds and burst convergence meets the 10-second target.
- Mutation attempts through every custom graph surface are rejected with no database change.

## 5. Build and Smoke-test the Add-on

```powershell
docker build -t hass-ontology-memgraph:test memgraph_addon
docker run --rm --name hass-ontology-memgraph-test -p 7687:7687 hass-ontology-memgraph:test
```

Run the container only in a disposable environment. Validate the aggregate health endpoint separately while the process is running.

Expected:

- Memgraph becomes healthy independently.
- GraphQL and Lab internal processes report their own status.
- Stopping GraphQL or Lab does not terminate Memgraph.
- GraphQL and Lab ports are not published by the production add-on configuration.
- GraphQL is reachable from the Home Assistant network peer only with the add-on-generated bearer token.

## 6. Validate Lab Fail-closed Behavior

### Community

Start the add-on with Community authorization capabilities.

Expected: the custom graph works; `ontology/lab_status` returns `available: false` with `enterprise_required`; no Lab launch action or reachable public port exists.

### Enterprise Read-only

In a disposable licensed test environment, configure the dedicated Lab user with the `readonly` role and restart the add-on.

Expected: both capability probes pass, administrators receive an ingress launch action, non-administrators remain denied, read queries work, and create/update/delete attempts fail without graph changes.

Validate owner-only secret permissions, restart persistence, rotation, non-disclosure, ingress base paths, and ingress WebSockets with `tests/integration/test_addon_secret_lifecycle.py` and `tests/contract/test_memgraph_addon_processes.py`.

## 7. Browser Validation

Start Home Assistant and run the browser suite against its local URL:

```powershell
npx playwright test tests\browser\ontology-graph.spec.js
```

Required viewports: 1440x900 desktop and 390x844 mobile.

Expected:

- Canvas pixel checks prove the graph is nonblank.
- Initial view contains areas, assigned devices, and a presentation-only Unassigned group where needed.
- Search, selection, expansion, filters, pan, zoom, fit, and reset work.
- Home Assistant icons and deterministic fallbacks render.
- Keyboard users can complete search, select, inspect, and expand through the synchronized semantic list.
- Controls and details do not overlap at either viewport.
- Selection and viewport survive incremental updates.
- Disconnect shows stale state; reconnect reconciles missed changes.

## 8. Final Quality Gate

```powershell
.\scripts\test-windows.ps1
```

Expected: the full Python suite passes. Also run Node, browser, and Docker checks above because they are separate toolchains and are not implied by the Python test script.

## 9. Validate First-time-user Success

Use at least 10 participants who have not previously used the Ontology Explorer graph. Give each participant the same representative fixture containing at least three areas, assigned devices, and expandable entities.

Protocol:

1. Start the participant on the Home Assistant overview with no written graph instructions.
2. Ask them to open the Ontology Explorer, identify a named area, and trace it to a specified device and entity without using a query.
3. Start timing with the request and stop when the participant correctly identifies all three objects.
4. Record completion, elapsed time, query usage, and any facilitator intervention without recording personal data.
5. Count success only when completion takes at most two minutes with no query or intervention.
6. Calculate `successful participants / total participants * 100`.

Expected: at least 90% succeed. With the minimum cohort of 10, at least 9 participants must succeed. Record anonymized aggregate results with the quickstart execution evidence.