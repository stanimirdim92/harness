# Spec: Export action label
Status: Approved
Ticket: WF-20
Change kind: Modify
Supersedes: N/A
Approved by: Fixture owner
Approved at: 2026-09-01

## Objective
Rename the export action's visible label without changing its action.

## Change Impact
Modified: REQ-001 label. Preserved: REQ-002 export action.

### Requirement: REQ-001 — Action label
Source: user request
The export action label must read Download.
#### Scenario: Export action is visible
- GIVEN the existing export action
- WHEN it is displayed
- THEN The label is Save.

### Requirement: REQ-002 — Preserve export behavior
Source: user request
Clicking the action retains the existing export behavior.
#### Scenario: Click the export action
- GIVEN the action is visible
- WHEN the user clicks it
- THEN the existing export callback runs exactly once.

## Testing Strategy
Run python3 verify.py; extend its existing label and callback assertions.
Source pointers: ui.py and verify.py. No architecture, schema or contract change.
