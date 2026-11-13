# Reviewers run at once

**Decision.** `/review` dispatches every reviewer for the round at once, with
no concurrency cap (owner's call, 2026-11-13). This supersedes
[0004](0004-reviewer-batch-cap-no-high-risk-exception.md)'s cap of 2.

Reviewers stay independent: no reviewer sees another's findings. `/review`
merges duplicates after all reports arrive.

The cap kept token burn steady. It never protected correctness: reviewers
hold only Read, Grep and Glob, so they cannot race on files, git or a
database. The owner's plan now has the rate-limit headroom for four
concurrent reviewers. The cost per round stays the same, and the wall time
drops by about half at Deep.

**Rejected — *let reviewers share findings.*** A reviewer that sees another's
findings anchors on them and covers less. Independent duplicates also confirm
a finding: three reviewers found LD-536's id overflow on their own.

**Revisit if.** Reviews hit the rate limit and run slower than in batches.
