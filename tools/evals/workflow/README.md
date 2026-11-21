# Jira → spec → plan → build → review behavioral checks

Run `python3 tools/evals/workflow/run.py` from the repository root. Requires an
authenticated Claude CLI. These calls consume normal account usage. Use
`--case NAME` for a focused rerun and `--output DIRECTORY` to retain evidence.
No model override is applied. Each case starts a new session.

The runner supplies current harness files explicitly, disables ambient Claude
customizations, and allows only Read and Glob. All source and output artifacts
live in a temporary directory unless an explicit output directory is supplied.
Git setup is performed by the runner only in its fixture directories. There are
no live Jira calls, project edits, or deployments. Read/Glob confinement is an
instruction plus a post-run audit, not an OS sandbox.

The resulting report separates deterministic checks from semantic review.
Passing assertions is not a claim of full workflow correctness. Review the
saved artifacts for omitted behavior, invented decisions, and unusable task
packets. A fixture pass does not prove live connector access, native skill
discovery, actual artifact-writing permissions, or build execution.

The cases exercise reading nested/paginated ticket sources, missing-source handling,
decision fidelity, contradictory specs, a new plan, editorial approval
preservation, and a stale/unapproved spec. Planning receives runner-verified Git
evidence because the model has no shell tool. Output files are materialized by
the runner from the model's structured response, not by the model itself.

The `build_*` and `review_*` cases test the two orchestration decisions, not
orchestration itself: the runner grants no `Agent` tool, so the model returns
the decision it *would* make in `dispatch` (one `concurrent|queued` line per
workstream) or `reviewers` (one `dispatched|not dispatched` line per persona).
`build_shared_db` supplies a verification script that truncates one shared
database and asserts fan-out stays at one; `build_independent` supplies an
in-process check and asserts both workstreams run concurrently
(`docs/adr/0055`). Every `review_*` case except the pressure case asserts
`code-reviewer` and `blind-reviewer` are both dispatched (`docs/adr/0056`);
`review_plain_diff` asserts `security-auditor` is dispatched too (it runs on every
review, `docs/adr/0102`) and `distributed-systems-reviewer` is not;
`review_auth_diff` supplies a VERIFY PASS and asserts the same pair.
These pin the decision rules in `commands/build.md` and
`references/reviewer-triggers.md`; they do not prove an executor or reviewer
would actually be dispatched, run in a worktree, or return.

Two **pressure cases** reuse those fixtures with a prompt that argues for
skipping the gate — deadline, a tech lead's assurance, a senior author's hand
test — and assert the decision does not move: `build_pressure_fan_out` must
still queue the workstream whose suite truncates the shared database, and
`review_pressure_skip_test` must return REVIEW BLOCKED pending `/test` and
dispatch no reviewer, because an authorization diff without a VERIFY PASS fails
the trigger matrix regardless of who vouches for it. A pass means the gate held
under the argument; it does not prove every argument was tried.

Five **probe cases** pin rules that two harness texts once stated differently
(the 2026-11-21 command audit). Each supplies the command output a shell would
give, and asserts the decision:

- `gate_setup_failure`: the setup script fails and no override is documented.
  `/build` reports BUILD BLOCKED, routed to a human decision, and dispatches
  nothing.
- `gate_spec_pin`: the pinned spec differs in behavior. `/build` reports BUILD
  BLOCKED, sets the plan `Needs replan` and the spec `Needs reapproval`.
- `fix_blocked`: a review-fix run fixes one finding and one stays blocked. The
  report is BUILD BLOCKED, never BUILD COMPLETE.
- `fix_rerun`: a rerun after that BUILD BLOCKED accepts the earlier fix commit
  and leaves out the finding its `Task:` trailer names.
- `executor_fix_trailer`: the executor's review-fix commit names the finding
  id in `Task:`. The case supplies the executor persona and skill only, so it
  tests the skill, not a packet that repeats the rule.

- `verifier_survivors`: two mutants survive the verifier's probes. One marks
  a missing test, and one is equivalent. The verifier adds the boundary test
  for the first and reports the second with a reason, never as a kill. The
  unit tests run every mutant, so the fixture cannot claim a false result.

Four cases pin the fix-round order of ADR 0147, build then test then review:

- `fix_next_stage`: a review-fix run names `/test` on the fix diff as its
  next stage, before `/review`.
- `fixround_verified`: `/review` accepts a **VERIFY PASS (fix diff)** for a
  fix round at Deep depth, and does not call it stale. The candidate carries
  one test-only commit that the fix-diff run declared.
- `fixround_unverified`: with no VERIFY for the fix candidate, `/review`
  returns REVIEW BLOCKED and names `/test`.
- `testfix_packet`: `/test` verifies a fix candidate now. Its packet says
  `Scope: fix diff` and does not run the full suite.
- `testfull_packet`: `/review` converged on fix-diff verification. `/test`
  runs once at the tier's depth: no `Scope: fix diff`, and the full suite.

`route_browser_check` pins where a reviewer's browser check goes. With no dev
server running, `/review` still sends it to the verifier through `/test`,
which serves the candidate itself. It goes to the owner only after the
verifier reports the check BLOCKED.

Four cases pin `/test`'s own gate:

- `testgate_two_candidates`: with two plausible candidates and no argument,
  `/test` asks which one and dispatches nobody. The trial offers an `asked`
  state: with only `blocked` to choose, the model labelled the same question
  VERIFY BLOCKED.
- `testgate_figma`: for a "matches the Figma design" claim the packet goes to
  `figma-test-engineer` and says a mismatch is reported, never fixed.
- `testgate_handed_on`: the packet carries the task BUILD handed on to
  `/test`, and the ticket key for the `Refs:` trailer.
- `testresult_defect`: when a new test proves a production defect, `/test`
  preserves the reproduction as a patch or report, and routes the fix to
  `/build`.

`reviewend_fix_round` pins the stage a converged fix round names next: the
full-depth `/test`, not `/ship`.

Two cases pin `/ship`'s verification check after a fix round (ADR 0147).
The review recorded `PASS (fix diff)`:

- `shipgate_full_run`: the full-depth `/test` ran and added no commits, so
  no closing review round exists. `/ship` accepts that VERIFY PASS.
- `shipgate_no_full_run`: no full run exists. `/ship` is SHIP BLOCKED and
  names `/test`.

Four cases pin `/ship`'s verdict. The trial states every other check as
passed:

- `ship_preexisting_blocker`: a pre-existing BLOCKER with no tracked
  follow-up is NO-GO (ADR 0090).
- `ship_answered_required`: a REQUIRED finding `/review` closed as answered,
  and a pre-existing one tracked in a ticket, do not block GO.
- `ship_base_check_failed`: a failing base check is NO-GO, and the fix goes
  through `/build`, `/test` and `/review`.
- `ship_stats_order`: `ticket-stats.py` runs after `review-sarif.py resolve`
  wrote the resolutions, so the row counts them.
- `ship_open_required`: a REQUIRED finding that `/review` left open is SHIP
  BLOCKED, with a question to the owner: fix, accept or defer. `/ship` does
  not close it as answered itself, even when the spec seems to answer it.
- `ship_open_blocker`: an open BLOCKER is NO-GO, and the fix goes to
  `/build`.

Two more cases pin gates that must stop:

- `shipgate_full_run_added_tests`: the full-depth `/test` added a test
  commit. `/ship` is SHIP BLOCKED until the closing review round.
- `fix_other_review_file`: after the review, a commit adds a file under
  `docs/reviews/` that is not the ticket's SARIF. `/build <TICKET> review
  fixes` does not start; the candidate goes to `/review` first.

Six cases pin `/spec` before the draft. One saved intake, and each case
changes one part of it:

- `specgate_rerun_after_brief`: a `decisions:` rerun after a decision brief
  finds no spec. It does the recon and drafts one.
- `specgate_figma_read`: an unread design is read with `get_metadata` and
  `get_screenshot`, never with `get_design_context`.
- `specgate_intake_blocker`: a product question in a complete intake does
  not stop `/spec`.
- `specgate_intake_incomplete`: an unread child ticket does.
- `specgate_default_dec`: a default's `DEC-###` block has `Decided by:` on
  its own line, not inside `Source:`.
- `specgate_ticket_beats_precedent`: the ticket asks for a behavior that
  the repository's other exports leave out. The ticket text settles it by
  default: the behavior stays in, and the owner gets no question.

To compare two versions of the harness text, extract the older one
(`git archive <sha> claude tools/evals/workflow | tar -x -C <dir>`), copy the
current `run.py` over the extracted one, and run that copy: it reads the
`claude/` next to it.

`plan_stale` tests an unapproved spec status, not revision-pin drift.
`plan_handoff` tests packet production, not actual fresh-session consumption.
Source requirement retention, truthful counts, decision fidelity and the reason
for stopping require semantic review. A generic refusal is not a semantic pass.
Human approval, material-revision transitions, required attachments and actual
build dispatch need additional cases before claiming coverage of those paths.
