# One eval runner, with trials, baselines and a verdict

**Context.** The owner had never run the harness evals alone. There were five
tools with five command lines, three fixture formats and three verdict
styles. A comparison needed a hand-typed `--baseline <path>`. Most cases ran
once, and one run is noise: two spec-eval runs of one harness scored 23/35 and
26/35. A new gate case meant editing `tools/evals/workflow/run.py` in three
places. Nothing asked for a gate run after a command changed, as
[0111](0111-reviewer-changes-are-rescored.md) does for reviewers. The spec is
`docs/specs/HR-2-SPEC.md`. The reasoning is in `docs/eval-rebuild-plan.md`.

**Decision — one runner.** `tools/evals/eval.py` is the one entry point. It
runs the suites `gates`, `tasks`, `bugs` and `recall`, and has `baseline`,
`report`, `review` and `todo`. `gates`, `tasks` and `bugs` take `--case`,
`--tag`, `--split`, `--trials` and `--jobs`. `tools/evals/core.py` holds what
the suites share: run storage, one `results.json` schema, trials, baselines,
the verdict and the report. `tools/evals/README.md` is the one page that
explains them. The owner can now learn one command and one report shape.

**Rejected — *keep five tools.*** The owner said "I have a hard time
understanding it" on 2026-11-23. Five command lines were the cause, and a
README over them would have documented five formats.

**Decision — trials.** Each model-driven case runs three times by default.
`--trials N` changes that. A case is PASS when every scored trial passed,
FLAKY when some did, and FAIL when none did. The rule is k of k, and it
replaces [0079](0079-eval-integrity-and-paired-comparison.md)'s "run each side
twice before you trust a close verdict". The old advice was a README sentence.
The new rule is code. A trial that times out, errors or returns nothing is
ERRORED. The core retries it once. A second failure stays ERRORED, is
reported, and blocks promotion to a baseline.

**Rejected — *one trial per case.*** The spec-eval scores of 23/35 and 26/35
came from one harness. One trial cannot tell a change from noise.

**Rejected — *run each side twice, by hand.*** This is the advice of
[0079](0079-eval-integrity-and-paired-comparison.md). Nothing counted the two
runs. Two runs cannot show a stable PASS, and the owner compared the numbers by
eye.

**Rejected — *five trials by default.*** The owner chose three by default on
2026-11-24 (plan question Q3). Five costs two thirds more, and no measurement
showed that three was too few. The first full run of 60 cases
with 3 trials cost $48.08 and took 26.8 minutes (run
`2026-11-25-121253-d81b0f9`). `--trials` raises the number for a close case.

**Rejected — *score an ERRORED trial as a fail, or retry until it passes.***
A timeout says nothing about the harness. Unlimited retries would hide a
broken setup.

**Decision — the baseline rule.** A run becomes a baseline only through
`eval.py baseline <suite> [<run>]`. The command refuses a run that did not
cover every case, ran fewer than three trials, had an ERRORED trial after its
retry, or has no schema 1 `results.json`. A subset run and a quick look can
therefore never become the yardstick. Runs go to
`tools/evals/results/<suite>/<YYYY-MM-DD-HHMMSS>-<sha7>/`. Git ignores that
folder, because runs hold private text. The core exits 2 and writes nothing
when the folder is not ignored.

**Rejected — *results outside the repository.*** Results beside the code are
easier to find. The ignore guard covers the risk that the repository is public.

**Decision — the verdict rule.** One rule applies to every suite, over items.
An item is a case for `gates` and `bugs`, and a hidden check for `tasks`.
States rank FAIL, FLAKY, PASS. The verdict is the first rule that applies:
WORSE, NOT BETTER, BETTER, SAME. For `gates`, any lost case is WORSE. For any
suite, a holdout case that was PASS and is not now is WORSE
([0117](0117-evals-carry-tags-and-a-holdout-split.md)). `tasks` checks use only
the count of items gained against items lost. The exit code is 0 for BETTER or
SAME, 1 for NOT BETTER or WORSE, and 2 when the run could not finish. This is
[0079](0079-eval-integrity-and-paired-comparison.md)'s item-by-item comparison,
now in one place. The `must` item rule left with spec-eval.

**Rejected — *a gate-only verdict, with other rules for other suites.*** The
owner would learn three rules. Gates are rules and must hold k of k. A task
trial is a whole pipeline run, so one flaky check of 49 is expected noise. It
must not make the run WORSE.

**Decision — why 0079's rejection of a significance test still stands.**
[0079](0079-eval-integrity-and-paired-comparison.md) rejected SAGE's test
because two fixtures and one run per side were too few. The data is larger
now, and it is still too small for a test to mean anything:
- `gates` has 60 cases, but a test needs items that move. In the baseline 51
  cases are PASS and 3 are FAIL in every trial. Only 6 are FLAKY. Five of
  those failed on a check that did not accept the answer's wording.
- `bugs` has 4 cases and `tasks` has 1 case. Three trials per case measure
  consistency, not a distribution.
- The cases are a hand-made list, not a random sample of tickets. A p-value
  would report more certainty than the design supports.
- The rebuild plan reached the same view: three trials are too few for a
  significance test, so the rule is consistency and a named list of losses.
- The list of cases gained and lost is still the useful part. Each lost case
  comes with a trial folder to read.

So the report says that three trials measure consistency and that a change of
one trial is not proof of a gain. [0079](0079-eval-integrity-and-paired-comparison.md)
is superseded only where it said "run each side twice".

**Rejected — *a significance test on the verdict.*** The reasons are above. Nothing in the data now lets a test tell a change from chance.

**Decision — gate cases are folders.** Each gate case is a folder,
`tools/evals/workflow/cases/<id>/`, with `case.json` and an optional `files/`
tree. Checks are declared rules. A case adds `check.py` only where no rule
states the check. Adding a case no longer means editing `run.py`. The
migration was proven by replay: for every case, the old code and the new
checks give the same map on stored outputs, and the stored maps keep guarding
the checks. `watched.txt` and the replay set run in CI without a model. Adding
a case still needs a replay file and a manifest entry, because the tests
require them.

**Rejected — *keep the cases in `run.py` and wrap them.*** Adding a case was
the hard part. A wrapper would leave it hard.

**Decision — the `Eval:` trailer, its watched list and its cost.** A commit
that touches a file a gate case reads carries an `Eval:` trailer. The trailer
is the last line of the `gates` report, or `not run - <reason>`.
`tools/checks/check-eval-trailer.py` checks it in CI, as `check-rescore.py`
does for `Review-eval:`. The watched list is generated from the harness files
that gate stages supply to the model. `eval.py gates --write-watched` writes it
to `tools/evals/workflow/watched.txt`, and a unit test fails when it is stale.
Codex files are not on it, because no case reads them. A full run costs about
$48. A focused run by stage tag costs a few dollars: the nine `ship*` cases
cost about $5.25 at the baseline. A wording-only change may say `Eval: not run`
with a reason.

**Rejected — *wait a few weeks before the trailer.*** The trailer is what
makes runs happen. Without it the gates would be run when someone remembered.

**Rejected — *a hand-written watched list that includes Codex files.*** A
trailer for a file no case reads demands a run that cannot measure the change.
A hand list drifts, and `check-rescore.py`'s list is the proof.

**Decision — the scripted owner turn.** `eval.py tasks` builds the add-business
sandbox and runs `/spec`, `/plan`, `/build`, `/test` and `/review` headless. It
plays the owner with separate turns sent after a draft exists. When a draft
holds `OPEN QUESTION` blocks that each mark one option `(recommended)`, the
driver sends one decision turn: "For every open question, take the recommended
option." It then sends "I read the whole spec. I approve it." The driver stops
on any other question, on BLOCKED, on a stage that runs too long, and after 90
minutes. No prompt sent before a draft exists contains approval text, so no
gate text changes ([0148](0148-owner-messages-do-not-override-pipeline-gates.md)).
Hidden tests grade each trial.

**Rejected — *a harness flag that skips approval.*** It is a gate bypass inside
the harness, which [0148](0148-owner-messages-do-not-override-pipeline-gates.md)
forbids.

**Rejected — *keep `tasks` a manual run, or script an answer for each question.***
The manual suite stayed unused. Someone must predict each question to script
answers, and an unmatched question still stops the trial. The first real trial
(`tools/evals/results/tasks/2026-11-25-130631-9209f99`) stopped at `/spec` on
two open questions that each had a recommended option.

**Decision — the copied harness, the Bash sandbox and the read audit.** A
headless run gets a copy of `commands`, `agents`, `skills`, `references`, `docs`
and `hooks`, and never a `claude/evals/` folder. The session gets no
`--add-dir` of `claude/`. The core reads the tool-call trace of every
headless trial, subagents and Bash command text included. A trial that names
`evals/add-business/hidden`, `evals/add-business/reference` or a path under
`claude/evals/` is LEAKED and fails. A probe tested a Claude Code Bash sandbox
that denies reads under `claude/evals/` while the stage scripts still run. It
failed on this host on 2026-11-25: the sandbox cannot start a nested user
namespace, so every Bash command was refused, `check-spec.py` included. Task
trials therefore run with prevention off, detection only. Every `tasks` report
says so.

**Rejected — *detect only, with no prevention attempt.*** A task score is
worthless if the agent saw the hidden tests. Prevention was worth one probe.

**Rejected — *a container for each trial.*** It was too heavy for the gain.

**Rejected — *deny the whole harness repository in the sandbox.*** `/spec` and
`/plan` run `check-spec.py` and `check-plan.py` through `~/.claude/` links into
this repository. A whole-repository deny would block them in every trial.

**Decision — the catch-up command and the hint.** `eval.py todo` lists, without
a model or network, each shipped ticket with an Approved plan and no Plan recall
row, and each Shipped bugs row with no eval case. Each item has a ready
command. A SessionStart hook, `claude/hooks/eval-todo-hint.sh`, prints one line
when the count is above zero. It prints nothing on a failure or after two
seconds. The owner sometimes skips `/release`, which was the only prompt for
these steps. `todo` finds a ticket only by a `(<TICKET> T` commit subject (OPEN-008).

**Rejected — *`todo` without the hint, or nothing.*** Without the hint a
skipped step stays skipped until the owner remembers to look.

**Decision — spec-eval is frozen.** It moved to `tools/evals/archive/spec-eval/`.
`eval.py` does not run it. Its judging tests still run in CI from the new
path. The private `LD-380` fixture is copied to
`~/harness-archive/spec-eval-fixtures/LD-380/`, and git still ignores it at the
new path. The owner reviews the freeze on 2026-12-25. [0079](0079-eval-integrity-and-paired-comparison.md)
and [0117](0117-evals-carry-tags-and-a-holdout-split.md) shaped spec-eval.

**Rejected — *delete spec-eval.*** It is the only `/spec` check on a real
ticket, and its fixture exists on this machine only.

**Rejected — *keep it as a suite with trials.*** It was the most work for the
weakest measure.

**Revisit if.** The owner reviews spec-eval on 2026-12-25 and chooses to delete
it or build it back. A host where the Bash sandbox starts would let a new
probe turn prevention on. A significance test is worth another look once a suite
holds enough items that move between runs.

Each of the ADRs 0067, 0093, 0100, 0111, 0117 and 0143 now has one line that
names the `eval.py` form of its command.
