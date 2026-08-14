# Quickstart: Validate Home Relationship Questions

This guide validates feature 004 end to end after implementation. It contains runnable scenarios, not implementation code. See [data-model.md](./data-model.md) for graph records and [contracts/](./contracts/) for exact interfaces.

## Prerequisites

- Home Assistant with the ontology integration configured against a reachable Memgraph instance.
- Docker Desktop running for real-Memgraph integration tests.
- A pre-upgrade test graph at schema `2.0.0` containing representative generated topology and semantic overrides.
- Test fixtures for battery, power, device/entity names, automations, a canonical gas-cylinder asset, and sensitive marker strings.
- On Windows, do not install this repository editable and do not invoke bare `pytest`; use `scripts/test-windows.ps1` so Home Assistant's POSIX compatibility stubs and Testcontainers settings are active.

Run static and baseline checks from the repository root:

```powershell
ruff check custom_components tests
.\scripts\test-windows.ps1 tests/unit tests/contract -q
```

## Scenario A: Migrate schema safely

1. Start the updated integration against the `2.0.0` fixture graph.
2. Verify startup succeeds and the schema sensor reports `3.0.0`.
3. Verify all preexisting Entity, Device, Area, semantic classification, override, and dependency records remain queryable.
4. Reload the integration and verify migration is a no-op with no duplicate records.
5. In the migration integration test, inject failure before the marker update. Verify the transaction rolls back and the marker remains `2.0.0`.
6. Present an unsupported schema version. Verify setup fails closed with a repair and does not mutate the graph.

Expected: [schema-migration.md](./contracts/schema-migration.md) is satisfied.

## Scenario B: Synchronize current measurements

1. Publish battery states for `%` values below, equal to, and above 20; also publish `unknown`, `unavailable`, malformed, nonfinite, out-of-range, voltage, and percentage-text variants.
2. Publish power states in `W` and `kW`, including positive, zero, and negative values, plus unsupported units.
3. Change only `unit_of_measurement` or `device_class` while keeping the state constant. Verify normalized metadata updates after the existing debounce interval.
4. Change only an unrelated attribute. Verify no graph write occurs and `measurement_last_updated` does not advance.
5. Rebuild/resync old states. Verify their stored Home Assistant `last_updated` values remain old.
6. Transition a valid reading to unavailable or invalid. Verify the prior normalized numeric property is removed.

Expected: only explicit allow-listed metadata is present; current values and statuses match [data-model.md](./data-model.md).

## Scenario C: Find low-battery rooms

1. Call `ontology.low_battery_areas` with defaults.
2. Verify fresh percentage readings strictly below 20 are grouped by current area and device.
3. Verify a value exactly 20 is excluded, devices with several qualifying sensors appear once, and directly area-assigned entities remain visible.
4. Age one source beyond 24 hours without changing it. Verify it is excluded and synchronization alone does not make it fresh.
5. Repeat with valid threshold, age, and limit overrides. Verify graph data is unchanged.
6. Ask Assist: “Which rooms have devices with low batteries?” and call MCP `low_battery_areas` when enabled.

Expected: all channels agree on content, ordering, warnings, and truncation.

## Scenario D: Find active consumers

1. Assign/infer roles covering consumer, producer, storage, grid import, grid export, and unknown.
2. Call `ontology.active_consumers` with defaults.
3. Verify only fresh consumer readings strictly above 1 W qualify; positive non-consumer and unknown-role readings do not.
4. Add a user role that conflicts with inference and verify the user role wins.
5. Give one device several qualifying readings. Verify the device appears once, all readings remain explanatory, and no unsupported sum is reported.
6. Add device-backed daily/monthly energy entities without current power readings. Verify their devices appear separately as known consumers without current power, not as proven active loads.
7. Ask Assist: “What appliances currently consume electricity?” and call MCP `active_consumers`.

Expected: all channels return the same role-aware consumer set and expose unresolved-role warnings only where supported.

## Scenario E: Resolve device dependencies and context

1. Create a device with multiple entities referenced by overlapping automations.
2. Query `ontology.automation_dependencies` by exact entity ID, unique entity name, exact device ID, and unique device name.
3. Verify the device answer is the complete de-duplicated automation union and names each entity establishing a dependency.
4. Create duplicate names across eligible targets. Verify an exact ID wins and a duplicate name returns bounded `ambiguous`, never the first match.
5. Query a resolved target with no dependencies and a missing target. Verify `empty` and `not_found` remain distinct.
6. Call `ontology.device_context` and verify every current associated entity appears once with name and stable ID.
7. Ask the two corresponding Assist questions and invoke both MCP tools.

Expected: resolution and envelopes match [read-operations.md](./contracts/read-operations.md).

## Scenario F: Manage gas supply knowledge

1. As a Home Assistant administrator, create an association from a uniquely resolved canonical gas cylinder to a Device and another to an Entity.
2. Repeat creation and verify stable IDs and record counts do not change.
3. Attempt the same operation as a non-administrator and through Assist/MCP. Verify every mutation is rejected or absent.
4. Query `ontology.supplied_targets`, ask “What is powered by my 48kg gas cylinder?”, and invoke MCP `supplied_targets`.
5. Delete a target from Home Assistant and resync. Verify the durable association remains, validation reports `unresolved_supply_target`, and the query does not fabricate a live target.
6. Restore the target and resync. Verify binding and query result return automatically.
7. Delete the association by stable statement ID and verify its generated bindings disappear.

Expected: associations survive generated topology lifecycle events and only administrators mutate them.

## Scenario G: Export and atomically import user knowledge

1. Export user knowledge and validate it against [user-managed-knowledge.schema.json](./contracts/user-managed-knowledge.schema.json).
2. Re-import the same payload twice. Verify IDs, record counts, and `created_at` values remain stable.
3. Modify one supplied record in a valid payload and omit another existing local record. Import and verify the included record is upserted while the omitted local record remains.
4. Import a legacy version 1 override-only payload and verify compatibility.
5. Inject malformed fields, a mismatched deterministic ID, conflicting duplicates, and an invalid role. Verify each rejects the entire payload before writing.
6. Inject a database failure during a valid multi-record import. Verify the transaction rolls back every record.
7. Rebuild, refresh semantics, resync, reload, and perform an export/import round trip. Verify supply associations, role assignments, and overrides remain unchanged.

Expected: import is validated, additive, idempotent, and atomic.

## Scenario H: Verify privacy, bounds, and degraded behavior

1. Seed fake token/password/credential strings in arbitrary graph properties and input target text.
2. Exercise all five reads through service, Assist, MCP, and relevant context exports. Download diagnostics and inspect audit records.
3. Verify no sensitive marker, raw utterance, raw exception, arbitrary attribute, or import body appears; only allow-listed fields and aggregate telemetry remain.
4. Populate more qualifying records and ambiguous candidates than the configured limit. Verify every list is bounded and explicitly marked truncated.
5. Time the five reads on a graph with several thousand entities. Verify each completes within 3 seconds.
6. Stop Memgraph, then exercise synchronization, mutation, each read, reload, and unload. Verify Home Assistant stays operational, reads return safe `degraded`, mutations make no partial changes, and no raw driver error escapes.
7. With MCP disabled, verify the endpoint remains unavailable. Enable it and verify existing authentication, local-network admission, read-only tool listing, and audit protections still apply.

## Focused automated commands

Run contract and unit coverage while iterating:

```powershell
.\scripts\test-windows.ps1 tests/contract tests/unit -q
```

Run real-Memgraph integration coverage with Docker Desktop available:

```powershell
.\scripts\test-windows.ps1 tests/integration -q
```

Run the complete suite and lint before sign-off:

```powershell
.\scripts\test-windows.ps1 -q
ruff check custom_components tests
```

Expected: all existing tests remain green, and every new operation has deterministic unit/contract coverage plus real-graph migration and lifecycle coverage.

## Environment-specific validation exceptions

- 2026-08-13 (Windows): the US2 unit and contract slice passed 76 tests. The
	real-Memgraph `tests/integration/test_active_consumers.py` cases could not
	start because Docker Desktop returned HTTP 500 for
	`http+docker://localnpipe/version`; both errors occurred in the session-scoped
	Testcontainers fixture before integration code executed. T040 remains open
	until Docker Desktop is available and Scenario D is completed.
