# run — tools you use during ticket work

These help while you work on tickets. They are optional: the pipeline
(intake → `/spec` → `/plan` → `/build` → `/test` → `/review` → `/ship`) works without them.

| File | What it does | Run |
| --- | --- | --- |
| `run-metrics.sh` | Reads a finished session's transcript and reports what it cost: tokens, how well tool calls were batched, large file reads, and signs of trouble. `--row` prints a line for the observation log. | `tools/run/run-metrics.sh --help` |
