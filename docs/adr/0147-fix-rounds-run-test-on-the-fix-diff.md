# Fix rounds run /test on the fix diff

**Context.** [0144](0144-fix-rounds-skip-test-until-review-converges.md)
removed `/test` from fix rounds. Its reason was the cost: a Deep re-verify ran
the full suite again, 15 minutes to 2 hours per round. The owner named the
real problem on 2026-11-21: `/test` tested the whole suite when it had to test
only the latest diff. The owner runs build, test, review in every round, and
wants each loop to verify, discover and fix. No ticket ran under 0144 before
this decision: no leadbuster session contains `DEFERRED (fix round)`.

**Decision.**
- After `/build <TICKET> review fixes`, `/test` verifies the fix diff only. It
  re-runs every check that diff can affect, and probes the conditions the fix
  adds or changes. It does not run the full suite, at any depth. It reports
  **VERIFY PASS (fix diff)**.
- `/review` requires that result for a fix round and records **Independent
  verification: PASS (fix diff)**. The depth rule does not make it stale. The
  status `DEFERRED (fix round)` is gone.
- When a round leaves no open BLOCKER or REQUIRED finding, `/test` runs once
  at the tier's depth on the whole candidate. At Deep that is the full suite
  and a probe on every changed condition
  ([0106](0106-risk-tiers-and-review-depth.md)). The closing review round and
  its round count stay as 0144 set them.
- A fix round may carry the test-only commits its fix-diff run declared. It
  is never the closing round: only the round after the full-depth `/test` is.
- `/ship` blocks on `PASS (fix diff)` until that full run exists.
- The same-failure sweep of the review-fix executor stays as 0144 set it.

The order is the usual one: someone other than the author verifies each
implementation step before review. The tier's depth is still met once before
`/ship`, so nobody gets a shallower check than the tier asks for.

Affected files: `claude/commands/review.md` §2, `claude/commands/test.md`
§Re-verification, `claude/commands/build.md` §Review fixes,
`claude/commands/ship.md` §1, `claude/agents/test-engineer.md` and its Figma
variant.

**Rejected — *(no /test in fix rounds, 0144).*** A runtime defect in a fix
shows up only at the final `/test`, after every later round built on it. The
owner does not accept that delay, and the cost that justified it was the full
suite, which this decision removes from fix rounds.

**Rejected — *(a fix-diff /test and no full run at the end).*** A fix that
breaks an unrelated test would never be caught. It also lowers Deep depth,
which 0106 and [0116](0116-lessons-from-ld-507.md) forbid.

**Cost.** One fix-diff `/test` per fix round. It runs focused tests and a few
probes, not the suite.

**Revisit if** a fix-diff `/test` takes more than 20 minutes on two tickets in
a row; or the final full `/test` fails on a defect that a fix round introduced
and its fix-diff run passed, on two tickets in a row.
