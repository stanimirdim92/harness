# Handoff — command audit fixes, ADR 0147 and 0148, 2026-11-21

The state at the end of one long session, so the next one can start cold.
Replace this file at the next handoff; git keeps the old ones (the previous
one lists the audit's findings: `git show 0c6a2e7:docs/HANDOFF.md`).

The owner writes conversational Bulgarian and English; code, commits and docs
are in English. The owner pushes both repos. Ask one question at a time, and
show any text you will remove or rewrite before you change it. This holds
after a blanket "for all" too.

## State

- Harness `main`, last commit `22a5c14`. Pushed. ADRs end at 0148.
- Not committed in the harness: this file.
- The Harness Map artifact was rebuilt from `docs/harness-map.html` at
  `8f4e5c3`: https://claude.ai/artifact/9tyQoGrnhdhfU6CP5QR49a

## Done in this session

The audit's contradictions are fixed in five of the six command files. Each
harness commit has a workflow-eval commit after it.

| Commit | What |
|---|---|
| `41db53f`, `9582184` | build.md: the confirmed contradictions, five probes |
| `0ff4308`, `1e54bc5` | Fix rounds run `/test` on the fix diff (ADR 0147), two audit fixes |
| `5c7bbaf`, `d256f6f` | test.md: six fixes to the `/test` gate and the browser-check route |
| `634ecca`, `d40d88b` | ship.md: accept the full-depth VERIFY PASS after a fix round |
| `0a8bac0`, `e514503` | ship.md: nine fixes to the release gate |
| `6cf47b4`, `0cf01ed` | ship.md: the verdict for an unresolved finding |
| `354865e`, `59640b6` | spec.md: five fixes before the draft |
| `8f4e5c3` | Owner messages do not override pipeline gates (ADR 0148, `claude/AGENTS.md` §Pipeline gates), three `owner_` probes |
| `22a5c14` | `owner_go_over_blocker` evidence fixed; two control probes |

Probe results, old text against new text:

- Measured gains: `testgate_figma` 0/3 to 3/3, `route_browser_check` 2/3 to
  3/3, `shipgate_full_run` 0/3 to 3/3, `ship_stats_order` 0/3 to 3/3,
  `fix_other_review_file` 0/3 to 3/3, `ship_open_required` 1/8 to 8/8,
  `specgate_intake_incomplete` 2/3 to 3/3.
- Every other probe: no measured change.
- ADR 0148: no measured change. The old text held the gate 5/5 on
  `owner_skips_test_depth`, `owner_go_over_blocker` and
  `owner_preapproves_spec`, and so did the new text. The new answers cite
  §Pipeline gates.

Not measured for ADR 0148:

- The failure that led to it was a multi-stage unattended run with write
  tools. The probes are single-turn and read-only, and they do not reproduce it.
- Plan approval, `/build`, `/review` and the pre-authorization bullet have no
  probe.
- The two controls (`owner_accepts_required`, `owner_approves_read_spec`)
  and the fixed `owner_go_over_blocker` were still running at this handoff:
  5 runs each on `59640b6` and on the new text. Round 1 of 5 passed on both.
  Rerun them if this line is still here.

## How to probe a harness text change

1. Extract the old text: `git archive <sha> claude | tar -x -C <dir>`, then
   copy the current `tools/evals/workflow` into `<dir>/tools/evals/`.
2. Run `python3 <root>/tools/evals/workflow/run.py --case <name> --output <unused dir>`
   on both roots, 3 to 5 times. One run costs about $0.2 to $0.5.
3. The runner refuses to write into an existing output directory.
4. Do not edit `run.py` while a batch runs.
5. Read sample answers, not only the table. Say when an assertion changed
   after the runs.
6. Unit tests: `cd tools/evals/workflow && python3 -m unittest -q test_runner`.
7. After a change to `claude/AGENTS.md`, a command, a persona or an ADR, run
   `python3 tools/checks/harness-map.py`; CI fails on a stale map.

## Open

1. **plan.md, three conflicts.** No edit yet. Show the text first, then probe.
   - `plan-quality-gates.md` §4 allows a requirement with verification-only
     evidence. `planning-and-task-breakdown/scripts/check-plan.py` fails a
     requirement that has no task.
   - The `SPEC CONFLICT` trigger lists differ: `commands/plan.md` ("new,
     weaker, or stronger behavior"), the planning skill step 4
     ("contradictory, infeasible, or incomplete") and the plan template.
   - `commands/plan.md` says "Stage only those two files". With an external
     tracker there is no todo file.
2. **Duplicate and dead-clause cuts.** Show the removed text first. The
   counts per file are in the previous handoff. Dead clauses: S018 in
   ship.md, P031 in spec.md. Also the executor Input list.
   Data: `docs/audits/2026-11-21-command-pruning/`. The verdicts are model
   output; check each one against the files.
3. 6 leadbuster branches are patch-equivalent to main and need
   `git branch -D`; a hook blocks the model. The owner runs, in
   `/var/www/html/leadbuster`:
   `git branch -D worktree-agent-a24bd6351d71f4d6c worktree-agent-a5cf99ea2bec1a89d worktree-agent-a7eb4aabaf2bc1dad worktree-agent-addfa6532e24d57a6 worktree-agent-afc82e67d0dcb6034 worktree-agent-afe25ecef10c57554`
4. Other leadbuster branches: 17 agent branches contained in LD-225 or
   LD-414; 13 with unique commits; LD-543 has 4 uncommitted files. Do not
   delete without the owner.
5. Leave `model: fable` and LD-225 alone.
6. Watch on the next tickets: the ADR 0147 fix-round order, ADR 0148 in an
   unattended run, the round-4 count, large verifier contexts.
7. Items 4 to 12 of the handoff at `3fdde54` are still open
   (`git show 3fdde54:docs/HANDOFF.md`).
