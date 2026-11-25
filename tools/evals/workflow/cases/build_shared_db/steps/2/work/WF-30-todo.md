## T001: Download label
**Requirements:** REQ-001
**Acceptance criteria:**
- [ ] Label is Download.
**Verification:** bash tests/run.sh
**Dependencies:** None
**Workstream:** ws-label
**Context pointers:** ui.py, verify.py, AGENTS.md
**Files/areas likely touched:** ui.py, verify.py
**Estimated scope:** S

## T002: Export summary
**Requirements:** REQ-002
**Acceptance criteria:**
- [ ] summarize([{"amount": 2}, {"amount": 3}]) returns count 2, total 5.
**Verification:** bash tests/run.sh
**Dependencies:** None
**Workstream:** ws-report
**Context pointers:** AGENTS.md
**Files/areas likely touched:** report.py, verify_report.py
**Estimated scope:** S
