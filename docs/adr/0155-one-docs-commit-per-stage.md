# One docs commit per stage

**Context.** On 2026-11-26 the owner asked to lower the number of commits.
About 40% of the commits on recent ticket branches change only the ticket's
docs:

| Branch | Commits | `docs:` | `review:` |
|---|---|---|---|
| LD-666 | 88 | 27 | 6 |
| LD-567 | 54 | 26 | 4 |
| LD-598 | 44 | 18 | 5 |

Most of them record one owner ruling or one ledger item each, for example
"record the owner choices for the round 1 review fixes". No rule asked for
that. `/spec` and `/review` said "commit … alone". `check-ledger.py` also
listed every SARIF commit as a commit with no task id. The fix for that
warning was one more ledger item and one more commit.

**Decision.**
- A stage commits the ticket's docs once, at its end, before it reports
  (`ticket-ledger.md`, **Commits**). Do not commit each ruling on its own.
- A ruling recorded between stages waits for the next stage's docs commit.
  When that stage needs a clean tree first, it commits the waiting docs in
  one commit.
- `/spec` commits the spec with the ticket's other uncommitted docs.
  `/review` commits the SARIF file with the round's ledger and spec changes.
- `check-ledger.py` does not list a commit that changes only
  `docs/reviews/<TICKET>.sarif` and the ticket's docs.
- Code and test commits do not change.

Affected files: `claude/references/ticket-ledger.md`,
`claude/commands/spec.md`, `claude/commands/review.md` §4,
`claude/skills/spec-driven-development/scripts/check-ledger.py` and its test.

**Rejected — *(squash docs commits at /release).*** History while working
stays as long as today, and a squash rewrites commits that may be pushed.

**Rejected — *(one commit per task instead of per test-first slice).*** It
cuts code commits too, but a failed slice gets harder to bisect.

**Cost.** One docs commit holds more than one ruling, so `git log` shows less
about each one. The open-items file still records each ruling and its date.

**Revisit if** an uncommitted ruling is lost between stages, or a stage
blocks on a dirty tree that holds only waiting docs.
