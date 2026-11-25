# review-eval judges the defect, not only the location

**Context.** [0093](0093-review-eval-and-noise-count.md) scored a bug case
CAUGHT when any BLOCKER or REQUIRED finding pointed within 3 lines of a line
the fix later changed. The first real run, LD-585 on 2026-11-18, scored 3/3
CAUGHT. Read by hand, no finding in the `ld-585` case was about the bug: every
one was about another part of the same change. The score was false.

The same run lost its evidence. Each review ran in a temporary project that
was deleted, so only `results.json` survived. The reports had to be rebuilt
from session transcripts.

**Decision.**
- A bug case carries `defect`: regexes taken from the fix. A finding counts as
  CAUGHT only when it is near a target line and its text matches one of them.
  The text is the SARIF message, ruleId and string properties, or the report
  line in the markdown fallback.
- A finding near the lines that matches no term is LOCATED and does not count.
  A case with no terms can reach LOCATED at best, and the run says so.
- `--new --defect TERM` writes the terms. Older cases need them added to
  `case.json` by hand.
- With `--output`, every case keeps `report.md`, `meta.json` and its SARIF
  files in `<output>/<case>/`.

**Rejected — an LLM judge.** It would read meaning better than regexes, but it
adds cost and its own variance to every run. Terms written from the fix are
cheap and repeatable. Read `report.md` when a verdict looks wrong.

**Cost.** Writing two or three terms per case, from the fix commit.

Run through `eval.py` (ADR 0152): `python3 tools/evals/eval.py bugs --repo <project>`.
