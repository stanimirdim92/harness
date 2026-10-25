# harness

The Claude Code and Codex harness: agents, commands, skills, hooks, the
runners that take a Jira ticket to `/ship`, its tools and tests, its decision
records and its observation log. Moved here from `setup_scripts` on
2026-10-25 with its history.

| Path | Contents |
| --- | --- |
| `dotfiles/claude/` | What `link_dotfiles.sh` links into `~/.claude`: `AGENTS.md`, `agents/`, `commands/`, `skills/`, `hooks/`, `references/`, `settings.json` |
| `dotfiles/codex/` | The Codex adapter: roles, hooks, config, `codex-worktree` |
| `dotfiles/tools/run/` | `ticket.py` (one ticket end to end), `pipeline.py` (`/build` → `/test` → `/review`), `batch-fix.py` |
| `dotfiles/tools/checks/` | Do the harness files agree with each other? CI runs them |
| `dotfiles/tools/tests/` | The harness's own tests |
| `dotfiles/tools/evals/` | Spec, plan-recall, review and pipeline evals |
| `dotfiles/docs/` | ADRs, `HANDOFF.md`, `observation-log.md`, the generated `harness-map.html` |

Start with [dotfiles/README.md](dotfiles/README.md) and
[dotfiles/ARCHITECTURE.md](dotfiles/ARCHITECTURE.md). The layout keeps the
`dotfiles/` prefix, because every path the harness names, in docs, CI and
`link_dotfiles.sh`, starts with it.

`.github/workflows/ci.yml` runs the self-tests. It stays at the root because
GitHub reads workflows only from there.
