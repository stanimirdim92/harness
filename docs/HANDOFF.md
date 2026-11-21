# Handoff — command pruning audit, SARIF per ticket, 2026-11-21

The state at the end of one long session, so the next one can start cold.
Replace this file at the next handoff; git keeps the old ones (the previous
one covers review loops, test speed and machine load, 2026-11-15 to 11-21).

The owner writes conversational Bulgarian and English; code, commits and docs
are in English. The owner pushes both repos. Ask one question at a time, and
show any text you will remove before you delete it.

## State

- Harness `main`, last commit `0379f20`. Not pushed. ADRs end at 0146.
- leadbuster `main`, last commit `07965b64`. Not pushed by this session.
- Not committed in the harness: this file and `docs/audits/2026-11-21-command-pruning/`.

## Done in this session

| Commit | What |
|---|---|
| `f9d426d` | Ticket template: bug variant, terms, examples, exact copy, how to check it; grilling loads on drafts |
| `28f7581` | Step-by-step example before spec approval; pre-existing findings go to follow-ups; verifiers never run two full suites at once |
| `8a82692` | `claude/settings.json`: built-in `/code-review` may run with the reviewers |
| `5463712` | `review.md`: two contradictions fixed; reviewer packets defined once, in `/review` §3 |
| `c4931ed`, `021c11c` | One review SARIF per ticket (ADR 0145): `review-sarif.py`, round count per approach, Prettier after each write |
| `0379f20` | `/explain` removed (ADR 0146) |
| leadbuster `9c88e91e` | 60 per-round SARIF files merged into 18 `docs/reviews/<TICKET>.sarif` |

leadbuster cleanup: 6 merged worktrees and 11 merged branches removed.

## Main task: the command pruning audit

Goal: keep or raise quality while removing text that agents do not need. Each
clause of the six command files got one verdict from the leadbuster
transcripts. Labels: USED, NOT-FOLLOWED, RARE-NEEDED, DUPLICATE, DEAD, UNKNOWN.

Data: `docs/audits/2026-11-21-command-pruning/`.

- `<cmd>-clauses.json`: the clause ids and their text.
- `<cmd>-verdicts.json`: `verdicts`, `conflicts` and `slips`, with session ids
  as evidence.
- The transcripts live in `~/.claude/projects/-var-www-html-leadbuster*`.

`review.md` was the pilot and is fixed (`5463712`). The other five:

| File | Duplicate words | Dead clauses | Conflicts confirmed / reported |
|---|---|---|---|
| build.md | 25 | 0 | 2 / 9 |
| test.md | 321 | 0 | 1 (+1 wording only) / 10 |
| ship.md | about 100 | 1 (S018, 80 words) | 2 / 12, #9 refuted |
| spec.md | 311 | 1 (P031, 32 words) | 3 (+1 plausible) / 6 |
| plan.md | 166 | 0 | 1 / 3 |

Main finding: the contradictions cause the slips; the duplicates mostly do
not. The subagents' claims are model output. Verify each one against the
files before you edit.

### Confirmed conflicts (checked against the files)

1. **build.md `Task:` trailer.** `build.md:372-373` requires `Task: CODE-2`
   on review-fix commits. `executor-development-discipline/SKILL.md:140,160-161`
   and `hooks/require-commit-trailers.sh:13-14` say to leave it out.
2. **build.md blocked finding.** `build.md:378-380` reports a blocked finding
   under BUILD COMPLETE. `build.md:316-317` forbids COMPLETE with open blockers.
3. **test.md surviving mutant.** `test.md:193-195` accepts "a stated reason
   why no test can". `test-engineer.md:235-237` only accepts a killing test.
4. **test.md production fix (wording).** `test.md:226-227` says a fix
   invalidates VERIFY. It does not name the ADR 0144 deferral in
   `review.md:63-70`.
5. **ship.md pre-existing BLOCKER.** `ship.md:153` says NO-GO without a tracked
   follow-up. `findings.md:28` says it never blocks.
6. **ship.md stats order.** `ship.md:59-73` runs `ticket-stats.py` before
   `ship.md:155-166` writes resolutions, so the row shows "0 fixed".
7. **plan verification-only requirements.** `plan-quality-gates.md:62-65`
   allows them. `check-plan.py:139-141` fails any requirement without a task.
8. **spec rerun line.** A decision brief ends with the `decisions:` line
   (`spec.md:43-44`), which "revises the same spec in place"
   (`spec.md:112-113`). No spec exists yet at that point.
9. **spec Figma tools (minor).** `spec.md:26-27` names two tools and says no
   code is generated. `spec.md:31-32` adds `get_design_context`.
10. **spec defaults (plausible).** `spec.md:75-76` lets precedent settle a
    question. `spec-quality-gates.md:22-23` says precedent may not weaken
    requested behavior.

Refuted: ship conflict 9 (a dead end when `/test` adds no commits).
`review.md:68-70` runs the closing round with no commits.

### Unverified conflicts worth checking first

- build: `target-selection.md:39-41` lacks the ADR 0144 exception; the
  spec-pin steps in `build.md:35-42` leave out "Needs reapproval"; the
  argument hint omits verify-fix mode, and that mode never ran through `/build`.
- test: mutation scope in a fix round; browser-check findings go to `/test` at
  once or after convergence; a Figma mismatch is "fix" in the skill but VERIFY
  FAIL in `/test`; the packet list in `test.md:66-74` drifted from `test-engineer.md`.
- ship: production-fix order (`/test` or `/review` first); who writes
  `answered`; no verdict for `STALE (depth)`; the template leaves out the
  shared-test option.
- spec: when to record a DEC, and where `Decided by:` goes; which intake
  blocker stops and which gets a decision brief.

### Gap across files: owner overrides

The owner often cuts checks or overrides gates by message:

- in /test, skipping the full suite or the mutation probes;
- in /ship, an override GO;
- in /spec and /plan, approval inside an unattended run.

No rule covers this, so every agent makes up its own format.
`risk-tiers.md:37` says nobody can ask for a shallower check. This needs an
owner decision.

### Proposed order (the owner has not chosen yet)

1. The confirmed contradictions, one file at a time, starting with build.md.
2. A rule for owner overrides (owner decision first).
3. The duplicate and dead-clause cuts, with removed text shown first.

## Open

1. Apply the audit fixes above, one owner decision at a time.
2. 6 leadbuster branches are patch-equivalent to main and need
   `git branch -D`; a hook blocks the model from running it. The owner runs,
   in `/var/www/html/leadbuster`:
   `git branch -D worktree-agent-a24bd6351d71f4d6c worktree-agent-a5cf99ea2bec1a89d worktree-agent-a7eb4aabaf2bc1dad worktree-agent-addfa6532e24d57a6 worktree-agent-afc82e67d0dcb6034 worktree-agent-afe25ecef10c57554`
3. leadbuster branches that are left: 17 agent branches contained in LD-225 or
   LD-414; 13 with unique commits (atomlock, `exp/LD-536-par`, `exp/LD-536-seq`,
   10 agent branches); LD-543 has 4 uncommitted files. Do not delete without
   the owner.
4. Leave `model: fable` and LD-225 alone. The owner will set fable to
   `opus[1m]` later.
5. Watch on the next tickets: ADR 0144 and 0145 behavior, the round-4 count,
   large verifier contexts, overlapping mutation runs.
6. Items 4 to 12 of the previous handoff (`git show 3fdde54:docs/HANDOFF.md`)
   are still open. Item 2 there is closed by ADR 0145, and item 3 is done.
