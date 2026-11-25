# evals — does the harness do good work?

Checks and tests only show that the harness is put together correctly. They
cannot show whether a change made its specs or plans better or worse. That
needs a ticket whose right answer is already known: one that shipped.

An eval runs the harness, or part of it, on such a ticket and measures how
close it gets to what really happened. Two of them run a real model and cost
money, so you run them by hand, after a ticket ships or after you change the
harness. Their scoring code has its own tests (`test_*.py`), which CI runs for
free.

| Folder | The question it answers | Cost |
| --- | --- | --- |
| `plan-recall/` | Did the plan name the files that really changed? Before coding, a plan lists the files it expects to touch. After the ticket ships, this compares that list with the real diff. 18 of 20 files named is 90%. | Free: it reads git and the plan |
| `spec-eval/` | How close does today's harness get to the spec you approved? It writes a fresh spec for a shipped ticket, on the code as it was before the work began, then compares it with the approved one. | One real `/spec` run, about $1.40. Scoring a spec you already have is free |
| `review-eval/` | Does `/review` catch bugs that really shipped? A bugfix commit points, through blame, at the commit that wrote the bug; `/review` runs on that commit and must flag those lines. Clean commits count noise. | One real `/review` per case |
| `workflow/` | Does the pipeline make the right calls on small made-up cases: which reviewers run, and whether `/test` is needed? | Real model runs |

## Did my harness change help?

Score before the change and save the result, then score after it and compare
the two item by item. Both `plan-recall` and `spec-eval` take `--baseline`.
They list what was gained and what was lost, so a loss cannot hide behind a
better average. Each folder's README has the commands.

## Ticket content stays local

Real tickets are private. `spec-eval` keeps its fixtures and run output in
folders git ignores, and this repository is public. Do not commit them.

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
| Prompt | `/spec EX-1` with the `spec-eval/fixtures/example/intake.md` intake, plus one line that asks for a `repo-recon` subagent before the decision brief |
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
compare them with an older run.

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

## Measured

One full run of every `workflow/` case with the runner as it stood before the
gate changes. Run output sits in `tools/evals/results/`, which git ignores.

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

### Three trials per case (the gates baseline)

The first baseline: `python3 tools/evals/eval.py gates`, with the default 3
trials and `--jobs 4`. The run is `tools/evals/results/gates/2026-11-25-121253-d81b0f9`.

| Item | Value |
| --- | --- |
| Date | 2026-11-25 |
| Harness commit | `d81b0f9` |
| Cases | 60, three trials each: 180 trials |
| Total cost | $48.0816 (about $0.27 a trial, 3.07 times the one-trial run) |
| Total duration | 1610992 ms (26.8 minutes, four trials at a time) |
| Trials that passed | 163 of 180 |
| Cases | 51 PASS, 6 FLAKY, 3 FAIL |
| Retries | 1 (`review_plain_diff` t2); no ERRORED trial after retry |

The cost is `cost_usd` in the run's `results.json`. FLAKY: `build_independent`,
`jira_complete`, `jira_paginated`, `jira_unavailable`, `specgate_figma_read`,
`verifier_survivors`. FAIL in every trial: `spec_decisions`, `review_auth_diff`,
`review_plain_diff`. Each has a row in `docs/observation-log.md`.
