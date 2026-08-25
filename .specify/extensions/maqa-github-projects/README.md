# MAQA GitHub Projects Integration

> GitHub Projects v2 integration for the [MAQA](https://github.com/GenieRobot/spec-kit-maqa-ext) spec-kit extension.

Tracks feature progress in a GitHub Projects v2 board. Items move through your Status field as features progress. Task lists are managed as GitHub markdown checkboxes in the issue body.

## Requirements

- [maqa](https://github.com/GenieRobot/spec-kit-maqa-ext) extension installed
- GitHub token with `project` scope: `GH_TOKEN` (or `gh auth login` — setup uses `gh auth token` as fallback)

## Installation

```bash
specify ext add maqa
specify ext add maqa-github-projects
```

## Setup

```bash
/speckit.maqa-github-projects.setup
```

Lists your GitHub Projects, maps Status field options to MAQA workflow slots, writes `maqa-github-projects/github-projects-config.yml`.

## Notes

GitHub Projects v2 does not have Trello-style checklists. Tasks are tracked as GitHub markdown task lists (`- [ ] item`) in the issue/draft body. The feature agent updates the body to check off items as they complete.

## License

MIT
