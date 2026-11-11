# Explore runs on Haiku

**Decision.** `claude/agents/Explore.md` overrides the built-in Explore agent.
It pins `claude-haiku-5-5` at `effort: xhigh`, with Read, Grep and Glob only,
`maxTurns: 30` and `omitClaudeMd: true`. It reports every hit as
`path:line: optional summary`, grouped by question, and ends with
`Not found:`. Owner's call, 2026-11-11.

Without the file, the built-in Explore inherits the session model (Opus).
Explore only locates code, so Haiku is enough. This adds a Haiku tier to the
role tiers of
[0056](0056-role-tiered-models-blind-review-recon-width-writer-isolation.md).
`validate-frontmatter.py` checks the pin.

Haiku at xhigh can put the whole answer in thinking and return empty text.
The persona tells it to write the full report as its reply.

**Rejected — *keep the built-in Explore.*** It runs on the session model, the
most expensive tier, for a search task.

**Rejected — *Haiku at the default effort (medium).*** Explore must find every
hit. The owner chose xhigh for search depth.

**Revisit if.** Explore reports miss hits that a later Grep finds, or return
empty text.
