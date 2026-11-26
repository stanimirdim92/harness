# Review stays on the diff; the fix-round /test is optional; the full suite runs by impact

**Context.** On 2026-11-26 the owner filed LD-669 for the unfixed review
findings of LD-666 and LD-567, "since they are mostly not related to this
ticket". The owner also said test and review take too long. The review SARIF agrees:

| | LD-666 | LD-567 |
|---|---|---|
| BLOCKER/REQUIRED fixed | 61 (0 pre-existing) | 26 (0 pre-existing) |
| ADVISORY left unfixed | 46 | 55 |
| ADVISORY fixed | 10 | 7 |

Of the 108 findings these two tickets left unfixed, 5 were pre-existing. The
rest were ADVISORY findings on the diff's own code: ops hardening, test
polish, doc hygiene. Every persona was told to record every issue
([0130](0130-no-advisory-cap.md)), and each one cost a full write-up, a
duplicate merge and an owner decision. `/review` already forbade new
ADVISORY findings in later rounds; LD-567 round 3 still recorded 17.

`/test` costs the most time: 21.6 min per run on average, 69 min at most, on
these two tickets. Each fix round added a fix-diff `/test`
([0147](0147-fix-rounds-run-test-on-the-fix-diff.md)). At Deep the full
suite ran on every High ticket. The verifier also re-ran it on judgment: the
first LD-666 Deep run ran it three times. Leadbuster CI runs no backend
suite, so `/test` is the only full run.

**Decision.**
- A review has a scope, defined in `findings.md` §Scope. `Scope: diff` is
  the default: reviewers look only for defects the diff introduces, makes
  reachable, or makes worse. They report BLOCKER and REQUIRED findings in
  full, ADVISORY findings as one line each, and nothing pre-existing.
  Every ADVISORY finding is listed, in every round, fix rounds included.
  Fixing one is optional. A one-line ADVISORY finding gets only the report's
  `A-#` number. It gets
  no independent check and no SARIF result. `/build` fixes one only when the
  owner names it.
- `/review <target> wide` gives `Scope: wide`: today's full behavior,
  pre-existing findings included. The gap sweep returns BLOCKER and REQUIRED
  only under `Scope: diff`.
- After `/build <TICKET> review fixes`, the next stage is `/review`. `/test`
  on the fix diff runs only when the owner asks. `/review` then records
  **Independent verification: NOT RUN (fix round)**. `/release` accepts it
  like `PASS (fix diff)`. The evidence is the fix build's
  failing-then-passing test for each finding.
- At Deep, `suite-scope.py` decides from the diff whether the full suite
  runs. It runs once when the diff touches one of these:
  - a manifest or lockfile, a migration, `config/`, `bootstrap/` or `routes/`;
  - test configuration or a shared test helper;
  - a path under `## Full suite` in the base `REVIEW.md`;
  - a PHP class that production code outside its module uses.

  Otherwise
  the verifier runs the focused tests the script lists. The verifier never
  re-runs the suite on judgment: a failure re-runs that file, and an
  order-dependent failure is compared with the base result.

Affected files:
- `claude/references/findings.md`, `risk-tiers.md`, `component-response-contracts.md`;
- the four reviewer personas, `test-engineer.md` and its Figma variant;
- `claude/commands/review.md`, `build.md` §Review fixes, `test.md`, `release.md`;
- the new `suite-scope.py` and its test, and `always-person.py`, whose
  REVIEW.md reader the new script shares.

**Rejected — *(drop ADVISORY findings by default).*** It removes most of the
noise, but the owner fixed 17 ADVISORY findings on these two tickets and
wants to keep seeing them.

**Rejected — *(only drop pre-existing findings).*** It removes 5 of 108.

**Rejected — *(the full suite only when the owner asks).*** CI runs no backend
suite, so a regression in untouched code would reach `main`.

**Cost.** A fix round's runtime defect that its own tests miss shows up at
the next `/test` or in production, not in a fix-diff run. An ADVISORY finding
gets less detail. `suite-scope.py` cannot see every cross-module reach, such
as a non-PHP caller or a string reference. Such a change runs focused tests,
unless the project lists the path under `## Full suite`. On LD-666, LD-567 and LD-598
the script still asks for the full suite (migrations, shared classes); the
saving there is one run instead of several.

**Revisit if** one of these happens:
- a defect introduced by a fix round reaches `/release` or production on two
  tickets;
- a regression outside the focused tests reaches `main` after a
  `Full suite: no`;
- the owner asks for `wide` on most tickets.
