# Implementation Plan: One eval runner the owner uses

Status: Approved
Spec: docs/specs/HR-2-SPEC.md
Modules: eval-core, gates, gate-trailer, tasks, bugs, recall, todo, docs-archive
Not yet planned: None
Spec status: Approved
Spec revision: git-commit:1bd1c2e91f44d824f6e8e1f8c7dabc115c90576a:docs/specs/HR-2-SPEC.md
Approved by: the owner (reply "approved, commit on main" in the Claude Code session, 2026-11-24)
Approved at: 2026-11-24

## Technical Approach

### Current Flow
- Gate cases: `tools/evals/workflow/run.py` builds each fixture in code
  (`prepare()`, `prepare_probe()`, lines 422–1136), sends one `claude -p`
  per case with Read/Glob only (line 1570), and asserts in `checks()`
  (lines 1149–1480). One trial, one `results.json`, no baseline.
- Headless suites: `spec-eval/run.py` links six harness folders into a
  throwaway project (`HARNESS_DIRS`, `link_tree`, `build_project`, lines
  103–160) and passes `--add-dir claude/` (line 215). `review-eval/run.py`
  reuses it (line 268).
- add-business: manual. `setup.sh` builds the sandbox, the owner types five
  commands, `grade.sh` scores.
- Comparison: `spec-eval` and `review-eval` take `--baseline <file>`;
  `plan-recall` takes `--baseline`. Verdict code is duplicated
  (`spec-eval/run.py:449`, `review-eval/run.py:391`).
- CI runs every scorer's unit tests, never a model (`.github/workflows/ci.yml`).

### Proposed Flow
1. `tools/evals/eval.py <suite>` resolves the suite and calls
   `core.run(suite, cases, trials, jobs)`.
2. `core` checks the results folder is ignored, makes the run folder, and for
   each case and trial calls the suite's `run_trial(case, folder)`. It retries
   an ERRORED trial once.
3. The suite returns a trial record. `core` rolls trials into an item state
   (PASS/FLAKY/FAIL), writes `results.json` schema 1, loads the baseline
   pointer, computes the verdict, writes `report.md`, prints it, and exits.
4. Headless suites (`tasks`, `bugs`) build their project with
   `sandbox.install_harness()` (copies, no `--add-dir`), and after the trial
   `sandbox.audit()` reads the stream-json trace for leaks.
5. `eval.py todo` and the SessionStart hook read git and the observation log
   only.

### Components and Responsibilities
- `tools/evals/core.py` (NEW): storage and ignore guard, schema, trial loop,
  baseline pointer, verdict, report, semantic review write.
- `tools/evals/sandbox.py` (NEW): harness copy install, session argument
  builder, trace audit (moved `audit_reads` logic plus Bash and subagents).
- `tools/evals/eval.py` (NEW): argument parsing, suite table, subcommands.
- `tools/evals/workflow/cases/<id>/` (NEW): case folders. `workflow/cases.py`
  (NEW): loader, setup steps, placeholders, declared rules.
  `workflow/run.py`: keeps `STAGES`, `prompt()`, the schema and
  `run_trial()`; loses `cases()`, `prepare*`, `checks()` after T008.
- `tools/evals/workflow/replay/` (NEW): replay outputs and expected maps.
- `tools/evals/tasks/run.py` (NEW): headless add-business driver (TD-001).
- `tools/evals/todo.py` (NEW): the catch-up scan.
- `tools/checks/check-eval-trailer.py` (NEW): CI trailer check.
- `claude/hooks/eval-todo-hint.sh` (NEW): SessionStart line.
- `tools/evals/archive/spec-eval/` (MOVED from `tools/evals/spec-eval/`).

### Affected Areas
- `tools/evals/` (all suites, new core, README)
- `tools/checks/`, `tools/tests/`, `.github/workflows/ci.yml`
- `claude/hooks/`, `claude/settings.json`, `claude/commands/ship.md`,
  `claude/references/component-response-contracts.md`
- `docs/observation-log.md`, `docs/HANDOFF.md`, `README.md`,
  `ARCHITECTURE.md`, `tools/README.md`, `docs/adr/`, `docs/harness-map.html`
  (generated)
- `.gitignore`

## Decisions and Provenance
- Python standard library only, `unittest`, one file per tool — spec Code
  Style; mirrors every current eval.
- The verdict lives once, in `core.py`; the suites' own verdict code is left
  in place for their old CLIs until docs-archive points them to `eval.py` —
  spec REQ-005, surgical-change rule.
- A gate case's stage-file map (`STAGES`) stays in `workflow/run.py` — a new
  case needs no code edit unless it needs a new stage (REQ-010).
- `harness-map.py --check` is rerun whenever a task adds a hook, a CI step or
  a script under `tools/` — project rule ADR 0069 (CI "Harness map is
  current").

### TD-001 — Where the tasks driver lives
- Choice: `tools/evals/tasks/run.py`; task content stays in `claude/evals/add-business/`.
- Alternatives: `claude/evals/add-business/drive.py`.
- Reason: every runner lives under `tools/evals/`; keeping driver code out of `claude/` keeps the copied harness free of eval code (REQ-008).
- Source: new technical decision; precedent `tools/evals/*/run.py`
- Affects: T014, T015

### TD-002 — Baseline pointer
- Choice: `tools/evals/results/<suite>/BASELINE`, a one-line file naming the run folder.
- Alternatives: a symlink; a field in each `results.json`.
- Reason: a plain file survives copying and is readable without code; one place to change on promotion (REQ-004).
- Source: new technical decision
- Affects: T003

### TD-003 — Replay set shape
- Choice: `tools/evals/workflow/replay/<case>.json` = a list of `{source, output, reads, fixture, expected}`, where `fixture` names the case's fixture, rebuilt by the replay test from the case's setup because `checks()` takes the directory, where `source` is `measured`, `test_runner` or `hand`, and `expected` is the old `checks()` map.
- Alternatives: keep outputs under `results/` (ignored, so CI could not run the replay).
- Reason: CI must run the replay without a model (REQ-012); WF fixtures are made up, so committing them is safe.
- Source: REQ-012
- Affects: T007, T008

### TD-004 — Session hint mechanics
- Choice: `claude/hooks/eval-todo-hint.sh` resolves the harness root from its own real path, runs `timeout 2 python3 <root>/tools/evals/eval.py todo --count`, prints the line only for a non-zero count, always exits 0. Registered under `SessionStart` matcher `startup|resume` beside `warn-stale-base.sh`.
- Alternatives: extend `warn-stale-base.sh`; a Python hook.
- Reason: one hook, one job, as every other hook here; the 2-second limit is enforced outside Python (REQ-030).
- Source: REQ-030; precedent `claude/hooks/warn-stale-base.sh`
- Affects: T020

### TD-005 — Gate trials isolation
- Choice: each trial builds its own fixture under `<run>/<case>/t<n>/fixture/`; `--jobs` uses a thread pool over trials; default `--jobs 4`.
- Alternatives: share one fixture per case across trials.
- Reason: the runner already asserts the fixture is unchanged (`fixture_unchanged`); sharing would couple trials (REQ-013).
- Source: REQ-013; `workflow/run.py:1580`
- Affects: T009

### TD-012 — Where `/build` runs
- Choice: branch `HR-2` in the main checkout, created from an up-to-date `main`, not a managed worktree. Sequential executors inherit it.
- Alternatives: a `.claude/worktrees/HR-2` worktree with `.worktreeinclude` entries for the ignored files.
- Reason: the work needs gitignored files that exist only in the main checkout: `tools/evals/review-eval/fixtures/ld-585*` (T016), `tools/evals/spec-eval/fixtures/LD-380` (T021), `claude/evals/add-business/hidden/node_modules` (T015), and every run under `tools/evals/results/` (T001 → T007, the T010 baseline). In a worktree, T021's move would merge back while the ignored `LD-380` stays at the old path without its `.gitignore`, so a private fixture would show as untracked in a public repository. `require-worktree-for-writers.sh` allows writers on a feature branch.
- Source: `~/.claude/references/worktrees.md`; `claude/hooks/require-worktree-for-writers.sh` header; the owner chose `main` for the spec commit (2026-11-24). Confirmed by the owner's answer to TD-011
- Affects: all tasks

### TD-006 — Pre-authorized: spend on paid runs
- Stop condition: a paid run whose cost is unknown or above a limit.
- Answer: limits — T001 ≤ $40 projected from its 5-case sample; T010 ≤ $120; the real turns of T002 and T013 ≤ $5 each; T015 one trial ≤ $30; T016 ≤ $40. Above a limit, stop and report the projection. T009's three-case real run is not covered and stays a stop.
- Source: owner approval, 2026-11-24
- Affects: T001, T002, T010, T013, T015, T016

### TD-007 — Pre-authorized: `pdo_sqlite` missing for `grade.sh`
- Stop condition: `grade.sh` cannot run because PHP lacks `pdo_sqlite` (probed 2026-11-24).
- Answer: no sudo. T015 finishes its unit work; its one real trial is written to `docs/tasks/HR-2-open.md` as open work and runs after the owner installs `php8.5-sqlite3`.
- Source: owner approval, 2026-11-24
- Affects: T015

### TD-008 — Pre-authorized: replay mismatch where the old check looks wrong
- Stop condition: the new checks differ from the old `checks()` on a case whose old result looks wrong.
- Answer: the new checks match the old behavior exactly; the suspected bug is recorded in `docs/observation-log.md`; no `expected` value changes.
- Source: owner approval, 2026-11-24
- Affects: T008

### TD-009 — Pre-authorized: size of the real `bugs` run
- Stop condition: how many paid `/review` runs T016 may make.
- Answer: the four `ld-585*` cases × 1 trial, `--budget 10` each.
- Source: owner approval, 2026-11-24
- Affects: T016

### TD-010 — Pre-authorized: `Eval:` trailer on this plan's own commits
- Stop condition: a commit of this plan touches a watched file after T012.
- Answer: when only a path or wording changes, `Eval: not run - <reason>`; when a decision rule's text changes, run `eval.py gates --tag <stage>` and paste its `Eval:` line.
- Source: owner approval, 2026-11-24
- Affects: T012, T017, T022

### TD-011 — Pre-authorized: build location and the owner's uncommitted edits
- Stop condition: writers on the main checkout, and the owner's uncommitted hunks in files a task edits.
- Answer: build on branch `HR-2` in the main checkout (TD-012). The owner's edits in `claude/settings.json`, `docs/HANDOFF.md` and `docs/ai-map.html` stay unstaged; the executor stages only its own hunks and inspects `git diff --cached` before each commit.
- Source: owner approval, 2026-11-24
- Affects: all tasks; T020, T022 in particular

## External Tool Access

| Tool | Access needed | Probe and result | Date |
|---|---|---|---|
| Claude CLI (`claude -p`) | headless runs, account usage | `claude -p "Reply with the single word ok." --max-budget-usd 0.05 --output-format json` — authenticated and charged $0.224; `is_error: true`, error subtype not read. A bare call costs more than $0.05. Version 2.1.331 | 2026-11-24 |
| PHP with `pdo_sqlite` | `grade.sh` for `tasks` | `php -v` → 8.5.13; `php -m \| grep -i pdo_sqlite` → **not loaded**. `grade.sh` cannot run here until it is installed | 2026-11-24 |
| Node, Playwright Chromium | `grade.sh` UI checks | `node --version` → v26.9.0; `hidden/node_modules/.bin/playwright` present; `~/.cache/ms-playwright/chromium-1255` present | 2026-11-24 |
| Leadbuster checkout | `bugs` cases, `todo` | `/var/www/html/leadbuster` exists; `git cat-file -t a47f7cfd` → commit | 2026-11-24 |
| Claude Code Bash sandbox setting | deny Bash reads under `claude/evals/` only (spec DEC-012) | not probed: the probe is task T013, by the spec (REQ-031) | — |

## Workstreams
Sequential by default; `/build` runs them in parallel only when asked.
- ws-core: eval-core (T002–T005)
- ws-gates: gates (T001, T006–T010)
- ws-trailer: gate-trailer (T011, T012)
- ws-tasks: tasks (T013–T015)
- ws-bugs: bugs (T016, T017)
- ws-recall: recall (T018)
- ws-todo: todo (T019, T020)
- ws-docs: docs-archive (T021–T023)

## Task Index
- [ ] T001 (S, ws-gates, deps: —) [REQ-014]: one full gate run with the current runner, 1 trial, outputs kept; cost and time in the eval README
- [ ] T002 (M, ws-core, deps: —) [REQ-008, REQ-009]: headless sessions get a copied harness with no `--add-dir`; the audit marks Read, Bash and subagent leaks; one real `/spec` turn proves the copy works
- [ ] T003 (M, ws-core, deps: —) [REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-006, TD-002]: the core stores runs in an ignored folder, runs trials with one retry, promotes baselines, and reports one verdict
- [ ] T004 (S, ws-core, deps: T003) [REQ-007]: `eval.py` prints the suite table and runs `baseline`, `report` and `review`

### CP-001 — Checkpoint: the core contract is fixed
- [ ] `cd tools/evals && python3 -m unittest -q test_core test_sandbox` passes
- [ ] `results.json` schema 1 and the suite `run_trial` interface are documented in `core.py`'s docstring and unchanged by later tasks without a replan
- [ ] The measurement outputs of T001 exist under `tools/evals/results/` and `git status` does not list them

- [ ] T005 (S, ws-core, deps: CP-001) [REQ-008]: spec-eval and review-eval build their projects with the shared install
- [ ] T006 (M, ws-gates, deps: CP-001) [REQ-010, REQ-011]: a gate case is a folder with setup steps, placeholders and declared checks
- [ ] T007 (M, ws-gates, deps: T001, T006) [REQ-012, TD-003]: the replay set covers every check of every case, true and false, against the old code
- [ ] T008 (L, ws-gates, deps: T007) [REQ-012]: all gate cases are folders, the replay proves them equal, and the old fixture and check code is gone
- [ ] T009 (M, ws-gates, deps: T008) [REQ-003, REQ-007, REQ-013, TD-005]: `eval.py gates` runs trials in parallel and rolls them into PASS/FLAKY/FAIL
- [ ] T010 (S, ws-gates, deps: T009) [REQ-014]: the first gates baseline is promoted and its flaky cases are logged

### CP-002 — Checkpoint: gates baseline established
- [ ] `tools/evals/results/gates/BASELINE` names a full 3-trial run with no ERRORED trial
- [ ] `cd tools/evals/workflow && python3 -m unittest -q test_runner test_migration` passes

- [ ] T011 (S, ws-trailer, deps: CP-002) [REQ-015, REQ-016]: the watched list is generated and the gates report ends with a ready `Eval:` line
- [ ] T012 (M, ws-trailer, deps: T011) [REQ-017]: CI fails a commit to a watched file without an `Eval:` result or reason
- [ ] T013 (S, ws-tasks, deps: T005) [REQ-031]: the probe shows whether the sandbox blocks eval reads while the stage scripts still run, and its record decides prevention
- [ ] T014 (M, ws-tasks, deps: T013) [REQ-018, REQ-019, TD-001]: the tasks driver runs the five stages headless, approves only after a draft, and stops with a reason
- [ ] T015 (M, ws-tasks, deps: T014) [REQ-007, REQ-020]: task trials are graded by the hidden tests into per-check states; one real trial is recorded
- [ ] T016 (M, ws-bugs, deps: T005) [REQ-007, REQ-021]: `eval.py bugs` runs review-eval cases with trials and prints a `Review-eval:` line
- [ ] T017 (S, ws-bugs, deps: T016, T012) [REQ-022, REQ-023]: `eval.py bugs add --from-log` builds a case from a log row, and `/ship` prints that command
- [ ] T018 (XS, ws-recall, deps: CP-001) [REQ-007, REQ-024]: `eval.py recall` passes through to `recall.py`
- [ ] T019 (S, ws-todo, deps: T017, T018) [REQ-029]: `eval.py todo` lists skipped recall rows and bugs without a case
- [ ] T020 (S, ws-todo, deps: T019) [REQ-030, TD-004]: a SessionStart hook prints the catch-up count when it is not zero
- [ ] T021 (S, ws-docs, deps: T005) [REQ-026]: spec-eval is frozen under the archive, with its private fixture copied out and still ignored
- [ ] T022 (M, ws-docs, deps: T010, T012, T015, T017, T018, T020, T021) [REQ-025, REQ-027]: one README explains the evals, and no live file names an old command
- [ ] T023 (S, ws-docs, deps: T022) [REQ-028]: the ADR records the rebuild and the old ADRs point to it

## Requirement Coverage
- REQ-001 → T003 → `test_core`: folder name, ignore guard on a temp repo, same-second collision
- REQ-002 → T003 → `test_core`: schema fields, `null` for unknown cost
- REQ-003 → T003, T009 → `test_core` stubbed trials (retry, ERRORED); `test_runner` trial folders
- REQ-004 → T003 → `test_core`: promote and each refusal
- REQ-005 → T003 → `test_core`: each verdict rule in order, per-suite items, new items, exit codes
- REQ-006 → T003 → `test_core`: read list, noise line, semantic review write
- REQ-007 → T004, T009, T015, T016, T018 → `test_core` argument and table tests; each suite's subcommand test
- REQ-008 → T002, T005 → `test_sandbox`: no `--add-dir`, no `evals/` in copy; recorded real `/spec` turn; review-eval and spec-eval tests pass
- REQ-009 → T002 → `test_sandbox`: Read, Bash, subagent leak traces; clean trace
- REQ-010 → T006 → `test_runner`: setup steps, placeholders, copy-a-case scenario
- REQ-011 → T006 → `test_runner`: each declared rule, custom `check.py`
- REQ-012 → T007, T008 → `test_migration`: coverage (true and false per check), map equality, fixture trees, stored expected maps
- REQ-013 → T009 → `test_runner`: PASS/FLAKY/FAIL, `--jobs` folders
- REQ-014 → T001, T010 → README entry; `BASELINE` file; observation-log rows
- REQ-015 → T011 → staleness test
- REQ-016 → T011 → trailer line format test
- REQ-017 → T012 → `tools/tests/test-check-eval-trailer.py`; CI step
- REQ-018 → T014 → stubbed driver: approval only after a draft; no pre-approval text
- REQ-019 → T014 → stubbed driver: each stop rule and its reason
- REQ-020 → T015 → grading tests on a recorded `grade.sh` JSON; one real trial; CI grader self-test unchanged
- REQ-021 → T016 → `test_review_eval.py` unchanged and passing; roll-up and trailer tests; `test-check-rescore.py` unchanged
- REQ-022 → T017 → row parser and `--from-log` tests
- REQ-023 → T017 → `rg` for the new command in `ship.md`, contracts and the log
- REQ-024 → T018 → same output and exit code from both commands
- REQ-025 → T022 → every README command run; owner run from the README (manual)
- REQ-026 → T021 → CI step on the new path; `git check-ignore`; copy listed
- REQ-027 → T022 → the spec's `rg` search
- REQ-028 → T023 → ADR index, pointer lines, `check-writing.py`
- REQ-029 → T019 → `test_todo`
- REQ-030 → T020 → hook test: count line, silent zero, silent error, 2-second limit
- REQ-031 → T013, T014 → probe record; driver writes the setting only on a recorded pass

Unmapped requirements: None
Orphan tasks: None

## Verification Strategy
- Task-focused: the packet's command; each is one of the lines below.
- Workstream:
  - ws-core: `cd tools/evals && python3 -m unittest -q test_core test_sandbox`
  - ws-gates: `cd tools/evals/workflow && python3 -m unittest -q test_runner test_migration`
  - ws-trailer: `python3 tools/tests/test-check-eval-trailer.py`
  - ws-tasks: `cd tools/evals/tasks && python3 -m unittest -q test_tasks`
  - ws-bugs: `cd tools/evals/review-eval && python3 test_review_eval.py`
  - ws-recall: `cd tools/evals/plan-recall && python3 test_recall.py`
  - ws-todo: `cd tools/evals && python3 -m unittest -q test_todo` and `bash tools/tests/test-eval-todo-hint.sh`
  - ws-docs: `python3 tools/checks/check-writing.py && python3 tools/checks/check-references.py`
- Integrated (from the repository root):
  `(cd tools/evals && python3 -m unittest -q test_core test_sandbox test_todo) && (cd tools/evals/workflow && python3 -m unittest -q test_runner test_migration) && (cd tools/evals/tasks && python3 -m unittest -q test_tasks) && (cd tools/evals/review-eval && python3 test_review_eval.py) && (cd tools/evals/plan-recall && python3 test_recall.py) && (cd tools/evals/archive/spec-eval && python3 test_judge.py && python3 test_produce.py) && python3 tools/tests/test-check-rescore.py && python3 tools/tests/test-check-eval-trailer.py && bash tools/tests/test-eval-todo-hint.sh && python3 tools/checks/harness-map.py --check && python3 tools/checks/check-references.py && python3 tools/tests/test-stale-instructions.py && python3 tools/checks/check-writing.py`
  Before T021 the spec-eval part runs from `tools/evals/spec-eval`.
- Manual/operational:
  - T001 measurement run and T010 baseline run (paid, recorded).
  - T002 one real `/spec` turn in a copied sandbox (paid, recorded).
  - T013 sandbox probe; T015 one real task trial (paid, needs `pdo_sqlite`).
  - T016 one real `bugs` run per the pre-authorization (paid).
  - REQ-025: the owner runs `gates` from the README alone.

## Sizing Exceptions
- T008 (L): the old fixture and check code may be deleted only in the slice
  that proves every case equal by replay (REQ-012). Splitting migration from
  deletion would leave a commit with two case sources and no proof that they
  agree; splitting by case group would leave `cases()` half-migrated.

## Risks and Mitigations

| Risk | Trigger/evidence | Mitigation | Task/checkpoint |
|---|---|---|---|
| The sandbox deny also blocks a stage script | the probe's `check-spec.py` call is refused | the probe records `fail` and trials run with detection only (REQ-031, DEC-012) | T013 |
| The copied harness misses a file a stage needs | the real `/spec` turn reads nothing under `.claude/`, or a refusal appears | copy all six folders and `AGENTS.md`; the real turn is the acceptance check | T002 |
| Replay passes with a weak check | a check with only true examples | coverage test fails such a check; hand-written false outputs added | T007 |
| Migration changes a gate's expected answer | replay map differs | old code stays; a changed expected answer is an owner question (spec Boundaries) | T008 |
| Measurement cost is high | T001 total cost | T010 waits for the pre-authorized limit; `--tag` for later runs | T001, T010 |
| `grade.sh` cannot run here | `pdo_sqlite` not loaded (probed) | unit work proceeds on a recorded `grade.sh` JSON; the real trial waits for the owner's install | T015 |
| Owner's uncommitted edits in `claude/settings.json` and `docs/HANDOFF.md` get committed | `git diff --cached` shows hunks the task did not write | stage only the task's own hunks (TD per pre-authorization); inspect `git diff --cached` before each commit | T020, T022 |
| The new `Eval:` check blocks this plan's own later commits | T017 and T022 edit `claude/commands/ship.md` after T012 | those commits carry `Eval:` per the pre-authorization | T017, T022 |
| Private output committed | `git status` lists a results or fixture path | ignore guard; `git check-ignore` tests | T003, T021 |

## Open Questions
None

---
Handoff: Ready for /build
