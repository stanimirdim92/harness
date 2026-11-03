# Headless runners removed

**Context.** ADRs 0108, 0109, 0114 and 0115 built runners that drive the
stages without a person: `batch-fix.py` (review fixes overnight),
`pipeline.py` (`/build` → `/test` → `/review` in `claude -p` sessions) and
`ticket.py` (one ticket from intake to `/ship`, with Slack and Jira). They
needed an unattended mode in `/spec`, `/plan` and `/ship`, and a `HANDOFF:`
line at the end of every stage report (`references/stage-handoff.md`) that
only the runners read. The owner decided on 2026-11-03 to run the stages
interactively only.

**Decision.**
- `tools/run/ticket.py`, `pipeline.py` and `batch-fix.py`, their tests, the
  LD-503 fixtures and their CI steps are deleted.
- `/spec`, `/plan` and `/ship` have no unattended mode. `/spec` keeps
  deciding Low and Medium questions by default and records them as `DEC-###`
  (§Deciding by default). Only explicit human approval makes a plan Approved.
- `references/stage-handoff.md` is deleted, and no stage report ends with a
  `HANDOFF:` line. The result lines (`BUILD COMPLETE`, `VERIFY PASS`, the
  review count line, the `/ship` decision) stay.
- `/build <TICKET> review fixes` and `/build <TICKET> verify fixes` stay.
  The user starts them.
- `ticket-stats.py` drops its `run:` line. The Harness Map shows `tools/run/`
  as a table, without the runner switches and variables.
- `run-metrics.sh` stays.

This supersedes 0108 (the overnight runner only), 0109, 0114 and 0115.

**Rejected.**
- Keep the runners unused: their tests and CI steps, and the `HANDOFF:`
  contract in five commands, cost upkeep for a path nobody runs.
- Keep the `HANDOFF:` line for people: the result line already says the
  outcome, and a person reads the next step from the report.

**Cost.** No overnight or end-to-end runs. Each stage needs a person to start
it. Git history keeps the runners if this is reversed.
