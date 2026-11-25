# Spec: CSV export of users

Status: Draft
Ticket: WF-50
Change kind: Modify
Supersedes: N/A
Approved by: —
Approved at: —

## Objective
An admin downloads every user as a CSV file from the admin page.

## Requirements

### Requirement: REQ-001 — Export users as CSV
Source: WF-50 Requirements, Acceptance Criteria

When an admin selects "Export users", the system MUST download a file named users.csv with one row per user and the columns name, email and role.

#### Scenario: Archived users are included
- GIVEN one active user and one archived user
- WHEN an admin selects "Export users"
- THEN users.csv holds two rows

## Change Impact
- Changed: reports.py `users_csv` gains the role column and includes archived users.

## Testing Strategy
- `python3 verify.py`
