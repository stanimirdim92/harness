# Ticket Template

The canonical shape of an agent-ready Jira ticket. `ticket-grilling` fills it
with the tech lead and the product owner before `/jira-ticket` and `/spec`.

The ticket carries what the repository cannot reveal: business rules,
decisions, edge cases and boundaries. `/spec` finds the code facts itself.
Point at code; do not design it. Class and method layout belongs to `/plan`.

```markdown
## Problem
[Who has the problem, what happens today, why it matters. 2–4 sentences.]

## Goal
[One sentence: what is true when this ticket is done.]

## Scope
In:
- [Behavior that changes]

Out:
- [Related behavior that must NOT change]

## Business rules
- [A rule the code cannot tell: numbers, limits, roles, timing, ordering.]

## Acceptance criteria
- AC1: Given [state], when [action], then [observable result].
- AC2: [At least one failure case: no permission, empty data, invalid input,
  external service down.]

## Technical pointers
- Entry point or closest precedent: [path::method]
- Reuse: [existing service, component or contract]
- Do not change: [public contract, table or API that others use]
- Data: [new column / migration / backfill / none]

## Decisions
- [Chose A over B, because ...]

## Open questions
- [Question] — owner: [name]
- None.

## Links
- [Figma node, parent or related tickets, API docs, thread]
```

## Definition of Ready

A ticket goes to `/jira-ticket` only when every item is true:

- [ ] The goal is one sentence.
- [ ] "Out" lists at least one item.
- [ ] Every acceptance criterion is observable and testable alone.
- [ ] At least one acceptance criterion covers a failure case.
- [ ] Every number is a number: no "fast", "a few", "large".
- [ ] No "TBD", "etc." or "same as before" without a link.
- [ ] Every technical pointer names a real path, confirmed in the repository.
- [ ] Open questions are "None.", or each one has an owner.
- [ ] One `/spec` can hold it: about 8 acceptance criteria or fewer.
