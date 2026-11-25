# Spec: Export label and summary
Status: Approved
Ticket: WF-30
Change kind: Modify
Supersedes: N/A
Approved by: Fixture owner
Approved at: 2026-09-01

## Objective
Rename the export label and add a pure export summary; the two are independent.

## Change Impact
Modified: REQ-001 label. Added: REQ-002 summary.

### Requirement: REQ-001 — Action label
Source: user request
The export action label must read Download.
#### Scenario: Export action is visible
- GIVEN the existing export action
- WHEN it is displayed
- THEN the label is Download.

### Requirement: REQ-002 — Export summary
Source: user request
summarize(rows) returns the row count and the sum of the amount column.
#### Scenario: Two rows
- GIVEN rows with amounts 2 and 3
- WHEN summarized
- THEN the result is count 2, total 5.

## Testing Strategy
Run the repository verification command named in AGENTS.md after each task.
Source pointers: ui.py, verify.py, AGENTS.md. No schema or public-contract change.
