# Intake: WF-50 — CSV export of users
Fetched: 2026-11-20, by the `jira-ticket` skill.

**Coverage**
- Tickets discovered: 2. Fully read: 1 (WF-50). Partially read: 0. Unread: 1 (WF-52, a child ticket titled "Export audit log"; retrieval failed with HTTP 403). Intake is incomplete.

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
- WF-52 could not be read (HTTP 403). Its requirements are unknown.

**Next action:** `/clear`, then `/spec WF-50`
