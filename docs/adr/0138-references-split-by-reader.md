# References split by reader

**Context.** `AGENTS.md` tells every session to read reference files whole: a
skipped section is a skipped gate. That rule is right, and it has a cost. A
pointer such as `component-response-contracts.md` §Dispositions makes the
reader load the whole file to use one section. The file stays in that
context for every later turn.

Four files were read this way:

| File | Words | What most readers used |
|---|---|---|
| `component-response-contracts.md` | 4,273 | §Dispositions (5 readers), §Review SARIF (1) |
| `plan-quality-gates.md` | 1,809 | §2 (`/build`, `/test`), §6 (`/review`, `/ship`, every session) |
| `documentation-practices.md` | 1,678 | §Project documentation (spec, plan, build, executor, recon) |
| `commands/build.md` | 3,294 | the parallel-workstream rules, off by default since ADR 0136 |

**Decision.** Move each section that a stage reads on its own into a file of
its own. The reader then loads only what it uses, and still reads it whole.

- `findings.md`: the dispositions, the `pre-existing` mark and the review
  SARIF. The four reviewers, `/review`, `/ship` and the review skill point
  here. `component-response-contracts.md` keeps its catalogue for
  maintainers and points here; no stage loads it now.
- `spec-pin.md`: the spec revision pin (was `plan-quality-gates.md` §2).
- `ticket-ledger.md`: the open-items register and `check-ledger.py` (was §6).
  `plan-quality-gates.md` keeps §1–§5 numbering, with §2 and §6 as pointers.
- `records.md`: ideas, decisions and memory. `documentation-practices.md`
  keeps project documentation only.
- `parallel-workstreams.md`: the conditions for concurrent executors.
  `build.md` keeps the sequential default and reads the file only when the
  user asks for parallel work. It is not in `worktrees.md`, because every
  worktree session reads that file.

No rule was reworded. Each moved section is the same text in a new file.

**Effect.** A file a stage reads drops from 4,273 to 482 words for each
reviewer, `/review` and `/ship`. `/test` reads 441 words in place of 1,809.
`/review` and `/ship` read 282 in place of 1,809 for the ledger. The pipeline
readers of project documentation read 583 in place of 1,678. One review round
reads about 20,000 fewer words before any later turn repeats them. These are
word counts, not measured tokens.

**Also fixed.** The contracts catalogue said thirteen hook files; there are
fifteen. Its test asserted the stale string. The test now derives the number
from the directory. It also checks that the disposition table and the SARIF
schema exist only in `findings.md`. The blind-reviewer template in the
catalogue gained the `**Findings:**` count line (ADR 0099).

**Rejected — a section-read rule.** Letting agents read only the cited section
would save the same tokens with no new files. It reverses the whole-read rule,
which exists because a skipped section is a skipped gate.

**Rejected — splitting `security-checklist.md`.** `security-auditor` uses all
of it. `repository-precedent.md` stays whole too: its §1 is most of the file.

**Revisit if.** A reader of one of the new files turns out to need a section
that stayed behind.
