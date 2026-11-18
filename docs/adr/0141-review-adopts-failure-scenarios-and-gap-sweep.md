# Review adopts failure scenarios, a wider check and a gap sweep

**Context.** Two sources had review practice the harness lacked.

- The vendored `code-review-and-quality` skill had sections `code-reviewer`
  never saw, because the persona does not load the skill (ADR 0006, the
  2026-11-18 fix to its "skill wins" line). They cover tests first, dead code,
  dependency upgrades and honest reporting.
- Claude Code's built-in `/code-review` gets its quality from structure, not
  from a long prompt. Every finding carries a concrete failure scenario. Narrow
  finder angles include deleted lines and the callers of changed functions.
  Every candidate gets a verifier, and a verifier refutes only with proof from
  the code. A last finder gets the verified list and hunts only for gaps.

**Decision.**
- `code-reviewer` gains short sections on tests, dead code and dependency
  changes, and rules 9 to 12 on honest reporting. Its Correctness axis gains
  two checks: the invariant each deleted line enforced, and the callers of each
  changed function.
- `findings.md`: every BLOCKER and REQUIRED finding names a failure scenario,
  the input or state and the wrong result. Without one, a claim is ADVISORY at
  most. The `code-reviewer` and `blind-reviewer` templates gain a `Failure:`
  field. `security-auditor` and `distributed-systems-reviewer` already ask for
  one.
- `/review` §Independent check (was §Verify each BLOCKER) also checks REQUIRED
  findings at Standard depth, not only at Deep. REFUTED needs proof from the
  code. A scenario that needs realistic state, such as a race or a rare but
  reachable path, gets UNSURE.
- `/review` §Sweep for gaps: at Standard and Deep, one fresh `code-reviewer`
  gets the deduplicated finding list and returns at most 8 new `GAP-#`
  findings. It is the one packet that carries other reviewers' findings.

The built-in prompt itself is not copied. Claude Code is proprietary, and this
repository is public. The ideas are restated in the harness's own words.

**Cost.** More verifier runs at Standard, one per REQUIRED finding, and one
extra reviewer run per round 1 at Standard and Deep. Not measured yet.

**Evidence.** None for this harness. review-eval has no cases, so no reviewer
change so far could be measured. Seed it before judging this one.

**Revisit if.** The first review-eval baseline shows the sweep adds noise
without new true findings, or the REQUIRED checks cost more than they refute.
