# HR-2 — task packets

Plan: docs/tasks/HR-2-plan.md · Spec: docs/specs/HR-2-SPEC.md

## T001: Measure one full gate run with the current runner

**Status:** Done

**Requirements:** REQ-014

**Description:** Paid run. Before any gate code changes, run every case once
with today's runner and keep every trial's output. The outputs feed the
replay set (T007). The figures go in the eval README.

**Acceptance criteria:**
- [ ] `.gitignore` lists `tools/evals/results/`, and `git check-ignore tools/evals/results/x` reports it (REQ-014, REQ-001 storage)
- [ ] First a sample: 5 cases from different stages, each with `--case`, into `tools/evals/results/measure-<YYYY-MM-DD>-sample`. Projected total = mean sample cost × case count. If the projection is above the TD-006 limit, stop and report it (TD-006)
- [ ] Then the rest, into `tools/evals/results/measure-<YYYY-MM-DD>` (the runner refuses an existing folder): `python3 tools/evals/workflow/run.py --output ...` ran every case in `cases()` not in the sample; each case folder holds `prompt.txt`, `trace.jsonl` and `result.json` (REQ-014)
- [ ] `tools/evals/README.md` has a "Measured" section: date, harness commit, Claude CLI version, total cost and duration, and per-case cost and duration, from `result.json` `model_usage` and `duration_ms` (REQ-014)
- [ ] Cases that ended in `execution_error` are listed by name in that section; they are rerun once with `--case` into a new folder, and the second result is the one recorded
- [ ] `git status` lists no file under `tools/evals/results/`

**Verification:**
- [ ] Manual check: the README section's total equals the sum of the per-case figures
- [ ] Tests pass: `cd tools/evals/workflow && python3 -m unittest -q test_runner`

**Dependencies:** None

**Workstream:** ws-gates

**Context pointers:**
- Project/module rules: `tools/evals/workflow/README.md` (how the runner is run); plan TD-006 (spend limit)
- Closest precedent: `docs/HANDOFF.md:96-105` (probe steps)
- Shared contract/invariant: run output is private-by-default and stays ignored

**Files/areas likely touched:**
- `.gitignore`
- `tools/evals/README.md`

**Estimated scope:** S

## T002: Headless sessions get a copied harness, and leaks are detected

**Status:** Done

**Requirements:** REQ-008, REQ-009

**Description:** New `tools/evals/sandbox.py`. `install_harness(project)`
copies `claude/{commands,agents,skills,references,docs,hooks}` and
`claude/AGENTS.md` into `<project>/.claude/` (as `CLAUDE.md` when the project
has none, as today) and writes `settings.local.json` exactly as
`spec-eval/run.py:150-160` does. `session_args(...)` builds `claude -p`
arguments with no `--add-dir`. `audit(trace_path)` returns `LEAKED` and the
offending calls. First prove that the copy works headless.

**Acceptance criteria:**
- [ ] One real headless `/spec` turn on the `fixtures/example/` intake runs in a project built by `install_harness()` with no `--add-dir`. Its stream-json trace shows reads of `.claude/commands/spec.md` and the spec skill, and no permission refusal. The command, cost and trace path are recorded in `tools/evals/README.md` (REQ-008)
- [ ] If that turn shows a refusal, the task stops and reports it: REQ-008 is then infeasible as written (SPEC CONFLICT), not patched around
- [ ] The copy holds no folder named `evals`; a test asserts it (REQ-008)
- [ ] `session_args()` never emits `--add-dir` of `claude/`, a parent of it, or a path under `claude/evals/`; a test asserts it (REQ-008)
- [ ] `audit()` marks LEAKED a trace with a `Read` of `claude/evals/add-business/hidden/checks.json`, a `Bash` command naming `evals/add-business/hidden`, and the same Bash command inside a subagent's events (events with a `parent_tool_use_id`) (REQ-009)
- [ ] `audit()` does not mark a trace that reads only sandbox and `.claude/` files (REQ-009)
- [ ] The real `/spec` turn uses `--output-format stream-json --verbose`, dispatches at least one subagent, and the recorded trace shows that subagent's tool calls with a `parent_tool_use_id`. If they do not appear, the task stops and reports it: REQ-009's subagent clause cannot be met from the trace (SPEC CONFLICT)

**Verification:**
- [ ] Tests pass: `cd tools/evals && python3 -m unittest -q test_sandbox`
- [ ] Manual check: the recorded real `/spec` turn

**Dependencies:** None

**Workstream:** ws-core

**Context pointers:**
- Project/module rules: spec Invariants section (hidden files never reach a scored trial)
- Closest precedent: `tools/evals/spec-eval/run.py:103-160` (`HARNESS_DIRS`, `link_tree`, `build_project`); `tools/evals/workflow/run.py` `audit_reads()` (`:1517`)
- Shared contract/invariant: no `--add-dir` of `claude/`; the copy excludes `evals/`

**Files/areas likely touched:**
- `tools/evals/sandbox.py`
- `tools/evals/test_sandbox.py`
- `tools/evals/README.md`

**Change-surface search:** `rg -n "add-dir|HARNESS_DIRS|link_tree|build_project|audit_reads" tools/evals`

**Estimated scope:** M

## T003: The core stores runs, runs trials, keeps baselines and gives one verdict

**Status:** Done

**Requirements:** REQ-001, REQ-002, REQ-003, REQ-004, REQ-005, REQ-006, TD-002

**Description:** New `tools/evals/core.py`. A suite supplies `items(case)`,
`run_trial(case, folder) -> dict`, and `state(trial) -> pass|fail|errored`.
The core owns the rest. Its module docstring documents schema 1 and this
interface (CP-001).

**Acceptance criteria:**
- [ ] Run folder `tools/evals/results/<suite>/<YYYY-MM-DD-HHMMSS>-<sha7>/`; refuses with exit 2 when `git check-ignore` does not report it; refuses to reuse an existing folder (REQ-001)
- [ ] `results.json` holds every schema 1 field of REQ-002; an unknown value is `null`; the run total says how many trials had no cost (REQ-002)
- [ ] Trials run `--trials N` (default 3) into `<case>/t<n>/`; an errored trial is retried once; a second failure stays ERRORED and is not scored; a retry that succeeds is noted (REQ-003)
- [ ] `baseline <suite> [<run>]` writes `results/<suite>/BASELINE`; it refuses a subset run, fewer trials than the default, an ERRORED trial, or a missing schema 1 file, each with its reason (REQ-004, TD-002)
- [ ] Verdict over items with FAIL < FLAKY < PASS, in the spec's rule order, with per-suite item kinds (case for gates and bugs, hidden check for tasks), rule 1 not applied to task checks, new items listed and not counted, exit 0/1/2 (REQ-005)
- [ ] Every spec scenario of REQ-005 is a test case, including "Task check lost" → NOT BETTER
- [ ] `report.md` and terminal output: verdict, baseline commit and date, lost/gained/flaky/new by name, a "read these" list with trial folders, cost and time beside the baseline's, the noise line when hashes match (REQ-006)
- [ ] `review <run> <case> ok|bad "<note>"` writes `semantic_review` with the note and date; the verdict does not read it (REQ-006)

**Verification:**
- [ ] Tests pass: `cd tools/evals && python3 -m unittest -q test_core`

**Dependencies:** None

**Workstream:** ws-core

**Context pointers:**
- Project/module rules: spec REQ-001–REQ-006; DEC-008 (retry once), DEC-009 (verdict over items)
- Closest precedent: `tools/evals/spec-eval/run.py:449-457` (`verdict()`), `tools/evals/review-eval/run.py:391` (exit codes)
- Shared contract/invariant: schema 1 and the suite interface, fixed at CP-001

**Files/areas likely touched:**
- `tools/evals/core.py`
- `tools/evals/test_core.py`

**Estimated scope:** M

## T004: `eval.py` prints the suite table and runs baseline, report and review

**Status:** Done

**Requirements:** REQ-007

**Acceptance criteria:**
- [ ] `python3 tools/evals/eval.py` with no arguments prints the four suites with question, when to run, and last measured cost (from the README "Measured" section, or `unmeasured`), and exits 0 (REQ-007)
- [ ] `eval.py baseline <suite>`, `eval.py report`, `eval.py review <run> <case> ok|bad "<note>"` call the core (REQ-007)
- [ ] Suites register in one table in `eval.py`; a suite not yet built prints "not built yet" and exits 2
- [ ] `--case` and `--tag` are repeatable; `--split`, `--trials` and `--jobs` parse for `gates`, `tasks` and `bugs` (REQ-007)

**Verification:**
- [ ] Tests pass: `cd tools/evals && python3 -m unittest -q test_core`

**Dependencies:** T003

**Workstream:** ws-core

**Context pointers:**
- Project/module rules: spec REQ-007
- Closest precedent: `tools/evals/review-eval/run.py` `main()` (argparse style)
- Shared contract/invariant: the suite table in `eval.py`

**Files/areas likely touched:**
- `tools/evals/eval.py`
- `tools/evals/test_core.py`

**Estimated scope:** S

## T005: spec-eval and review-eval use the shared install

**Status:** Done

**Requirements:** REQ-008

**Description:** Why the removed code exists: `adcd217` (2026-10-03, "spec-eval: run repo-backed fixtures against the project at a commit") added the link install so "the project's own .claude and CLAUDE.md stay; the harness merges beside them". The copy must keep that merge: copy per entry when the project already has the folder. `--add-dir` predates the history here (first seen in `75dfdc6`, a move); its reason is not recorded. Replace the link install and `--add-dir` in both suites with
`sandbox.install_harness()` and `sandbox.session_args()`. Move the layout
tests from `spec-eval/test_produce.py` into `tools/evals/test_sandbox.py`.

**Acceptance criteria:**
- [ ] `spec-eval/run.py` `build_project()` and `run_claude()`, and `review-eval/run.py` `produce()`, use the shared module; `rg -n "add-dir" tools/evals` matches only tests that assert its absence (REQ-008)
- [ ] `review-eval/run.py` no longer imports `spec_eval` for the install (REQ-008)
- [ ] A project with its own `.claude/agents/` keeps it, and the harness entries are added beside it (precedent `adcd217`)
- [ ] `review-eval` sessions use `--output-format stream-json --verbose` and keep the trace, so `sandbox.audit()` can read it (REQ-009)
- [ ] The moved layout tests pass in `test_sandbox.py`; `test_produce.py` keeps only what is specific to spec-eval
- [ ] `test_review_eval.py`, `test_judge.py` and `test_produce.py` pass

**Verification:**
- [ ] Tests pass: `cd tools/evals && python3 -m unittest -q test_sandbox && cd spec-eval && python3 test_judge.py && python3 test_produce.py && cd ../review-eval && python3 test_review_eval.py`

**Dependencies:** CP-001

**Workstream:** ws-core

**Context pointers:**
- Project/module rules: spec REQ-008
- Closest precedent: T002's `sandbox.py`
- Shared contract/invariant: no `--add-dir` of `claude/`

**Files/areas likely touched:**
- `tools/evals/spec-eval/run.py`
- `tools/evals/spec-eval/test_produce.py`
- `tools/evals/review-eval/run.py`
- `tools/evals/review-eval/test_review_eval.py`
- `tools/evals/test_sandbox.py`

**Change-surface search:** `rg -n "spec_eval\.|HARNESS_DIRS|link_tree|build_project|add-dir" tools/evals`

**Estimated scope:** S

## T006: A gate case is a folder with setup steps and declared checks

**Status:** Done

**Requirements:** REQ-010, REQ-011

**Description:** New `tools/evals/workflow/cases.py`: load
`cases/<id>/case.json`, build the fixture from `files/` and `setup`
(copy, write, `git init`, `git commit`, `capture`), substitute `{name}`
placeholders in later writes and in `evidence`, and evaluate declared checks.
`check.py` with `def checks(result, reads, directory) -> dict` is optional per
case. The old `cases()` path keeps working until T008.

**Acceptance criteria:**
- [ ] `case.json` fields per REQ-010; a missing field names the case and the field (REQ-010)
- [ ] A setup that commits a spec, captures `spec_sha` and writes a plan containing `{spec_sha}` yields the real commit id in the plan (REQ-010)
- [ ] Declared rules: `state`, field `regex` / `not_regex`, decision line (via `parse_decisions`), report name (via `report_name`), status line (via `status_line`), fixture unchanged, access confined (REQ-011)
- [ ] A case with `check.py` runs its custom checks beside the declared ones (REQ-011)
- [ ] Copying a test case folder and changing `case.json` adds a runnable case with no `.py` edit (REQ-010)

**Verification:**
- [ ] Tests pass: `cd tools/evals/workflow && python3 -m unittest -q test_runner`

**Dependencies:** CP-001

**Workstream:** ws-gates

**Context pointers:**
- Project/module rules: spec REQ-010, REQ-011; DEC-006
- Closest precedent: `tools/evals/workflow/run.py` `prepare()` (`:967`), `parse_decisions()` (`:1504`), `report_name()` (`:1491`), `status_line()` (`:1498`)
- Shared contract/invariant: the structured-output `SCHEMA` (`run.py:13`) is unchanged

**Files/areas likely touched:**
- `tools/evals/workflow/cases.py`
- `tools/evals/workflow/test_runner.py`

**Estimated scope:** M

## T007: The replay set covers every check, true and false

**Status:** Pending

**Requirements:** REQ-012, TD-003

**Description:** Characterization before migration. Build
`workflow/replay/<case>.json` from T001's outputs, the outputs already in
`test_runner.py`, and hand-written outputs. Store the old `checks()` map for
each output as `expected`.

**Acceptance criteria:**
- [ ] One replay file per case in today's `cases()` (REQ-012)
- [ ] For every check name of every case, at least one output gives true and one gives false under the old `checks()`; a coverage test fails and names any check that lacks one (REQ-012)
- [ ] Each output's `expected` equals what the old `checks()` returns today; the test asserts it (REQ-012)
- [ ] The replay files hold no path under `/var/www/html/leadbuster` and no private ticket key (`rg -n "LD-[0-9]|leadbuster" tools/evals/workflow/replay` is empty)

**Verification:**
- [ ] Tests pass: `cd tools/evals/workflow && python3 -m unittest -q test_migration`

**Dependencies:** T001, T006

**Workstream:** ws-gates

**Context pointers:**
- Project/module rules: spec REQ-012; plan TD-003
- Closest precedent: `tools/evals/workflow/test_runner.py` (synthetic outputs per check)
- Shared contract/invariant: `expected` is the old behavior; it is never edited to make a new check pass

**Files/areas likely touched:**
- `tools/evals/workflow/replay/`
- `tools/evals/workflow/test_migration.py`

**Estimated scope:** M

## T008: All gate cases are folders, proven equal, and the old code is gone

**Status:** Pending

**Requirements:** REQ-012

**Description:** Migrate every case to `cases/<id>/`. When the replay test
shows equal maps and equal fixture trees for every case, delete `cases()`,
`prepare()`, `prepare_probe()`, `checks()` and the fixture helpers they alone
use. Why they exist: the case fixtures were built in code from the first
workflow eval (`75dfdc6` and earlier; history before the 2026-10-03 move is
not in this repository), and the probe cases came in `9582184` (2026-11-21).
They are replaced, not dropped: every fixture and check moves to a folder,
proven equal by replay. Record this in the commit body.

**Acceptance criteria:**
- [ ] Every case of today's `cases()` exists as a folder; the count matches (REQ-012)
- [ ] For every case, the fixture tree from the folder equals the old one except commit ids and values derived from them (REQ-012)
- [ ] For every replay output, the new checks give the old `expected` map (REQ-012)
- [ ] Only after both hold: the old code is deleted; `test_migration.py` still passes against the stored `expected` maps (REQ-012)
- [ ] If any case differs and the old behavior looks wrong, the task stops and asks the owner (TD-008); it does not change `expected`

**Verification:**
- [ ] Tests pass: `cd tools/evals/workflow && python3 -m unittest -q test_runner test_migration`

**Dependencies:** T007

**Workstream:** ws-gates

**Context pointers:**
- Project/module rules: spec REQ-012; spec Boundaries ("Ask first: changing a gate case's expected answer")
- Closest precedent: T006 loader
- Shared contract/invariant: `STAGES`, `prompt()` and `SCHEMA` stay in `run.py`

**Files/areas likely touched:**
- `tools/evals/workflow/cases/`
- `tools/evals/workflow/run.py`
- `tools/evals/workflow/test_runner.py`
- `tools/evals/workflow/test_migration.py`

**Change-surface search:** `rg -n "cases\(\)|prepare_probe|prepare\(|def checks|from run import|import run" tools/evals tools/tests`

**Sizing exception:** see plan; kept L because the delete is only allowed in the same slice that proves equality.

**Estimated scope:** L

## T009: `eval.py gates` runs trials in parallel and rolls them up

**Status:** Pending

**Requirements:** REQ-003, REQ-007, REQ-013, TD-005

**Acceptance criteria:**
- [ ] `workflow/run.py` exposes `run_trial(case, folder)` for the core; each trial builds its own fixture under `<case>/t<n>/fixture/` (REQ-003, TD-005)
- [ ] `--jobs N` (default 4) runs trials in parallel; a test with a stubbed `claude` over 3 cases × 3 trials yields 9 separate trial folders (REQ-013)
- [ ] Case state PASS / FLAKY / FAIL from scored trials (REQ-013)
- [ ] `instruction_hashes` per case are recorded as today (REQ-002)
- [ ] `eval.py gates` with `--case`, `--tag`, `--split`, `--trials`, `--jobs` works (REQ-007)
- [ ] One real run: `eval.py gates --case ship_open_blocker --case fix_rerun --case testgate_figma --trials 3` prints a report

**Verification:**
- [ ] Tests pass: `cd tools/evals/workflow && python3 -m unittest -q test_runner test_migration`
- [ ] Manual check: the three-case real run's report

**Dependencies:** T008

**Workstream:** ws-gates

**Context pointers:**
- Project/module rules: spec REQ-013; DEC-003
- Closest precedent: `tools/evals/workflow/run.py` `main()` loop (`:1551-1594`)
- Shared contract/invariant: core suite interface (CP-001)

**Files/areas likely touched:**
- `tools/evals/workflow/run.py`
- `tools/evals/eval.py`
- `tools/evals/workflow/test_runner.py`

**Estimated scope:** M

## T010: Promote the first gates baseline and log its flaky cases

**Status:** Pending

**Requirements:** REQ-014

**Description:** Paid run, within TD-006's limit. Run all gate cases with 3
trials and promote the run.

**Acceptance criteria:**
- [ ] `eval.py gates` ran every case with 3 trials and no ERRORED trial after retry; `eval.py baseline gates` accepted it (REQ-014)
- [ ] Each FLAKY case has a row in `docs/observation-log.md`, in the table that fits (a harness finding), naming the case and its trial folders (REQ-014)
- [ ] `tools/evals/README.md` "Measured" section adds the 3-trial cost and time

**Verification:**
- [ ] Manual check: `cat tools/evals/results/gates/BASELINE` names the run; `eval.py report` shows "no baseline" was replaced by the run's figures

**Dependencies:** T009

**Workstream:** ws-gates

**Context pointers:**
- Project/module rules: plan TD-006 (spend limit); spec REQ-014
- Closest precedent: `docs/observation-log.md` table shapes
- Shared contract/invariant: baseline rules (REQ-004)

**Files/areas likely touched:**
- `docs/observation-log.md`
- `tools/evals/README.md`

**Estimated scope:** S

## T011: Generated watched list and the ready `Eval:` line

**Status:** Pending

**Requirements:** REQ-015, REQ-016

**Acceptance criteria:**
- [ ] `eval.py gates --write-watched` writes `tools/evals/workflow/watched.txt`: the sorted union of `claude/<path>` for every file any case's stage supplies (`STAGES` plus `COMMON_FILES` as `prompt()` selects them) (REQ-015)
- [ ] A unit test regenerates the list in memory and fails, naming the paths, when the file differs (REQ-015)
- [ ] The gates report ends with `Eval: gates <a>/<n> PASS -> <b>/<n> PASS, flaky <x> -> <y> (<VERDICT>); <run folder>`; without a baseline the `-> ` part is left out; a subset names its selection (REQ-016)

**Verification:**
- [ ] Tests pass: `cd tools/evals/workflow && python3 -m unittest -q test_runner`

**Dependencies:** CP-002

**Workstream:** ws-trailer

**Context pointers:**
- Project/module rules: spec REQ-015, REQ-016; DEC-005, DEC-007
- Closest precedent: `tools/evals/review-eval/README.md` trailer lines
- Shared contract/invariant: the trailer text format, read by T012

**Files/areas likely touched:**
- `tools/evals/workflow/run.py`
- `tools/evals/workflow/watched.txt`
- `tools/evals/core.py`
- `tools/evals/workflow/test_runner.py`

**Estimated scope:** S

## T012: CI fails a watched-file commit without an `Eval:` line

**Status:** Pending

**Requirements:** REQ-017

**Description:** New `tools/checks/check-eval-trailer.py`, modelled on
`check-rescore.py`, reading `watched.txt`. The rule starts at the commit that
adds the check: earlier commits are not checked.

**Acceptance criteria:**
- [ ] Exit 1 for a non-merge commit touching a watched path with no `Eval:` trailer, or a bare "not run"; exit 0 for a result line or `not run - <reason>`; exit 2 on a git error; an all-zero range start is skipped (REQ-017)
- [ ] Commits older than the check's own commit are skipped (REQ-017)
- [ ] It never reads `Review-eval:`; a commit to `claude/commands/review.md` with only `Review-eval:` fails this check and passes `check-rescore.py` (REQ-017)
- [ ] `tools/tests/test-check-eval-trailer.py` covers: missing, bare not run, reason, result, unwatched commit, both trailers, zero range, pre-rule commit
- [ ] `.github/workflows/ci.yml` has a step beside "Reviewer changes carry a rescore", with the same range logic; `tools/checks/README.md` lists the check; `docs/harness-map.html` regenerated
- [ ] This task's own commit carries `Eval: not run - adds the check, no decision changed`

**Verification:**
- [ ] Tests pass: `python3 tools/tests/test-check-eval-trailer.py && python3 tools/tests/test-check-rescore.py`
- [ ] Build/static check succeeds: `python3 tools/checks/harness-map.py --check`

**Dependencies:** T011

**Workstream:** ws-trailer

**Context pointers:**
- Project/module rules: ADR 0111; spec REQ-017
- Closest precedent: `tools/checks/check-rescore.py`, `tools/tests/test-check-rescore.py`, ci.yml step "Reviewer changes carry a rescore"
- Shared contract/invariant: `watched.txt` (T011)

**Files/areas likely touched:**
- `tools/checks/check-eval-trailer.py`
- `tools/tests/test-check-eval-trailer.py`
- `tools/checks/README.md`
- `.github/workflows/ci.yml`
- `docs/harness-map.html`

**Change-surface search:** `rg -n "check-rescore" .github tools docs/harness-map.html`

**Estimated scope:** M

## T013: Probe the Bash sandbox and record whether prevention is on

**Status:** Pending

**Requirements:** REQ-031

**Description:** Paid probe. In a project built by `install_harness()`,
write Claude Code's sandbox settings into `settings.local.json` so Bash may
not read under `claude/evals/`, by the repository path
(`/var/www/html/personal/harness/claude/evals/`) and by any `~/.claude/...`
path that resolves into it. The rest of the repository stays readable: the
stages run `~/.claude/skills/.../check-spec.py` and `check-plan.py` through
links into it (spec DEC-012). Run one headless session and one subagent that
each `cat` `<harness>/claude/evals/add-business/ticket.md`, and have the
session run `python3 ~/.claude/skills/spec-driven-development/scripts/check-spec.py`
on a sample spec.

**Acceptance criteria:**
- [ ] The probe script `tools/evals/tasks/probe_sandbox.py` records `pass` only when both `cat` reads are refused and the `check-spec.py` call runs and prints its result; otherwise `fail` (REQ-031)
- [ ] A unit test feeds the record parser a probe trace where `check-spec.py` was refused, and gets `fail` (REQ-031 "Stage scripts blocked")
- [ ] The setting denies nothing outside `claude/evals/`; the test asserts the written deny paths (REQ-031, DEC-012)
- [ ] `tools/evals/README.md` records the result, date, Claude Code version and the exact setting used (REQ-031)
- [ ] When the result is `fail`, nothing else changes: T014 runs with detection only

**Verification:**
- [ ] Manual check: the recorded probe result
- [ ] Tests pass: `cd tools/evals/tasks && python3 -m unittest -q test_tasks` (the record parser)

**Dependencies:** T005

**Workstream:** ws-tasks

**Context pointers:**
- Project/module rules: spec REQ-031, DEC-011, DEC-012; plan External Tool Access (not probed yet)
- Closest precedent: T002's real-turn record
- Shared contract/invariant: the probe record line, read by T014

**Files/areas likely touched:**
- `tools/evals/tasks/probe_sandbox.py`
- `tools/evals/tasks/test_tasks.py`
- `tools/evals/README.md`

**Estimated scope:** S

## T014: The tasks driver runs the pipeline headless and stops with a reason

**Status:** Pending

**Requirements:** REQ-018, REQ-019, TD-001

**Description:** `tools/evals/tasks/run.py`: `setup.sh` into the trial
folder, `install_harness()`, the sandbox setting when T013 recorded `pass`,
then `/spec`, `/plan`, `/build`, `/test`, `/review` with `claude -p` and
`--resume` within a stage.

**Acceptance criteria:**
- [ ] After `/spec` or `/plan` presents a Draft and asks for approval, the driver sends the separate owner turn of REQ-018, in that session (REQ-018)
- [ ] A test scans every turn sent before a draft exists: none contains "approve" (REQ-018)
- [ ] REQUIRED or BLOCKER findings from `/review` get one fix round as the pipeline routes it (REQ-018)
- [ ] Stops on BLOCKED, an owner question other than the approval, a stage time limit, or 90 minutes of wall time; records reason and stage (REQ-019)
- [ ] All of the above are tested with a stubbed `claude` that replays recorded stage outputs
- [ ] The sandbox setting (eval content only, DEC-012) is written only when the probe record says `pass`; otherwise every `tasks` report starts with "prevention off: detection only" (REQ-031)

**Verification:**
- [ ] Tests pass: `cd tools/evals/tasks && python3 -m unittest -q test_tasks`

**Dependencies:** T013

**Workstream:** ws-tasks

**Context pointers:**
- Project/module rules: ADR 0148; spec REQ-018, REQ-019, DEC-002
- Closest precedent: `tools/evals/spec-eval/run.py:196-216` (resume and reply turn); workflow case `owner_approves_read_spec`
- Shared contract/invariant: no pre-approval text before a draft

**Files/areas likely touched:**
- `tools/evals/tasks/run.py`
- `tools/evals/tasks/test_tasks.py`
- `tools/evals/tasks/fixtures/` (recorded stage outputs for the stub)

**Estimated scope:** M

## T015: Task trials are graded by the hidden tests

**Status:** Pending

**Requirements:** REQ-007, REQ-020

**Acceptance criteria:**
- [ ] After each trial, `grade.sh <sandbox>` runs and its JSON is stored in the trial folder (REQ-020)
- [ ] Trial record: checks passed of total, failed check ids, stop reason, stage reached, LEAKED from `sandbox.audit()` (REQ-020, REQ-009)
- [ ] Per hidden check: PASS / FLAKY / FAIL over trials; case result: trials that passed every check (REQ-020)
- [ ] The report says that 3 trials measure consistency and one trial's change is not proof (REQ-020)
- [ ] `eval.py tasks` runs the suite (REQ-007)
- [ ] Grading is tested on a recorded `grade.sh` JSON without PHP
- [ ] One real trial (`eval.py tasks --trials 1`) is recorded with its cost in the README. If `pdo_sqlite` is still missing, this criterion is BLOCKED and reported, per TD-007
- [ ] The CI grader step is unchanged and passes (REQ-020)

**Verification:**
- [ ] Tests pass: `cd tools/evals/tasks && python3 -m unittest -q test_tasks`
- [ ] Manual check: the real trial record

**Dependencies:** T014

**Workstream:** ws-tasks

**Context pointers:**
- Project/module rules: `claude/evals/add-business/README.md`; spec REQ-020; DEC-009
- Closest precedent: `claude/evals/add-business/grade.sh` output shape
- Shared contract/invariant: hidden checks are items for the verdict

**Files/areas likely touched:**
- `tools/evals/tasks/run.py`
- `tools/evals/tasks/test_tasks.py`
- `tools/evals/eval.py`
- `tools/evals/README.md`

**Estimated scope:** M

## T016: `eval.py bugs` runs shipped-bug cases with trials

**Status:** Pending

**Requirements:** REQ-007, REQ-021

**Acceptance criteria:**
- [ ] `review-eval/run.py` exposes `run_trial(case, folder)`; the judge (`judge()`, `:193`) is unchanged (REQ-021)
- [ ] Bug case: PASS only if every trial is CAUGHT; FLAKY if some; FAIL if none. Clean case: PASS only if no trial has a BLOCKER or REQUIRED finding (REQ-021)
- [ ] The report ends with a `Review-eval:` line that `check-rescore.py` accepts (REQ-021)
- [ ] `test_review_eval.py` and `test-check-rescore.py` pass unchanged; new roll-up and trailer tests added (REQ-021)
- [ ] `eval.py bugs --repo <project>` runs the suite (REQ-007)
- [ ] One real run per TD-009 is recorded with its cost in the README

**Verification:**
- [ ] Tests pass: `cd tools/evals/review-eval && python3 test_review_eval.py && cd ../../.. && python3 tools/tests/test-check-rescore.py`

**Dependencies:** T005

**Workstream:** ws-bugs

**Context pointers:**
- Project/module rules: ADR 0093, 0111, 0143; spec REQ-021
- Closest precedent: `tools/evals/review-eval/run.py`
- Shared contract/invariant: `Review-eval:` format (`tools/checks/check-rescore.py` docstring)

**Files/areas likely touched:**
- `tools/evals/review-eval/run.py`
- `tools/evals/review-eval/test_review_eval.py`
- `tools/evals/eval.py`
- `tools/evals/README.md`

**Estimated scope:** M

## T017: Add a bug case from the log, and `/ship` prints that command

**Status:** Pending

**Requirements:** REQ-022, REQ-023

**Acceptance criteria:**
- [ ] `eval.py bugs add --repo <p> --from-log <sha> --defect <re>...` finds the "Shipped bugs" row whose fix-commit column names the sha, uses its bug text as the description, and builds the case as `run.py --new --fix` does (REQ-022)
- [ ] No row → exit 2 with "no Shipped bugs row names <sha>"; no `--defect` → refused (REQ-022)
- [ ] Without `--from-log`, `bugs add` accepts `run.py --new`'s arguments (REQ-022)
- [ ] `claude/commands/ship.md:86-87, 298`, `claude/references/component-response-contracts.md:451` and `docs/observation-log.md:227-231` show `python3 tools/evals/eval.py bugs add --repo <project> --from-log <fix sha> --defect <term>` (REQ-023)
- [ ] The commit that edits `ship.md` carries an `Eval:` line per TD-010

**Verification:**
- [ ] Tests pass: `cd tools/evals/review-eval && python3 test_review_eval.py && cd ../../.. && python3 tools/tests/test-contracts-doc.py && python3 tools/checks/check-references.py`
- [ ] Build/static check succeeds: `rg -n "review-eval/run.py --new" claude docs/observation-log.md` is empty

**Dependencies:** T016, T012

**Workstream:** ws-bugs

**Context pointers:**
- Project/module rules: ADR 0100; spec REQ-022, REQ-023
- Closest precedent: `tools/evals/review-eval/run.py --new`
- Shared contract/invariant: the observation log's "Shipped bugs" table columns

**Files/areas likely touched:**
- `tools/evals/eval.py`
- `tools/evals/review-eval/run.py`
- `tools/evals/review-eval/test_review_eval.py`
- `claude/commands/ship.md`
- `claude/references/component-response-contracts.md`
- `docs/observation-log.md`

**Change-surface search:** `rg -n "review-eval/run.py --new" claude docs tools README.md ARCHITECTURE.md`

**Estimated scope:** S

## T018: `eval.py recall` passes through to `recall.py`

**Status:** Pending

**Requirements:** REQ-007, REQ-024

**Acceptance criteria:**
- [ ] `eval.py recall <args>` runs `plan-recall/recall.py <args>` and returns its exit code; no run folder, no trials (REQ-024)
- [ ] A test on a temp git repo gives the same stdout and exit code from both commands (REQ-024)

**Verification:**
- [ ] Tests pass: `cd tools/evals/plan-recall && python3 test_recall.py && cd .. && python3 -m unittest -q test_core`

**Dependencies:** CP-001

**Workstream:** ws-recall

**Context pointers:**
- Project/module rules: ADR 0067
- Closest precedent: `tools/evals/plan-recall/recall.py`
- Shared contract/invariant: recall's flags unchanged

**Files/areas likely touched:**
- `tools/evals/eval.py`
- `tools/evals/test_core.py`

**Estimated scope:** XS

## T019: `eval.py todo` lists skipped eval steps

**Status:** Pending

**Requirements:** REQ-029

**Acceptance criteria:**
- [ ] In a project checkout: lists each ticket with an Approved `docs/tasks/<T>-plan.md`, a `(<T> T` commit subject on the default branch, and no Plan recall row in the harness `docs/observation-log.md`, with a ready `eval.py recall` command (REQ-029)
- [ ] Lists each Shipped bugs row with an empty or `—` Eval case column, with a ready `eval.py bugs add --from-log` command (REQ-029)
- [ ] No `docs/tasks/` → bug rows only; nothing found → "nothing to catch up"; always exit 0; `--count` prints `<tickets> <bugs>` only (REQ-029)
- [ ] No model, no network: the test runs with `PATH` lacking `claude` (REQ-029)
- [ ] The four spec scenarios are tests on a temp git repo and a sample log

**Verification:**
- [ ] Tests pass: `cd tools/evals && python3 -m unittest -q test_todo`

**Dependencies:** T017, T018

**Workstream:** ws-todo

**Context pointers:**
- Project/module rules: spec REQ-029, DEC-010
- Closest precedent: `tools/evals/plan-recall/recall.py` (git reading, `--subject-only`)
- Shared contract/invariant: observation-log table columns

**Files/areas likely touched:**
- `tools/evals/todo.py`
- `tools/evals/test_todo.py`
- `tools/evals/eval.py`

**Estimated scope:** S

## T020: SessionStart prints the catch-up count

**Status:** Pending

**Requirements:** REQ-030, TD-004

**Acceptance criteria:**
- [ ] `claude/hooks/eval-todo-hint.sh` prints `evals: <n> tickets without recall, <m> bugs without a case — run eval.py todo` when the count is above zero (REQ-030)
- [ ] Zero, a failure, or more than 2 seconds → no output, exit 0 (REQ-030)
- [ ] Registered in `claude/settings.json` under `SessionStart` matcher `startup|resume`, after `warn-stale-base.sh` (TD-004)
- [ ] `tools/tests/test-eval-todo-hint.sh` covers the four cases with a stubbed `eval.py`
- [ ] `docs/harness-map.html` regenerated
- [ ] The commit stages only this task's hunks of `claude/settings.json`; the owner's existing uncommitted hunk stays unstaged (TD-011)

**Verification:**
- [ ] Tests pass: `bash tools/tests/test-eval-todo-hint.sh`
- [ ] Build/static check succeeds: `python3 tools/checks/harness-map.py --check`
- [ ] Manual check: `git diff --cached claude/settings.json` shows only the new hook entry before the commit

**Dependencies:** T019

**Workstream:** ws-todo

**Context pointers:**
- Project/module rules: spec REQ-030; global rule on isolating commits; plan TD-004, TD-011
- Closest precedent: `claude/hooks/warn-stale-base.sh`, `tools/tests/test-worktree-hooks.sh`
- Shared contract/invariant: hooks never block a session

**Files/areas likely touched:**
- `claude/hooks/eval-todo-hint.sh`
- `claude/settings.json`
- `tools/tests/test-eval-todo-hint.sh`
- `tools/tests/README.md`
- `docs/harness-map.html`

**Change-surface search:** `rg -n "warn-stale-base" claude tools docs/harness-map.html`

**Estimated scope:** S

## T021: spec-eval is frozen, its private fixture kept and ignored

**Status:** Pending

**Requirements:** REQ-026

**Description:** spec-eval predates the history here (first seen in `75dfdc6`, 2026-10-03, a move); ADR 0079 and 0117 shaped it. DEC-001 freezes it, not deletes it. It runs on branch `HR-2` in the main checkout (TD-012), so the ignored fixture moves with the folder.

**Acceptance criteria:**
- [ ] Before the move: `tools/evals/spec-eval/fixtures/LD-380/` is copied to `~/harness-archive/spec-eval-fixtures/LD-380/`; `tools/evals/archive/README.md` records the path (REQ-026)
- [ ] `git mv tools/evals/spec-eval tools/evals/archive/spec-eval`; the ignored fixture folder is moved with it (REQ-026)
- [ ] `git check-ignore tools/evals/archive/spec-eval/fixtures/LD-380/intake.md` reports it ignored; `git status` does not list it (REQ-026)
- [ ] The CI step "Spec-eval judging logic" runs from the new path and passes (REQ-026)
- [ ] `eval.py` has no spec-eval suite (REQ-026)

**Verification:**
- [ ] Tests pass: `cd tools/evals/archive/spec-eval && python3 test_judge.py && python3 test_produce.py`
- [ ] Manual check: `ls ~/harness-archive/spec-eval-fixtures/LD-380/` shows `intake.md` and `expectations.json`

**Dependencies:** T005

**Workstream:** ws-docs

**Context pointers:**
- Project/module rules: spec REQ-026, DEC-001
- Closest precedent: `tools/evals/spec-eval/.gitignore` (folder-relative rules)
- Shared contract/invariant: private fixtures are never committed

**Files/areas likely touched:**
- `tools/evals/archive/spec-eval/`
- `tools/evals/archive/README.md`
- `.github/workflows/ci.yml`
- `docs/harness-map.html`

**Change-surface search:** `rg -n "evals/spec-eval|spec_eval|spec-eval/" .github tools claude docs README.md ARCHITECTURE.md`

**Estimated scope:** S

## T022: One README explains the evals; no live file names an old command

**Status:** Pending

**Requirements:** REQ-025, REQ-027

**Acceptance criteria:**
- [ ] `tools/evals/README.md` covers every point of REQ-025, in plain words, and lists spec-eval under "Archived" with a review date one month after T021 (REQ-025, REQ-026)
- [ ] Each suite README starts by pointing to `eval.py` (REQ-025)
- [ ] Every command on the page was run as written; the task report lists each with its exit code (REQ-025)
- [ ] References updated in `.github/workflows/ci.yml` (header comment), `README.md`, `ARCHITECTURE.md`, `tools/README.md`, `docs/HANDOFF.md`, `docs/observation-log.md`, `claude/commands/ship.md`, `claude/references/component-response-contracts.md` (REQ-027)
- [ ] `rg -n "tools/evals/(spec-eval|review-eval|workflow)/run.py"` matches only suite READMEs, the archive, ADRs and dated logs or audits (REQ-027)
- [ ] Commits stage only this task's hunks of `docs/HANDOFF.md`; any commit editing `claude/commands/ship.md` carries an `Eval:` line per TD-010
- [ ] Manual: the owner runs `gates` from the README alone and states the verdict; recorded in the task report (REQ-025)

**Verification:**
- [ ] Build/static check succeeds: `python3 tools/checks/check-references.py && python3 tools/tests/test-stale-instructions.py && python3 tools/checks/harness-map.py --check && python3 tools/checks/check-writing.py`

**Dependencies:** T010, T012, T015, T017, T018, T020, T021

**Workstream:** ws-docs

**Context pointers:**
- Project/module rules: `claude/AGENTS.md` §Writing for humans; spec REQ-025, REQ-027
- Closest precedent: `tools/tests/README.md` (one-page shape)
- Shared contract/invariant: none

**Files/areas likely touched:**
- `tools/evals/README.md`
- `tools/evals/workflow/README.md`
- `tools/evals/review-eval/README.md`
- `tools/evals/plan-recall/README.md`
- `claude/evals/add-business/README.md`
- `.github/workflows/ci.yml`
- `README.md`
- `ARCHITECTURE.md`
- `tools/README.md`
- `docs/HANDOFF.md`
- `docs/observation-log.md`
- `claude/commands/ship.md`
- `claude/references/component-response-contracts.md`

**Change-surface search:** `rg -n "tools/evals/(spec-eval|review-eval|workflow|plan-recall)|evals/add-business" --glob '!docs/adr/**' --glob '!tools/evals/**'`

**Estimated scope:** M

## T023: The ADR records the rebuild

**Status:** Pending

**Requirements:** REQ-028

**Acceptance criteria:**
- [ ] `docs/adr/0149-one-eval-runner-trials-and-baselines.md` records every point of REQ-028 in the Decision/Rejected format, including why ADR 0079's rejection of a significance test still stands (REQ-028)
- [ ] ADR 0079 has a "Superseded in part by 0149" line; ADRs 0067, 0093, 0100, 0111, 0117 and 0143 each have one "Run through `eval.py` (ADR 0149)" line where they name a command (REQ-028)
- [ ] `docs/adr/README.md` lists 0149 (REQ-028)

**Verification:**
- [ ] Build/static check succeeds: `python3 tools/checks/check-writing.py && python3 tools/checks/check-references.py`

**Dependencies:** T022

**Workstream:** ws-docs

**Context pointers:**
- Project/module rules: `adr-recording` skill; `~/.claude/references/records.md`
- Closest precedent: `docs/adr/0111-reviewer-changes-are-rescored.md`, `docs/adr/0117-evals-carry-tags-and-a-holdout-split.md`
- Shared contract/invariant: none

**Files/areas likely touched:**
- `docs/adr/0149-one-eval-runner-trials-and-baselines.md`
- `docs/adr/README.md`
- `docs/adr/0079-eval-integrity-and-paired-comparison.md`
- `docs/adr/0067-change-surface-in-plans-and-plan-recall.md`
- `docs/adr/0093-review-eval-and-noise-count.md`
- `docs/adr/0100-shipped-bugs-become-eval-cases.md`
- `docs/adr/0111-reviewer-changes-are-rescored.md`
- `docs/adr/0117-evals-carry-tags-and-a-holdout-split.md`
- `docs/adr/0143-review-eval-judges-the-defect-not-the-location.md`

**Estimated scope:** S
