# Plan: rebuild the evals so the owner uses them

Status: Draft, 2026-11-23. Not approved. Nothing here is built yet.
Decisions: Q1, Q2, Q3, Q5, Q6 answered by the owner on 2026-11-23/24. Q4
waits for the A1 measurement.
Next step: `/spec` on this plan.

## 1. Goal

The owner runs one command after a harness change and reads one short report.
The report answers one question: "Did my change make the harness better,
worse, or neither?"

Success criteria:

- One entry point, `tools/evals/eval.py`, runs every suite.
- With no flags, a run compares itself to a stored baseline. The owner never
  types a `results.json` path.
- Every model-driven case runs more than once (trials). The report shows how
  many trials passed, not one pass or fail.
- The report fits on one screen. Per suite it shows: cases that got worse,
  cases that got better, flaky cases, cost and duration.
- One README explains every suite in plain words: what it answers, when to run
  it, the command, and the last measured cost.
- The owner can run it without help. Test: the owner runs the gate suite from
  the README alone, and reads the verdict correctly.

## 2. Why

The evals exist, but the owner has never run one alone. They are hard to
understand. An eval that nobody runs gives no information.

The causes:

- Five tools, five command lines, three fixture formats, three verdict styles.
- Comparison needs a manual `--baseline <path>` from an earlier run.
- Most suites run each case once. One run is noise: two spec-eval runs of the
  same harness scored 23/35 and 26/35 (spec-eval README).
- The most valuable suite, `add-business`, needs a person to type five
  pipeline commands and approve two artifacts by hand.
- Fixture creation is expensive (spec-eval: Jira freeze, as-of date, base
  commit, hand-written expectations).

The external reference is the eval-driven-development article
(x.com/sermakarevich, 2026-11-18) and Anthropic's "Demystifying evals for AI
agents". Both say: grade outcomes with code first, run several trials, keep a
holdout. The harness already does the holdout (ADR 0117) and the code-first
grading (ADR 0143). It lacks trials and usability.

## 3. Current state

| Suite | Path | Cases | Drives a model | Compares to baseline | Trials | CI |
|---|---|---|---|---|---|---|
| workflow (gate decisions) | `tools/evals/workflow/` | ~60, in `cases()` of `run.py` (1597 lines) | yes, `claude -p`, Read/Glob only, 240 s timeout | no | 1 | unit tests only (`test_runner.py`) |
| add-business (full pipeline) | `claude/evals/add-business/` | 1 ticket, 49 hidden checks | yes, by hand | no | 1 | grader self-test |
| review-eval (shipped bugs) | `tools/evals/review-eval/` | 4 private cases (`ld-585*`), gitignored | yes, headless `/review` | yes, `--baseline` | 1 (2 advised) | unit tests; `check-rescore.py` trailer |
| spec-eval (spec term recall) | `tools/evals/spec-eval/` | 1 private fixture (`LD-380`) + `example/` | yes, headless `/spec` | yes, `--baseline` | 1 (2 advised) | unit tests |
| plan-recall | `tools/evals/plan-recall/` | none, runs on any shipped ticket | no, free | yes, `--baseline` | n/a | unit tests |

Facts that constrain the rebuild:

- **F1. The hidden tests can leak.** spec-eval and review-eval give the
  session `--add-dir <ROOT>/claude` (`HARNESS` in `spec-eval/run.py:41`).
  `claude/` contains `claude/evals/add-business/hidden/` and `reference/`. A
  headless add-business run set up the same way could read the answers.
- **F2. review-eval imports spec-eval.** `review-eval/run.py:268` uses
  `spec_eval.HARNESS`, and the harness install code (`link_tree`,
  `HARNESS_DIRS`, the `settings.local.json` writer, `spec-eval/run.py:103-160`)
  lives in spec-eval. `test_produce.py` covers it.
- **F3. The workflow runner refuses to overwrite.** It stops if
  `<output>/results.json` or a case folder exists (`run.py:1558`). Trials need
  one folder per trial.
- **F4. Workflow results end as `semantic_review: pending`.** A pass covers
  the assertions only. Nobody records the semantic review.
- **F5. The `Review-eval:` trailer is a CI contract.** `check-rescore.py` and
  `tools/tests/test-check-rescore.py` parse it (ADR 0111).
- **F6. Private data.** The repository is public. review-eval cases, spec-eval
  fixtures and run output name a private project. They are gitignored today.
- **F7. No headless pipeline driver exists in this repository.** HR-1's
  `ticket.py` and `pipeline.py` are not here (`rg --files` finds neither).
- **F8. The gates forbid pre-approval.** An instruction to run unattended is
  not approval (global rules; ADR 0148). The workflow case
  `owner_preapproves_spec` pins it. The case `owner_approves_read_spec` shows
  that an owner turn after the draft does count.
- **F9. Cost is unmeasured** for workflow and add-business. ~60 cases × 3
  trials is ~180 model runs.

## 4. Open decisions (owner)

Ask these one at a time. Each answer changes the work.

- **Q1. Spec-eval: delete, freeze, or keep?**
  - *Delete* removes the hardest tool. It also removes the only `/spec`
    measure on a real ticket. That conflicts with "back changes with probes
    on real tickets". It reverses part of ADR 0079.
  - *Freeze* keeps the code and fixture, out of the new runner and the
    README's main path. Revisit after the new suites have run for a month.
  - Recommendation: **freeze**. Delete later if nobody runs it.
  - **Answer (owner, 2026-11-23): freeze.** D1 takes the freeze branch.
- **Q2. Scripted approval in the add-business sandbox.** The driver needs the
  spec and the plan approved. Options:
  - *(a)* The driver sends a separate owner turn after each draft: "I read
    the whole spec. I approve it." This is the same shape as
    `owner_approves_read_spec`. No gate changes. Recommended.
  - *(b)* A harness flag that skips approval. Rejected in advance: it adds a
    gate bypass to the harness itself.
  - *(c)* Keep it manual. Then the suite stays unused.
  - **Answer (owner, 2026-11-24): (a) scripted owner turn.** Phase B is
    unblocked.
- **Q3. Trial count.** Default 3. Gate cases must pass 3/3. Raise to 5 for a
  model or persona change? Recommendation: 3 by default, `--trials N` to
  raise.
  - **Answer (owner, 2026-11-24): 3 by default, `--trials N` to raise.** A run
    with fewer trials than the default never becomes a baseline (§5.5).
- **Q4. Cost cap per run.** One cap per suite run, which stops the run when
  reached. Needs the A1 measurement first.
  - **Deferred until A1 has run.** Ask with the measured numbers.
- **Q5. Where results live.** Outside the repository
  (`~/.local/share/harness-evals/`) keeps private output out of git for every
  suite. Inside, gitignored, matches today. Recommendation: outside.
  - **Answer (owner, 2026-11-24): inside, gitignored.** Results go to
    `tools/evals/results/` (§5.6). A2 adds a guard that this path stays
    ignored.
- **Q6. A gate-suite trailer.** Should a commit that changes a command or a
  gate carry an `Eval:` trailer, as reviewer changes carry `Review-eval:`?
  Recommendation: not now. Decide after the owner has used the suite.
  - **Answer (owner, 2026-11-24): yes, in Phase A.** Task A8.

## 5. Target design

### 5.1 Suites

| Suite name | Source | Question | Grading | When to run |
|---|---|---|---|---|
| `gates` | workflow cases | Does each command still make the right call? | code assertions on the structured answer | after a change to a command, persona, skill or reference |
| `tasks` | add-business (+ later tasks) | Does the whole pipeline ship working code? | hidden tests (API + Playwright) | after a model change or a large harness change |
| `bugs` | review-eval cases | Does `/review` still catch shipped bugs, without noise? | defect terms near the fixed lines | after a reviewer change (ADR 0111) |
| `recall` | plan-recall | Did a plan name the files that changed? | file-set comparison, free | after a ticket ships |

spec-eval follows Q1.

### 5.2 One entry point

```text
python3 tools/evals/eval.py gates                 # all gate cases, 3 trials, compare to baseline
                                                  # output: tools/evals/results/ (gitignored)
python3 tools/evals/eval.py gates --case ship_open_blocker
python3 tools/evals/eval.py gates --tag ship
python3 tools/evals/eval.py tasks
python3 tools/evals/eval.py bugs --repo /var/www/html/leadbuster
python3 tools/evals/eval.py recall --repo ./ --ticket LD-380 ...   # same flags as today
python3 tools/evals/eval.py baseline gates        # mark the latest full run as the baseline
python3 tools/evals/eval.py report                # reprint the last report
```

The existing `run.py` files stay as the suite implementations. `eval.py`
calls them through one small interface. Their own command lines keep working
during the move.

### 5.3 Trials

- A case runs `--trials N` times (default 3, Q3). Each trial gets its own
  folder: `<run>/<case>/t1/`, `t2/`, `t3/` (F3).
- Trials of read-only cases (`gates`) may run in parallel. `--jobs` defaults
  to 4. Task trials run one at a time, because each one runs a full pipeline.
- A trial that fails for infrastructure reasons (timeout, CLI error, empty
  output) is **ERRORED**. It is retried once. It is never scored as a pass or
  a fail.
- The report states that trials measure consistency. 3 trials do not give a
  precise rate. "2/3 → 3/3" on a task is not proof of a gain, and the report
  says so.

### 5.4 Per-case result

| Suite | Case result |
|---|---|
| `gates` | **PASS** = every trial passed. **FLAKY** = some passed. **FAIL** = none passed. A gate must be PASS. |
| `tasks` | Pass rate over trials, and per hidden check the count of trials that passed it. |
| `bugs` | CAUGHT / LOCATED / MISSED per trial (ADR 0143), then the same PASS/FLAKY/FAIL roll-up. Clean cases: noise count per trial. |

### 5.5 Baseline and verdict

- A baseline is one stored full run of a suite. It records the harness commit,
  the dirty flag, the `instruction_hashes`, the model, the trial count and the
  case list.
- `eval.py baseline <suite>` promotes a run explicitly. A run becomes the
  baseline only when it covered every case, used at least the default trial
  count, and had no ERRORED trial. A
  `--case` or `--tag` subset never becomes a baseline (it compares against
  the matching cases of the baseline).
- When the instruction hashes equal the baseline's, the report says "harness
  unchanged since baseline: this run measures noise".
- Verdict per suite, in this order:
  1. **WORSE**: a gate case went from PASS to FLAKY or FAIL, or a holdout case
     the baseline passed is lost (ADR 0117), or a `must` item is lost.
  2. **NOT BETTER**: as many or more cases lost than gained.
  3. **BETTER**: more gained than lost, nothing in rule 1.
  4. **SAME**: no case changed state.
- The report always lists every lost case by name, with the trial folders to
  read. A loss never hides behind a better total (ADR 0079).
- Exit code: 0 for BETTER or SAME, 1 for NOT BETTER or WORSE, 2 when the run
  could not finish.

### 5.6 Storage and report

- Results go to `tools/evals/results/<suite>/<date>-<sha7>/` (Q5). The whole
  `results/` folder is gitignored. Baselines are stored there too, so a new
  machine starts without one.
- Guard: a CI unit test runs `git check-ignore` on a sample results path and
  fails if it is not ignored. `eval.py` also refuses to write when the path is
  not ignored.
- One `results.json` per run, with a versioned schema
  (`"schema": 1`):

  ```json
  {
    "schema": 1,
    "suite": "gates",
    "harness": {"commit": "abc1234", "dirty": false, "instruction_hashes": {}},
    "model": "...", "trials": 3, "started": "...", "duration_s": 0, "cost_usd": 0,
    "cases": [
      {"id": "ship_open_blocker", "split": "optimization", "tags": ["ship"],
       "result": "PASS",
       "trials": [{"n": 1, "state": "pass", "checks": {}, "cost_usd": 0, "duration_ms": 0, "folder": "t1"}]}
    ]
  }
  ```

- `report.md` beside it, and the same text on the terminal:

  ```text
  gates  BETTER  (baseline 818af2b, 2026-11-20)
    lost    0
    gained  2   fix_rerun FLAKY -> PASS, testgate_figma FAIL -> PASS
    flaky   1   specgate_default_dec 2/3   -> read t3/
    cost    $4.10 (baseline $3.90)   time 11 min
  ```

### 5.7 Semantic review (F4)

The `gates` assertions check the decision, not the reasoning. The report keeps
a "read these" list: cases that changed state, and every FLAKY case. For each,
the owner reads `explanation` in one trial folder. The run records
`semantic_review: pending` until the owner runs
`eval.py review <run> <case> ok|bad "<note>"`. The verdict does not wait for it.

### 5.8 Headless `tasks` driver

- `setup.sh` builds the sandbox, as today.
- The harness goes into the sandbox's `.claude/` as links to
  `commands agents skills references docs hooks`, as spec-eval does today.
  **No `--add-dir` of `claude/`** (F1). An audit after the run fails the trial
  if any tool call read a path under `claude/evals/`.
- The driver runs each stage with `claude -p` in the sandbox and keeps the
  session (`--resume`) inside one stage:
  1. `/spec ADD-1`, then, after the draft, an owner turn (Q2 a): "I read the
     whole spec. I approve it."
  2. `/plan ADD-1`, then the same owner turn for the plan.
  3. `/build ADD-1`, `/test ADD-1`, `/review ADD-1`.
  4. If `/review` returns REQUIRED or BLOCKER findings: one fix round, as the
     pipeline routes it. Then stop.
- The driver stops a trial on BLOCKED, a question to the owner it cannot
  answer, the cost cap, or a 90-minute wall clock. It records why it stopped.
- `grade.sh` scores the sandbox. The trial's case result is the pass count of
  the 49 checks, plus the stage it reached.

### 5.9 What does not change

- The case content of `gates`, the hidden checks of `add-business`, the
  `bugs` judge (ADR 0143), the holdout split (ADR 0117).
- The `Review-eval:` trailer format (F5). The new `bugs` report prints a
  ready trailer line in that format.
- `/ship` still prints the command to add a shipped bug as a case. Only the
  command changes.
- Unit tests of every scorer still run in CI. No model run in CI.

## 6. Work, in order

Each task lists its files, the steps, and the check that proves it is done.
Phases A–C are useful alone. Stop after any phase if the result is enough.

### Phase A — measure and unify `gates` (no behavior change to any case)

**A1. Measure today's cost and time.**
- Run `python3 tools/evals/workflow/run.py --output <dir>` once, all cases.
- Record per-case `duration_ms` and `model_usage`, and the total, in
  `tools/evals/README.md`.
- Verify: the numbers are in the README with the date and the commit.
- Unblocks Q3 and Q4.

**A2. Shared eval core.**
- New `tools/evals/core.py`: run folder layout, `results.json` writer
  (schema 1), trial loop with retry of ERRORED, baseline load and store,
  the verdict function (§5.5), the report renderer.
- New `tools/evals/test_core.py`: verdict cases (gate PASS→FLAKY is WORSE;
  holdout loss is WORSE; subset run compares only its cases; ERRORED is never
  scored; identical hashes print the noise line).
- Add `tools/evals/results/` to `.gitignore`. `core.py` refuses to write a run
  folder that `git check-ignore` does not report as ignored.
- Verify: `python3 -m unittest -q test_core` passes, including the
  `check-ignore` guard test. CI runs it (`ci.yml`, new step beside the other
  eval unit tests).

**A3. `gates` on the core.**
- Split `workflow/run.py` `main()` into `run_case(name, folder) -> trial` and
  keep the existing CLI as a thin wrapper.
- Trials go to `<case>/t<n>/` (F3).
- Add `--jobs`.
- Verify:
  - `test_runner.py` still passes unchanged.
  - A new unit test runs `run_case` with a stubbed `claude` that returns a
    fixed structured answer, for 3 trials, and checks the folders and
    `results.json`.
  - One real run of 3 cases × 3 trials completes and prints a report.

**A4. `eval.py` entry point with `gates`, `baseline`, `report`.**
- Verify: `eval.py gates --case ship_open_blocker --trials 2` writes to the
  results folder and prints the report. `eval.py baseline gates` refuses a
  subset run and accepts a full one.

**A5. First real baseline.**
- Run `eval.py gates` in full with 3 trials. Promote it.
- Write the FLAKY cases into `docs/observation-log.md`. A flaky gate is a
  harness finding in its own right.
- Verify: the baseline folder exists. A second run with no harness change
  prints the "measures noise" line and SAME, or lists only flaky cases.

**A6. README rewrite.**
- `tools/evals/README.md` becomes the one page: the suite table (§5.1), the
  commands (§5.2), how to read a report, the measured cost, and what each
  suite does not prove.
- Each suite README keeps its detail, and starts with "Run it through
  `eval.py`".
- Verify: the owner runs `gates` from the README alone and states the verdict
  back (success criterion 6). Every command in the README runs.

**A7. ADR.**
- New ADR: "One eval runner, trials and a stored baseline". It supersedes the
  comparison parts of ADR 0079 and says what changed: 0079 rejected a
  statistical test for 1–2 runs per side; this ADR uses a consistency rule
  (k of k), not a significance test.
- Verify: `docs/adr/README.md` index lists it. ADR 0079 gets a
  "Superseded in part by" line.

**A8. `Eval:` trailer for gate changes (Q6).** Starts after A5, because the
trailer needs a baseline to compare against.
- Watched paths: every harness file the gate suite supplies to a case. The
  runner already lists them per case (`files` from `prompt()`, recorded as
  `instruction_hashes`). `core.py` writes the union to
  `tools/evals/workflow/watched.txt`, and a unit test fails when the list is
  stale. One list, made by code, never typed by hand.
- Trailer format, in the same style as `Review-eval:`:

  ```text
  Eval: gates 58/60 PASS -> 60/60 PASS, flaky 2 -> 0 (BETTER); tools/evals/results/gates/2026-12-01-abc1234
  Eval: not run - wording only, no change to any decision
  ```

- `eval.py gates` prints the ready trailer line at the end of the report.
- New `tools/checks/check-eval-trailer.py`, modelled on `check-rescore.py`:
  - It fails a pushed or PR commit that touches a watched path with no
    `Eval:` trailer, or with a bare "not run".
  - A commit that touches both a watched path and a reviewer file needs both
    trailers. The two checks stay separate, and neither knows the other.
  - The rule starts with its commit. Earlier commits are not checked.
- New `tools/tests/test-check-eval-trailer.py`: a missing trailer, a bare
  "not run", "not run - reason", a result line, a commit with no watched path.
- Add the check to `ci.yml` and to `tools/checks/README.md`.
- The A7 ADR records the trailer, its watched set, and its cost. This mirrors
  ADR 0111.
- Verify:
  - The new unit tests pass.
  - `check-eval-trailer.py` passes on the A8 commit itself. That commit
    carries `Eval: not run - adds the check, no decision changed`.
  - A throwaway branch commit that edits `claude/commands/ship.md` without a
    trailer fails the check locally.

### Phase B — `tasks` headless

**B1. Move the harness install out of spec-eval (F2).**
- New `tools/evals/sandbox.py`: `install_harness(project)` (the
  `link_tree`/`HARNESS_DIRS`/settings code), with no `--add-dir` of
  `claude/`.
- `spec-eval/run.py` and `review-eval/run.py` import it from there.
- Move the layout tests from `spec-eval/test_produce.py` to
  `tools/evals/test_sandbox.py`.
- Verify: all three unit test files pass. A test asserts the session
  arguments contain no `--add-dir` that covers `claude/evals/`.

**B2. Read audit for hidden files.**
- Reuse `audit_reads` from `workflow/run.py` (moved to `core.py`). A trial
  fails as LEAKED if any tool call touches `claude/evals/`.
- Verify: a unit test feeds a trace with a `Read` of
  `claude/evals/add-business/hidden/checks.json` and gets LEAKED.

**B3. Driver.**
- New `claude/evals/add-business/drive.py`, or `tools/evals/tasks/run.py`
  (pick one in the spec; the eval content stays in `claude/evals/`).
- Implements §5.8: stages, owner turns, stop rules, stop reason, cost cap,
  wall clock.
- Verify:
  - Unit test with a stubbed `claude` covers each stop rule.
  - One real trial runs to the end, or stops with a recorded reason. Its
    `grade.sh` output lands in the trial folder.

**B4. `tasks` in `eval.py`.**
- Verify: `eval.py tasks --trials 1` runs one trial and reports the 49-check
  score. Record the measured cost in the README.

**B5. Baseline for `tasks`.**
- Run 3 trials. Promote the run.
- Verify: baseline stored. The README gains the measured cost per trial.

**B6. (Later) Two more tasks on the same seed.**
- Each adds one trap the pipeline must handle:
  - a migration on existing rows,
  - an auth rule,
  - or a ticket that contradicts the code.
- Each comes with hidden checks, a reference solution, and the CI self-test
  (reference passes, seed fails), as add-business does.
- Verify: `ci.yml` self-test step covers each new task.

### Phase C — `bugs` and `recall` under the runner

**C1. `bugs` on the core.**
- Wrap `review-eval/run.py` the same way as A3: `run_case`, trials,
  `results.json` schema 1.
- The report prints a ready `Review-eval:` trailer line (F5).
- Verify: `test_review_eval.py` passes. `test-check-rescore.py` passes
  unchanged. One real run of the four `ld-585*` cases with 3 trials.

**C2. Cheap case creation.**
- `eval.py bugs add --repo <project> --fix <sha> --defect <re>...` wraps
  `run.py --new`. It also accepts `--from-log <row>`, which reads the fix
  commit and the bug text from the "Shipped bugs" table.
- Update the command `/ship` prints: `claude/commands/ship.md:86-87` and
  `:298`, `claude/references/component-response-contracts.md:451`,
  `docs/observation-log.md:231`.
- Verify: unit test for the row parser. `rg -n "review-eval/run.py --new"`
  returns only the suite README.

**C3. `recall` through `eval.py`.**
- A thin pass-through, free. No trials.
- Verify: `eval.py recall` with the README's LD-380 flags gives the same
  figures as `recall.py`.

### Phase D — clean-up (after Q1)

**D1. Spec-eval per Q1.**
- *Freeze:* move it under `tools/evals/archive/spec-eval/`. Keep its unit
  tests in CI. Remove it from the main README table and link it from an
  "Archived" line.
- *Delete:* first archive the private fixture `fixtures/LD-380` outside the
  repository (it is gitignored, so git cannot restore it). Show the owner the
  list of removed paths before deleting.
- Verify: `rg -n "spec-eval"` lists only the archive, the ADRs, and the
  history notes.

**D2. Reference updates.** Every place that names an old path or command:
- `.github/workflows/ci.yml` lines 5–6, 144–224
- `README.md`, `ARCHITECTURE.md:152-164`, `tools/README.md:11, 50-64`
- `docs/HANDOFF.md:96-105` (probe steps)
- `docs/observation-log.md:40, 206, 227-231, 272`
- `claude/commands/ship.md`, `claude/references/component-response-contracts.md`
- Verify: `rg -n "tools/evals/(spec-eval|review-eval|workflow)/run.py"`
  returns only suite READMEs and ADRs. CI passes.

**D3. ADR follow-ups.** ADRs 0067, 0093, 0100, 0111, 0117 and 0143 stay valid.
Each gets one "Run through `eval.py` (ADR NNNN)" line where it names a
command. No decision in them changes.

## 7. Risks

| Risk | Effect | Control |
|---|---|---|
| Trials triple the cost | The owner stops running evals | A1 measures first; `--trials 1` for a quick look; tags for a cheap relevant subset |
| The `Eval:` trailer makes every command edit expensive | Owner writes "not run" by reflex, and the trailer means nothing | "not run" needs a reason (as ADR 0111); `--tag` runs only the cases that read the changed file; review the "not run" share after a month |
| Hidden tests leak to the agent | `tasks` scores look perfect and mean nothing | B1 (no `--add-dir`), B2 (read audit), unit test on the session arguments |
| A scripted owner turn reads as pre-approval | Breaks ADR 0148's intent | Q2 (a): the turn comes after the draft, inside the eval driver only; no harness flag |
| A bad run becomes the baseline | Every later verdict is wrong | Baseline only by explicit command, only from a full run with no ERRORED trial |
| Flaky gates hide real regressions | The owner learns to ignore FLAKY | A flaky gate is a finding: A5 logs each one in the observation log |
| Losing private fixtures | Cannot rebuild `LD-380`, `ld-585*` | Archive before any move or delete (D1) |
| Private run output committed | Leadbuster commits and files published in a public repo | `results/` gitignored; CI `git check-ignore` test; `eval.py` refuses to write to a tracked path (§5.6) |

## 8. Not in this plan

- An optimizer loop that edits the harness until a score rises. Rejected in
  ADR 0117.
- A model judge for spec quality. Code checks first (ADR 0143). Revisit only
  if `tasks` shows spec problems the hidden tests cannot see.
- Running model evals in CI.
- Statistical significance tests. 3 trials are too few. The rule is
  consistency (k of k) and a named list of losses.
