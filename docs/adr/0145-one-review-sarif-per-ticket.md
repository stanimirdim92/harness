# One review SARIF per ticket

**Decision.** `/review` appends each round to one file per ticket,
`docs/reviews/<TICKET>.sarif`, instead of writing `<TICKET>-<sha>.sarif` per
round ([0120](0120-review-sarif-committed-under-docs.md)). Each round
adds one run per reviewer. Every run carries `round`, `approach`,
`reviewedCommit` and `closing` in its `properties`, and a distinct
`automationDetails.id`. The round-4 stop
([0089](0089-review-converges-in-three-rounds.md)) counts the rounds that are
not closing rounds and belong to the current approach, the highest one in the
file. A new approach restarts the count and keeps the earlier rounds in the
file; this per-approach reset is the owner's choice (2026-11-21).

A helper, `claude/skills/code-review-and-quality/scripts/review-sarif.py`,
does every read and write: `round`, `add`, `latest`, `resolve` and `merge`.
No command loads the file whole: a merged LD-546 file is 240 KB. `merge`
folds a ticket's old per-round files in, ordered by when each reviewed commit
was made. The add commit cannot order them: one commit moved 17 old files at
once. Every other command refuses to run while old files exist, so a ticket
on an old branch cannot restart at round 1 without notice. Leadbuster tickets
migrate one at a time, on their next `/review`. `review-noise.py` and
`ticket-stats.py` read both formats.

The reasons, from leadbuster on 2026-11-21:
- 60 review files for 18 tickets, up to 7 for one ticket.
- The file count put the closing round after `/test` toward round 4, the
  known gap in [0144](0144-fix-rounds-skip-test-until-review-converges.md).
  `add --closing` closes it.
- A new approach deleted the old files, so the history was lost.
- 26 of 1,005 finding ids repeat across rounds of one ticket, so `resolve`
  writes the newest round that holds the id, or the one `--round` names.

The merge was proved on a clone of leadbuster. `review-noise.py --json`,
`review-noise.py --repeats` and `ticket-stats.py` gave the same totals before
and after it.

**Rejected — *keep one file per round (ADR 0120).*** It keeps the closing-round
gap and the clutter, and a round count that depends on deleting files.

**Rejected — *a ticket-wide round cap.*** It would stop LD-414-style runs (8
rounds over 3 approaches), but it forces an override on every legitimate new
approach. The owner chose the per-approach reset; the file still shows the
ticket-wide total.

**Rejected — *per-round files in a per-ticket folder.*** Fewer files at the
top level, but the same count by files and the same gap.

**Revisit if** a code-scanning tool rejects several runs of one tool in one
file, or a ticket passes 8 rounds across approaches.
