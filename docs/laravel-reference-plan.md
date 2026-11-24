# Laravel reference: plan

Status: Steps 1–6 built 2026-11-24, not committed. Step 7 open.

## Goal

Keep a reference copy of the Leadbuster quality setup in `laravel/`. The copy
must follow Leadbuster when it changes.

Two uses:

1. A map, so no moving part is forgotten when one changes.
2. A kit, so a new Laravel project can take the setup.

## Success criteria

- `laravel/` holds every in-scope file, byte-identical to Leadbuster at the
  commit in `laravel/SOURCE.lock`.
- One command reports every in-scope file that changed in Leadbuster since that
  commit. It also reports new files in the watched folders.
- One command copies the changes and moves the lock forward.
- `laravel/README.md` lists each part, why it exists, and the order to set it
  up in a new project.
- The sync tool has a test in `tools/tests/`. Harness CI runs it without
  access to Leadbuster.

## Owner decisions

- **Verbatim copy in the public harness** (2026-11-24). The owner accepts that
  company detail becomes public: module names, database names, provider names.
  Secrets stay out. Step 4 enforces that.
- **`.ai/rules/*` are output of the `infer-conventions` skill.** The kit carries
  the skill and how to run it. The rules are copied only as an example.

## Layout

```
laravel/
  README.md        map + setup order for a new project
  MANIFEST         one Leadbuster path or glob per line, with a group
  SOURCE.lock      Leadbuster commit SHA and date of the last sync
  files/           the copies, at their Leadbuster relative paths
tools/laravel/
  sync.py          check (exit 1 on drift) and apply
tools/tests/
  test-laravel-sync.py
```

The copies stay under `files/` so their `.github/` and `.githooks/` do not
act on the harness.

## Scope

`laravel/MANIFEST` is the current scope. The tables below are the first draft.

### In scope (MANIFEST groups)

| Group | Leadbuster paths |
|---|---|
| static-analysis | `phpstan.neon`, `phpstan.ci.neon`, `deptrac.php`, `pint.json`, `phpunit.xml`, `.editorconfig`, `composer.json` (scripts and dev tools) |
| ci | `.github/workflows/*.yml`, `bin/ci-*.py`, `tests/ci_*_test.py` |
| hooks | `.pre-commit-config.yaml`, `.githooks/pre-commit`, `bin/pre-commit.py`, `bin/setup-quality.sh`, `bin/check-file-size.py`, `tests/quality_hooks_test.py` |
| test-runner | `bin/worktree-*`, `bin/schema-*`, `bin/worktree-databases.php`, `config/database.php`, `tests/TestCase.php`, `tests/Pest.php`, `tests/bootstrap.php`, `tests/Shell/*`, `tests/Unit/ArchitectureTest.php`, `tests/Unit/Worktree*Test.php`, `tests/Feature/{WorktreeIsolation,WorkerDatabaseReset,TestSchemaTemplate}Test.php`, `.worktreeinclude` |
| agent-docs | `AGENTS.md`, `TESTING.md`, `CONVENTIONS.md`, `COMMANDS.md`, `bin/README.md`, `boost.json` |
| agent-skills | `.ai/skills/*`, `.ai/guidelines/*` |
| rules-example | `.ai/rules/*`, `.ai/repo-map.md` |

### Out of scope

| Path | Reason |
|---|---|
| `phpstan-baseline.neon`, Deptrac baselines | Project debt. A new project starts at zero. |
| `.env*`, `.gitleaksignore`, `.claude/settings.local.json` | Secrets or local state. |
| `database/schema/*`, `composer.lock`, `yarn.lock` | Project data. Regenerated per project. |
| `app/`, `Modules/`, domain tests, `docs/tasks/*` | Business code and ticket records. |

Step 1 confirms each row against the files. `deptrac.yaml` and
`deptrac_clean.yaml` changed recently; Step 1 checks if they are still used.

## Steps

Each step has its check.

1. **Write `MANIFEST` and `README.md`.** Read each in-scope file once and give
   it one line in the README: what it does, what it depends on.
   Check: every path in the MANIFEST exists at Leadbuster `HEAD`.
2. **Write `tools/laravel/sync.py` and its test (TDD).**
   - `check`: `git -C <leadbuster> diff --name-only <lock>..HEAD` over the
     MANIFEST. Also list new files in watched folders (`bin/`,
     `.github/workflows/`, `tests/Shell/`, `.ai/skills/`) that the MANIFEST
     does not cover. Exit 1 on any hit.
   - `apply`: copy from committed `HEAD` (`git show`), never the working
     tree. Write the new SHA to `SOURCE.lock`.
   - Leadbuster path from `--source` or `LEADBUSTER_DIR`.
   Check: the test builds a temporary git repo as a fake Leadbuster. A changed
   file makes `check` exit 1 and name it. No change exits 0. `apply` gives
   byte-identical copies.
3. **First sync.** Run `apply` against Leadbuster `f1176fec` or later.
   Check: `check` exits 0 right after.
4. **Secret gate.** Run gitleaks on `laravel/` before the first commit and in
   harness CI.
   Check: gitleaks reports nothing. A planted fake key makes it fail.
5. **Wire into the harness.**
   - Add `laravel/` to README.md "Not synced" (`dotfiles-sync` skill).
   - Add the sync test to `.github/workflows/ci.yml`.
   - Add `check` to the SessionStart hook as a warning only, when
     `LEADBUSTER_DIR` exists.
   Check: CI green. A session start with a stale lock prints the warning.
6. **ADR.** Record the decision with `adr-recording`. Rejected: git submodule
   (private repo inside a public one), symlinks (break on other machines and in
   CI), sanitized templates and a private repo (owner choice).
7. **Reuse proof (at the first new project, not now).** Follow the README on a
   fresh `laravel new` app. PHPStan, Deptrac, Pint, the hooks and the test
   runner must run. Fix the README where it was wrong.

## How it follows Leadbuster

- After a quality change in Leadbuster: `tools/laravel/sync.py apply`, then
  commit `laravel/` with the Leadbuster SHA in the message.
- A session start warns when the lock is behind.
- A new file in a watched folder fails `check` until it is added to the
  MANIFEST or to a skip list with a reason.

## Risks

- Public exposure of company detail. The owner accepted it. Secrets stay
  gated by Step 4.
- The README map can drift from the files. `check` catches file changes, not
  README staleness. Each `apply` prints the changed groups so the README
  lines for them get a review.
