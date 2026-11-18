# The incremental-implementation skill is removed

**Context.** [0039](0039-runtime-catalog-narrowed-by-observed-use.md) kept
`incremental-implementation` for explicit standalone use. Since then:

- No agent preloads it and no command routes to it. It is explicit-only
  (`disable-model-invocation`), and the only mention left was a line in
  `definition-of-done.md`.
- Its content now lives elsewhere. Slicing by verifiable behavior and the
  foundation-task rule are in `planning-and-task-breakdown`. The increment
  cycle is in `executor-development-discipline` and `test-driven-development`.
  Feature flags and rollback are in `deprecation-and-migration`.
- [0121](0121-git-workflow-skill-removed.md) removed a skill on the same
  profile: never preloaded, never invoked.

**Decision.**
- Delete `claude/skills/incremental-implementation/` and its Codex pointer.
- Move its two rules that had no other home, contract-first and risk-first,
  into `planning-and-task-breakdown` §Behavioral Tasks and Dependencies as two
  bullets. The plan is where task order is decided.
- Drop the mention in `definition-of-done.md` and `README.md`.

**Rejected — keep it for standalone use.** 0039 argued that low counters are
weak evidence. That still holds, but the skill no longer holds anything the
pipeline lacks. Keeping it means one more file to keep in step with the
skills that replaced it.

**Cost.** About 830 words of standalone guidance are gone, including the
worked examples. Recover them from git history if a task needs them.

This supersedes 0039's decision to retain this one skill.
