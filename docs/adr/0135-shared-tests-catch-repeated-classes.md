# Shared tests catch repeated finding classes before review

**Context.** `review-noise.py --repeats` on leadbuster lists
`loose-input-validation` in 6 tickets. A bad route id that returns a 500
instead of a 4xx was found in LD-495, LD-522 and the LD-536 experiment. Each
time it cost a review round. [0105](0105-repeated-findings-fixed-at-the-source.md)
offered a lint rule, a REVIEW.md line or a CLAUDE.md line. A REVIEW.md line
still waits for review, and a CLAUDE.md line is a request, not a check.

**Decision.** A shared test the project's suite runs is the second choice in
the fix-at-the-source order, after a lint rule: a dataset every new
endpoint's test uses, or an architecture test. `/build` runs it, so the class
fails at build, not at review. `/ship` proposes it with the file and the first
use; the owner accepts or declines, as in 0105.

**Rejected — *a REVIEW.md line only.*** The class reaches review, and a fix
round, before anything catches it.

**Revisit if.** A class with a shared test still reaches review.
