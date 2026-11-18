# Open items and the ticket ledger

The register for work the spec, plan and todo do not track, and the check that
keeps the four files in agreement. `/review` and `/ship` run the check; every
session writes to the register.

The spec, plan and todo are checked when `/spec` and `/plan` write them. Work
after that can leave them behind without any gate noticing:

- a decision added in conversation;
- a gap deferred "for /review";
- a commit made outside `/build`;
- a failing test or question known only in chat.

LD-365 lost three weeks to this (`../../docs/adr/0088-ticket-ledger-check.md`).

**The register.** `docs/tasks/[TICKET]-open.md` holds every item the other three
files do not track. Its shape is in `templates/open-items.md`. Create it with
the first item. Write an item there when it appears, not only into the chat or
a compaction summary.

- A plan or todo line that defers work ("known gap", "deferred", "follow-up",
  "for /review") names the `OPEN-###` id that tracks it.
- A commit outside `/build` that changes more than the ticket's docs gets an
  `unplanned commit` item that names its short sha. A behavior change also
  gets a `DEC-###` in the spec, and the plan goes to `Needs replan`.
- A DEC that changes an earlier DEC or a Boundaries `Never:` rule says so in an
  `Amends:` line that names the rule.

**The check.** `check-ledger.py` compares the four files, the plan's spec pin
and the branch's commits:

```bash
python3 ~/.claude/skills/spec-driven-development/scripts/check-ledger.py <TICKET>
```

`/review` runs it, and `/ship` runs it with `--ship`, which also fails on an
`Open` item and on a `Pending` task the plan index does not mark superseded.
Run it on request after any work outside the pipeline.
