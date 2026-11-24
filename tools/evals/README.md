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
