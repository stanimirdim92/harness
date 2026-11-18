# `/spec` always takes its Jira intake from the jira-ticket skill

**Context.** When no intake existed, `/spec` was told to "follow `jira-ticket`
§§1–3": fetch Jira itself, using the skill's steps as a reference. The skill
was never invoked. So the intake rules ran from a paraphrase, the intake file
of [0084](0084-each-stage-starts-in-a-fresh-context.md) was not always written, and
user-pasted ticket text could reach the spec without the skill's checks.

**Decision (owner's call, 2026-11-18).**
- Every Jira intake comes from the `jira-ticket` skill. `/spec` reuses a
  complete, current intake from the conversation or
  `docs/specs/<TICKET>-intake.md`. Otherwise it invokes the skill before recon
  or drafting.
- `/spec` does not fetch Jira itself or rebuild intake from memory. Ticket text
  the user pastes goes through the skill too, which already takes pasted
  contents as its source when Jira is unavailable.
- When `/spec` invoked it, the skill saves the intake file and returns to
  `/spec`, which continues in the same session. Run on its own, it still stops
  and recommends `/clear`, then `/spec`.

**Cost.** Intake run inside `/spec` leaves the raw Jira payloads in `/spec`'s
context. 0084 measured that at about 48k tokens on LD-380. The old inline fetch
paid the same. Running `/jira-ticket`, then `/clear`, then `/spec` stays the
cheaper path.

**Rejected — make `/spec` stop and ask for `/jira-ticket` first.** That is one
more manual step on every ticket for a saving the user can already choose.
