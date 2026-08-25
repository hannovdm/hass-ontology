# MAQA GitHub Projects Changelog

## 0.1.0 — 2026-03-26

Initial release.

- Setup command: reads GitHub Projects v2 via GraphQL API, maps Status field options to MAQA workflow slots
- Populate command: creates draft issues per feature with markdown task lists; skips existing; safe to re-run
- Coordinator integration: auto-detected when github-projects-config.yml + GH_TOKEN present
- Uses gh CLI token automatically when GH_TOKEN is not explicitly set
