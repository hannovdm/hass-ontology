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

## Execution Record (T063)

Executed 2026-08-21 on a Linux automation sandbox (Python 3.13.1, Node.js 22.23.2, Docker with a real `memgraph/memgraph` container). The Windows commands above were run as their direct `python -m pytest` equivalents because `scripts/test-windows.ps1` only wraps the same pytest invocation with Windows-specific `PYTHONPATH`/`TC_HOST` shims.

| Scenario | Result |
| --- | --- |
| 1. Existing regression tests | Blocked - Home Assistant version gap (see gaps below); `tests/integration/test_websocket_api_performance.py` passed, `tests/contract/test_websocket_api_contract.py` could not set up the entry |
| 2. Graph contracts and security | Passed - 56 tests |
| 3. Internal GraphQL service | Blocked - `npm ci` cannot download packages (see gaps below) |
| 3a. Both backend modes | Passed - 9 tests, after fixing the defect listed below |
| 4. Real Memgraph integration tests | Passed - 14 tests against a real Memgraph container |
| 5. Add-on build and smoke test | Blocked - the GraphQL build stage needs `npm ci`; the previously broken `memgraph/lab` copy path was fixed and verified separately |
| 6. Lab fail-closed behavior | Partially passed - `tests/integration/test_addon_secret_lifecycle.py` and `tests/contract/test_memgraph_addon_processes.py` passed (11 tests); the Community and Enterprise runtime probes need a running add-on and an Enterprise license |
| 7. Browser validation | Blocked - Playwright and its browsers cannot be installed (see gaps below) |
| 8. Final quality gate | Partially passed - 472 passed, 45 failed, 43 errors; 43 failures and all 43 errors are the Home Assistant version gap, leaving the two defects listed below |
| 9. First-time-user success | Not executed - needs at least 10 human participants (see gaps below) |

### SC-001 usability results

The protocol was not executed in this environment because it requires at least 10 first-time human participants and a facilitator, neither of which an automation sandbox can provide. No participant timing or completion data exists yet, so the threshold calculation is `0 successful / 0 total`, which is undefined rather than a pass or a fail. SC-001 therefore remains unvalidated and must be run on a Home Assistant instance with a real cohort; record the anonymized per-participant completion flag, elapsed time, query usage, and intervention flag, then the `successful participants / total participants * 100` result here.

### Defects found and fixed

- `tests/integration/test_graph_gateway_lifecycle.py` did not stub `lab_access.close()`, so unload failed on an un-awaitable `MagicMock` on every platform. The test now stubs and asserts that close.
- `memgraph_addon/Dockerfile` copied Memgraph Lab from `/app`, which does not exist in the pinned Lab image, so the add-on image could never build. It now copies `/home/lab`, and `memgraph_addon/supervisor.conf` starts that layout through `dist-backend/index.js`. The corrected copy was verified with an equivalent two-stage build.

### Defects found and still open

Both are outside this feature's surfaces and are left for their own features:

- `tests/contract/test_mcp_server_contract.py::test_tools_list_returns_exactly_the_eight_read_only_tools_with_input_schema` fails with `KeyError: 'low_battery_areas'` because `_TOOL_INPUT_SCHEMAS` in `custom_components/ontology/mcp_server.py` lacks entries for the relationship tools listed in `MCP_TOOL_NAMES`.
- `tests/integration/test_active_consumers.py::test_active_consumers_uses_effective_roles_and_real_relationships` fails because an explicit `producer` role override still yields the `ok` outcome instead of `empty`.

### Environment-only gaps

These blocked scenarios are limitations of the automation sandbox, not of the feature, and must be re-run on a normal developer machine before this quickstart counts as fully executed:

- The available package index caps `homeassistant` at 2025.4.4, which predates the `supports_response` argument of `async_register_admin_service` that the integration uses, so every test that sets up a config entry fails during setup. All 43 remaining failures and all 43 errors in scenario 8 come from this single cause and are expected to pass on a supported Home Assistant version.
- npm package downloads are redirected to an unreachable mirror, so `npm ci` fails for `memgraph_addon/graphql` and `tests/browser`. This blocks scenario 3, the GraphQL stage of the scenario 5 image build, scenario 7, and the Playwright browser downloads.
- Scenario 5's runtime checks, both scenario 6 runtime probes, and scenario 7 additionally need a running Home Assistant instance and, for the Enterprise probe, a disposable licensed Memgraph environment.
- Scenario 9 needs human participants and cannot be automated.
- Docker-backed tests need `pytest-socket` to permit the Docker socket. On Linux the `pytest-homeassistant-custom-component` allow-list of `127.0.0.1` blocks it, so this run used a local-only pytest plugin that re-enabled sockets. Nothing in the repository was changed for that shim.