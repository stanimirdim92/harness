# Intake: WF-50 — CSV export of users
Fetched: 2026-11-20, by the `jira-ticket` skill.

**Coverage**
- Tickets discovered: 1. Fully read: 1 (WF-50). Partially read: 0. Unread: 0.

**Requirements**
- The admin page gets an "Export users" action that downloads a CSV file.
- The columns are name, email and role.
- The export includes archived users.

**Acceptance Criteria**
- The file is named users.csv.
- Each user is one row.

**Constraints**
- None explicitly specified.

**Design references**
- None.

**Questions for `/spec`**
- Which module owns the existing exports?

**Blockers**
- None.

**Next action:** `/clear`, then `/spec WF-50`
