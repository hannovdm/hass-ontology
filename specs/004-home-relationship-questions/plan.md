# Implementation Plan: Home Relationship Questions

**Branch**: `004-home-relationship-questions` | **Date**: 2026-08-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-home-relationship-questions/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command; its definition describes the execution workflow.

## Summary

Extend the existing Home Assistant Ontology integration with normalized current battery and power metadata, explicit energy-role semantics, durable user-managed gas-supply knowledge, deterministic target resolution, and five shared bounded read operations. Upgrade the Memgraph ontology additively from schema `2.0.0` to `3.0.0`; preserve user knowledge as durable statement records whose generated bindings can be reconciled after rebuilds; and expose the same result semantics through administrator-controlled Home Assistant services, Assist, and the existing authenticated read-only MCP endpoint.

## Technical Context

**Language/Version**: Python 3.13 in current Home Assistant Core; local tooling remains compatible with Python 3.11+ per `pyproject.toml`.

**Primary Dependencies**: Home Assistant custom-integration APIs (config entries/options, state and registry events, services, Assist intents, diagnostics, repairs, storage) and the existing `neo4j>=5.0` async Bolt driver for Memgraph. No new runtime dependency.

**Storage**: Local Memgraph graph. Entity nodes hold normalized current measurement properties only. Durable `SupplyAssociation` statement nodes hold user-managed supply knowledge. Durable `EnergyRoleAssignment` statement nodes hold either inferred or user-managed roles under source-specific stable identities, with user-managed assignments taking precedence. Home Assistant Recorder remains responsible for history.

**Testing**: Existing pytest, pytest-asyncio, pytest-homeassistant-custom-component, Ruff, and testcontainers/Memgraph stack; Windows validation uses `./scripts/test-windows.ps1`.

**Target Platform**: Home Assistant OS, Supervised, or Core on the existing 8 GB x86_64 reference host, connected to a local Memgraph service over Bolt.

**Project Type**: Single Home Assistant custom integration under `custom_components/ontology` with contract, unit, and integration tests.

**Performance Goals**: Each new bounded read returns within 3 seconds on a benchmark graph containing at least 5,000 entities across at least 1,000 devices and at least 500 qualifying rows before bounds are applied; accepted measurement changes become queryable within the existing three-second debounce interval; each accepted debounced update creates at most one entity write and unrelated attribute-only churn creates none.

**Constraints**: Local-first and cloud-optional; asynchronous and non-blocking; schema migration must be exact-predecessor, idempotent, and atomic; imports must validate fully before one atomic additive merge; all AI-facing surfaces remain read-only; mutation and import require a Home Assistant administrator; arbitrary attributes, raw utterances, credentials, secrets, and exception messages must not enter graph, exports, audit records, or responses.

**Scale/Scope**: One Home Assistant instance and config entry, at least 5,000 entities across at least 1,000 devices in performance validation, hundreds of qualifying results bounded by existing query limits, five read capabilities, seven administrator user-knowledge operations (two role, three supply, export, and import), three new Assist intents, and three new MCP tools plus two enhanced existing tools.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Design evidence |
|---|---|---|
| I. Home Assistant Native Integration First | PASS | All configuration, services, Assist intents, diagnostics, repairs, and lifecycle work remain inside the existing config-entry integration. Mutations use Home Assistant's native administrator-service helper. |
| II. Local-First and Privacy-Preserving | PASS | Memgraph and Home Assistant are the only required runtimes. Measurement ingestion and exports use explicit allow-lists; read results retain recursive redaction. |
| III. Memgraph and Cypher Foundation | PASS | New graph semantics and all bounded reads use the existing Memgraph/Bolt client and parameterized Cypher. No second datastore or graph language is introduced. |
| IV. Async, Non-Blocking Runtime | PASS | Event filtering occurs in memory, updates retain per-entity debounce, graph I/O remains async, and Memgraph failure produces degraded responses without failing Home Assistant. |
| V. Generated, Inferred, User Data Separation | PASS | Current measurements are Home Assistant sourced; inferred roles are marked inferred; durable supply and role records are marked user; generated bindings can be recreated without deleting user statements. |
| VI. Schema Versioning and Migration | PASS | Schema advances from `2.0.0` to `3.0.0` through an exact-predecessor additive transaction that updates the schema marker last and is a no-op when already current. |
| VII. Tests Before Confident Implementation | PASS | Design requires deterministic unit tests, service/MCP/Assist contract tests, and real-Memgraph migration, lifecycle, relationship, privacy, failure, and performance coverage. |
| VIII. Observable and Repairable | PASS | Validation adds unresolved user-knowledge findings; diagnostics add aggregate measurement/role/supply counts and sanitized operation outcomes without raw values or identifiers. |
| IX. Small Incremental Delivery | PASS | Work separates migration/transactions, measurement sync, user knowledge, shared reads, channels, exports/diagnostics, and integration validation. |
| X. Explicit AI Safety Boundaries | PASS | Assist and MCP expose only read operations. Supply and role writes exist only as admin Home Assistant services; arbitrary Cypher safety remains unchanged. |

**Pre-design gate result**: PASS. No constitution violations require justification.

**Post-Phase-1 re-check**: PASS. The data model, contracts, and validation quickstart preserve every gate above. Durable statement nodes strengthen generated/user separation; no design artifact introduces a cloud dependency, unbounded traversal, non-admin mutation, or AI-facing write operation.

## Project Structure

### Documentation (this feature)

```text
specs/004-home-relationship-questions/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
custom_components/ontology/
├── __init__.py              # Extend services, startup migration, lifecycle reconciliation
├── const.py                 # Schema/export versions, fields, roles, labels, services, intents
├── memgraph_client.py       # Add managed write-transaction boundary
├── schema_migrations.py     # New exact 2.0.0 -> 3.0.0 additive migration
├── graph_builder.py         # Normalize measurements and clear obsolete values
├── event_listener.py        # Allow-listed attribute changes with retained debounce context
├── coordinator.py           # Serialize measurement writes and knowledge reconciliation/import
├── semantic_classifier.py   # Inferred energy roles and canonical gas assets
├── user_knowledge.py        # New supply/role CRUD, reconciliation, export/import
├── overrides.py             # Preserve semantic-override compatibility
├── query_tools.py           # Shared resolver and five bounded reads
├── intent_handlers.py       # New and enhanced Assist rendering
├── intents/en.yaml          # English sentence variants for all five questions
├── mcp_server.py            # New read tools and enhanced schemas/dispatch
├── context_export.py        # Allow-listed measurement and knowledge projections
├── validation.py            # Unresolved supply/role findings
├── agent_audit.py           # Sanitized operation outcomes
├── diagnostics.py           # Aggregate measurement/role/supply health
├── redact.py                # Recursive redaction for new nested result shapes
├── config_flow.py           # Threshold and freshness options
├── manifest.json            # Integration release metadata (independent of graph schema version)
├── services.yaml            # Read and administrator mutation service schemas
├── strings.json
└── translations/en.json

README.md                    # User-facing options, services, intents, MCP, and migration documentation

tests/
├── contract/                # Services, Assist sentences, MCP schemas, export format
├── unit/                    # Normalization, filtering, resolver, CRUD/import, rendering
└── integration/             # Migration, graph lifecycle, parity, privacy, performance
```

**Structure Decision**: Extend the existing single integration and established test split. Add only two focused modules: `schema_migrations.py` owns version transitions, while `user_knowledge.py` owns durable supply/role records and their generated endpoint bindings. Shared reads remain in `query_tools.py`, preventing transport-specific implementations.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No Constitution Check violations were identified; this section is not applicable.
