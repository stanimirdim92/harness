# Archive

Evals the owner froze. `eval.py` does not run them. Their unit tests still run
in CI, so the code does not rot while it waits for a review.

## spec-eval

`spec-eval/` re-runs `/spec` on a shipped ticket and compares the result with
the spec the owner approved. The owner froze it on 2026-11-23 (spec HR-2,
DEC-001; ADR 0152). It moved here on 2026-11-25. The main README lists the
review date.

The real fixture `LD-380` names a private project. Git ignores it, and this
repository is public. A copy sits outside the repository:

| Item | Value |
| --- | --- |
| Copy | `~/harness-archive/spec-eval-fixtures/LD-380/` |
| Files | `intake.md`, `expectations.json`, `reference-spec.md` |
| Live path | `tools/evals/archive/spec-eval/fixtures/LD-380/` (git ignores it) |

The copy is the only backup. Git cannot restore the fixture. Never commit it.

To run the frozen tests:

```bash
cd tools/evals/archive/spec-eval
python3 test_judge.py
python3 test_produce.py
```
