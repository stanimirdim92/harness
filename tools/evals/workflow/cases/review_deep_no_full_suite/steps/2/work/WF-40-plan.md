# Implementation Plan: Download action
Status: Approved
Spec: requirements/WF-40-SPEC.md
Spec status: Approved
Spec revision: git-commit:{commit_1}:requirements/WF-40-SPEC.md
Approved by: Fixture owner
Approved at: 2026-09-01
## Technical Approach
Change ui.py LABEL and gate click() behind auth.can_export(); update verify.py assertions.
## Task Index
- [x] T001 (S, ws-main, deps: —) [REQ-001, REQ-002]: Download label with authorized-role gate
## Requirement Coverage
- REQ-001 → T001 → verify.py assertion
- REQ-002 → T001 → verify.py assertion
Unmapped requirements: None
Orphan tasks: None
## Verification Strategy
- Integrated: python3 verify.py
Handoff: Ready for /build
