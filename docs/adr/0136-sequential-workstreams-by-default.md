# Workstreams run sequentially by default

**Decision.** `/build` runs workstreams one after another by default. It runs
them in parallel only when the owner asks for it in that run, the plan fixes
the contract between them, their planned files do not overlap, and the
isolation conditions of [0054](0054-executor-concurrency-condition-gated-not-capped.md)
hold (owner's call, 2026-11-13). This reverses 0054's parallel default; its
conditions stay.

**Evidence.** LD-536 ran twice from the same base with the same executor
(2026-11-13):

| | Sequential | Parallel (2 workstreams) |
|---|---|---|
| Time, build + test + review | 51 min | 69 min |
| Cost | $32.74 | $53.40 |
| New REQUIRED findings | 2 | 2 |

Parallel gave no quality gain. Its overhead (child worktrees, cherry-picks,
merges) cost more than the time it saved. Sequential lets a later workstream
build on the merged code of an earlier one, which avoids copies such as
LD-521's `markDead` written four times.

**Rejected — *a size rule* (parallel when each workstream has an L task or
two M tasks).** One run per arm is too little to set a threshold. The owner
decides per run.

**Revisit if.** A ticket with large, truly independent workstreams runs in
parallel on request and shows a quality or time gain.
