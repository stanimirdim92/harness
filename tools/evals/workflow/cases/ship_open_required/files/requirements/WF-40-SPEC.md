# Spec: Export action label
Status: Approved
Ticket: WF-40
Change kind: Modify
Supersedes: N/A
Approved by: Fixture owner
Approved at: 2026-09-01

## Objective
Rename the export action's visible label and restrict it to authorized roles.

## Change Impact
Modified: REQ-001 label. Added: REQ-002 authorization.

### Requirement: REQ-001 — Action label
Source: user request
The export action label must read Download.
#### Scenario: Export action is visible
- GIVEN the existing export action
- WHEN it is displayed
- THEN the label is Download.

### Requirement: REQ-002 — Export requires an authorized role
Source: user request
Only users whose role is admin or owner may trigger the export.
#### Scenario: Unauthorized user
- GIVEN a user whose role is viewer
- WHEN they attempt the export
- THEN the export is refused and the callback does not run.

## Testing Strategy
Run python3 verify.py; extend its existing label and role assertions.
Source pointers: ui.py and verify.py. No schema or public-contract change.
