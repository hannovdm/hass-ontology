# MAQA Changelog

## 0.1.6 — 2026-08-20

- Setup command: fix deployed subagent templates pointing at a nonexistent `.claude/commands/speckit.maqa.*.md` path — commands are installed by `specify ext add` under `.specify/extensions/maqa/commands/`, not `.claude/commands/`. Native subagents (coordinator, feature, QA) could not previously locate their own workflow instructions on current spec-kit Claude integrations (skills-based, not commands-based).
- Setup command: bump deployed coordinator and QA subagents from `haiku` to `sonnet`. Both do branching orchestration / semantic judgment (board detection, CI-gate and QA-cadence decisions, grammar/WCAG/security review) that isn't reliably mechanical work.

## 0.1.5 — 2026-03-28

- Feature agent: add CRITICAL cwd warning — Bash resets working directory to main repo between invocations; every git/test command must be prefixed with `cd <worktree> &&` to prevent index corruption and file bleed into main repo
- Setup command: propagate cwd warning into deployed `.claude/agents/feature.md` key rules

## 0.1.4 — 2026-03-27

- Feature agent: commit before returning is now **non-negotiable** — removes the previous "stage only, no commit" rule that caused permanent work loss when worktrees were deleted without merging
- Feature agent: optional `git push` after commit, gated on new `auto_push` config setting (default: `false`)
- QA agent: new step 0 — verify a commit exists on the feature branch before proceeding; immediately FAILs if branch is staged-only (catches the work-loss scenario early)
- Coordinator: reads `qa_cadence` from config and passes `auto_push` to feature agents in SPAWN block
- Config: added `auto_push` (default `false`) and `qa_cadence` (`per_feature` | `batch_end`, default `per_feature`) to `config-template.yml`

## 0.1.3 — 2026-03-27

- Coordinator: multi-board auto-detection — detects maqa-trello, maqa-linear, maqa-github-projects, maqa-jira, maqa-azure-devops in priority order
- Coordinator: CI gate integration — checks maqa-ci pipeline status before handing off to QA
- Config: added `board: auto` field to config-template.yml

## 0.1.2 — 2026-03-26

- Coordinator: auto-populate prompt triggers whenever any local spec is missing from the board (not only when board is empty)

## 0.1.1 — 2026-03-26

- Coordinator: auto-populate prompt when Trello board is empty but local specs exist

## 0.1.0 — 2026-03-26

Initial release.

- Coordinator command: assess ready features, create git worktrees, return SPAWN plan
- Feature command: implement one feature per worktree, optional TDD cycle, optional tests
- QA command: static analysis quality gate with configurable checks
- Setup command: deploy native Claude Code subagents to .claude/agents/
- Optional Trello integration via companion extension maqa-trello
- Language-agnostic: works with any stack; configure test runner in maqa-config.yml
