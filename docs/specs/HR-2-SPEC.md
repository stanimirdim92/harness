# Spec: One eval runner the owner uses

Status: Approved
Ticket: N/A (harness work; key HR-2 for the eval rebuild)
Change kind: Modify
Supersedes: N/A (ADR 0079's comparison rules are superseded in part by the ADR in REQ-028)
Approved by: the owner (reply "approved, commit on main" in the Claude Code session, 2026-11-24; reapproved after the REQ-031 revision, same reply, 2026-11-24)
Approved at: 2026-11-24

Index: [Objective](#objective) · [Capability Map](#capability-map) ·
[Change Impact](#change-impact) · [Requirements](#requirements) ·
[Material Decisions](#material-decisions) · [Testing Strategy](#testing-strategy)

## Objective

The owner has never run the harness evals alone. Five tools have five command
lines, three fixture formats and three verdict styles. Comparison needs a
manual `--baseline <path>`. Most cases run once, and one run is noise (two
spec-eval runs of one harness scored 23/35 and 26/35). A new gate case means
editing `tools/evals/workflow/run.py` (1597 lines) in three places.

This change gives the owner one command, `tools/evals/eval.py`. It runs each
model-driven case several times, compares the run with a stored baseline, and
prints one short report. Gate cases become folders of data. The full-pipeline
eval (add-business) runs without the owner. A commit that changes a file the
gate cases read carries an `Eval:` trailer, checked in CI.

Background and the full reasoning: `docs/eval-rebuild-plan.md`. That plan is
input; this spec is the contract.

Out of scope:
- A cost cap per run. It waits for the cost measurement in REQ-014 (plan Q4).
- New tasks beyond add-business (plan B6).
- A model judge for spec quality, an optimizer loop (rejected, ADR 0117),
  significance tests, model runs in CI.
- Codex reviewer and gate files in the `Eval:` watched list. Gate cases do
  not read them (REQ-015).

## Capability Map

Approved by the owner on 2026-11-24 in the Claude Code session ("Yes").

| Module id | Responsibility | Depends on | Requirements |
|---|---|---|---|
| eval-core | Run storage and its gitignore guard, `results.json` schema, trials, baseline, verdict, report, the `eval.py` entry, harness install for headless runs, the read audit | — | REQ-001–REQ-009 |
| gates | Gate cases as folders, their migration, trials and results, the first measurement and baseline | eval-core | REQ-010–REQ-014 |
| gate-trailer | The generated watched list, the `Eval:` trailer line, the CI check | gates | REQ-015–REQ-017 |
| tasks | Headless add-business driver with the scripted owner turn, stop rules, grading, the Bash sandbox | eval-core | REQ-018–REQ-020, REQ-031 |
| bugs | review-eval under the core, the `Review-eval:` line, case creation from the observation log | eval-core | REQ-021–REQ-023 |
| recall | plan-recall through `eval.py` | eval-core | REQ-024 |
| docs-archive | The one-page README, spec-eval frozen, old references updated, the ADR | all modules above | REQ-025–REQ-028 |
| todo | `eval.py todo` and the session-start hint: shipped tickets without a recall row, shipped bugs without a case | recall, bugs | REQ-029–REQ-030 |

Build order: eval-core → gates → gate-trailer; eval-core → tasks, bugs, recall;
bugs, recall → todo; then docs-archive.

The `todo` module was added on 2026-11-24 after the map was approved, from the
owner's answer "eval.py todo + session hint". The other modules are unchanged.

## Change Impact

- Added behavior: `eval.py todo` and a SessionStart hint (REQ-029, REQ-030);
  `tools/evals/eval.py` and `tools/evals/core.py` (REQ-001–
  REQ-007); trials and baselines for every model-driven suite; the headless
  `tasks` driver (REQ-018–REQ-020); the `Eval:` trailer and
  `tools/checks/check-eval-trailer.py` (REQ-015–REQ-017);
  `eval.py bugs add --from-log` (REQ-022).
- Modified behavior:
  - Gate cases move from `workflow/run.py` code to case folders (REQ-010–
    REQ-012). The workflow CLI's per-run output layout changes to the core
    layout (REQ-001, REQ-003).
  - The harness-install code moves from `spec-eval/run.py` to a shared module.
    No session for a headless run gets `--add-dir` of `claude/` (REQ-008).
  - The command `/ship` prints for a shipped bug changes to
    `eval.py bugs add` (REQ-023).
  - ADR 0079's "compare by eye, run each side twice" is replaced by trials and
    the verdict rule (REQ-005, REQ-028).
- Removed behavior: spec-eval leaves the main path. It is frozen under
  `tools/evals/archive/spec-eval/`, with its unit tests kept in CI (REQ-026).
- Renamed behavior: N/A. Suite names (`gates`, `tasks`, `bugs`, `recall`) are
  new names in `eval.py`; folder paths stay except spec-eval's.
- Explicitly preserved behavior:
  - The `Review-eval:` trailer format and `check-rescore.py`, with its tests,
    unchanged (REQ-021).
  - The review-eval judge: defect terms near the fixed lines, CAUGHT /
    LOCATED / MISSED (ADR 0143) (REQ-021).
  - The holdout rule: a lost holdout case is WORSE (ADR 0117) (REQ-005).
  - The add-business hidden checks, `setup.sh`, `grade.sh`, and the CI grader
    self-test (reference 49/49, seed fails) (REQ-020).
  - plan-recall's flags and figures (REQ-024).
  - Every gate case's assertions, as proven by REQ-012.
  - The gates: no case or driver text pre-approves a spec or plan
    (ADR 0148) (REQ-018).
- Compatibility/migration constraints:
  - Private data: review-eval cases, the spec-eval `LD-380` fixture and all
    run output name a private project. The repository is public. They stay
    gitignored (REQ-001, REQ-026).
  - The `LD-380` and `ld-585*` fixtures exist on this machine only. Git cannot
    restore them (REQ-026).
  - Runs made before this change have no schema 1 `results.json`. They cannot
    be a baseline (REQ-004).

## Requirements

### eval-core

### Requirement: REQ-001 — Runs are stored in one ignored place
Source: owner decision Q5, 2026-11-24 ("Inside, gitignored"); plan §5.6

The eval core MUST write each run to
`tools/evals/results/<suite>/<YYYY-MM-DD-HHMMSS>-<sha7>/`, where `<sha7>` is
the harness commit. If `git check-ignore` does not report that folder as
ignored, then the core MUST stop before it writes anything, with exit 2.

#### Scenario: Normal run
- GIVEN `tools/evals/results/` is listed in `.gitignore`
- WHEN `eval.py gates` starts at harness commit `abc1234`
- THEN it writes to `tools/evals/results/gates/2026-12-01-101500-abc1234/`

#### Scenario: Ignore rule missing
- GIVEN the `.gitignore` line for `tools/evals/results/` was removed
- WHEN any suite starts
- THEN it prints that the results folder is not ignored, writes nothing, and exits 2

#### Scenario: Two runs in the same second
- GIVEN a run folder with the same name exists
- WHEN a second run starts
- THEN it stops with exit 2 and does not overwrite the first folder

### Requirement: REQ-002 — One results format
Source: plan §5.6; F3, F4 of the plan

Every suite MUST write one `results.json` per run with `"schema": 1` and:
the suite name; the harness commit, dirty flag and `instruction_hashes` (for
`gates`, each file a case's prompt supplies; for `tasks` and `bugs`, each file
of the installed harness, REQ-008); the
model; the trial count; start time, duration and cost; and per case its id,
split, tags, result, and per trial its number, state, checks, cost, duration
and folder. A field the suite cannot know MUST be `null`, never left out.

#### Scenario: Gate run
- GIVEN a gate run of 2 cases with 3 trials
- WHEN it finishes
- THEN `results.json` holds `"schema": 1`, 2 cases, 3 trials each, and the per-trial `checks` map

#### Scenario: Unknown cost
- GIVEN the CLI returns no cost for a trial
- WHEN the trial is written
- THEN its `cost_usd` is `null` and the run total says how many trials had no cost

### Requirement: REQ-003 — Trials
Source: owner decision Q3, 2026-11-24 ("3, --trials to raise"); plan §5.3

Each model-driven case MUST run `--trials N` times, default 3, each trial in
its own folder `<case>/t<n>/`. When a trial ends with a timeout, a CLI error,
or empty output, the core MUST mark it ERRORED, retry it once, and MUST NOT
score an ERRORED trial as a pass or a fail.

#### Scenario: Default
- GIVEN no `--trials` flag
- WHEN `eval.py gates --case ship_open_blocker` runs
- THEN folders `t1/`, `t2/`, `t3/` exist under the case folder

#### Scenario: Infrastructure failure
- GIVEN trial 2 times out, and its retry also times out
- WHEN the case result is computed
- THEN trial 2 is ERRORED, the result counts 2 scored trials, and the report names the ERRORED trial

#### Scenario: Retry succeeds
- GIVEN trial 2 times out and its retry passes
- WHEN the case result is computed
- THEN trial 2 counts as a pass and the report notes one retry

### Requirement: REQ-004 — Baselines are promoted on purpose
Source: plan §5.5; advisor review (a subset or errored run must never become the baseline)

A run MUST become a suite's baseline only through `eval.py baseline <suite>
[<run>]`, which takes the latest run when none is named. The command MUST
refuse a run that did not cover every case of the suite, ran fewer trials
than the default, had an ERRORED trial after retry, or has no schema 1
`results.json`.

#### Scenario: Promote a full run
- GIVEN a full gate run with 3 trials and no ERRORED trial
- WHEN the owner runs `eval.py baseline gates`
- THEN that run is recorded as the gates baseline

#### Scenario: Refuse a subset
- GIVEN the latest run used `--tag ship`
- WHEN the owner runs `eval.py baseline gates`
- THEN it refuses and names the reason: not every case ran

#### Scenario: Refuse a quick look
- GIVEN the latest run used `--trials 1`
- WHEN the owner runs `eval.py baseline gates`
- THEN it refuses: fewer trials than the default 3

#### Scenario: No baseline yet
- GIVEN no baseline exists for `tasks`
- WHEN `eval.py tasks` finishes
- THEN the report shows results without a verdict and says how to promote the run

### Requirement: REQ-005 — Verdict
Source: ADR 0079 (item-by-item comparison), ADR 0117 (holdout), plan §5.5; DEC-009

When a baseline exists, the run MUST compare every item it ran with the same
item in the baseline. An item is a case for `gates` and `bugs`, and a hidden
check for `tasks`. Each item has a state, ordered FAIL < FLAKY < PASS
(REQ-013, REQ-020, REQ-021). An item is gained when its state moved up and
lost when it moved down. The run MUST give one verdict, the first that
applies:
1. WORSE: for `gates`, any case lost; for any suite, a holdout case the
   baseline had at PASS is no longer PASS.
2. NOT BETTER: as many or more items lost than gained.
3. BETTER: more items gained than lost.
4. SAME: no item changed.

Rule 1 MUST NOT apply to `tasks` hidden checks, which are not holdout items.
The exit code MUST be 0 for BETTER or SAME and 1 for NOT BETTER or WORSE. If
the run could not finish, then the exit code MUST be 2. An item in the run but
not in the baseline MUST be listed as new and MUST NOT count as gained or
lost.

#### Scenario: Gate becomes flaky
- GIVEN the baseline has `ship_open_blocker` PASS (3/3)
- WHEN a run has it at 2/3 and gains two other cases
- THEN the verdict is WORSE and the report names `ship_open_blocker`

#### Scenario: Holdout lost
- GIVEN a holdout bug case CAUGHT in the baseline
- WHEN a run misses it and gains three optimization cases
- THEN the verdict is WORSE

#### Scenario: Subset run
- GIVEN a run with `--tag ship` of 8 cases, all unchanged
- WHEN it is compared
- THEN the verdict is SAME and covers only those 8 cases

#### Scenario: Task check lost
- GIVEN the `tasks` baseline has hidden check `AC3-dup-phone` at PASS (3/3) and no other change
- WHEN a run has it at 2/3 and gains `IR-double-submit` from FLAKY to PASS
- THEN one item is lost and one gained, so the verdict is NOT BETTER, not WORSE

#### Scenario: New case
- GIVEN a case added after the baseline
- WHEN a run includes it
- THEN the report lists it under "new" and the verdict ignores it

### Requirement: REQ-006 — Report
Source: plan §5.6, §5.7; F4 (semantic review pending)

Each run MUST print a report and save it as `report.md` in the run folder. It
MUST show, per suite: the verdict and the baseline commit and date; lost,
gained, flaky and new cases by name; a "read these" list with the trial
folder of every case that changed state and every FLAKY case; cost and
duration with the baseline's figures. When the run's `instruction_hashes`
equal the baseline's, the report MUST say "harness unchanged since baseline:
this run measures noise". `eval.py review <run> <case> ok|bad "<note>"` MUST
record a semantic review in that run's `results.json`; the verdict MUST NOT
wait for it.

#### Scenario: Read list
- GIVEN `specgate_default_dec` passed 2 of 3 trials
- WHEN the report prints
- THEN "read these" names `specgate_default_dec` and its failing trial folder

#### Scenario: Noise run
- GIVEN no harness file changed since the baseline
- WHEN `eval.py gates` runs
- THEN the report prints the noise line

#### Scenario: Semantic review
- GIVEN a run with `semantic_review: pending` on `fix_rerun`
- WHEN the owner runs `eval.py review <run> fix_rerun ok "names CODE-1 skip"`
- THEN that case's `semantic_review` holds `ok`, the note and the date

### Requirement: REQ-007 — One entry point
Source: plan §5.2; owner goal "one command"

`tools/evals/eval.py` MUST provide `gates`, `tasks`, `bugs`, `recall`,
`baseline`, `report` and `review`. `gates`, `tasks` and `bugs` MUST accept
`--case` (repeatable), `--tag` (repeatable), `--split`, and `--trials`.
When `eval.py` gets no arguments, it MUST print the suite table: name,
question, when to run, last measured cost.

#### Scenario: Help
- GIVEN no arguments
- WHEN the owner runs `python3 tools/evals/eval.py`
- THEN it prints the four suites with their question and last measured cost, and exits 0

#### Scenario: Reprint
- GIVEN a finished gates run
- WHEN the owner runs `eval.py report`
- THEN it prints the last run's report again without running anything

### Requirement: REQ-008 — Headless runs get a copy of the harness, not the evals
Source: plan F1, F2; advisor review (hidden-test leak); `spec-eval/run.py:103-120, 214-216`

Today the install links `claude/commands`, `agents`, `skills`, `references`,
`docs` and `hooks` into the project's `.claude/` and passes `--add-dir
claude/`, so the session may read through the links. When the core starts a
headless Claude session for a suite, it MUST instead copy those six folders
and `AGENTS.md` into the project's `.claude/`, and write
`settings.local.json` as today. The session arguments MUST NOT contain
`--add-dir` of `claude/` or of any folder that contains `claude/evals/`. The
copy MUST NOT contain any `evals/` folder. spec-eval and review-eval MUST use
this shared install.

#### Scenario: Arguments
- GIVEN the tasks driver builds its `claude -p` command
- WHEN a unit test inspects the arguments
- THEN no `--add-dir` value is `claude/`, a parent of it, or a path under `claude/evals/`

#### Scenario: Copy works without --add-dir
- GIVEN a sandbox with the copied harness and no `--add-dir`
- WHEN one real headless `/spec` turn runs in it (recorded once, not in CI)
- THEN the trace shows reads of `.claude/commands/spec.md` and the skill, and no permission refusal

#### Scenario: Shared use
- GIVEN the install moved to the shared module
- WHEN the review-eval and archived spec-eval unit tests run
- THEN they pass, with the layout test now in the shared module's tests

### Requirement: REQ-009 — Read audit
Source: plan B2; F1

When a headless trial ends, the core MUST read its tool-call trace,
including the tool calls of subagents and every Bash command text. If any
tool call or command names `evals/add-business/hidden`,
`evals/add-business/reference`, or a path under `claude/evals/`, then the
trial MUST be LEAKED.
A LEAKED trial MUST count as a fail and MUST be named in the report.

#### Scenario: Leak
- GIVEN a trace with a `Read` of `claude/evals/add-business/hidden/checks.json`
- WHEN the audit runs
- THEN the trial is LEAKED and fails

#### Scenario: Leak through Bash in a subagent
- GIVEN an executor subagent ran `cat /var/www/html/personal/harness/claude/evals/add-business/hidden/api/dup.test.php`
- WHEN the audit runs
- THEN the trial is LEAKED and fails

#### Scenario: Sandbox read
- GIVEN a trace that reads only sandbox files and linked harness files
- WHEN the audit runs
- THEN the trial is not LEAKED

### gates

### Requirement: REQ-010 — A gate case is a folder
Source: owner decision 2026-11-24 ("Cases as folders"); plan §5.1

Each gate case MUST be a folder `tools/evals/workflow/cases/<id>/` with
`case.json` and an optional `files/` tree. `case.json` MUST hold: `stage`
(a key of the stage-file map), `request`, `split`, `tags`, `checks`, and
optional `setup` and `evidence`. `setup` MUST be an ordered list of steps:
copy `files/`, write a file, `git init`, `git commit` with a message, and
`capture` a commit id under a name. `{name}` placeholders in later written
files and in `evidence` MUST be replaced by the captured values. A new case
MUST need no edit to any `.py` file unless it uses a custom check
(REQ-011).

#### Scenario: Add a case by copying
- GIVEN `cases/ship_open_blocker/` exists
- WHEN the owner copies it to `cases/ship_open_major/`, edits `case.json` and one file
- THEN `eval.py gates --case ship_open_major` runs it with no code change

#### Scenario: Commit ids
- GIVEN a case whose `setup` commits the spec, captures `spec_sha`, then writes a plan containing `{spec_sha}`
- WHEN the fixture is built
- THEN the plan file holds the real commit id of the spec commit

### Requirement: REQ-011 — Declared checks
Source: owner decision 2026-11-24; current assertions in `workflow/run.py:1149-1480`

`checks` MUST map each check name to one declared rule: `state` equals a
value; a field matches or does not match a regex; a decision line for a name
(as `parse_decisions` reads today) equals a value; a report name or status
line (as `report_name` and `status_line` read today) equals a value; the
fixture is unchanged; tool access stayed in the fixture. Where a check cannot
be declared, the case MAY add `check.py` with a function that returns a
`{name: bool}` map. The case result MUST be all checks passing.

#### Scenario: Declared
- GIVEN `checks: {"no_go": {"field": "explanation", "regex": "NO-GO"}}`
- WHEN a trial's explanation contains `NO-GO`
- THEN `no_go` is true

#### Scenario: Custom
- GIVEN `verifier_survivors` needs the mutant table
- WHEN it has a `check.py`
- THEN its custom checks run beside the declared ones

### Requirement: REQ-012 — Migration keeps every assertion
Source: owner decision 2026-11-24 ("old and new must give the same result before the old code is removed"); advisor review (a check that is always true)

Every case in today's `cases()` MUST be migrated to a folder. The replay set
MUST be committed as `tools/evals/workflow/replay/<case>.json`: structured
outputs from the REQ-014 measurement run, plus the synthetic outputs that
`test_runner.py` already uses, plus hand-written outputs where needed. The
gate fixtures are made up (`WF-*`), so the replay set holds no private data.
For every check of every case, the replay set MUST hold at least one output
where the old `checks()` gives true and one where it gives false. Before the
old `prepare`, `prepare_probe` and `checks` code is removed, a replay test
MUST show, for every case:
- the fixture tree built from the folder equals the one the old code builds,
  except for commit ids and the values derived from them; and
- every replay output gives the same name-to-value map from the old and the
  new checks.

The old code's maps MUST be stored in the replay files as the expected
values, so the replay test keeps checking the new checks after the old code
is gone. The replay MUST run without a model, in CI. If any case differs, then
the old code MUST stay.

#### Scenario: Equal
- GIVEN the replay set for all cases
- WHEN the replay test runs
- THEN every case gives identical check maps and fixture trees, and the test passes

#### Scenario: A check is never false
- GIVEN `testgate_figma` has a check with only true outputs in the replay set
- WHEN the coverage part of the replay test runs
- THEN it fails and names the check that has no false example

#### Scenario: A check drifts
- GIVEN the new `fix_rerun` checks read `code-1` differently from the old code
- WHEN the replay runs
- THEN it fails and names `fix_rerun` and the differing check

#### Scenario: After the old code is gone
- GIVEN the old code was removed
- WHEN a later edit breaks a declared rule
- THEN the replay test fails against the stored expected maps

### Requirement: REQ-013 — Gate result per case
Source: owner decision Q3; plan §5.4

The gate result MUST be PASS if every scored trial passed, FLAKY if some
passed, and FAIL if none passed. Gate trials MUST be able to run in
parallel with `--jobs N`; each trial MUST use its own fixture folder.

#### Scenario: Flaky
- GIVEN trials pass, fail, pass
- WHEN the case result is computed
- THEN it is FLAKY (2/3)

#### Scenario: Parallel
- GIVEN `--jobs 4` and 3 cases × 3 trials
- WHEN the run finishes
- THEN 9 trial folders exist, none shared, and the results equal a `--jobs 1` run's structure

### Requirement: REQ-014 — First measurement and baseline
Source: plan A1, A5; F9 (cost unmeasured)

Before the migration (REQ-012), one full gate run with 1 trial MUST be made
with the current runner, keeping every trial's structured output. Its total
and per-case cost and duration MUST be recorded in `tools/evals/README.md`
with the date and harness commit. After REQ-012, one full gate run with the
default trials MUST be promoted as the first baseline, and each FLAKY case of
that run MUST be recorded as a row in `docs/observation-log.md`.

#### Scenario: Measurement
- GIVEN the current runner
- WHEN the measurement run finishes
- THEN the README shows its cost, duration, date and commit, and the outputs feed REQ-012's replay

#### Scenario: Flaky at baseline
- GIVEN the first baseline has `specgate_default_dec` FLAKY
- WHEN the baseline is promoted
- THEN `docs/observation-log.md` has a row naming that case

### gate-trailer

### Requirement: REQ-015 — Watched files are generated
Source: owner decision Q6, 2026-11-24 ("Yes, in Phase A"); plan A8

The watched list MUST be the union of the harness files any gate case's stage
supplies in its prompt, as `claude/<path>`, written to
`tools/evals/workflow/watched.txt` by `eval.py gates --write-watched`. If the file differs
from the generated list, then a unit test MUST fail.

#### Scenario: New stage file
- GIVEN a stage gains `references/findings.md`
- WHEN the unit tests run without regenerating `watched.txt`
- THEN the staleness test fails and names the missing path

### Requirement: REQ-016 — Trailer line
Source: owner decision Q6; ADR 0111 trailer style

The gates report MUST end with a ready trailer line:
`Eval: gates <passed>/<total> PASS -> <passed>/<total> PASS, flaky <a> -> <b> (<VERDICT>); <run folder>`,
with the `-> ` part left out if no baseline exists. Where the run is a
subset, the line MUST name the selection (`--tag ship` or the case count).

#### Scenario: Full run
- GIVEN a baseline at 58/60 PASS, flaky 2, and a run at 60/60, flaky 0
- WHEN the report ends
- THEN it prints `Eval: gates 58/60 PASS -> 60/60 PASS, flaky 2 -> 0 (BETTER); tools/evals/results/gates/<run>`

### Requirement: REQ-017 — CI checks the trailer
Source: owner decision Q6; precedent `tools/checks/check-rescore.py`

`tools/checks/check-eval-trailer.py --range <range>` MUST fail (exit 1) a
non-merge commit in the range that touches a watched path and has no
`Eval:` trailer, or whose trailer starts with "not run" without a reason
after a dash or colon. It MUST pass a commit with a result line or with
`not run - <reason>`. It MUST exit 2 on a git error, and MUST skip a range
that starts at an all-zero commit. Commits before the commit that adds the
check MUST NOT be checked. It MUST run in `.github/workflows/ci.yml` and be
listed in `tools/checks/README.md`. It MUST NOT read or require the
`Review-eval:` trailer.

#### Scenario: Missing trailer
- GIVEN a commit that edits `claude/commands/ship.md` with no `Eval:` trailer
- WHEN the check runs on its range
- THEN it exits 1 and names the commit and the file

#### Scenario: Reason given
- GIVEN the same commit with `Eval: not run - typo fix, no rule changed`
- WHEN the check runs
- THEN it exits 0

#### Scenario: Both trailers needed
- GIVEN a commit that edits `claude/commands/review.md` (watched by both checks) with only `Review-eval:`
- WHEN both checks run
- THEN `check-rescore.py` passes and `check-eval-trailer.py` fails

### tasks

### Requirement: REQ-018 — Driver with a scripted owner turn
Source: owner decision Q2, 2026-11-24 ("Scripted owner turn"); ADR 0148; workflow case `owner_approves_read_spec`

`eval.py tasks` MUST build a sandbox with `claude/evals/add-business/setup.sh`,
install the harness (REQ-008), and run `/spec ADD-1`, `/plan ADD-1`,
`/build ADD-1`, `/test ADD-1` and `/review ADD-1` headless, in order. When
`/spec` or `/plan` presents a draft for approval, the driver MUST send a
separate turn in that session: "I read the whole spec. I approve it." (or
"plan"). No prompt the driver sends before a draft exists MUST contain
approval or pre-approval text. When `/review` reports REQUIRED or BLOCKER
findings, the driver MUST run one fix round as the pipeline routes it.

#### Scenario: Approval after the draft
- GIVEN `/spec ADD-1` returned a Draft spec and asked for approval
- WHEN the driver continues
- THEN it sends the approval turn, and the spec header reads `Status: Approved`

#### Scenario: No pre-approval
- GIVEN the driver's prompt texts
- WHEN a unit test scans every turn sent before a draft exists
- THEN none contains "approve"

### Requirement: REQ-019 — The driver stops and says why
Source: plan §5.8

The driver MUST stop a trial when: a stage reports BLOCKED; a stage asks the
owner a question other than the approval of REQ-018; a single stage exceeds
its time limit; or the trial exceeds 90 minutes of wall time. The trial
record MUST hold the stop reason and the last stage reached.

#### Scenario: Question
- GIVEN `/plan` returns a SPEC CONFLICT question to the owner
- WHEN the driver reads it
- THEN the trial stops with reason `question` and stage `/plan`, and grading still runs

#### Scenario: Wall clock
- GIVEN 90 minutes have passed during `/build`
- WHEN the limit is reached
- THEN the session is stopped, the reason is `time`, and grading still runs

### Requirement: REQ-020 — Task trials are graded by the hidden tests
Source: `claude/evals/add-business/README.md`; plan §5.4

After each trial, the driver MUST run `grade.sh` on the sandbox and store its
JSON in the trial folder. The trial record MUST hold checks passed of the
total, the stop reason, the stage reached and LEAKED (REQ-009). Each hidden
check MUST get a state over trials: PASS if every scored trial passed it,
FLAKY if some did, FAIL if none did. The case result MUST be the count of
trials that passed every check, with the per-check states. The report MUST say that 3 trials measure consistency and
that a change of one trial is not proof of a gain.

#### Scenario: Grade
- GIVEN a trial that reached `/review`
- WHEN grading ends
- THEN the trial holds e.g. `47/49`, the failed check ids, stop reason `done`, stage `/review`

#### Scenario: Grader self-test unchanged
- GIVEN the CI grader step
- WHEN CI runs
- THEN the reference still scores 49/49 and the seed still fails

### Requirement: REQ-031 — Task trials cannot read the eval content
Source: owner decision 2026-11-24 (Q1 = B, "detect and prevent"); owner decision 2026-11-24 (`/plan` SPEC CONFLICT, "REQ-031=1"); DEC-011, DEC-012

Before the first real task trial, a probe MUST establish whether Claude
Code's sandbox settings, written into the sandbox's `settings.local.json`,
deny a headless `claude -p` session, and its subagents, a Bash read of a file
under `claude/evals/`. The deny MUST cover that folder by its repository path
and by every `~/.claude/...` path that resolves into it. The deny MUST NOT
cover the rest of the harness repository, because the stages call harness
scripts through `~/.claude/` links into it (for example
`python3 ~/.claude/skills/spec-driven-development/scripts/check-spec.py`).
If both eval reads are refused and that `check-spec.py` call still runs, then
the probe MUST record `pass`; otherwise it MUST record `fail`. The probe result MUST be recorded in
`tools/evals/README.md` with the date and the Claude Code version. Where the
probe passed, every task trial MUST run with that setting. If the probe
failed, then task trials MUST run with detection only (REQ-009), and every
`tasks` report MUST state "prevention off: detection only".

#### Scenario: Probe passes
- GIVEN the sandbox setting denies reads under `claude/evals/`
- WHEN the probe session and a subagent each run `cat <harness>/claude/evals/add-business/ticket.md`, and the session runs `python3 ~/.claude/skills/spec-driven-development/scripts/check-spec.py <a sample spec>`
- THEN both `cat` commands are refused, `check-spec.py` runs and prints its result, and the probe records "pass" with the date and version

#### Scenario: Stage scripts blocked
- GIVEN a setting that refuses the `cat` commands and also refuses `check-spec.py`
- WHEN the probe runs
- THEN it records "fail", because the stages would lose their own checks

#### Scenario: Probe fails
- GIVEN the setting does not refuse a subagent's Bash read
- WHEN the probe runs
- THEN it records "fail", task trials still run, and each `tasks` report starts with "prevention off: detection only"

#### Scenario: Prevention blocks a real read
- GIVEN the probe passed and a trial's executor tries to read `hidden/`
- WHEN the read is refused
- THEN the audit (REQ-009) still marks the trial LEAKED, because the attempt is in the trace

### bugs

### Requirement: REQ-021 — Shipped-bug cases under the core
Source: ADR 0093, 0111, 0143; plan C1; F5

`eval.py bugs --repo <project>` MUST run every review-eval case with trials
(REQ-003) and results in schema 1 (REQ-002). Per trial, the judge MUST stay
the one in `review-eval/run.py` (CAUGHT, LOCATED, MISSED; noise on clean
cases). A bug case MUST be PASS only if every trial is CAUGHT, FLAKY if some are,
and FAIL if none are. A clean case MUST be PASS only if no trial has a
BLOCKER or REQUIRED finding, FLAKY if some trials do, and FAIL if all do. The report MUST
end with a ready `Review-eval:` line in the format `check-rescore.py`
accepts. `check-rescore.py` and its tests MUST NOT change.

#### Scenario: Trailer line
- GIVEN a baseline at bugs 3/4 and a run at 4/4, clean 1/1, holdout 1/1
- WHEN the report ends
- THEN it prints a `Review-eval: bugs 3/4 -> 4/4, clean 1/1 -> 1/1, holdout 1/1 -> 1/1 (BETTER); <run folder>` line

#### Scenario: Located only
- GIVEN a trial whose finding is near the lines but names no defect term
- WHEN it is judged
- THEN the trial is LOCATED and the case is not PASS

### Requirement: REQ-022 — Add a case from the observation log
Source: ADR 0100; plan C2

`eval.py bugs add --repo <project> --from-log <fix sha>` MUST read the
"Shipped bugs" row of `docs/observation-log.md` whose fix-commit column names
that sha, take the bug text as the case description, and build the case as
`review-eval/run.py --new --fix <sha>` does. It MUST still require at least
one `--defect` term. If no row names the sha, then it MUST stop with exit 2
and say so. `eval.py bugs add` without `--from-log` MUST accept the same
arguments as `run.py --new`.

#### Scenario: From the log
- GIVEN a row whose fix commit is `leadbuster a47f7cfd`
- WHEN the owner runs `eval.py bugs add --repo $P --from-log a47f7cfd --defect 'accent'`
- THEN a case is built from that fix and its description is the row's bug text

#### Scenario: No row
- GIVEN no row names `deadbee`
- WHEN `--from-log deadbee` runs
- THEN it exits 2 with "no Shipped bugs row names deadbee"

### Requirement: REQ-023 — The pipeline prints the new command
Source: ADR 0100; `claude/commands/ship.md:86-87, 298`; `claude/references/component-response-contracts.md:451`

When `/ship` prints the eval command for a shipped-bug fix, it MUST print
`python3 tools/evals/eval.py bugs add --repo <project> --from-log <fix sha> --defect <term>`.
The observation log's instructions (`docs/observation-log.md:227-231`) MUST
show the same command.

#### Scenario: Ship output
- GIVEN `/ship` records a shipped-bug row
- WHEN it prints the eval command
- THEN the command is the `eval.py bugs add` form above

### recall

### Requirement: REQ-024 — Plan recall through the entry point
Source: plan C3; ADR 0067

`eval.py recall` MUST pass its arguments to `plan-recall/recall.py` and MUST
give the same figures and exit code. It MUST NOT run trials or write a run
folder.

#### Scenario: Same figures
- GIVEN the LD-380 flags in the plan-recall README
- WHEN run through `eval.py recall` and through `recall.py`
- THEN both print the same recall figures and exit with the same code

### docs-archive

### Requirement: REQ-025 — One page explains the evals
Source: owner statement 2026-11-23 ("I have a hard time understanding it"); plan A6

`tools/evals/README.md` MUST explain, in plain words: what each suite answers;
when to run it; its command; how to read a report and a verdict; how to add,
change, retire and re-baseline cases; how to catch up with `eval.py todo`; what each suite does not prove; and the
last measured cost and time. Every command on the page MUST run as written.
Each suite README MUST start by pointing to `eval.py`.

#### Scenario: Owner run
- GIVEN only the README
- WHEN the owner runs the gates suite and reads its report
- THEN the owner states the verdict and the cases to read without help

### Requirement: REQ-026 — spec-eval is frozen, not lost
Source: owner decision Q1, 2026-11-23 ("Freeze")

spec-eval MUST move to `tools/evals/archive/spec-eval/` and MUST NOT be a
suite of `eval.py`. Its unit tests MUST keep running in CI from the new path.
Before the move, the gitignored `fixtures/LD-380` folder MUST be copied
outside the repository, and the copy's path recorded in
`tools/evals/archive/README.md`. The main README MUST list it under
"Archived", with the review date one month after the move.

#### Scenario: After the move
- GIVEN the move commit
- WHEN CI runs
- THEN the archived spec-eval unit tests pass from the new path

#### Scenario: Private fixture stays ignored after the move
- GIVEN `tools/evals/archive/spec-eval/fixtures/LD-380/` exists after the move
- WHEN `git check-ignore tools/evals/archive/spec-eval/fixtures/LD-380/intake.md` runs
- THEN it reports the path as ignored, and `git status` does not list it

#### Scenario: Fixture kept
- GIVEN the move is done
- WHEN the owner lists the recorded copy path
- THEN `LD-380/intake.md` and `expectations.json` are there

### Requirement: REQ-027 — Old references updated
Source: plan D2

Every reference to `tools/evals/{spec-eval,review-eval,workflow}/run.py`
commands MUST point to `eval.py` or the archive, in: `.github/workflows/ci.yml`,
`README.md`, `ARCHITECTURE.md`, `tools/README.md`, `docs/HANDOFF.md`,
`docs/observation-log.md`, `claude/commands/ship.md` and
`claude/references/component-response-contracts.md`.
`rg -n "tools/evals/(spec-eval|review-eval|workflow)/run.py"` MUST then match
only suite READMEs, the archive, ADRs and dated logs or audits.

#### Scenario: Search
- GIVEN the docs-archive commits
- WHEN the search runs
- THEN no command in a live instruction file names an old `run.py`

### Requirement: REQ-028 — The decision is recorded
Source: `adr-recording` skill; plan A7, D3

A new ADR MUST record: one runner, trials, the baseline rule, the verdict
rule, gate cases as folders, the `Eval:` trailer with its watched list and
cost, the scripted owner turn, the copied harness with the Bash sandbox and
the read audit, the catch-up command and hint, and spec-eval frozen. It MUST say that it
replaces ADR 0079's "run each side twice" with a k-of-k consistency rule,
and why 0079's rejection of a significance test still stands. ADR 0079 MUST
get a "Superseded in part by" line. ADRs 0067, 0093, 0100, 0111, 0117 and
0143 MUST each get a line pointing to `eval.py` where they name a command.

#### Scenario: Index
- GIVEN the ADR commit
- WHEN `docs/adr/README.md` is read
- THEN it lists the new ADR, and ADR 0079 links to it

### todo

### Requirement: REQ-029 — A catch-up list of skipped eval steps
Source: owner statement 2026-11-24 ("Sometimes i skip ship command"); owner decision 2026-11-24 ("eval.py todo + session hint")

When the owner runs `eval.py todo` in a project checkout, it MUST list,
without a model and without network access:
- each ticket that has an Approved plan in `docs/tasks/<TICKET>-plan.md`, has
  at least one commit on the default branch whose subject names
  `(<TICKET> T`, and has no row in the "Plan recall" table of the harness
  `docs/observation-log.md`; each with a ready `eval.py recall` command; and
- each "Shipped bugs" row whose "Eval case" column is empty or `—`, with a
  ready `eval.py bugs add --from-log <fix sha>` command.

If the checkout has no `docs/tasks/`, then it MUST list the bug rows only.
It MUST exit 0 whether or not it finds items.

#### Scenario: Skipped recall
- GIVEN `docs/tasks/LD-600-plan.md` is Approved, `(LD-600 T001)` is on `main`, and no Plan recall row names LD-600
- WHEN the owner runs `eval.py todo` in that project
- THEN it lists LD-600 with the `eval.py recall --ticket LD-600 --subject-only ...` command

#### Scenario: Ticket not shipped
- GIVEN `docs/tasks/LD-601-plan.md` is Approved but no `(LD-601 T` commit is on `main`
- WHEN `eval.py todo` runs
- THEN LD-601 is not listed

#### Scenario: Bug without a case
- GIVEN a Shipped bugs row with fix commit `leadbuster b12c34d` and an empty Eval case column
- WHEN `eval.py todo` runs
- THEN it lists that row with `eval.py bugs add --repo <project> --from-log b12c34d --defect <term>`

#### Scenario: Nothing missing
- GIVEN every shipped ticket has a recall row and every bug row has a case
- WHEN `eval.py todo` runs
- THEN it prints "nothing to catch up" and exits 0

### Requirement: REQ-030 — Session-start hint
Source: owner decision 2026-11-24 ("eval.py todo + session hint")

When a Claude Code session starts or resumes, a SessionStart hook MUST run
the REQ-029 count and, if the count is above zero, print one line:
`evals: <n> tickets without recall, <m> bugs without a case — run eval.py todo`.
If the count is zero, or the check fails, or it takes more than 2 seconds,
then the hook MUST print nothing and MUST exit 0. It MUST NOT block or delay
the session beyond that limit.

#### Scenario: Items pending
- GIVEN `eval.py todo` would list 2 tickets and 1 bug
- WHEN a session starts in that project
- THEN the session start shows `evals: 2 tickets without recall, 1 bugs without a case — run eval.py todo`

#### Scenario: Broken log
- GIVEN `docs/observation-log.md` cannot be parsed
- WHEN a session starts
- THEN the hook prints nothing and exits 0

## Material Decisions

### DEC-001 — spec-eval is frozen
- Decision: Move spec-eval to an archive folder; keep its unit tests; leave it out of `eval.py`; review in a month.
- Alternatives: delete it (loses the only `/spec` check on a real ticket); keep it as a suite with trials (most work, weak measure).
- Reason: removes the hardest tool from the main path without losing the real-ticket fixture (REQ-026).
- Source: owner, 2026-11-23, Claude Code session (plan Q1)
- Decided by: owner, 2026-11-23, plan Q1
- Affects: REQ-026, REQ-027

### DEC-002 — Scripted owner turn in the sandbox
- Decision: The driver approves the spec and plan with a separate owner turn after each draft.
- Alternatives: a harness flag that skips approval (a gate bypass in the harness); keep the suite manual (it stays unused).
- Reason: same shape as `owner_approves_read_spec`; no gate text changes (REQ-018).
- Source: owner, 2026-11-24, Claude Code session (plan Q2)
- Decided by: owner, 2026-11-24, plan Q2
- Affects: REQ-018

### DEC-003 — Three trials by default
- Decision: 3 trials by default, `--trials N` to change; a run below the default never becomes a baseline.
- Alternatives: decide after measuring; 5 by default.
- Reason: k-of-k consistency for gates at a cost to be measured (REQ-003, REQ-004).
- Source: owner, 2026-11-24, Claude Code session (plan Q3)
- Decided by: owner, 2026-11-24, plan Q3
- Affects: REQ-003, REQ-004, REQ-013

### DEC-004 — Results inside the repository, ignored
- Decision: `tools/evals/results/`, gitignored, with a guard that refuses to write when it is not ignored.
- Alternatives: outside the repository (`~/.local/share/harness-evals/`).
- Reason: easy to find beside the code; the guard covers the public-repo risk (REQ-001).
- Source: owner, 2026-11-24, Claude Code session (plan Q5)
- Decided by: owner, 2026-11-24, plan Q5
- Affects: REQ-001

### DEC-005 — `Eval:` trailer in this change
- Decision: Commits that touch a file a gate case reads carry an `Eval:` trailer, checked in CI.
- Alternatives: decide after a few weeks of use.
- Reason: makes runs happen, as ADR 0111 does for reviewers (REQ-015–REQ-017).
- Source: owner, 2026-11-24, Claude Code session (plan Q6)
- Decided by: owner, 2026-11-24, plan Q6
- Affects: REQ-015, REQ-016, REQ-017

### DEC-006 — Gate cases are folders
- Decision: Each gate case is a folder of data with declared checks; custom Python only where needed; migration proven by replay.
- Alternatives: keep cases in `workflow/run.py` and only wrap it.
- Reason: adding a case was the hard part (REQ-010–REQ-012).
- Source: owner, 2026-11-24, Claude Code session
- Decided by: owner, 2026-11-24, Claude Code session
- Affects: REQ-010, REQ-011, REQ-012

### DEC-007 — The `Eval:` watched list comes only from what gate cases read
- Decision: Watch exactly the harness files gate cases supply, generated by code; Codex files are not watched.
- Alternatives: a hand-written list like `check-rescore.py`'s, including Codex files.
- Reason: a trailer for a file no case reads would demand a run that cannot measure the change. A hand list drifts. Risk: Low.
- Source: plan A8; precedent `check-rescore.py` (hand list), rejected for drift
- Decided by: default (interactive)
- Affects: REQ-015

### DEC-008 — An infrastructure failure is retried once and never scored
- Decision: ERRORED trials are retried once; a second failure stays ERRORED, is reported, and blocks promotion to baseline.
- Alternatives: score errors as fails; retry until success.
- Reason: a timeout says nothing about the harness; unlimited retries hide a broken setup. Precedent: review-eval already marks such a case `ERRORED (not scored)`. Risk: Low.
- Source: `tools/evals/review-eval/README.md` ("ERRORED (not scored)")
- Decided by: default (interactive)
- Affects: REQ-003, REQ-004

### DEC-009 — One verdict rule over items, per suite
- Decision: Items are cases (`gates`, `bugs`) or hidden checks (`tasks`), each with a FAIL < FLAKY < PASS state. Any lost gate case or lost holdout makes WORSE; `tasks` checks use only the gained-versus-lost count. The `must` rule leaves with spec-eval.
- Alternatives: a gate-only verdict with separate rules per suite; WORSE on any lost `tasks` check.
- Reason: one rule the owner learns once (REQ-005). Gates are rules and must hold k of k. A task trial is a full pipeline run, so one flaky check of 49 is expected noise and must not fail the whole run. Risk: Low.
- Source: advisor review; ADR 0117 (holdout); plan §5.4
- Decided by: default (interactive)
- Affects: REQ-005, REQ-013, REQ-020, REQ-021

### DEC-010 — Catch-up does not depend on `/ship`
- Decision: A free `eval.py todo` command and a one-line session-start hint list skipped recall rows and bug cases.
- Alternatives: `eval.py todo` only, without the session line; nothing (run steps by hand).
- Reason: the owner sometimes skips `/ship`, which is today the only prompt for these steps (REQ-029, REQ-030).
- Source: owner, 2026-11-24, Claude Code session
- Decided by: owner, 2026-11-24, Claude Code session
- Affects: REQ-029, REQ-030

### DEC-011 — Prevent and detect hidden-file reads
- Decision: Copy the harness (REQ-008), deny Bash reads of the eval content through Claude Code's sandbox once a probe shows it works headless and in subagents (REQ-031, scope narrowed by DEC-012), and audit every trace (REQ-009).
- Alternatives: detect only; run each task trial in a container.
- Reason: a task score is worthless if the agent saw the hidden tests; prevention closes the Bash path that detection can only catch afterwards. The container was too heavy for the gain.
- Source: owner, 2026-11-24, Claude Code session (Q1 = B)
- Decided by: owner, 2026-11-24, Claude Code session
- Affects: REQ-008, REQ-009, REQ-031

### DEC-012 — The sandbox denies only the eval content
- Decision: The Bash sandbox denies reads under `claude/evals/`, by its repository path and by any `~/.claude/...` path into it; the probe passes only if the stage scripts still run.
- Alternatives: deny the whole harness repository and require the stage scripts to run (fails on this machine, so prevention would be off); copy the stage scripts into the session too and rewrite the `~/.claude/...` paths in the copied commands, then deny the whole repository (larger change to the copied harness).
- Reason: `~/.claude/skills`, `commands`, `hooks`, `references` and `agents` link into this repository, and `/spec` and `/plan` run `check-spec.py` and `check-plan.py` through them. A whole-repository deny would block those checks in every trial (REQ-031, REQ-018).
- Source: `/plan HR-2` SPEC CONFLICT, 2026-11-24; owner decision "REQ-031=1"
- Decided by: owner, 2026-11-24, `/spec HR-2 decisions: REQ-031=1`
- Affects: REQ-031

## Tech Stack

Python 3 standard library only, as every current eval (`argparse`, `json`,
`subprocess`, `unittest`). Claude CLI `claude -p` with
`--output-format stream-json` and `--json-schema` (gates, as
`workflow/run.py:1570`). add-business grading: PHP 8.2+ with `pdo_sqlite`,
Node 20+, Playwright Chromium (its README).

## Commands

Existing, found in source:
- `cd tools/evals/workflow && python3 -m unittest -q test_runner` (`docs/HANDOFF.md:105`)
- `python3 tools/evals/workflow/run.py --case <name> --output <dir>` (workflow README)
- `python3 tools/evals/review-eval/run.py --fixture <c> --repo $P --output <dir> [--baseline <file>]`
- `python3 tools/checks/check-rescore.py --range <range>`
- `claude/evals/add-business/setup.sh DEST` and `grade.sh DEST`
- `python3 ~/.claude/skills/spec-driven-development/scripts/check-spec.py docs/specs/HR-2-SPEC.md`

New, defined by this spec: the `eval.py` commands in REQ-007, REQ-015,
REQ-022, REQ-024; `tools/checks/check-eval-trailer.py --range <range>`.

## Project Structure

```text
tools/evals/
  eval.py                 entry point (REQ-007)
  core.py                 storage, schema, trials, baseline, verdict, report (REQ-001–006)
  sandbox.py              harness install and read audit (REQ-008, REQ-009)
  results/                gitignored run output and baselines (REQ-001)
  workflow/cases/<id>/    gate case folders (REQ-010)
  workflow/replay/        committed replay outputs and expected maps (REQ-012)
  workflow/watched.txt    generated watched list (REQ-015)
  review-eval/            bugs suite, judge unchanged (REQ-021)
  plan-recall/            recall suite (REQ-024)
  archive/spec-eval/      frozen (REQ-026)
claude/evals/add-business/  task content; driver location is a plan decision (TD)
tools/checks/check-eval-trailer.py  (REQ-017)
```

## Code Style

Match the existing eval scripts: one file per tool, standard library, module
docstring that states usage and exit codes (see `check-rescore.py`), tests in
`test_*.py` beside the code, run by `python3 -m unittest`.

## Testing Strategy

| Requirement | Evidence | Layer |
|---|---|---|
| REQ-001, REQ-002 | unit tests: folder naming, ignore guard (temp git repo), schema fields, `null` for unknown | `tools/evals/test_core.py` |
| REQ-003, REQ-013 | unit tests with a stubbed `claude`: trial folders, ERRORED retry, PASS/FLAKY/FAIL, `--jobs` | `test_core.py`, `workflow/test_runner.py` |
| REQ-004, REQ-005, REQ-006 | unit tests: each refusal, each verdict rule in order, new-case listing, noise line, read list, semantic review write | `test_core.py` |
| REQ-007 | unit test of argument parsing and the no-argument table | `test_core.py` |
| REQ-008, REQ-009 | unit tests: no `--add-dir` of `claude/`; copy holds no `evals/`; traces with a hidden-file read by Read, by Bash, and inside a subagent are LEAKED. One real headless turn in a copied sandbox, recorded | `tools/evals/test_sandbox.py` |
| REQ-010, REQ-011 | unit tests: setup steps, placeholders, each declared rule, custom `check.py` | `workflow/test_runner.py` |
| REQ-012 | replay test over every case, no model: maps old vs new, true-and-false coverage per check, fixture trees; stored expected maps | `workflow/test_migration.py`, `workflow/replay/` |
| REQ-014 | the measurement run's README entry; the baseline folder; observation-log rows | manual run, recorded |
| REQ-015–REQ-017 | unit tests: staleness; trailer line format; check cases (missing, bare not run, reason, result, unwatched, both trailers, zero range) | `tools/tests/test-check-eval-trailer.py` |
| REQ-031 | probe record in the README; one real probe session plus subagent, recorded, showing both eval reads refused and `check-spec.py` run; a unit test that the probe records `fail` when the stage script is refused; a unit test that the driver writes the setting only when the record says pass | manual probe, `tools/evals/tasks` tests |
| REQ-018–REQ-020 | unit tests with a stubbed `claude`: approval only after draft, each stop rule; one real trial run, recorded | `tools/evals/tasks` tests (path is a plan TD) |
| REQ-021, REQ-022 | `test_review_eval.py` unchanged and passing; row parser test; `test-check-rescore.py` unchanged | existing + new unit tests |
| REQ-023, REQ-027 | `rg` searches named in the requirements | command output |
| REQ-024 | same output from both commands on one ticket | manual run, recorded |
| REQ-025 | owner run from the README alone | owner, recorded |
| REQ-026 | CI step for archived tests; copy path listed | CI, `ls` |
| REQ-028 | ADR index and the pointer lines | file read |
| REQ-029 | unit tests on a temp git repo and a sample log: skipped recall, unshipped ticket, bug without case, nothing missing, no `docs/tasks/` | `tools/evals/test_todo.py` |
| REQ-030 | hook tests: count line, zero is silent, parse error is silent, 2-second limit | `tools/tests/` hook test, as for the other hooks |

CI runs every unit test. No test drives a real model.

## Invariants and Mechanism Proof

Invariant: a task trial that read a hidden-test or reference file does not
count as a pass.

Decided (DEC-011, DEC-012): detect and prevent. The copy (REQ-008) removes
every pointer to `claude/`. The Bash sandbox (REQ-031) denies reads of
`claude/evals/` when the probe shows it works, and leaves the rest of the
repository readable so the stages' own scripts still run. The audit (REQ-009) fails any trial
whose trace names a hidden path. If the probe fails, prevention is off, the
report says so, and the guarantee is "no leaked trial is scored".

Writers of the hidden content into a session: the session arguments
(`--add-dir`), the harness install in `.claude/`, the sandbox built by
`setup.sh`, and any tool call that names an outside path. `setup.sh` copies
only `seed/` (its header). REQ-008 closes the first two. REQ-009 covers the
last, for the main session and subagents.

Evidence: the REQ-008 argument test, the REQ-008 real-turn scenario, the
REQ-009 trace tests (including the Bash-in-subagent case), and the REQ-031
probe record.

No cross-row or concurrent data invariant exists. Parallel gate trials share
nothing: each has its own fixture folder (REQ-013).

## Data Lifecycle

- Run folders: kept until the owner deletes them; nothing removes them
  automatically. A baseline is a pointer to a run folder; deleting that
  folder leaves no baseline, and the next run reports "no baseline".
- Cases: retired by deletion with the reason in the commit (ADR 0117), never
  edited to pass.
- Private fixtures: copied outside the repository before any move (REQ-026).

## Boundaries

- Always: keep private case content and run output gitignored; prove gate
  migration by replay before removing old code; keep `check-rescore.py` and
  the review-eval judge unchanged.
- Ask first: deleting any private fixture; changing a gate case's expected
  answer; changing the `Review-eval:` format.
- Never: add an approval-skipping flag to the harness; let a subset, quick or
  errored run become a baseline; run a model in CI.

## Open Questions

None.
