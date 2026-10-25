# Harness files live under ``

**Context.** The repository root is the server setup: nginx, PHP-FPM, Redis,
MySQL, kernel tuning, `tools/php_update.sh`. The harness had spread into that
root: its README and architecture doc, `docs/` (ADRs, ideas, memory,
observation log, map) and `tools/` (validators, tests, evals, the linker).
A reader of the root saw a harness, not the setup scripts.

**Decision.** Everything that belongs to the harness lives under ``.

| Was | Now |
| --- | --- |
| `README.md`, `ARCHITECTURE.md` | `README.md`, `ARCHITECTURE.md` |
| `docs/adr/`, `IDEAS.md`, `MEMORY.md`, `observation-log.md`, `harness-map.html` | `docs/` |
| `tools/` (all but `php_update.sh`) | `tools/` |

The root keeps the server files, `tools/php_update.sh`, `docs/terminal.md`,
and a short README that points to ``. `.github/workflows/ci.yml`
stays at the root because GitHub reads workflows only there; its steps now run
`tools/...`.

Path conventions after the move:
- Prose names paths from the repository root (`tools/evals/plan-recall/recall.py`).
- Markdown links stay relative to the file that holds them.
- `docs/adr/`, `docs/IDEAS.md` and `docs/MEMORY.md` in harness instructions
  (`AGENTS.md`, `adr-recording`, `documentation-practices.md`) still mean the
  *target project's* records, not this repository's.
- `batch-spec.sh` reads `spec-batch.txt` next to itself by default, so it works
  from any project checkout.

`docs/` and `tools/` are not linked into `$HOME`; the linker
still links only `claude/*` and `codex/*` destinations.
ADR bodies had their path mentions updated with the move; their decisions are
unchanged.

**Rejected.** A separate `harness/` directory beside ``: the harness
*is* the dotfiles, and two top-level homes would split one system again.

**Amendment 2026-10-03 — `tools/` grouped by use.** Twenty-two files
in one folder were hard to navigate. They now sit in `setup/` (the linker),
`run/` (batch spec runner, run metrics), `checks/` (the four validators),
`tests/` (every self-test) and `evals/` (plan recall, spec eval, workflow
runner), with `tools/README.md` as the index. Behavior is unchanged;
`batch-spec.sh` still finds `spec-batch.txt` beside it in `run/`.

**Amended 2026-10-25.** The harness is its own repository,
`stanimirdim92/harness`, so the `dotfiles/` level this ADR introduced is gone:
`claude/`, `codex/`, `docs/` and `tools/` sit at the repository root, and
every path in the harness lost the prefix. The reason for the level, keeping
the harness apart from server setup files, no longer applies.
