# The executor searches before it adds, and checks its own diff

**Context.** Reviews of eight leadbuster tickets keep finding the same three
kinds of defect after `/build`:

- logic copied instead of reused: `markDead` four times (LD-521 BLIND-11),
  two URL normalizers (BLIND-6), a duplicated resolver (LD-479 CR-1), a
  hand-copied config value (LD-536 CODE-12);
- comments with a false reason, or with review ids (LD-522 R3-2, R3-3,
  CODE-11; LD-521 BLIND-25);
- project rules missed: `DB::transaction`, a FormRequest rule, EN fallbacks,
  `lb-*` tokens.

The executor ran Sonnet 5.5 at the session effort, `medium` (ADR 0066). Its
only reuse rule covered reuse the plan already claimed.

**Decision.**
- `executor-development-discipline` adds §Search Before You Add, §Comments
  and §Check Your Diff Before Handoff. The completion evidence lists each new
  function with the code searched for it, and what the diff check fixed.
- `/build` puts the base branch's `REVIEW.md` path in every executor packet.
- `executor` and `figma-executor` declare `effort: high` (owner's call,
  2026-11-13).

**Rejected — *Opus 5.5 for the executor.*** It costs more per token. Measure
`high` effort and the new rules first.

**Rejected — *`xhigh` effort.*** Slower and costlier per turn, with no
measurement yet.

**Revisit if.** The next three tickets' reviews still show copied logic or
false comments. Then try Opus 5.5 for the executor.
