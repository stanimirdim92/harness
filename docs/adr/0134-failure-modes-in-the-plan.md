# The plan lists failure modes for distributed changes

**Context.** Several REQUIRED findings were design flaws, not coding slips.
The plan had already fixed the mechanism, so no executor rule could prevent
them. Each one cost a review round.

- LD-536 round 1, DIST-1: two clicks at once push the same row twice.
- LD-536 experiment, BLIND-2: the row is marked `pending` before the push and
  never rolled back, so a failed push leaves it stuck.
- LD-522: leaked slots, a lock released before `failed()`, and a requeue that
  resets a live run.

**Decision.**
- When the change would trigger `distributed-systems-reviewer`
  (`reviewer-triggers.md`), the plan carries a Failure Modes table. Each row
  is a step that can fail or run twice, its effect, the design answer, and
  the task whose test proves it.
- A row with no design answer is an open question for the owner.
- `/review` gives the table to `distributed-systems-reviewer`, which checks
  each answer against the code and names any step the table misses.

**Rejected — *a distributed-systems review of the plan.*** It adds an agent
run to every such ticket. The table puts the same question to the planner,
and the owner approves the answers with the plan.

**Revisit if.** Distributed REQUIRED findings keep coming back on tickets
whose plan has the table.
