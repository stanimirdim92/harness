# Handoff — review loops, test speed and machine load, 2026-11-15 to 2026-11-21

The state at the end of one long session, so the next one can start cold.
Replace this file at the next handoff; git keeps the old ones (the previous
one covers the ticket runner, 2026-10-19 to 10-20).

The owner writes conversational Bulgarian and English; code, commits and docs
are in English. The owner pushes the work repos.

## State

- Harness `main`, last commit `bbfafd7` (fix rounds skip /test, ADR 0144).
  Not pushed by this session. ADRs end at 0144.
- `docs/harness-map.html` is stale (`harness-map.py --check` fails). It was
  stale before this session's edits. Regenerate and commit it.
- leadbuster `main` has the runner and Vitest limits; last commit `6c22ea50`.
- llms `main`: `5bb991c` removed the AI Map. The map now lives only in
  `docs/ai-map.html` here.

## Decisions made in this session

| Area | Decision | Where |
|---|---|---|
| Verifier | Serves the candidate itself on `127.0.0.1`; never asks the owner for a browser check | `test-engineer` §2, `commands/test.md` |
| Verifier tools | `TaskStop` and `Monitor` granted to both verifiers | agent `tools:` |
| chrome-devtools MCP | Stays on `@latest` on purpose | `claude/mcp/setup.sh`, ADR 0070 revision |
| Mutation | Scripted, one mutant per run; a run that fails before its tests start is not a kill; a tool counts only from a serial run | ADR 0137, `test-engineer` §6 |
| Mutation scope | A whole-class tool (`--mutate`) runs only for a class the candidate adds, in place of the probes; a fix round probes only the fix; a timeout is never a kill | `test-engineer` §6 |
| Full suite | Once per verify; after a test-only commit, re-run only the changed test files, unless a shared helper, fixture or test config changed | `test-engineer` §6 |
| Review loop | A review-fix round records verification DEFERRED and skips `/test`; `/test` runs once when review has no open BLOCKER or REQUIRED, then a closing review round that does not count toward round 4; `/ship` blocks on DEFERRED | ADR 0144 |
| Review fixes | The executor checks the code next to each fix for the same failure | `commands/build.md` §Review fixes |
| Context | `autoCompactWindow` 500000 | `claude/settings.json` |

## leadbuster test infrastructure

- `bin/worktree-test.sh`:
  - A full suite takes one of three machine-wide slots (`LB_FULL_SUITE_SLOTS`, default 3, set by the owner). Focused runs (a path, `--filter`, `--group`, `--testsuite`, `--mutate`) never wait.
  - 4 workers, or 2 when another checkout holds its test lock (read from `/proc/locks`, device and inode).
  - `--mutate` runs Pest's mutation testing on one worker, with pcov. It rejects `--everything` and `--processes`.
- `vitest.config.ts`: `maxWorkers: 4`.
- `bin/worktree-doctor.sh` reports a missing pcov.
- Pest 5.3.6 and pest-plugin-mutate 5.0.2. Pest issue #2018 makes the parallel `--mutate` report false kills.
- Local MySQL drop-in `/etc/mysql/mysql.conf.d/zz-dev-speed.cnf`: `skip-log-bin`, `sync_binlog = 0`, `innodb_flush_log_at_trx_commit = 2`.
  - Creating the 127 test tables went from 9.4 s to 0.9 s.
  - One Backfill test-file run went from 17 s to 4.6 s.
  - The file is local only; another machine needs the same file.

## Evidence worth keeping

- Machine: 16 cores, 30 GB RAM.
  - 4 parallel full suites at 4 workers froze it on 2026-11-16; the owner hit reset.
  - 2 suites at 4 workers dropped free RAM below 3 GB within 86 s while other sessions ran Vitest (about 4.6 GB).
  - With 3 slots, the worst case is 4 + 2 + 2 = 8 workers. A suite picks its worker count once, when it starts.
- LD-414: 8 review rounds over 3 approaches, no finding refuted.
  - At least 6 later BLOCKER or REQUIRED findings came from the previous round's fix commits.
  - Two round-1 runs on the same code reported different sets.
- LD-546 Deep verify took 2 h 20 min:
  - `--mutate` on a class LD-538 added: 87 min, 333 of 474 mutants timed out.
  - A second full suite: 15 min.
  - ADR 0144 and the §6 rules above remove both. Nothing measures that yet.

## Open

1. **Measure** ADR 0144 and the new §6 rules on the next Deep tickets. Revisit clauses are in ADR 0144.
2. **Known gap in ADR 0144.** If the closing review round writes a SARIF, `/build`'s file count includes it toward round 4.
3. **One SARIF per ticket** (proposed, not decided). Each round appends a `runs[]` entry. The count then survives approach changes and gives a ticket-wide round cap. It touches `review.md`, `build.md`, `ship.md`, four scripts, and amends ADR 0120.
4. **Reviewer proposals from LD-414, not decided:**
   - A: a threat boundary in the spec;
   - B: a ticket-wide round cap (covered by item 3);
   - D: pre-existing findings go to a follow-up ticket by default.
5. **IDEAS.md: "Freeze approved acceptance criteria"** (from the Anthropic harness articles). Revisit only if probes show agents edit approved criteria.
6. **AI Map:** the online artifact has one item more than `docs/ai-map.html`, K33 (Stanford CME295). The owner did not answer whether to sync the repo copy.
7. **Test DB reuse between runs:** not built. It saves at most 2.3 s per run, and leftover rows could make runs flaky.
8. **LD-546:** the backfill test with a real 1 s sleep (`--sleep 1000`) belongs to that ticket's session.
9. **Not committed, other work:**
   - leadbuster `docs/tasks/LD-594-open.md` (OPEN-009 to 013, another session);
   - llms: the owner's notes, an image move, and `.air/settings.json`.
10. **Staging MySQL config** (the owner pasted it; not acted on):
    - `bind-address = 0.0.0.0`: check the firewall;
    - `innodb_flush_log_at_trx_commit=0` has a wrong comment;
    - `innodb_redo_log_capacity = 2G;` has a stray `;`;
    - `slow_query_log=8`;
    - the file sits in `mariadb.conf.d` but is a MySQL config; local is MySQL 9.7.2.
11. **Optional safety net:** `earlyoom`, which the owner would install.
12. **Unconfirmed:** whether the owner turned off the artifact setting in `settings.local.json`.
