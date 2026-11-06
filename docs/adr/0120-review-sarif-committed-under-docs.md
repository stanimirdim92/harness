# Review SARIF committed under docs/reviews

**Context.** `/review` wrote its SARIF file to
`<git-common-dir>/review/<TICKET>-<sha>.sarif`, outside the working tree and
never committed (ADR 0093). The file was hard to find, was lost with a fresh
clone, and needed a copy step because the Write tool refuses the git directory
in a worktree. The spec and the plan already live in `docs/` and are committed.
The owner decided on 2026-11-04 to keep the review findings there too.

**Decision.**
- `/review` writes `docs/reviews/<TICKET>-<sha>.sarif` and commits it alone.
  The sha in the name is the reviewed commit, the one before the SARIF commit.
- A commit that changes only `docs/reviews/<TICKET>-*.sarif` or
  `docs/tasks/<TICKET>-open.md` after review leaves the reviewed code
  unchanged. `/ship` reports it as a ledger-only commit, and
  `/build <TICKET> review fixes` accepts it.
- `/ship` commits the resolutions it writes into the file.
- Reviewers get every diff without `docs/reviews/`.
- `review-noise.py` and `ticket-stats.py` read `docs/reviews/` by default.

**Rejected.**
- `docs/reviews/` and gitignored: easy to open, but lost with a fresh clone
  or a removed worktree, and every project needs the ignore rule.
- Keep the git directory: the reasons in Context.

**Cost.** Each review round and each `/ship` adds a commit to the ticket
branch. Files already in `<git-common-dir>/review/` stay there. Copy them to
`docs/reviews/` to keep their history in `review-noise.py`.
