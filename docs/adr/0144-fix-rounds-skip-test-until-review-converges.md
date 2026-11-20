# Fix rounds skip /test until review converges

**Context.** `/build <TICKET> review fixes` already named `/review` as its
next stage, but `/review` §2 required a VERIFY PASS for the exact candidate.
So every fix round ran build → test → review. Tickets often ran build ×3,
test ×7, review ×7 (owner, 2026-11-20). A Deep re-verify takes 15 min to 2 h:
LD-546's took 2 h 20 min on 2026-11-20.

LD-414 (8 rounds, no finding refuted) showed why findings come out over many
rounds. At least 6 later BLOCKER and REQUIRED findings came from the previous
round's fix commits: the fix created the next finding.

**Decision.**
- A fix round does not go to `/test`. The earlier VERIFY PASS and the
  executor's test-first proof for each finding cover it. `/review` records
  **Independent verification: DEFERRED (fix round)**.
- When a round leaves no open BLOCKER or REQUIRED finding, `/test` runs once on
  that candidate, at the tier's depth. A closing review round then covers the
  commits `/test` added. It records PASS and does not count toward the round-4
  stop ([0089](0089-review-converges-in-three-rounds.md)).
- `/ship` blocks on DEFERRED.
- The review-fix executor looks for the same failure next to each fix (the
  rest of the function, its callers, code that copies the pattern) and checks
  that its own fix adds no new case of it.

**Rejected — keep /test every round.** It catches a runtime-only defect one
round earlier. It costs a full re-verify per round, and the review finds most
fix defects anyway.

**Cost.** A runtime-only defect in a fix now shows up at the final `/test`,
not in the round that made it. That can add one fix round at the end.

**Revisit if** the final `/test` after a deferred run fails on a defect a fix
round introduced, on two tickets in a row; or the round count does not drop
on the next three tickets that need review fixes.
