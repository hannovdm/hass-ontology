# Assist Intent Contract

Assist is read-only. Every handler delegates to the corresponding shared read operation and converts its envelope to concise speech and card text. It never creates supply associations or energy-role assignments.

## Intents

| Intent | Required slot | Shared operation | Example variations |
|---|---|---|---|
| `OntologyLowBatteryAreas` | none | `low_battery_areas` | “Which rooms have devices with low batteries?”, “Where are the low batteries?” |
| `OntologyActiveConsumers` | none | `active_consumers` | “What appliances currently consume electricity?”, “Which devices are using power?” |
| `OntologyAutomationDependencies` | `target` | `automation_dependencies` | “Which automations depend on the garage motion sensor?”, “What automations use {target}?” |
| `OntologySuppliedTargets` | `cylinder` | `supplied_targets` | “What is powered by my 48kg gas cylinder?”, “What does {cylinder} supply?” |
| `OntologyDeviceContext` | `device` | `device_context` | “Show all entities associated with the dishwasher.”, “What entities belong to {device}?” |

English sentence lists include “which automations” wording and natural preposition variants. Slot text is passed unchanged to the shared resolver and is never logged as a raw utterance.

## Rendering

- Low batteries: group by room and name devices/entities with percentages.
- Active consumers: name each device, qualifying watt readings, and area where known.
- Dependencies: name automations and the entities that establish each dependency.
- Supplied targets: name devices/entities and their areas where known.
- Device context: name every bounded associated entity with stable entity ID.

`empty`, `not_found`, `ambiguous`, and `degraded` have distinct localized responses. Ambiguous responses present a bounded candidate list and ask the user to use a stable ID or a more specific name. Truncation is spoken/textually disclosed. All rendered values pass through recursive redaction.
