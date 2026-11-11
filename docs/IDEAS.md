# Ideas

The unjudged parking lot — things worth doing that haven't been decided
yet. Format and how this differs from `docs/adr/*.md` (judged, built) is
defined in `claude/references/documentation-practices.md`; don't
duplicate that explanation here.

Add freely, one line if that's all there is, but say what makes it worth
doing, not just what it is.

## Parked

- **Main-session read-size gate (the `shunt` pattern)** — **S**. Spotify's
  `shunt` plugin (`spotify/portal-ai-plugins` → `plugins/shunt/`, v0.2.0; the
  `sorantis` fork stops six days before it landed) turns "don't read big files
  inline" from a CLAUDE.md sentence into a `PreToolUse` hook: a `Read` without
  `offset`/`limit`, or `cat|head|tail|less|more`, on a file over 350 lines is
  denied with a redirect to a bulk reader. Same lesson 0044/0049/0055 applied
  here — a guarantee the config states is one the harness enforces — and the
  sentences it would enforce are still advisory:
  `claude/references/repository-precedent.md` §1 "Do not turn a
  bounded check into an inline repository survey" and `CLAUDE.md` §Session and
  context "Keep raw tool output … out of active context". The reader half is
  already the stronger one here: `repo-recon` reports `path:line` pointers
  (`agents/repo-recon.md` rule 1), which shunt's worker cannot — `bulk-read`
  streams unnumbered `cat` output and its README lists editing under "What
  doesn't get delegated". Only the forcing half is missing. Shape if adopted:
  one hook on `Read` + `Bash`, **main session only** — hook input carries
  `agent_id` inside a subagent, so every persona is exempt and recon and
  executors keep whole-file reads; `hookSpecificOutput` deny form, not shunt's
  legacy `decision`; fixtures in `tools/tests/test-hooks.sh` including the cases
  shunt's own evals get wrong (`cat f 2>/dev/null` and `cat a b c` pass its
  `>`/first-argument checks; `head -100 f` is blocked and eval #5 asserts it).
  Adopting it amends ADR 0051, which rejected size as a dispatch trigger — a
  size gate forces dispatch by size in practice. **Revisit when** the
  observation period's `run-metrics.sh` "LARGE TOOL RESULTS" section shows the
  main session repeatedly taking whole-file results over the threshold in areas
  a bounded check or recon should have covered, or 0051's own revisit clause
  fires (bounded checks expanding into inline surveys). Related: run
  `repo-recon` on a cheaper model for pure inventory questions — the cost lever
  shunt actually pulls (Gemini 2.5 Flash worker); ours is isolated context at
  the same per-token price. Source: Spotify Engineering, "Portal by Spotify cut
  my Claude Code token usage by 90%" (2026-09). The 90% is displaced
  main-context input estimated as chars/4 on an internal 162K-line Java
  monorepo; worker-side tokens and the follow-up targeted read an edit needs
  are not counted, and the committed fixtures (largest 602 lines) cannot
  reproduce the table.

- **Unattended-run prompt addition (Opus 5.5)** — **S**. It is worth doing for
  runs with nobody to answer, such as headless `claude -p` evals and scheduled
  agents. In those runs an early stop wastes the run. The Opus 5.5 guide says
  the model "is responsive to instructions that name the specific kinds of
  early stop you want it to avoid". Source:
  `platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5`,
  section "Unattended agentic runs". Conditions from the guide:
  - Add it at the end of the system prompt from the first request. A later
    addition changes `system` and invalidates earlier thinking blocks.
  - Leave it out of human-in-the-loop sessions, so not the interactive main
    session.
  - Keep a confirmation step for risky or irreversible actions.
  - Expect more tool calls and output tokens per task.

  The guide's text, verbatim:

  > A standing instruction from the user, the person you are working for. It
  > is about how your turns end. A message with no tool call in it ends your
  > turn, and the work stops there until you are asked to continue. The user
  > has seen you end turns in four ways while work they asked for was still
  > owed, and does not want any of them. One: a long summary of what was done
  > that closes by announcing the next step and has no tool call, so the next
  > thing never starts. Two: an offer to carry on with something unless the
  > user would prefer otherwise, which stops to wait for an answer the user
  > was not going to give. Three: a list of decisions for the user when, by
  > your own account, none of them blocks the rest of the work. Four: deciding
  > that this is a good place to report, because the turn has been long or a
  > milestone is done. Status notes are welcome, and so are your
  > recommendations on open decisions, but put them in the same message as
  > your next tool call and carry on with whatever does not depend on the
  > user's answer. If you notice yourself inviting the user to redirect you or
  > offering to wait, delete it and do the next thing. The stops the user does
  > want are the ones where nothing can move without them, or where the thing
  > blocking you is deliberately protected from you. This does not override
  > the need for confirmation on risky or destructive actions.

  Related, same page, section "Time signals for multiagent harnesses": a
  harness line such as `elapsed 340s / 1200s` after each message makes the
  model pace its work. Without a budget, the guide suggests one sentence:
  "Time matters here: do not spend time that can be avoided, and the earlier a
  correct result is obtained, the better." The budget is advisory, so keep a
  hard timeout.

## Considered and rejected

| Idea | Reason rejected |
|---|---|
| `repo-recon` on Haiku 5.5 (`claude-haiku-5-5`) to cut recon cost | Spec-eval on LD-380 (2026-10-11, branch `experiment/haiku-recon`) scored worse than the Sonnet 5.5 baseline. The spec's recurring misses are code-reading gaps, so the recon reader is the wrong place to save. Recon stays on Sonnet 5.5. |

- **Delta specs merged into living per-capability specs** (from
  Fission-AI/openspec): per-ticket specs become deltas
  (ADDED/MODIFIED/REMOVED/RENAMED requirements) against a living
  `docs/specs/<capability>/spec.md`, and `/ship` owns merging the delta —
  fixes specs going stale after shipping, since nothing currently owns
  updating them. The `### Requirement:`/`#### Scenario:` anchors adopted in
  0040 are the prerequisite that makes the merge mechanical. Scope: ~3
  harness edits (`spec-driven-development`, `templates/spec.md`, `ship.md`)
  plus an ADR; artifacts live per project; no new skill — fold the sync into
  `/ship`'s Documentation attestation. Open decisions before adopting:
  (a) capability taxonomy — who names/bounds capabilities (proposed default:
  `/spec` proposes the capability name, approved with the spec);
  (b) bootstrap — lazy founding, where the first delta in an area *is* the
  initial living spec (proposed default), vs backfilling from shipped specs;
  (c) merge timing — proposed default: merge is required for the
  Documentation PASS, so GO cannot be issued with an unmerged delta (before
  GO writes truth for a possible NO-GO; after GO risks the forgetting this
  cures);
  (d) concurrent tickets touching one requirement — merge in dependency
  order, re-read the living spec from disk, mirroring sequential
  integration. A delta whose implementation was withheld is never merged.
  Cost honestly: a standing per-ship obligation and a new failure mode (a
  stale merge makes the living spec lie, worse than no spec); pays off with
  repeated tickets in the same area, overhead for one-offs. See
  `docs/adr/0040-openspec-conventions-adopted.md`.
