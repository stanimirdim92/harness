# Owner messages do not override pipeline gates

**Context.** The 2026-11-21 command audit found one gap in every stage. The
owner sometimes cut a check or overrode a gate by message: skip the full suite
or the mutation probes in `/test`, an override GO in `/ship`, approval of a
spec or plan inside an unattended run. No rule covered it, so each agent made
up its own format. In one session the agent set `Approved` on a spec and a
plan after "run spec plan build unattended", and logged that the owner had
read neither. `claude/references/risk-tiers.md` already says that nobody can
ask for a shallower check than the tier.

**Decision.** A message in the conversation does not change a gate of `/spec`,
`/plan`, `/build`, `/test`, `/review` or `/ship`, and that includes the
owner's message. The owner chose this on 2026-11-21. A stage that gets such a
message says in one line that the gate stays, then does what the gate says.
An instruction to run unattended is not approval of a spec or a plan: the run
stops at the approval request. A pre-authorization recorded in an approved
plan stays valid, because the plan approval is its gate. To change a gate,
the owner changes the harness or the project's rules in their own commit, and
the next run follows the new text. One rule, in one place, means no agent has
to invent a format for an exception.

Affected files: `claude/AGENTS.md` §Pipeline gates. No command changes: the
commands already state their gates without an exception.

**Rejected — *(allow every override and record it).*** The stage would obey,
and write the gate, the owner's words and the date in its report and in the
ticket ledger. The owner declined it on 2026-11-21. A recorded exception is
still a check that did not run, and the record does not find the defect.

**Rejected — *(allow overrides except approval).*** It keeps unread documents
from being marked Approved, and still lets a run skip the full suite or ship
over an open finding. The owner declined it with the first alternative.

**Revisit if** a gate change is committed and then reverted for a single
ticket, twice. That would show the owner needs a one-run exception that the
harness text cannot give.
