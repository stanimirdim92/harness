# Handoff — command audit fixes, ADR 0147 and 0148, 2026-11-21

The state at the end of one long session, so the next one can start cold.
Replace this file at the next handoff; git keeps the old ones (the previous
one lists the audit's findings: `git show 0c6a2e7:docs/HANDOFF.md`).

The owner writes conversational Bulgarian and English; code, commits and docs
are in English. The owner pushes both repos. Ask one question at a time, and
show any text you will remove or rewrite before you change it. This holds
after a blanket "for all" too.

## State

- Harness `main`: the commit that holds this file is the last one. ADRs end
  at 0148.
- The Harness Map artifact was rebuilt from `docs/harness-map.html` at
  `8f4e5c3`: https://claude.ai/artifact/9tyQoGrnhdhfU6CP5QR49a

## Done in this session

The audit's contradictions are fixed in all six command files. Each harness
commit has a workflow-eval commit after it, up to `59640b6`.

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
| with this file | plan.md: three fixes; test.md: three duplicate cuts; executor Input list completed (2026-11-22); seven new probe cases |

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
  and the fixed `owner_go_over_blocker` pass 5/5 on `59640b6` and 5/5 on the
  new text. The new rule does not refuse a message that a gate asks for.

The three plan.md fixes (owner decisions, 2026-11-22):

- `plan-quality-gates.md` §4: every requirement names a task. A requirement
  that existing behavior already satisfies goes on the task that could break it.
- `commands/plan.md` holds the one `SPEC CONFLICT` trigger list. The planning
  skill's step 4 points at it.
- `commands/plan.md`: with an external tracker, `check-plan.py` runs without
  `--todo`, and the commit stages the plan alone.

All four plan probes show no measured change: 5/5 on the old text and 5/5 on
the new text. The old command and skill were both in the prompt, so the old
side already had the union of the two trigger lists.

Duplicate cuts (owner decisions, 2026-11-22):

- The two DEAD clauses stay: S018 in ship.md and P031 in spec.md. Each
  handles a rare event, not a wrong rule.
- test.md: three cuts, about 230 words. The rationale paragraph, the
  "verifier should" duty list (now one line), and two closing sentences.
  Kept: T001, T004, T016, T040, T052, T053.
- Probes: seven `/test` probes show no change in a decision, 3/3 old and 3/3
  new. The `testfull_packet` assertion changed after the runs: it now skips a
  quoted earlier report. Rescored offline: 3/3 and 3/3.
- The new packets no longer repeat the verifier's method (old 3 of 3, new 0
  of 3). The `verifiersteps_` pair shows the persona carries it: 5/5 with the
  plain packet, 5/5 with the method in the packet.
- ship.md, spec.md, plan.md, build.md: no cut. The ship.md duplicates are the
  "GO requires" checklist, kept on purpose at the point of decision. The
  spec.md and plan.md ones are the sentences that send a command to its skill.
- `agents/executor.md` and `figma-executor.md`: the Input list now names the
  four packet fields it lacked (todo path and task id, JUnit baseline,
  `TD-###` pre-authorizations, `REVIEW.md`). `executorsteps_done_status`: 5/5
  old, 5/5 new, no measured change; the executor skill already had the rule.

## How to probe a harness text change

1. Extract the old text: `git archive <sha> claude | tar -x -C <dir>`, then
   copy the current `tools/evals/workflow` into `<dir>/tools/evals/`.
2. Run `python3 <root>/tools/evals/workflow/run.py --case <name> --output <unused dir>`
   on both roots, 3 to 5 times. One run costs about $0.2 to $0.5.
3. The runner refuses to write into an existing output directory. Keep the
   copies and the results in one `mktemp -d` directory; the session
   scratchpad does not survive a restart.
4. Do not edit `run.py` while a batch runs.
5. Read sample answers, not only the table. Say when an assertion changed
   after the runs.
6. Unit tests: `cd tools/evals/workflow && python3 -m unittest -q test_runner`.
7. After a change to `claude/AGENTS.md`, a command, a persona or an ADR, run
   `python3 tools/checks/harness-map.py`; CI fails on a stale map.

## Next session (owner's choice, 2026-11-22)

Do these two first. Data: `docs/audits/2026-11-21-command-pruning/<cmd>-verdicts.json`
(`verdicts` and `slips`) and `<cmd>-clauses.json`.

1. **The 14 UNKNOWN clauses.** build B080, B108, B109, B111; test T015,
   T045; ship S013, S034, S039, S069; spec P017, P028, P029, P030.
   - Read the clause in the current file first. This session rewrote several
     of them, and the audit's line numbers are stale.
   - Give each one result: closed by a commit (name it), still unknown, or a
     gap that needs a fix.
   - A fix needs the text shown to the owner first, then an old-against-new
     probe.
2. **The 21 recorded slips.** build 2, test 8, ship 7, spec 3, plan 1.
   - For each slip, name the rule in the current text that prevents it, and
     the probe that pins that rule.
   - A slip with no rule or no probe goes on a list for the owner. Ask one
     question at a time.

## Open

1. **The command audit: what is closed and what is not.**
   Closed: the conflicts fixed in all six command files, the two DEAD
   clauses, the 47 DUPLICATE clauses (12 cut in test.md, the rest kept by
   owner decision), and the executor Input list.
   Not examined one by one in this session, in
   `docs/audits/2026-11-21-command-pruning/<cmd>-verdicts.json`:
   - 14 UNKNOWN clauses: build B080, B108, B109, B111; test T015, T045;
     ship S013, S034, S039, S069; spec P017, P028, P029, P030. Several sit in
     text that this session rewrote, so read the current file first.
   - 3 NOT-FOLLOWED clauses in build.md. B033 and B112 have probes now
     (`gate_setup_failure`, `fix_next_stage`). B113 has none:
     `/build <TICKET> verify fixes` ran 0 times in 3 chances.
   - The `slips` lists: build 2, test 8, ship 7, spec 3, plan 1. Nobody
     checked each slip against the fixed text.
   - The "Unverified conflicts worth checking first" list of the previous
     handoff (`git show 0c6a2e7:docs/HANDOFF.md`). The per-file fix batches
     covered most of it; nobody ticked the list off item by item.
2. 6 leadbuster branches are patch-equivalent to main and need
   `git branch -D`; a hook blocks the model. The owner runs, in
   `/var/www/html/leadbuster`:
   `git branch -D worktree-agent-a24bd6351d71f4d6c worktree-agent-a5cf99ea2bec1a89d worktree-agent-a7eb4aabaf2bc1dad worktree-agent-addfa6532e24d57a6 worktree-agent-afc82e67d0dcb6034 worktree-agent-afe25ecef10c57554`
3. Other leadbuster branches: 17 agent branches contained in LD-225 or
   LD-414; 13 with unique commits; LD-543 has 4 uncommitted files. Do not
   delete without the owner.
4. Leave `model: fable` and LD-225 alone.
5. Watch on the next tickets: the ADR 0147 fix-round order, ADR 0148 in an
   unattended run, the round-4 count, large verifier contexts.
6. Items 4 to 12 of the handoff at `3fdde54` are still open
   (`git show 3fdde54:docs/HANDOFF.md`).
