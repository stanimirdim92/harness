# Mutation probes are scripted, one mutant per run

**Decision.** `test-engineer` §6 runs its mutation probes from one script. The
script applies one mutant, runs the focused tests, restores the file and
checks it is clean, then moves to the next. Mutants may run in parallel in
disposable checkouts with their own test databases, never two in one
checkout. A run that fails before its tests start is not a kill. A mutation
tool's result counts only from a serial run, never from its parallel mode
(owner's call, 2026-11-15).

**Evidence.** LD-491 (2026-11-15):

- The verifier's own script probed 13 mutants: 11 killed, 2 survived (fewer
  transaction retries; a tag limit of 21 instead of 20).
- One batch with all 13 mutants would have turned red on the first kill and
  hidden both survivors.
- `pest --mutate --parallel` (plugin 4.0.1) on the same 7 classes reported
  "100%": 478 mutants in 11 s, then 1,558 in 36 s. A focused run of the same
  tests takes about 22 s, so most mutants never ran a test. One run crashed
  on "Argument list too long". The runs mutated the wrong files because they
  also passed `--everything`, which makes Pest ignore `--class`
  (`MutationTestRunner.php`); that part was a usage error.
- Serial `pest --mutate` (Pest 5.3.6, plugin 5.0.2) through leadbuster's
  `bin/worktree-test.sh --mutate`, one worker database: with unrelated tests
  it scored 0.05% (nothing falsely killed). On `PaidAdsTickerEventGenerator`
  with its 39 unit tests: 389 mutants, 282 killed, 101 survived, 6 timeouts,
  74%, in 659 s (about 1.7 s per mutant). The result is plausible, but it
  covers the whole class, not only the changed conditions.
- Pest issue [#2018](https://github.com/pestphp/pest/issues/2018) (open, plugin
  5.0.2) explains it: a mutant counts as killed when its child process exits
  non-zero for any reason. `--processes` reaches the child without
  `--parallel`, and long filters and short timeouts fail it too.

**Rejected.**
- *Apply all mutants at once and split red runs.* Most mutants are killed, so
  nearly every batch is red and the split ends at one run per mutant. Two
  mutants can also mask each other.
- *`pest --mutate --parallel` as the probe.* Its score is inflated by #2018.
- *Serial `pest --mutate` as the only probe.* It is valid but mutates whole
  classes: 389 mutants for one class, where a ticket changes a few dozen
  conditions.

**Revisit if.** Pest issue #2018 is fixed in a released `pest-plugin-mutate`,
and a parallel run on a ticket with known survivors reports those survivors
and a plausible time per mutant. Also revisit if Pest can limit mutants to
changed lines: serial runs would then replace most scripted probes.
