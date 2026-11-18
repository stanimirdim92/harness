# Claude Code's built-in `/code-review` runs in `/review` as a trial reviewer

**Context.** Claude Code ships a `/code-review` skill. It runs narrow finder
angles as agents, checks every candidate with a verifier, and at higher
effort sweeps for gaps (ADR 0141). The owner wants to test it against the
harness's own reviewers on real tickets. Copying its prompt into this public
repository is not an option, but invoking it is.

**Decision (owner's call, 2026-11-18).**
- In round 1, `/review` invokes the built-in `/code-review` in its own session,
  right after it dispatches the personas and before it reads their reports.
- The effort level follows the depth: Quick `medium`, Standard `high`, Deep
  `xhigh`. It never gets `--fix`, `--comment` or `max`, and its offer to run
  `/verify` is declined, because `/test` already ran.
- Its findings become `CR-#` and get dispositions from `findings.md`. Then they
  go through the same grouping, independent check and gap sweep as the rest.
- The report states the range it reviewed and one overlap line: findings only
  it raised, findings a persona also raised, and persona findings it missed.
- Codex has no such skill and records it as not available. Later rounds skip
  it, because it cannot review a fix diff alone.

**Cost.** Unmeasured. At `high` it runs about eight finder agents and one
verifier per candidate, on top of the personas.

**Rejected — run it in a subagent.** A subagent cannot start agents, so the
skill would fall back to its single-pass mode and the test would not show its
real behavior.

**Revisit after** about five reviewed tickets. Read the overlap lines. If it
seldom finds anything alone, remove it. If the personas seldom find what it
misses, consider making it a standing reviewer and cutting a persona.
