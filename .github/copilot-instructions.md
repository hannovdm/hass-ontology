# Copilot instructions for hass-ontology

## Version bumping — MANDATORY rule

**Both files must always be bumped together in the same edit:**

| File | Field |
|------|-------|
| `custom_components/ontology/manifest.json` | `"version"` |
| `pyproject.toml` | `version` (line 3, under `[project]`) |

The release workflow reads `manifest.json` for the version, and the Python packaging tooling reads `pyproject.toml`. If they diverge the build breaks. Never bump one without the other.

Additionally, whenever the version changes, update the `?v=VERSION` cache-buster strings in these panel JS import statements to match:

- `custom_components/ontology/panel/ontology-panel.js` — two imports at the top
- `custom_components/ontology/panel/ontology-graph.js` — one import at the top

Use `multi_replace_string_in_file` to update all four locations atomically.
