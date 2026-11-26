# A converged fix round goes straight to /release

**Context.** [0147](0147-fix-rounds-run-test-on-the-fix-diff.md) kept a
full-depth `/test` on the whole candidate after the last fix round, and
[0144](0144-fix-rounds-skip-test-until-review-converges.md) a closing review
round on the commits that `/test` added. Each fix round already runs a
fix-diff `/test` and a `/review` of the fix. On LD-567 (2026-11-26) the owner
ruled that the extra full run and the closing round cost a full suite and one
more review for no new finding: "Fix my harness to not require full depth and
test after review".

**Decision.**
- When a fix round's `/review` records **Independent verification: PASS (fix
  diff)** and leaves no open BLOCKER or REQUIRED finding, the next stage is
  `/release`.
- `/release` accepts `PASS (fix diff)` from such a round. It needs no
  full-depth `/test` and no closing round.
- Closing rounds are gone. `review-sarif.py --closing` and the `closing`
  property stay only to read older records.
- The fix-diff `/test` of each fix round, the first full VERIFY at the tier's
  depth, and the round-4 stop stay as they were.

Affected files: `claude/commands/review.md` §1, §2 and §4,
`claude/commands/test.md` §Re-verification, `claude/commands/release.md` §1
and §Risk (at Deep, the full-suite check reads the last full VERIFY PASS
before the fix rounds), and the workflow eval cases `reviewend_fix_round`,
`shipgate_no_full_run`, `shipgate_full_run`; `testfull_packet` and
`shipgate_full_run_added_tests` are retired.

**Rejected — *(keep the full-depth /test at the end, 0147).*** It catches a
fix that breaks a test outside the fix diff. The owner accepts that risk: the
fix-diff run re-runs every check the diff can affect.

**Cost.** A fix that breaks an unrelated test is caught only by CI or after
release. At Deep, the candidate's final commits get no full-suite run and no
mutation probe beyond the fix-diff probes.

**Revisit if** a defect introduced by a fix round reaches production, or CI
fails after `/release` on a test the fix-diff run did not re-run.
