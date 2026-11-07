# The git-workflow-and-versioning skill is removed

**Context.** No agent preloaded `git-workflow-and-versioning`, and it never ran
by description. Usage counters and transcripts showed zero invocations since
install. Other files only cited its §Ticket trailers section, and `/ship` ran
its `scripts/base-check.sh` by path. Executors never read the commit rules they
were told to follow there. The global rules in `AGENTS.md` §3 and the
`require-commit-trailers.sh` hook already cover staging and trailers.

**Decision.**
- Delete `claude/skills/git-workflow-and-versioning/` and its Codex pointer
  `codex/skills/git-workflow-and-versioning/`.
- Move the commit-message fallback and §Ticket trailers into
  `executor-development-discipline`. Every executor preloads that skill, so the
  rules now reach the agent that commits.
- Move `base-check.sh` to `skills/code-review-and-quality/scripts/`. `/ship`
  already runs its other scripts from there.
- Repoint `/plan`, `/ship`, `test-engineer`, `figma-test-engineer`, the trailer
  hook, `harness-map.py` and `test-base-check.sh` to the new places.

**Rejected.** Preload the skill into every executor. It adds about 3k tokens to
each executor's start for rules that `AGENTS.md` §3 and the hook already
enforce.

**Cost.** The branching, release, worktree and advanced-git reference pages
are gone. Recover them from git history if a task needs them.

Supersedes the skill references in ADR 0028, 0033, 0073 and 0095.
