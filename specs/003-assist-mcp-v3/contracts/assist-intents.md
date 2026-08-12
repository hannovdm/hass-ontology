# Contract: Assist intents (`intent_handlers.py` + `intents/en.yaml`)

Registers native Home Assistant intents (research.md §1) invocable through the default (non-LLM) Assist conversation agent. Every intent delegates to the shared functions in `query_tools.py`/`impact_analysis.py` (research.md §7) and returns the common `ToolResult` shape (data-model.md §2) translated into an `intent.IntentResponse`.

**Sentence loading**: `custom_components/ontology/intents/en.yaml` is the canonical bundled sentence template, but Home Assistant's default agent never reads it from inside a custom integration's own package - `intent_handlers.async_ensure_custom_sentences()` copies it into `<config>/custom_sentences/en/ontology.yaml` on every `async_setup_entry` (idempotent; triggers `conversation.reload` only when the content changes) so Assist actually recognizes the sentences. All slot/list names are prefixed `ontology_` (`{ontology_entity}`, `{ontology_area}`, `{ontology_device}`, `{ontology_term}`) to avoid colliding with Home Assistant's own built-in `area`/`name` slot lists.

## `OntologyAutomationDependencies`

- **Sentences** (`intents/en.yaml`): "what automations depend on {ontology_entity}", "what uses {ontology_entity}", "what depends on {ontology_entity}".
- **Slots**: `ontology_entity` (name or entity_id, matched via a wildcard slot list).
- **Behavior**: Calls `query_tools.automation_dependencies(entity)` (FR-008). On success, response includes each related automation and its reason where available (US2 Scenario 1).
- **Not-found behavior**: If `ontology_entity` cannot be resolved, returns a clear "not found" `IntentResponseType.ERROR`-free conversational response (not a Python exception) and does not run an unbounded query (FR-012, SC-006).

## `OntologyAreaContents`

- **Sentences**: "what devices are in {ontology_area}", "what's in the {ontology_area}", "what is in the {ontology_area}".
- **Slots**: `ontology_area` (name or area_id, matched via a wildcard slot list).
- **Behavior**: Calls `query_tools.area_context(area)` (FR-009); response groups entities by device where possible (US2 Scenario 2).
- **Not-found behavior**: as above (FR-012).

## `OntologyEntityContext`

- **Sentences**: "what is {ontology_entity} connected to", "tell me about {ontology_entity}".
- **Slots**: `ontology_entity`.
- **Behavior**: Calls `query_tools.entity_context(entity)` (FR-010); response includes device, area, domain, integration, semantic classifications, and direct dependencies where available (US2 Scenario 3).
- **Not-found behavior**: as above (FR-012).

## `OntologyDeviceContext`, `OntologyImpactAnalysis`, `OntologySearch`

- **Slots**: `ontology_device`, `ontology_entity`, `ontology_term` respectively.
- **Behavior**: Thin Assist wrappers over `query_tools.device_context`, `impact_analysis.analyze`, and `query_tools.search` respectively (FR-011). Same not-found contract as above (FR-012).

## Diagnostics contract

Every intent invocation above (success or not-found) appends exactly one `AssistQueryRecord` (data-model.md §5) via `agent_audit.py`: the intent name, resolution status, result count, and timestamp — never the raw utterance (FR-028, FR-029, US8 Scenario 3).

## Non-goals

No intent in this release triggers any write/change to Home Assistant or the ontology graph (FR-033); no LLM Tool API registration is added in v3 (research.md §1).
