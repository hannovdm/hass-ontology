# Home Assistant Ontology Integration Constitution

## Version

**Constitution version:** 1.0.0  
**Project:** Home Assistant Ontology Integration  
**Primary release target:** v1 Core Integration and Memgraph Ontology Sync  
**Runtime:** Home Assistant custom integration  
**Database:** Memgraph  
**Primary language:** Python  
**Architecture choice:** Integration under Devices & Services, not AppDaemon app  
**Deployment principle:** Local-first, cloud-optional, privacy-preserving

## Purpose

This constitution defines the non-negotiable engineering, architecture, security, testing, and delivery principles for the Home Assistant Ontology Integration project.

All specifications, plans, tasks, implementations, refactors, tests, and AI-generated code must comply with this constitution. If a feature requirement conflicts with this constitution, the constitution wins unless it is explicitly amended and versioned.

The project exists to create a first-class Home Assistant integration that synchronizes Home Assistant metadata into a local Memgraph graph database, making the smart home structure queryable through Cypher and extensible toward semantic enrichment, impact analysis, Assist integration, MCP, and local AI use cases.

---

## Core Principles

### I. Home Assistant Native Integration First

The ontology capability must be implemented as a Home Assistant custom integration under `custom_components/ontology`, configured through Devices & Services.

The integration must follow Home Assistant integration patterns:

- Use `manifest.json` with a stable `domain`, `version`, `config_flow`, and `iot_class`.
- Use `config_flow.py` for UI-based setup.
- Use config entries, not YAML-only setup.
- Use Home Assistant services for user-triggered operations.
- Use Home Assistant entity platforms for sensors and buttons.
- Use diagnostics and repairs for operational visibility.
- Support clean setup, unload, reload, and error handling.

The project must not be implemented as an AppDaemon app, dashboard-only app, or standalone script.

**Rationale:** The ontology is a platform-level capability that needs access to Home Assistant registries, events, lifecycle management, diagnostics, services, and entities. It belongs in the integration model.

---

### II. Local-First and Privacy-Preserving by Default

All core functionality must run locally.

v1 and v2 must not require any cloud API, cloud database, cloud LLM, remote telemetry, or external hosted service. v3 may expose context to local or user-selected AI systems, but cloud usage must remain optional and explicit.

The integration must:

- Keep ontology data local in Memgraph.
- Keep Home Assistant secrets out of Memgraph unless explicitly required and safely redacted.
- Redact credentials from logs, diagnostics, exports, and error messages.
- Never export passwords, tokens, long-lived access tokens, API keys, or secret values.
- Avoid sending Home Assistant metadata to any external service by default.

**Rationale:** A smart home ontology can reveal sensitive information about occupants, rooms, devices, routines, presence, security systems, and automations. Local-first privacy is a core design constraint.

---

### III. Memgraph and Cypher Are the Graph Foundation

Memgraph is the predefined graph database for this project. Cypher is the predefined query language.

The integration must:

- Connect to Memgraph as an external service or container.
- Use idempotent Cypher writes wherever possible.
- Use stable identifiers for Home Assistant objects.
- Treat Memgraph as the ontology and relationship store, not as a time-series database.
- Store only current entity state in the graph by default.
- Leave historical state storage to Home Assistant Recorder.

The integration must not introduce Neo4j, RDF, OWL, SPARQL, GraphDB, Jena, or a second graph database in v1 unless the constitution is amended.

**Rationale:** Memgraph provides the desired local, open-source, Cypher-compatible, container-friendly graph runtime for an 8 GB x86 Home Assistant host.

---

### IV. Asynchronous, Non-Blocking Home Assistant Runtime

The integration must not block Home Assistant startup, shutdown, event processing, or the main event loop.

The integration must:

- Use async-compatible Home Assistant APIs.
- Perform graph synchronization asynchronously.
- Apply timeouts when connecting to Memgraph.
- Handle Memgraph unavailability without crashing Home Assistant.
- Defer heavy work away from setup where practical.
- Use debouncing or batching for high-frequency events.
- Avoid excessive graph writes from rapid `state_changed` events.

If Memgraph is unavailable, Home Assistant must remain stable and the integration must expose the problem through diagnostics, repair issues, health sensors, and logs.

**Rationale:** Home Assistant stability is more important than ontology freshness.

---

### V. Generated, Inferred, and User-Managed Data Must Be Separated

The graph must clearly distinguish data created from Home Assistant metadata, data inferred by semantic rules, and data explicitly provided by the user.

Graph nodes and relationships must use source metadata where relevant:

```text
source = "home_assistant"
source = "generated"
source = "inferred"
source = "user"
```

Rebuilds and resync operations must not accidentally destroy user-managed semantic relationships unless the user explicitly requests destructive behavior.

**Rationale:** The ontology will become valuable because of user enrichment and semantic overrides. Generated sync logic must not overwrite user knowledge.

---

### VI. Schema Versioning and Idempotent Migration Are Mandatory

The ontology schema must be explicitly versioned in Memgraph.

The graph must contain an `OntologySchema` node similar to:

```cypher
MERGE (s:OntologySchema {name: "home_assistant_ontology"})
SET s.version = "1.0.0",
    s.updated_at = datetime()
```

Every release that changes labels, relationship types, required properties, migration behavior, or graph semantics must update schema versioning and define migration behavior.

Graph writes must be idempotent by default. Re-running a sync must update existing data rather than duplicating nodes or relationships.

**Rationale:** The project is intended to evolve from v1 metadata sync to v2 semantic enrichment and v3 Assist/MCP capability. Safe evolution requires versioned schema discipline.

---

### VII. Tests Before Confident Implementation

Every meaningful implementation task must include tests or an explicit reason why tests are not applicable.

Required v1 test categories:

- Config flow success and failure.
- Memgraph connection success and failure.
- Full graph sync idempotency.
- Entity, device, area, and state update behavior.
- Service registration and service execution.
- Diagnostic data redaction.
- Integration setup, unload, and reload.
- Memgraph outage handling.

Tests must prefer deterministic fixtures and mocked Home Assistant registries where practical. Integration tests may use a local Memgraph container where needed.

**Rationale:** The project will be built through SpecKit and AI-assisted coding. Tests are the guardrail that prevents plausible but incorrect implementation.

---

### VIII. Observable, Diagnosable, and Repairable by Design

The integration must expose its operational state through Home Assistant-native mechanisms.

The integration must provide diagnostic entities such as:

```text
sensor.ontology_health
sensor.ontology_nodes
sensor.ontology_relationships
sensor.ontology_last_sync
sensor.ontology_last_error
sensor.ontology_schema_version
```

The integration must provide control entities such as:

```text
button.ontology_rebuild
button.ontology_validate
button.ontology_resync
```

The integration must provide services for:

```text
ontology.rebuild
ontology.resync
ontology.sync_entity
ontology.validate
```

Repeated operational failures, such as Memgraph being unreachable, should create Home Assistant repair issues where appropriate.

**Rationale:** The user should not need to inspect container logs first to understand whether the ontology is healthy.

---

### IX. Small, Incremental Delivery Over Big-Bang Features

Development must proceed in small, verifiable increments.

The preferred delivery sequence is:

1. Integration loads and unloads cleanly.
2. Config flow validates Memgraph connectivity.
3. Schema node can be written and read.
4. Initial metadata graph can be built.
5. Diagnostic sensors and services work.
6. Incremental updates work.
7. Validation and repair flows work.
8. v2 semantic features are added only after v1 is stable.
9. v3 Assist, MCP, and AI context features are added only after v2 is stable.

No feature should combine unrelated infrastructure, UI, AI, and graph behavior in one implementation step.

**Rationale:** The project touches Home Assistant internals, an external graph database, user metadata, async event handling, and future AI integration. Incremental delivery reduces risk.

---

### X. Explicit Safety Boundaries for AI and Query Surfaces

Any query or AI-facing surface must be safe by default.

v1 must not expose arbitrary Cypher query execution.  
v2 may expose read-only Cypher querying with explicit write-operation rejection.  
v3 may expose MCP and Assist tools, but they must be read-only by default.

The following operations must be rejected from user-facing or AI-facing query surfaces unless an explicit future design allows them safely:

```text
CREATE
MERGE
DELETE
DETACH
SET
REMOVE
DROP
LOAD CSV
CALL dbms
CALL mg
CALL algo
```

AI and MCP features must not be allowed to mutate Home Assistant or Memgraph state by default.

**Rationale:** The ontology can influence troubleshooting and automation decisions. AI-assisted reads are useful; uncontrolled writes are unsafe.

---

## Technical Standards

### Python Standards

- Use Python compatible with current supported Home Assistant versions.
- Prefer async functions for Home Assistant lifecycle and I/O operations.
- Use type hints for public functions and important internal interfaces.
- Keep modules focused and small.
- Avoid global mutable state except constants.
- Use dataclasses where they improve clarity.
- Handle expected exceptions explicitly.
- Log actionable errors without leaking secrets.

### Home Assistant Standards

- Use `async_setup_entry` and `async_unload_entry`.
- Use config entries for setup.
- Use platform forwarding for sensors and buttons.
- Register and unregister services cleanly.
- Register and unregister event listeners cleanly.
- Use Home Assistant diagnostics for redacted troubleshooting data.
- Use repair issues for repeated user-actionable problems.

### Memgraph Standards

- Use stable node identifiers.
- Use `MERGE` for idempotent writes.
- Keep generated graph data distinguishable from user-managed graph data.
- Avoid unbounded traversals in services or diagnostics.
- Do not store full historical state in Memgraph by default.
- Treat Memgraph connection failure as degraded behavior, not a Home Assistant fatal error.

### Repository Standards

The repository must keep the following structure unless explicitly changed by a spec and plan:

```text
custom_components/
└── ontology/
    ├── __init__.py
    ├── manifest.json
    ├── config_flow.py
    ├── const.py
    ├── coordinator.py
    ├── memgraph_client.py
    ├── graph_builder.py
    ├── event_listener.py
    ├── services.yaml
    ├── sensor.py
    ├── button.py
    ├── diagnostics.py
    ├── repairs.py
    ├── strings.json
    └── translations/
        └── en.json
```

Additional files must have a clear responsibility and must not become catch-all utility modules.

---

## Security and Privacy Requirements

The integration must never intentionally expose:

- Home Assistant secrets.
- Memgraph passwords.
- Access tokens.
- API keys.
- Credentials embedded in URLs.
- Sensitive configuration values.
- Full diagnostics containing raw secret-bearing structures.

Diagnostics and exports must redact sensitive values.

The integration must prefer allow-list export models over block-list export models for v3 AI context.

---

## Performance Requirements

The integration must be suitable for an 8 GB x86 Home Assistant host.

The integration must:

- Avoid memory-heavy local caches where practical.
- Avoid storing time-series state history in Memgraph.
- Batch graph writes where possible.
- Avoid unbounded Cypher result sets.
- Avoid excessive writes from high-frequency entity state changes.
- Keep graph sync observable and cancel-safe.

Performance regressions must be treated as functional issues if they affect Home Assistant responsiveness.

---

## Compatibility Requirements

The integration must target Home Assistant custom integration compatibility first.

The project must not assume:

- Home Assistant OS only.
- Home Assistant Supervised only.
- A specific add-on store.
- A specific container orchestrator.
- A cloud-managed Memgraph instance.
- A GPU or local LLM runtime on the Home Assistant host.

The integration must support Memgraph running as a separate container reachable over the configured host and port.

---

## Delivery Workflow

This project follows Spec-Driven Development.

All work must flow through:

```text
constitution -> specify -> clarify when needed -> plan -> tasks -> analyze when needed -> implement -> test -> review
```

Feature specs must describe what and why.  
Plans must describe how.  
Tasks must be atomic, testable, and traceable to specs.  
Implementation must not introduce features that are absent from the active spec and plan.

---

## Review Gates

Before implementation begins, confirm:

- The feature aligns with this constitution.
- Home Assistant integration lifecycle impact is understood.
- Memgraph schema impact is understood.
- Security and privacy impact is understood.
- Tests are defined.
- Destructive graph operations are explicit.
- User-managed data preservation is addressed.

Before merge, confirm:

- Tests pass.
- Integration loads and unloads cleanly.
- Secrets are redacted from diagnostics and logs.
- Graph writes are idempotent.
- Home Assistant remains stable when Memgraph is unavailable.
- Documentation reflects new services, entities, or schema changes.

---

## Versioning Policy

The constitution uses semantic versioning.

- **MAJOR:** Changes to core principles, architecture decisions, privacy posture, or required technology choices.
- **MINOR:** New principles or materially expanded guidance that remains compatible with existing principles.
- **PATCH:** Wording clarifications, formatting, typo fixes, or non-substantive refinements.

Every constitution amendment must include:

- Version change.
- Date of change.
- Summary of change.
- Reason for change.

---

## Current Governance Decisions

The following decisions are active and binding:

```text
1. Build as Home Assistant integration, not app.
2. Configure through Devices & Services.
3. Use Python as primary implementation language.
4. Use Memgraph as predefined graph database.
5. Use Cypher as graph query language.
6. Keep Memgraph external to Home Assistant runtime.
7. Keep core functionality local-first.
8. Store current graph state, not full time-series history.
9. Preserve user-managed semantic data across generated refreshes.
10. Keep AI and MCP surfaces read-only by default.
```

---

## Amendment Log

| Version | Date | Change | Reason |
|---|---|---|---|
| 1.0.0 | 2026-07-22 | Initial constitution for Home Assistant Ontology Integration | Establish project guardrails before v1 implementation |
