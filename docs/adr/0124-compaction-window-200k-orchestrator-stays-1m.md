# Compaction window back to 200k; the orchestrator stays on opus[1m]

**Decision.** `CLAUDE_CODE_AUTO_COMPACT_WINDOW` is `200000` in
`claude/settings.json`. Commit `b78366c` made this change, and the owner kept
it (2026-11-10). This entry reverses only the window half of
[0043](0043-automatic-memory-and-compaction-window-restored.md). Automatic
memory stays on.

The main session model stays `opus[1m]`. The model keeps its 1M context. The
session compacts at 200k, so each request carries less context.

The variable also applies to every subagent. It overrides the frontmatter
field `autoCompactWindow`
(https://code.claude.com/docs/en/sub-agents). The `opus[1m]` reviewers
therefore compact at 200k too. That cost is accepted here.

**Rejected — *keep 500k (0043).*** The owner chose 200k after running 500k.
A long session at 500k carries up to 500k tokens on every request.

**Rejected — *drop the orchestrator to a 200k-context model.*** The owner
chose to keep `opus[1m]` for the main session.

**Revisit if.** Reviewers hit the 200k compaction during one review. Then
set a larger `autoCompactWindow` in the reviewer agent files. That field
works only after this variable is removed from `env`.
