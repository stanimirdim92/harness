# Open items: HR-2

| Id | Item | Kind | Owner | Disposition |
|---|---|---|---|---|
| OPEN-001 | When a fixture project has its own `CLAUDE.md` or `AGENTS.md`, `sandbox.install_harness()` writes the harness rules to `.claude/AGENTS.md`, which Claude Code does not load. The old link install had the same gap (root `AGENTS.md`). A probe must show whether user-level memory still loads under `--setting-sources project,local` before the rule changes (found at T005, `5c6b7b5`). | question | the owner | Open |
| OPEN-002 | The command `/ship` is now `/release`, because the built-in `/ship` hid it (ADR 0151, commit "Rename the /ship command to /release", on branch HR-2). HR-2's approved spec, plan and todo still say `/ship`. Later HR-2 tasks (T019, T022, T023) must use `/release`. | follow-up | the owner | Open |
| OPEN-003 | The build moved from branch `HR-2` to `main` after `e7c1218`; `main` was fast-forwarded to HR-2. This replaces TD-012 and the branch part of TD-011. | follow-up | the owner | Accepted — the build continues on `main`; owner, 2026-11-25: "all to main. switch to main" |
