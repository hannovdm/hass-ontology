# Contract: Assist intents (`intent_handlers.py` + `intents/en.yaml`)

Registers native Home Assistant intents (research.md §1) invocable through the default (non-LLM) Assist conversation agent. Every intent delegates to the shared functions in `query_tools.py`/`impact_analysis.py` (research.md §7) and returns the common `ToolResult` shape (data-model.md §2) translated into an `intent.IntentResponse`.

## `OntologyAutomationDependencies`

- **Sentences** (`intents/en.yaml`, illustrative — exact wording finalized during implementation): "what automations depend on {entity}", "what uses {entity}".
- **Slots**: `entity` (name or entity_id, fuzzy-resolved against the entity registry/graph).
- **Behavior**: Calls `query_tools.automation_dependencies(entity)` (FR-008). On success, response includes each related automation and its reason where available (US2 Scenario 1).
- **Not-found behavior**: If `entity` cannot be resolved, returns a clear "not found" `IntentResponseType.ERROR`-free conversational response (not a Python exception) and does not run an unbounded query (FR-012, SC-006).

## `OntologyAreaContents`

- **Sentences**: "what devices are in {area}", "what's in the {area}".
- **Slots**: `area` (name or area_id).
- **Behavior**: Calls `query_tools.area_context(area)` (FR-009); response groups entities by device where possible (US2 Scenario 2).
- **Not-found behavior**: as above (FR-012).

## `OntologyEntityContext`

- **Sentences**: "what is {entity} connected to", "tell me about {entity}".
- **Slots**: `entity`.
- **Behavior**: Calls `query_tools.entity_context(entity)` (FR-010); response includes device, area, domain, integration, semantic classifications, and direct dependencies where available (US2 Scenario 3).
- **Not-found behavior**: as above (FR-012).

## `OntologyDeviceContext`, `OntologyImpactAnalysis`, `OntologySearch`

- **Behavior**: Thin Assist wrappers over `query_tools.device_context`, `impact_analysis.analyze`, and `query_tools.search` respectively (FR-011). Same not-found contract as above (FR-012).

## Diagnostics contract

Every intent invocation above (success or not-found) appends exactly one `AssistQueryRecord` (data-model.md §5) via `agent_audit.py`: the intent name, resolution status, result count, and timestamp — never the raw utterance (FR-028, FR-029, US8 Scenario 3).

## Non-goals

No intent in this release triggers any write/change to Home Assistant or the ontology graph (FR-033); no LLM Tool API registration is added in v3 (research.md §1).
