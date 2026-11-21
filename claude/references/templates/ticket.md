# Ticket Template

The canonical shape of an agent-ready Jira ticket. `ticket-grilling` fills it
with the tech lead and the product owner before `/jira-ticket` and `/spec`.

The ticket carries what the repository cannot reveal: business rules,
decisions, edge cases and boundaries. `/spec` finds the code facts itself.
Point at code; do not design it. Class and method layout belongs to `/plan`.

```markdown
## Problem
[Optional, when the ticket has a clear user: As a [user], I want [action], so
that [benefit].]

[Who has the problem, what happens today, why it matters. 2–4 sentences.]

## Goal
[One sentence: what is true when this ticket is done.]

## Terms
[Optional. Domain words this ticket uses in a product-specific sense.]
- [Term]: [what it means in this product]

## Scope
In:
- [Behavior that changes]

Out:
- [Related behavior that must NOT change]

## Business rules
- [A rule the code cannot tell: numbers, limits, roles, timing, ordering.]

## Examples
[Optional. Real sample data where possible, with personal data anonymized.]
- [Input or state] → [expected result]
- [Edge case input] → [expected result]

## Exact copy
[Optional. Text the user sees, word for word. The AI uses it unchanged.]
- [Where it shows, e.g. button, error message, email subject]: "[exact text]"

## Acceptance criteria
- AC1: Given [state], when [action], then [observable result].
- AC2: [At least one failure case: no permission, empty data, invalid input,
  external service down.]

## How to check it
[Optional. How a person sees the result. Never put passwords or keys here.]
- Account or tenant: [name, and where its credentials are kept]
- Environment and feature flag: [local / staging; flag name and value]
- Steps: [1. ... 2. ... → what the person sees]

## Technical pointers
[The author may leave this blank. Grilling fills each pointer and confirms it
in the repository.]
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

## Bug variant

For a bug, replace "Problem" with "Bug report". Keep every other section.
`/spec` turns the bug report into the reproduction evidence of
[the bugfix spec](bugfix-spec.md).

```markdown
## Bug report
Steps to reproduce:
1. [Exact steps or input, not paraphrased]

Expected: [What should happen]
Actual: [What happens: quoted error, measured value or screenshot]
Frequency: [Always / intermittent, with the observed rate]
Environment: [Environment, tenant, version, browser]
Evidence: [Log excerpt, query result, screenshot, error-tracker link]
Impact: [Who or what data is affected; is stored data already wrong?]

## Goal
[One sentence: what is true when the bug is fixed. It sets the scope of the
fix, for example every affected tenant or only the reported one.]
```

In a bug ticket:

- AC1 states that the steps to reproduce now give the expected result.
- One acceptance criterion names nearby behavior that must stay the same.

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
- [ ] Bug only: "Actual" is quoted or measured, not described.
- [ ] Bug only: one acceptance criterion names behavior that must stay the same.
