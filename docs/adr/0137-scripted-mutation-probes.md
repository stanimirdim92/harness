# Mutation probes are scripted, one mutant per run

**Decision.** `test-engineer` §6 runs its mutation probes from one script. The
script applies one mutant, runs the focused tests, restores the file and
checks it is clean, then moves to the next. Mutants may run in parallel in
disposable checkouts with their own test databases, never two in one
checkout. A run that fails before its tests start is not a kill. A mutation
tool's score is not evidence (owner's call, 2026-11-15).

**Evidence.** LD-491 (2026-11-15):

- The verifier's own script probed 13 mutants: 11 killed, 2 survived (fewer
  transaction retries; a tag limit of 21 instead of 20).
- One batch with all 13 mutants would have turned red on the first kill and
  hidden both survivors.
- `pest --mutate` (plugin 4.0.1) on the same 7 classes reported "100%" four
  times: 478 mutants in 11 s, then 1,558 in 36 s. It ignored `--class`, and
  one run crashed on "Argument list too long". A focused run of the same
  tests takes about 22 s, so most mutants never ran a test.
- Pest issue [#2018](https://github.com/pestphp/pest/issues/2018) (open, plugin
  5.0.2) explains it: a mutant counts as killed when its child process exits
  non-zero for any reason. `--processes` reaches the child without
  `--parallel`, and long filters and short timeouts fail it too.

**Rejected.**
- *Apply all mutants at once and split red runs.* Most mutants are killed, so
  nearly every batch is red and the split ends at one run per mutant. Two
  mutants can also mask each other.
- *`pest --mutate --parallel` as the probe.* Its score is inflated by #2018,
  and it mutates whole classes, not only the changed conditions.

**Revisit if.** Pest issue #2018 is fixed in a released `pest-plugin-mutate`,
and a run on a ticket with known survivors reports those survivors and a
plausible time per mutant.
