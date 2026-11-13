# No cap on ADVISORY findings

**Decision.** Reviewers report every ADVISORY finding, and `/review` keeps all
of them in its report (owner's call, 2026-11-13). This removes:

- the `ADVISORY findings` row of `references/risk-tiers.md` (3 per reviewer at
  Quick, the `REVIEW.md` nit cap at Standard and Deep);
- the nit cap that [0091](0091-review-md-guides-every-reviewer.md) put in
  `references/templates/review.md` and in each reviewer's packet.

The cap was there to keep reviewers from padding reports with false
findings. A cap inside a reviewer also makes the model drop real findings
before anyone sees them. The finding standard, the confidence field and the
independent check (ADR 0092) now carry the false-finding guard.

In a before/after probe on the LD-536 diff, the uncapped `security-auditor`
reported one real ADVISORY that the capped version dropped.

**Rejected — *apply the cap in `/review` and count what it leaves out.*** It
keeps the findings visible, but it still hides them from the owner.

**Revisit if.** The owner declines or refutes many ADVISORY findings as false
(`docs/reviews/*.sarif` resolutions), or they crowd out BLOCKER and REQUIRED
findings in the reports the owner reads.
