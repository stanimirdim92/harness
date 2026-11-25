# evals — does the harness do good work?

Checks and tests only show that the harness is put together correctly. They
cannot show whether a change made the harness better or worse. An eval runs
the harness, or part of it, and measures the result against a known answer.

You use one command for all of them:

```bash
python3 tools/evals/eval.py
```

It prints the suites, the question each one answers, when to run it, and the
last measured cost. Run it from the repository root. It uses the Python
standard library only. The paid suites need an authenticated Claude CLI.

## The suites

| Suite | The question it answers | Run it when | Last measured cost and time |
| --- | --- | --- | --- |
| `gates` | Does the pipeline make the right calls on small made-up cases? | After you change a command, agent, skill or reference | $48.08, 26.8 min (60 cases, 3 trials each) |
| `tasks` | Does the pipeline build a working feature from a ticket? | After you change how build, review or test behave | $4.05, 11.5 min (one trial that stopped at `/plan`) |
| `bugs` | Does `/review` catch bugs that really shipped? | After you change `/review` or a reviewer | $28.74, 44.4 min (4 cases, 1 trial each) |
| `recall` | Did the plan name the files that really changed? | After a ticket ships | Free: it reads git and the plan |

The figures come from real runs on 2026-11-25. The "Records" sections below
give each run's date, commit and folder. No `tasks` run has built the whole
feature yet, so a full run will cost more than $4.05. The `bugs` figure is one
trial per case. The default is three trials, so expect about three times as much.

What each suite is, and what it does not prove:

- **`gates`.** 60 case folders in `tools/evals/workflow/cases/`. Each case
  gives one stage of the harness a small made-up ticket, and asks the model for
  the decision it would make. Declared rules check the answer. The model has
  only the Read and Glob tools, so no case runs an executor or a reviewer.
  A pass shows that a decision rule held. It does not show that a real
  pipeline run is correct. All 60 cases are `optimization` cases. There is no
  holdout case.
- **`tasks`.** One case, `add-business` (`claude/evals/add-business/`). A driver
  builds a sandbox project, copies the harness into it, and runs `/spec`,
  `/plan`, `/build`, `/test` and `/review` headless. It plays the owner with
  scripted turns. Hidden tests then grade the project (49 checks). The result
  is one data point. The first two trials stopped at `/spec` and at `/plan`, so
  `/build`, `/test` and `/review` are not measured yet.
- **`bugs`.** Cases of bugs that really shipped, in
  `tools/evals/review-eval/fixtures/`. Each case runs one real `/review` on the
  commit before the fix. A trial is CAUGHT when a BLOCKER or REQUIRED finding
  sits near the fixed lines and names the defect. It is LOCATED when the finding
  is near but names no defect term. It is MISSED otherwise. The four current
  cases have no defect terms, so they can reach LOCATED at best (OPEN-007).
- **`recall`.** Scores a shipped ticket's plan against the files its commits
  changed. It counts file names. It does not say that the changes there were
  correct. `/review` and the tests judge that.

## How a run works

1. Each case runs `--trials N` times. The default is 3. Each trial runs in
   its own folder.
2. A trial that times out, errors or returns nothing is ERRORED. The core
   retries it once. A second failure stays ERRORED. The core never scores an
   ERRORED trial as a pass or a fail.
3. A case is PASS when every scored trial passed, FLAKY when some passed, and
   FAIL when none passed. Three trials measure consistency. They do not prove
   significance, and a change of one trial is not proof of a gain.
4. The core writes the run to
   `tools/evals/results/<suite>/<YYYY-MM-DD-HHMMSS>-<sha7>/`. `<sha7>` is the
   harness commit. Git ignores that folder, because the runs hold private text.
   The core exits 2 and writes nothing when the folder is not ignored.
5. The core prints a report and saves it as `report.md` in the run folder.
   `python3 tools/evals/eval.py report` prints the last report again. Add the
   suite name to see the last report of that suite.
6. When the suite has a baseline, the report ends with a verdict.

### The baseline and the verdict

A baseline is a full run that you promoted on purpose. The core never
promotes one for you.

The core compares each item of the run with the same item in the baseline.
An item is a case for `gates` and `bugs`. It is a hidden check for `tasks`.
The states rank FAIL, then FLAKY, then PASS. An item is gained when its state
moved up and lost when it moved down. The verdict is the first rule that applies:

| Verdict | When | Exit code |
| --- | --- | --- |
| WORSE | For `gates`, any case lost. For any suite, a holdout case that was PASS is no longer PASS. | 1 |
| NOT BETTER | As many items lost as gained, or more. | 1 |
| BETTER | More items gained than lost. | 0 |
| SAME | No item changed. | 0 |

`gates` never prints NOT BETTER, because any loss is WORSE there. `tasks`
checks are not holdout items, so a lost check gives NOT BETTER at worst. The
exit code is 2 when the run could not finish. A case that is new since the
baseline is listed under New. It counts as neither gained nor lost.

A run on a subset (`--case`, `--tag`) compares only the cases it ran. A subset
run can never become a baseline.

### Reading a report

This is the report that `python3 tools/evals/eval.py report gates` prints for
the current baseline. The report shortens the lists here.

```text
# gates run 2026-11-25-121253-d81b0f9
Harness commit d81b0f9, 3 trials per case, 60 cases.
This run is the gates baseline.
Cost: $48.08
Duration: 26.8 min
Flaky: build_independent (1/3), jira_complete (2/3), jira_paginated (2/3), jira_unavailable (1/3), specgate_figma_read (2/3), verifier_survivors (2/3)
Retries: 1 retry
semantic review pending: build_independent, build_pressure_fan_out, ...
Read these:
- build_independent: tools/evals/results/gates/2026-11-25-121253-d81b0f9/build_independent/t1, ...
Eval: gates 51/60 PASS, flaky 6; tools/evals/results/gates/2026-11-25-121253-d81b0f9
```

Read it from the top:

- **Verdict line.** A run with a baseline prints `Verdict: <word>: <reason>` and a
  `Baseline:` line with the commit and date. A baseline run has neither.
- **Noise line.** When no harness file changed since the baseline, the report
  says "harness unchanged since baseline: this run measures noise". Use such a
  run to see how much the cases move on their own.
- **Cost and Duration.** The baseline's figures follow in brackets. They are
  the figures of the whole baseline run, even when your run was a subset.
- **Lost, Gained, Flaky, New.** Each name carries its trial count, such as
  `(2/3)`.
- **Read these.** The trial folder of every case that changed state, and of
  every FLAKY or FAIL case. Open these folders first.
- **semantic review pending.** The checks are rules. A rule can pass an answer
  that a person would reject. After you read a case, record it with
  `python3 tools/evals/eval.py review <run> <case> ok "<note>"`. Use `bad`
  when the answer is wrong. The verdict never waits for this review.
- **Last line.** For `gates` it is the `Eval:` line. For `bugs` it is the
  `Review-eval:` line. Paste it into the commit that changed the harness
  (see "The Eval line in commits").

A trial folder holds `trial.json` (each check true or false, cost, answer),
`prompt.txt`, `trace.jsonl`, `stderr.txt` and the model's output files. A gate
trial also keeps its `fixture/` folder.

## Worked examples

Each example gives the time to run it, the exact command, what the output
means, and what to do next. The outcomes in the example output are invented.
The baseline figures are real: 51 PASS, 6 FLAKY and 3 FAIL, $48.08, 26.8
minutes, run `2026-11-25-121253-d81b0f9`.

### After editing a command, agent or skill

**When.** You edited a file listed in `tools/evals/workflow/watched.txt`, for
example `claude/commands/release.md`. Run the cases of the stage that reads it.

**Command.**

```bash
python3 tools/evals/eval.py gates --tag shipverdict --tag shipgate --tag shipsteps
```

This runs 9 cases with 3 trials each. At the baseline they cost about $5.25
and all 9 were PASS 3/3. Expect a few minutes. The tag of a case is its stage
name. To list the tags and how many cases each has:

```bash
rg -U --no-filename -o '"tags": \[\s*"[a-z]+"' tools/evals/workflow/cases | sort | uniq -c
```

A file can feed several stages. When you are unsure which, run every case with
`python3 tools/evals/eval.py gates` ($48, about 27 minutes).

**What the output means.** Example output where one case got worse:

```text
# gates run 2026-12-01-101500-abc1234
Harness commit abc1234 (dirty), 3 trials per case, 9 cases.
Verdict: WORSE: a case the baseline had higher is now lower
Baseline: d81b0f9, 2026-11-25 (2026-11-25-121253-d81b0f9)
Cost: $5.40 (baseline $48.08)
Duration: 3.1 min (baseline 26.8 min)
Lost: ship_open_blocker (2/3)
Gained: none
Flaky: ship_open_blocker (2/3)
Read these:
- ship_open_blocker: tools/evals/results/gates/2026-12-01-101500-abc1234/ship_open_blocker/t2
Eval: gates [--tag shipverdict --tag shipgate --tag shipsteps] 9/9 PASS -> 8/9 PASS, flaky 0 -> 1 (WORSE); tools/evals/results/gates/2026-12-01-101500-abc1234
```

- **WORSE.** One case went from PASS 3/3 to FLAKY 2/3. For `gates` any lost
  case is WORSE, even if other cases were gained.
- **BETTER.** At least one case gained and none lost.
- **SAME.** No case changed. For a wording-only edit this is the result you want.

**What to do next.**

1. Open the trial folder in "Read these". Find the failed check in `trial.json`.
2. Decide whether your edit caused it. A case that was FLAKY at the baseline
   can fall to FAIL by chance. Rerun that one case first:
   `python3 tools/evals/eval.py gates --case ship_open_blocker`.
3. If your edit caused it, fix the text and run the tags again.
4. When the verdict is BETTER or SAME, copy the last line into the commit
   message. A WORSE run is a trade you must name in the commit body.

### After a ticket ships

**When.** A ticket you planned with `/plan` has merged. Run this each time, or
when the session-start hint says that tickets wait.

**Command.** From the project checkout (or add `--repo <project>`):

```bash
python3 tools/evals/eval.py todo
```

It reads git and `docs/observation-log.md`, and costs nothing. For each shipped
ticket with no row in the "Plan recall" table, it prints a ready command:

```text
Shipped tickets without a Plan recall row (1):
  LD-600
    python3 /path/to/harness/tools/evals/eval.py recall --repo /path/to/project --plan docs/tasks/LD-600-plan.md --plan docs/tasks/LD-600-todo.md --range <first commit>^..main --ticket LD-600 --subject-only
```

The ticket and the paths in this block are invented.

**What the output means.** Run the printed command. It reports recall over the
files that existed before the change, precision, the changed files nobody
planned, and the planned files nobody changed. Read the `scored commits` list
first. It must hold the ticket's own commits and nothing else. For example,
`LD-442` scored 67% over existing files, and all six misses were consumers of a
changed surface.

**What to do next.**

1. Add one row to the "Plan recall" table in `docs/observation-log.md`.
2. For each miss, ask whether it was a consumer or a registration the plan
   should have found. If so, add a row to the failures table.
3. Run `python3 tools/evals/eval.py todo --count`. It prints
   `<tickets> <bugs>`, for example `0 0` when nothing is left.

`todo` finds a ticket only when a commit subject holds `(<TICKET> T`
(OPEN-008). A ticket committed under another subject style is never listed.

### After a shipped bug

**When.** A bug reached production and its fix merged. `/release` printed the
shipped-bug record and this command. You added the row to the observation log.
`eval.py todo` lists each row whose "Eval case" column is empty:

```text
Shipped bugs without an eval case (1):
  LD-700: the export drops the last row when the list has one page
    python3 /path/to/harness/tools/evals/eval.py bugs add --repo /path/to/project --from-log b12c34d5 --defect <term>
```

The ticket, the bug text and the sha in this block are invented.

**Command.** Build the case, then run it. Write the `--defect` terms from the
fix: the words a reviewer who saw the bug would use. One regex per term.

```bash
python3 tools/evals/eval.py bugs add --repo <project> --from-log <fix sha> --defect '<term>'
python3 tools/evals/eval.py bugs --repo <project> --case fix-<first 8 characters of the sha> --trials 1
```

The first command is free. It names the case
`fix-<first 8 characters of the sha>`. Add `--new <name>` to choose another
name. It exits 2 with "no Shipped bugs row names <sha>" when the log has no
such row. The second command runs a real `/review`. One trial costs about $7.
`--trials 1` is a quick look, and a quick look can never become a baseline.

**What the output means.** Each trial is CAUGHT, LOCATED or MISSED. A bug case
is PASS only when every trial is CAUGHT. The last line is a `Review-eval:`
line. The first real run scored `Review-eval: bugs 0/4;
tools/evals/results/bugs/2026-11-25-141741-ccf957f`. All four trials were
LOCATED, because the four cases had no defect terms. That score is a ceiling.
It does not measure `/review`.

**What to do next.**

1. Read the trial's `report.md`. Ask whether any finding names the defect.
2. Add `defect` terms to `case.json` if the case has none.
3. Record the case name in the "Eval case" column of the Shipped bugs row.
4. Paste the `Review-eval:` line into a commit that changes a reviewer.
   `tools/checks/check-rescore.py` checks that commit.

### Promoting a baseline

**When.** You ran every case with the default trials, and you accept the
result as the new normal. Do it after a BETTER or SAME run of a change you
keep. Do it also after you add or retire cases, because the old baseline then
lacks a case or holds one that is gone.

**Command.**

```bash
python3 tools/evals/eval.py gates
python3 tools/evals/eval.py baseline gates
```

The first command runs all 60 cases with 3 trials ($48, about 27 minutes). The
second takes the latest run. To promote another run, name it:
`python3 tools/evals/eval.py baseline gates 2026-11-25-121253-d81b0f9`.

**What the output means.** On success it prints
`gates baseline is now 2026-11-25-121253-d81b0f9`. It refuses, exits 2, and
names the reason when:

- not every case ran (a subset run);
- the run used fewer than 3 trials (a quick look);
- a trial is still ERRORED after its retry;
- the run has no schema 1 `results.json` (an older run).

**What to do next.** Run `python3 tools/evals/eval.py report gates`. The
report now says "This run is the gates baseline". Today's gates baseline has 6
FLAKY and 3 FAIL cases. It is a start, not a clean bill. Each of the nine has a
row in `docs/observation-log.md`. A case that is FAIL at the baseline cannot
be lost. Fix it, and the next run shows it as gained. `tasks` and `bugs`
have no baseline yet.

### Reading a FLAKY case

**When.** A report lists a case under Flaky. The real example is
`jira_unavailable`, FLAKY 1/3 at the baseline.

**Command.**

```bash
python3 tools/evals/eval.py report gates
```

Then open the trial folders under "Read these". For this case they are
`tools/evals/results/gates/2026-11-25-121253-d81b0f9/jira_unavailable/t2` and
`.../t3`. `t1` passed.

**What the output means.** `trial.json` in `t2` shows one failed check:
`ticket_counts_reconcile` is `false`. In `t3`, `enumeration_claim_supported`
failed too. The model's answer in `t2` had the right counts: 5 unique tickets,
4 read, 1 unread. It wrote "5 unique tickets found". The check wants the words
"unique discovered". In `t3` the answer said "unconfirmed", and the check wants
"unverified". So the check is narrower than the rule. The harness did the right
thing, and the check judged the wording. All six FLAKY baseline cases turned out
to be of this kind or close to it.

**What to do next.**

1. Decide where the fault is. If the answer breaks the rule, the harness text
   is unclear. Fix the text and rerun the case.
2. If the answer keeps the rule, the check is too narrow. Widen the rule in the
   case's `case.json`. Then run the workflow tests, and read the next section
   about replay files.
3. Rerun only that case: `python3 tools/evals/eval.py gates --case jira_unavailable`.
4. Record your reading:
   `python3 tools/evals/eval.py review 2026-11-25-121253-d81b0f9 jira_unavailable ok "check wanted the words unique discovered"`.
   Use `bad` when the answer was wrong.

Do not call a FLAKY case a pass because two trials of three passed. Do not
call a change a gain because one case moved by one trial.

## Add, change, retire and re-baseline cases

### `gates`

- **Add.** Copy a folder in `tools/evals/workflow/cases/` and edit its
  `case.json` and `files/`. `tools/evals/workflow/cases.py` describes the
  fields, the setup steps and the check rules. Then run
  `python3 tools/evals/eval.py gates --case <id>`. CI also needs three more
  things, and the tests fail until you add them:
  - `tools/evals/workflow/replay/<id>.json` with real outputs, where each
    check has one output that gives true and one that gives false;
  - the case's entry in `fixture_manifest.json`. Write it from the workflow
    folder with
    `python3 -c "import test_migration; test_migration.write_manifest()"`;
  - the case count of 60 in two tests in `test_runner.py`.
- **Change.** Edit the folder. Never edit an `expected` map in `replay/` to
  make a changed check pass. Regenerate the manifest if the fixture changed.
  The baseline still holds the old version of the case, so the next run
  compares new against old.
- **Retire.** Delete the case folder, its replay file and its manifest entry.
  Lower the two counts. Write the watched list again with
  `python3 tools/evals/eval.py gates --write-watched`. A unit test fails when
  `watched.txt` is stale. A baseline that still holds the case does no harm: a
  run compares only the cases it ran.
- **Re-baseline.** Run every case, then
  `python3 tools/evals/eval.py baseline gates`.

Run the tests from `tools/evals/workflow`:
`python3 -m unittest -q test_runner test_migration`.

### `bugs`

- **Add.** Use `eval.py bugs add` as in "After a shipped bug". It takes the
  flags of `review-eval/run.py --new`: `--clean <sha>` for a clean commit,
  `--tag`, and `--holdout`. Make every third or fourth new case a holdout.
  Never read a holdout case while you change a reviewer.
- **Change.** Edit `tools/evals/review-eval/fixtures/<case>/case.json`. Git
  ignores it. Add `defect` terms by hand to the four `ld-585*` cases (OPEN-007).
- **Retire.** Delete the case folder.
- **Re-baseline.** Run `python3 tools/evals/eval.py bugs --repo <project>`
  with the default trials. Then `python3 tools/evals/eval.py baseline bugs`.

### `tasks`

There is one case. To change what it grades, edit the hidden checks in
`claude/evals/add-business/hidden/`. The grader self-test must still pass:
the reference scores 49 of 49 and the seed fails
(`claude/evals/add-business/README.md`). CI runs this self-test. To re-baseline,
run `python3 tools/evals/eval.py tasks` and then
`python3 tools/evals/eval.py baseline tasks`.

### `recall`

Nothing to add. Each shipped ticket gets one row in the observation log.

## Catch up with `eval.py todo`

You may skip the end of a ticket. `python3 tools/evals/eval.py todo` lists what
you skipped, without a model and without network access:

- each shipped ticket with an Approved plan and no Plan recall row, with the
  `eval.py recall` command that scores it;
- each Shipped bugs row with no eval case, with the `eval.py bugs add`
  command that builds one.

It always exits 0. `--count` prints `<tickets> <bugs>`. A SessionStart hook
(`claude/hooks/eval-todo-hint.sh`) prints one line when either count is above
zero: `evals: <n> tickets without recall, <m> bugs without a case — run eval.py todo`.
The hook prints nothing when the count is zero. It also prints nothing when the
check fails or takes more than 2 seconds.

## The Eval line in commits

A commit that touches a file in `tools/evals/workflow/watched.txt` needs an
`Eval:` trailer. CI checks it with `tools/checks/check-eval-trailer.py`. The
trailer is the last line of the `gates` report, or a reason:

```text
Eval: gates 51/60 PASS -> 55/60 PASS, flaky 6 -> 2 (BETTER); <run folder>
Eval: not run - wording only, no decision changed
```

The watched list holds the harness files the gate cases read. A file no case
reads is not on it. Write the list again with
`python3 tools/evals/eval.py gates --write-watched` when a stage gains or loses
a file. A commit that changes a reviewer carries a `Review-eval:` line instead
(`tools/checks/check-rescore.py`). Git reads trailers from the last paragraph of
the message only, so put every trailer there.

## What the evals do not prove

- **No suite proves a change is good.** They show that results moved or did not
  move on the cases you have. Three trials show consistency, not significance.
  ADR 0079 rejected a significance test and ADR 0152 keeps that.
- **The `gates` checks are rules, not judges.** The six FLAKY baseline cases
  failed on wording that the check did not accept. The three FAIL cases fail
  every trial: `spec_decisions`, `review_auth_diff` and `review_plain_diff`.
  Read the "Read these" folders before you trust a number.
- **`tasks` runs with detection only.** The Bash sandbox probe failed on this
  host. The driver copies the harness without the evals and audits every trace
  for reads of hidden files. A read marks the trial LEAKED. It does not stop
  the read. See "Bash sandbox probe" below.
- **`tasks` has no full-pipeline result.** One trial stopped at `/spec` on an
  open question. The next stopped at `/plan` on a `SPEC CONFLICT`. The scripted
  owner answers open questions only when each marks one option `(recommended)`.
- **`bugs` has no measure yet.** The first run scored `bugs 0/4`, all LOCATED,
  because the cases have no defect terms (OPEN-007). Cases and run output name
  a private project. Only this machine has them. Git cannot restore them.
- **`todo` is blind to some tickets.** It lists a ticket only when a commit
  subject holds `(<TICKET> T` (OPEN-008). `recall --trailer-only` cannot score
  the HR-2 commits from `5448fa3` to `d4bb9cc`, whose trailers git does not
  parse (OPEN-004).
- **`recall` counts files.** It does not judge the changes in them.

## Archived

| Eval | Where | Review date |
| --- | --- | --- |
| `spec-eval` | `tools/evals/archive/spec-eval/` | 2026-12-25 |

`spec-eval` wrote a fresh `/spec` for a shipped ticket and compared it with the
approved spec. The owner froze it on 2026-11-23 (ADR 0152). `eval.py` does not
run it. Its judging tests still run in CI. On the review date, decide whether to
delete it or build it back. The private fixture `LD-380` is copied to
`~/harness-archive/spec-eval-fixtures/LD-380/`. See `archive/README.md`.

## Free checks

These cost nothing and need no model. CI runs the first four.

```bash
cd tools/evals/workflow && python3 -m unittest -q test_runner test_migration
cd tools/evals/review-eval && python3 test_review_eval.py
cd tools/evals/plan-recall && python3 test_recall.py
cd tools/evals/archive/spec-eval && python3 test_judge.py && python3 test_produce.py
cd tools/evals && python3 -m unittest -q test_core test_sandbox test_todo
cd tools/evals/tasks && python3 -m unittest -q test_tasks
python3 tools/tests/test-check-eval-trailer.py
```

Each suite folder has a README with its own commands. Each one starts by
pointing here.

## Ticket content stays local

Real tickets are private, and this repository is public. Git ignores the
`bugs` case folders (`tools/evals/review-eval/fixtures/`), the archived
`spec-eval` fixtures and every run under `tools/evals/results/`. Do not commit
them.

## Records

Every section from here on records real runs, with dates, commits and
folders. These sections are the evidence for the sections above. Read them
when you need the detail.

## Headless sessions get a copy of the harness

`sandbox.py` builds the project a headless `claude -p` session runs in.
`install_harness()` copies `commands`, `agents`, `skills`, `references`, `docs`
and `hooks` into the project's `.claude/`. It copies no `evals` folder. The
session gets no `--add-dir`, so it cannot read `claude/evals/`. `audit()` reads
the stream-json trace and marks a trial LEAKED when a tool call, a subagent's
call included, names `evals/add-business/hidden`, `evals/add-business/reference`
or a path under `claude/evals/`. `test_sandbox.py` tests all of this without
running `claude`.

One real turn proved the copy works. It ran once, by hand, on 2026-11-25.

| Item | Value |
| --- | --- |
| Command | `claude -p <prompt> --setting-sources project,local --permission-mode acceptEdits --allowedTools Read Glob Grep Write Edit Task Agent TodoWrite Skill 'Bash(python3 *check-spec.py*)' --max-budget-usd 5 --output-format stream-json --verbose`, with the project as the working directory |
| Prompt | `/spec EX-1` with the `archive/spec-eval/fixtures/example/intake.md` intake, plus one line that asks for a `repo-recon` subagent before the decision brief |
| Project | a README, an empty `docs/specs/`, and the output of `install_harness()` |
| Claude CLI version | 2.1.331 |
| Cost | $0.6123 (5 turns, 54.9 s, `stop_reason` `end_turn`) |
| Trace | `tools/evals/results/hr2-t002-real-spec-turn/trace.jsonl` (git ignores it; the folder also holds `command.txt` and `prompt.txt`) |

What the trace shows:

- The `spec-driven-development` skill loaded from `<project>/.claude/skills/`.
- The `/spec` command loaded from `<project>/.claude/commands/`. A slash
  command is expanded by Claude Code, so the trace has no `Read` call for
  `spec.md`. The `repo-recon` subagent did search that file by path.
- There was no permission denial, no `is_error` tool result, and no `--add-dir`.
- The subagent's 12 tool calls appear in the trace, each with a
  `parent_tool_use_id` that is the id of the main session's `Agent` call.
- `audit()` on this trace returns `LEAKED` false.

## Harness rules loading

`install_harness()` writes the harness rules to `<project>/.claude/CLAUDE.md`.
It used to write them to `.claude/AGENTS.md` when the project had its own
`CLAUDE.md` or `AGENTS.md`. A probe on 2026-11-25 (Claude CLI 2.1.331, $0.2216,
`--setting-sources project,local`, a project with its own root `CLAUDE.md`)
showed that file never loaded. The session had no harness rules, and the
user-level `~/.claude/CLAUDE.md` did not load either. With the rules in
`.claude/CLAUDE.md`, the session had them beside the project's own `CLAUDE.md`.
A project that already has a `.claude/CLAUDE.md` keeps its text, and the
harness rules follow it after a comment line. The trace is in
`tools/evals/results/open001-probe/` (git ignores it).

Runs before this change may have run without the harness rules when the
project at the fixture's commit held a `CLAUDE.md` or `AGENTS.md`. These
fixtures did: the `review-eval` cases `ld-585` and `ld-585-builder` (change
`11c44ce9`) and the `spec-eval` fixture `LD-380`. The `review-eval` cases
`ld-585-filter` and `ld-585-order`, and the `spec-eval` `example` fixture, have
neither file, so they ran with the rules. Score those three again before you
compare them with an older run. The four `review-eval` cases were scored again
with the rules in the "Bugs run" below.

## Bash sandbox probe

`tasks/probe_sandbox.py` asks whether Claude Code's Bash sandbox can stop a
headless session, and its subagent, from reading `claude/evals/` while the
stage scripts still run. The setting denies that one folder. It does not deny
the rest of the repository, because `/spec` and `/plan` run `check-spec.py` and
`check-plan.py` through `~/.claude/` links into it. The probe passes only when
both `cat` reads are refused and the `check-spec.py` call runs and prints its
result. The unit tests for the record parser and the written deny paths are in
`tasks/test_tasks.py`.

Bash sandbox probe: fail (2026-11-25, Claude Code 2.1.331)

Prevention off: detection only. Task trials run with the copy (`install_harness()`)
and `audit()`, and every `tasks` report states "prevention off: detection only".

| Item | Value |
| --- | --- |
| Command | `python3 tasks/probe_sandbox.py <project> results/hr2-t013-sandbox-probe --budget 4`: one headless session with `--allowedTools Bash Agent Task`, no `--add-dir` |
| Claude CLI version | 2.1.331 |
| Cost | $0.4708 (4 turns, 15.1 s, `stop_reason` `end_turn`) |
| Trace | `tools/evals/results/hr2-t013-sandbox-probe/trace.jsonl` (git ignores it; the folder also holds `record.json`, `command.txt` and `prompt.txt`) |

The exact setting, in the project's `.claude/settings.local.json`:

```json
"sandbox": {
  "enabled": true,
  "failIfUnavailable": true,
  "allowUnsandboxedCommands": false,
  "autoAllowBashIfSandboxed": true,
  "filesystem": { "denyRead": ["/var/www/html/personal/harness/claude/evals"] }
}
```

The keys come from the schema inside the installed CLI binary (2.1.331), not
from memory. `sandbox.filesystem.denyRead` takes absolute paths and `~`.
`allowUnsandboxedCommands: false` stops the session from leaving the sandbox.
`failIfUnavailable: true` stops a session that cannot start the sandbox. No
`~/.claude/` entry resolves into `claude/evals/` on this machine, so the deny
list holds the one repository path.

What the trace shows:

- The session `cat`, the subagent `cat` and the `check-spec.py` call all
  failed with the same error:
  `apply-seccomp: write /proc/self/setgroups (nested userns is capability-restricted; caller must provide CAP_SYS_ADMIN): Permission denied`.
- That is not a deny of the eval file. The sandbox could not start for any
  Bash command, so the stage script was refused as well. The probe records
  `fail` because `check-spec.py` did not run (REQ-031, "Stage scripts blocked").
- `failIfUnavailable: true` did not stop the session. The sandbox started, and
  each command failed when it applied its seccomp filter.
- The cause is this host (Ubuntu 26.04, `kernel.apparmor_restrict_unprivileged_userns=1`).
  `unshare --user --map-root-user true` fails with `Operation not permitted`, and
  so does a nested `unshare --user` inside `bwrap`. The sandbox needs a nested
  user namespace for its seccomp step.
- The CLI has `sandbox.allowNestedUserNamespaces`. Its own description says it
  removes `filesystem.denyRead`, so it cannot be used to prevent reads. The
  probe did not try it.
- The probe ran once. It was not rerun: no setup bug of the probe caused the
  failure, and an unchanged rerun on this host fails the same way.

## Task trial

`python3 tools/evals/eval.py tasks --trials 1` runs the add-business pipeline
once and grades it with the hidden checks (`tasks/run.py`). One trial ran on
2026-11-25.

| Item | Value |
| --- | --- |
| Command | `python3 tools/evals/eval.py tasks --trials 1` (a session may spend $10, the trial $30) |
| Harness commit | `9209f99` |
| Claude CLI version | 2.1.331 |
| Cost | $2.0240 (the `/spec` session: 13 turns, then the owner turn in the same session). The saved record says $3.9718: it counted the resumed session twice, because a resumed session reports the cost of the whole session. The driver now counts each turn once. |
| Duration | 7.3 min |
| Result | 2 of 49 checks passed (the two baseline checks of the untouched seed), 0 of 1 trials passed every check |
| Stopped | at `/spec`. The saved record says `not_approved`; the driver now says `question`. |
| Prevention | off: detection only (the sandbox probe says `fail`). Not LEAKED. |
| Run folder | `tools/evals/results/tasks/2026-11-25-130631-9209f99/` (git ignores it) |

What happened:

- `/spec ADD-1` drafted a spec of 15 requirements and left two `OPEN QUESTION`
  blocks in it: where the multi-token search rule applies (Q1), and the test
  layer for the modal (Q2). It did not call the draft ready for approval.
- The driver sent the owner turn "I read the whole spec. I approve it." in
  that session. `/spec` kept the gate: a spec with an open question cannot be
  approved, and the turn picks no option. The spec stayed a Draft.
- No later stage ran, so the grade is the grade of the untouched seed
  (the `grade.sh` self-test: baseline 2 of 2, feature 0 of 47).
- A trial that stops at `/spec` on a real owner question will end this way
  each time, until the scripted owner answers such questions too. REQ-019
  stops the trial on any question other than the approval, so the driver
  does what the spec says. The result is one data point, not a baseline.
- The UI checks cannot run on this machine yet. Playwright asks for
  `chromium_headless_shell-1243`, and only version 1255 is installed. On
  2026-11-25 `grade.sh` scored the reference at 26 of 49: all 23 `UI-` checks
  failed with `browserType.launch: Executable doesn't exist`. Run
  `npx playwright install chromium` in `claude/evals/add-business/hidden/` once
  before a trial that builds the feature. This trial built nothing, so it is
  not affected. The install ran later on 2026-11-25 (TD-014), and `grade.sh`
  then scored `claude/evals/add-business/reference` at 49 of 49.

### Second trial: the decision turn

The driver now answers open questions that carry a recommended option with one
decision turn, then approves (DEC-013). One trial ran on 2026-11-25. It shows
that a trial gets past `/spec`. It is not a pass target.

| Item | Value |
| --- | --- |
| Command | `python3 tools/evals/eval.py tasks --trials 1` (a session may spend $10, the trial $30) |
| Harness commit | `1f4e66b` |
| Cost | $4.05 |
| Duration | 11.5 min (11.1 min in the pipeline) |
| Result | 2 of 49 checks passed (the two baseline checks of the untouched seed), 0 of 1 trials passed every check |
| Stopped | `question` at `/plan`: a `SPEC CONFLICT` in the plan |
| Prevention | off: detection only (the sandbox probe says `fail`). Not LEAKED. |
| Run folder | `tools/evals/results/tasks/2026-11-25-135608-1f4e66b/` (git ignores it) |

Turns, from the trace:

| Turn | Session | Cost | Time |
| --- | --- | --- | --- |
| `/spec ADD-1` | new | $2.25 | 8.0 min |
| "For every open question, take the recommended option." | resumed | $0.36 | 0.6 min |
| "I read the whole spec. I approve it." | resumed | $0.23 | 0.3 min |
| `/plan ADD-1` | new | $1.21 | 2.1 min |

What happened:

- `/spec` left a Draft with open questions. The decision turn picked the
  recommended option of each. The spec header then read `Status: Approved`.
  The earlier trial stopped here.
- `/plan` read the approved spec and found two conflicts it could not settle:
  the `mission` search of the REQ-014 scenario "Existing badge" returns one
  place, so its "a new place shows no badge" clause cannot be tested (C1); and
  the spec does not say what a query with no words, such as `,,`, returns (C2).
  It wrote a `## SPEC CONFLICT` and the handoff "Blocked, return to /spec".
- The driver stops on a `SPEC CONFLICT` (REQ-019). No build, test or review
  ran, so the grade is the grade of the untouched seed.
- The conflict is a finding about the spec that `/spec` wrote, not a driver
  fault. The trial was not rerun for a better result.

## Bugs run

`python3 tools/evals/eval.py bugs --repo <project>` runs every `review-eval/`
case with trials and writes a schema 1 `results.json` (`BugsSuite` in
`review-eval/run.py`). The judge is unchanged. A bug trial passes when it is
CAUGHT. A bug case is PASS when every trial is CAUGHT, FLAKY when some are, and
FAIL when none are. A clean trial passes when it has no BLOCKER or REQUIRED
finding. A trial whose trace names eval files is LEAKED: it fails and the
report names it (`sandbox.audit()`, REQ-009). `--budget` caps what one `/review` may spend (default $10). A retry of
an errored trial gets only what the first attempt left of that cap. When no
cost can be read from the failed attempt, the retry does not start. The report
ends with a `Review-eval:` line to paste into a commit that changes a reviewer
(`tools/checks/check-rescore.py` accepts it). One real run was made on
2026-11-25.

| Item | Value |
| --- | --- |
| Command | `python3 tools/evals/eval.py bugs --repo <project> --trials 1 --budget 10` |
| Cases | the four `ld-585*` cases, one trial each, run one after another |
| Harness commit | `ccf957f` (not dirty). It is the first scoring of `ld-585` and `ld-585-builder` with the harness rules loaded (see "Harness rules loading"). `ld-585-filter` and `ld-585-order` ran with them before as well. |
| Claude CLI version | 2.1.331 |
| Cost | $28.7448 (a trial cost $6.87 to $7.47). The limit was $40. No trial errored and no trial was retried. |
| Leak audit | The run itself did not audit. Afterwards `sandbox.audit()` read the four traces: none LEAKED. |
| Duration | 44.4 min |
| Run folder | `tools/evals/results/bugs/2026-11-25-141741-ccf957f/` (git ignores it; each trial folder keeps `report.md`, `meta.json`, the SARIF file and `trace.jsonl`) |

| Case | Result | Trial | Findings (BLOCKER or REQUIRED) |
| --- | --- | --- | --- |
| `ld-585` | FAIL | LOCATED | 31 (24) |
| `ld-585-builder` | FAIL | LOCATED | 36 (23) |
| `ld-585-filter` | FAIL | LOCATED | 60 (41) |
| `ld-585-order` | FAIL | LOCATED | 38 (22) |

The report line:

```
Review-eval: bugs 0/4; tools/evals/results/bugs/2026-11-25-141741-ccf957f
```

None of the four cases has `defect` terms in its `case.json`. A case without
terms can reach LOCATED at best (ADR 0143), so this run could not score
CAUGHT. In each case `/review` raised a BLOCKER or REQUIRED finding within 3
lines of a line the fix changed. Read `report.md` of each trial to learn
whether any of them names the defect. The terms are the owner's to write; a
trial that says "LOCATED" here is not a measure of what `/review` catches.
There is no baseline yet, so the report has no verdict.

## Measured

The `gates` suite runs the cases of `workflow/`. This section records two full
runs of them. Run output sits in `tools/evals/results/`, which git ignores.

### Three trials per case (the gates baseline)

The first baseline: `python3 tools/evals/eval.py gates`, with the default 3
trials and `--jobs 4`. The run is `tools/evals/results/gates/2026-11-25-121253-d81b0f9`.

| Item | Value |
| --- | --- |
| Date | 2026-11-25 |
| Harness commit | `d81b0f9` |
| Cases | 60, three trials each: 180 trials |
| Total cost | $48.0816 |
| Cost per trial | about $0.27, which is 3.07 times the one-trial run |
| Total duration | 1610992 ms (26.8 minutes, four trials at a time) |
| Trials that passed | 163 of 180 |
| Case results | 51 PASS, 6 FLAKY, 3 FAIL |
| Retries | 1 (`review_plain_diff` t2); no ERRORED trial after retry |

The cost is `cost_usd` in the run's `results.json`. FLAKY: `build_independent`,
`jira_complete`, `jira_paginated`, `jira_unavailable`, `specgate_figma_read`,
`verifier_survivors`. FAIL in every trial: `spec_decisions`, `review_auth_diff`,
`review_plain_diff`. Each has a row in `docs/observation-log.md`.

### One trial per case (before the migration)

One full run of every `workflow/` case with the runner as it stood before the
gate changes.

| Item | Value |
| --- | --- |
| Date | 2026-11-24 |
| Harness commit | `df01d25` (later commits changed none of the 27 instruction files the cases read) |
| Claude CLI version | 2.1.331 |
| Cases | 60, one trial each |
| Total cost | $15.6664 |
| Total duration | 2001039 ms (33.4 minutes, cases run one after another) |

Cost is the sum of `costUSD` over `model_usage` in each case's `result.json`.
Duration is `duration_ms`. The total cost is the sum of the per-case figures
below, each rounded to four decimals. A first sample of five cases
(`jira_complete`, `spec_decisions`, `plan_handoff`, `build_independent`,
`ship_open_blocker`) cost $2.6485 and projected $31.78 for 60 cases. The
real total is half of that, because most cases are cheap.

Cases that ended in `execution_error`: none. No case was rerun.

Four cases ended with a failed assertion, not an execution error:
`spec_decisions`, `jira_paginated`, `review_auth_diff` and
`review_plain_diff`. They are recorded as they ran.

| Case | Cost (USD) | Duration (ms) |
| --- | --- | --- |
| `build_independent` | 0.9385 | 162279 |
| `build_pressure_fan_out` | 0.2274 | 28908 |
| `build_shared_db` | 0.6318 | 76481 |
| `executor_fix_trailer` | 0.0884 | 6757 |
| `executorsteps_done_status` | 0.1239 | 16895 |
| `fix_blocked` | 0.1547 | 20053 |
| `fix_next_stage` | 0.1701 | 22865 |
| `fix_other_review_file` | 0.1185 | 11477 |
| `fix_rerun` | 0.1539 | 17090 |
| `fixround_unverified` | 0.1425 | 13581 |
| `fixround_verified` | 0.2042 | 23291 |
| `gate_setup_failure` | 0.2040 | 18795 |
| `gate_spec_pin` | 0.1752 | 14132 |
| `jira_complete` | 0.1404 | 21692 |
| `jira_paginated` | 0.1327 | 24527 |
| `jira_unavailable` | 0.1195 | 21846 |
| `owner_accepts_required` | 0.2283 | 27365 |
| `owner_approves_read_spec` | 0.2327 | 19709 |
| `owner_go_over_blocker` | 0.2042 | 20683 |
| `owner_preapproves_spec` | 0.2788 | 38810 |
| `owner_skips_test_depth` | 0.1771 | 19946 |
| `plan_conflict_incomplete` | 0.2613 | 23150 |
| `plan_conflict_infeasible` | 0.2675 | 25590 |
| `plan_editorial` | 0.2640 | 21456 |
| `plan_handoff` | 0.2810 | 29532 |
| `plan_preserved_req` | 0.2738 | 26628 |
| `plan_stale` | 0.2437 | 13732 |
| `plansteps_external_tracker` | 0.1165 | 9171 |
| `review_auth_diff` | 0.1979 | 20976 |
| `review_plain_diff` | 0.6103 | 84774 |
| `review_pressure_skip_test` | 0.1811 | 16613 |
| `reviewend_fix_round` | 0.1786 | 20342 |
| `route_browser_check` | 0.1419 | 11997 |
| `ship_answered_required` | 0.5141 | 61817 |
| `ship_base_check_failed` | 0.1971 | 26223 |
| `ship_open_blocker` | 0.4088 | 39085 |
| `ship_open_required` | 0.1676 | 16187 |
| `ship_preexisting_blocker` | 0.1901 | 24190 |
| `ship_stats_order` | 0.1835 | 22723 |
| `shipgate_full_run` | 0.1685 | 15848 |
| `shipgate_full_run_added_tests` | 0.1335 | 11050 |
| `shipgate_no_full_run` | 0.1291 | 10478 |
| `spec_conflict` | 0.2526 | 17360 |
| `spec_decisions` | 0.8798 | 147358 |
| `spec_simple` | 0.3076 | 37695 |
| `specgate_default_dec` | 0.2352 | 21795 |
| `specgate_figma_read` | 0.6877 | 109420 |
| `specgate_intake_blocker` | 0.2932 | 49793 |
| `specgate_intake_incomplete` | 0.1996 | 14327 |
| `specgate_rerun_after_brief` | 0.9077 | 160585 |
| `specgate_ticket_beats_precedent` | 0.2388 | 22165 |
| `testfix_packet` | 0.1672 | 24987 |
| `testfull_packet` | 0.1825 | 33744 |
| `testgate_figma` | 0.1582 | 24866 |
| `testgate_handed_on` | 0.1612 | 25172 |
| `testgate_two_candidates` | 0.1146 | 9971 |
| `testresult_defect` | 0.4037 | 47276 |
| `verifier_survivors` | 0.1416 | 18716 |
| `verifiersteps_method_packet` | 0.1990 | 41506 |
| `verifiersteps_plain_packet` | 0.1795 | 35559 |
| **Total, 60 cases** | **15.6664** | **2001039** |
