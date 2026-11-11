# Compaction window raised to 400k

**Decision.** `CLAUDE_CODE_AUTO_COMPACT_WINDOW` and `autoCompactWindow` are
`400000` in `claude/settings.json` (owner's call, 2026-11-11). This reverses
the window in [0124](0124-compaction-window-200k-orchestrator-stays-1m.md).
The main session stays on `opus[1m]`, and the variable still applies to every
subagent.

In the LD-520 `/spec` run (session `259ed286`), the main session reached a
peak of 160k and compacted at 10:22. After the compaction it read the whole
31k-character spec again, and it lost context from the earlier rounds.

**Rejected — *keep 200k (0124).*** A `/spec` run with several decision rounds
reaches the 200k window and compacts mid-ticket.

**Rejected — *500k (0043).*** The owner ran 500k before and lowered it. Each
request near the top of the window carries up to 500k tokens.

**Revisit if.** Sessions often go past 300k, or the token cost per request
rises more than the compaction savings.
