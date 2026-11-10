# repo-recon runs at effort medium

**Decision.** `claude/agents/repo-recon.md` sets `effort: medium` (owner's
call, 2026-11-10). Recon only locates files and precedents and reports
pointers, so it needs less depth than the writers. The executor and
test-engineer personas keep `high` from `modelSettings` in
`claude/settings.json`. This narrows
[0063](0063-sonnet-5-5-pins-and-fable-advisor.md) for recon only.

The subagents doc says a frontmatter `effort` overrides the session effort.
It does not say how the field interacts with `modelSettings`. That precedence
is unverified.

**Rejected — *keep `high` for recon (0063).*** The owner chose `medium`.
Anthropic's guidance also starts agentic work at `medium`.

**Rejected — *lower `modelSettings` for the whole Sonnet pin.*** That would
also lower the executor and test-engineer, which write code.

**Revisit if.** Recon reports miss precedents that a later stage has to find
itself.
