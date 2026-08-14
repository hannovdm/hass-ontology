# Schema Migration Contract

## Versions

- Exact predecessor: `2.0.0`
- Target: `3.0.0`

## Startup behavior

| Observed state | Required behavior |
|---|---|
| No schema node/fresh graph | Build current schema at `3.0.0`. |
| `2.0.0` | Run one additive managed transaction, then continue setup. |
| `3.0.0` | No-op migration and continue setup. |
| Any other version or malformed marker | Preserve graph, create/retain mismatch repair, and fail setup closed. |
| Memgraph unavailable | Preserve Home Assistant operation, report degraded/unavailable setup according to existing integration behavior, and do not claim migration success. |

## Transaction requirements

The exact migration:
1. Establishes constraints/indexes needed for `SupplyAssociation` and `EnergyRoleAssignment` with idempotent operations supported by Memgraph.
2. Preserves all existing nodes, relationships, semantic overrides, and source metadata.
3. Does not fabricate measurement values, roles, or supply associations.
4. Updates the singleton schema marker to `3.0.0` as the final statement in the same transaction.

Any failure rolls back all migration changes. A retry from `2.0.0` is safe. A retry from `3.0.0` is a no-op. Rebuild and resync never downgrade or rewrite the schema marker.

## Verification

Migration contract tests use a real Memgraph container and prove:
- existing v2 graph records remain queryable;
- the marker changes only after successful migration;
- injected failure leaves the marker and data at v2;
- rerun produces one current marker and no duplicate durable statements;
- unsupported versions fail closed without graph mutation.
