# Open items: HR-2

| Id | Item | Kind | Owner | Disposition |
|---|---|---|---|---|
| OPEN-001 | When a fixture project has its own `CLAUDE.md` or `AGENTS.md`, `sandbox.install_harness()` writes the harness rules to `.claude/AGENTS.md`, which Claude Code does not load. The old link install had the same gap (root `AGENTS.md`). A probe must show whether user-level memory still loads under `--setting-sources project,local` before the rule changes (found at T005, `5c6b7b5`). | question | the owner | Open |
