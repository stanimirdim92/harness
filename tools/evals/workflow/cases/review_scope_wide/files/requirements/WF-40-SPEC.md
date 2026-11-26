# Spec: Export action label
Status: Approved
Ticket: WF-40
Change kind: Modify
Supersedes: N/A
Approved by: Fixture owner
Approved at: 2026-09-01

## Objective
Rename the export action's visible label without changing its action.

## Change Impact
Modified: REQ-001 label. Preserved: existing callback behavior.

### Requirement: REQ-001 — Action label
Source: user request
The export action label must read Download.
#### Scenario: Export action is visible
- GIVEN the existing export action
- WHEN it is displayed
- THEN the label is Download.

## Testing Strategy
Run python3 verify.py; extend its existing label and callback assertions.
Source pointers: ui.py and verify.py. No schema or public-contract change.
