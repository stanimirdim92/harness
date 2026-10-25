# Evals carry tags and a holdout split

**Context.** The harness has three evals that compare a change against a
baseline item by item: spec-eval, review-eval and plan-recall (ADR 0067,
0093, 0111). LangChain's "Better Harness" recipe (2026-04) adds two things
the evals lacked: every case carries behavior tags, so a change to one rule
gets a cheap, relevant run; and each category is split into an optimization
set, read while changing the harness, and a holdout set, never read. A
change that gains on the holdout did not fit the cases it saw. The post
reports no numbers, so it is a pattern, not evidence. The item-by-item
comparison and the list of lost cases already existed here.

**Decision.**
- A review-eval case carries `tags` and a `split` (`optimization` or
  `holdout`). `--new` takes `--tag` and `--holdout`. `--all`, `--tag` and
  `--split` select cases. The run prints a holdout line and a by-tag line.
- With a baseline, a holdout case the baseline passed and the run lost is
  WORSE, whatever the optimization cases gained. The `Review-eval:` trailer
  names the holdout count too.
- A spec-eval fixture carries `split` and `tags`; an expectation may carry
  `tags`. `--tag` judges a subset. The holdout fixture runs last; its verdict
  is the one that says a change generalizes.
- Every third or fourth new case is a holdout, from the same source as the
  rest. Cases built before this ADR count as optimization with no tags.
- Saturated cases are retired, not kept: a case every run passes for months
  measures nothing.

**Rejected.** An optimizer loop that edits prompts and tools by itself until
the score rises. The post itself guards it with a prompt and a human review
because "agents are famous cheaters". Here every rule change is a commit with
an ADR and a rescore (ADR 0111); that is the stricter version of the same
gate, at the cost of speed.

**Cost.** None at run time: the fields are read from the case files. A holdout
run is the same price per case as any other.
