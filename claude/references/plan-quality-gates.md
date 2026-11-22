# Plan Quality Gates

The plan-side counterpart to `spec-quality-gates.md`: what makes a plan
approvable, how its approval and its spec pin are recorded, and the id rules
that let `/build`, `/review` and `/ship` address the same units of work.

Requirement-id rules and the `REQ-###` chain live in `spec-quality-gates.md` §3
and are not repeated here.

## 1. Plan approval state

The plan carries its own status, for the same reason the spec does: the handoff
line records approval as prose at the bottom of one document, and prose is not
readable by a later session or a downstream gate.

| Status | Meaning | Set by |
|---|---|---|
| `Draft` | Being written, or an Open Question remains | `/plan`, on creation |
| `Approved` | The human approved this exact plan | `/plan`, only after explicit human approval |
| `Needs replan` | Approved once, then materially changed — or its spec pin went stale behaviorally | whichever stage made or discovered the change |
| `Superseded` | Replaced by a later plan for the same work | the superseding plan's `/plan` run |

- `/plan` never sets `Approved` on its own judgment, and a passing approval check
  is not approval. Record `Approved by` as the human identified themselves and
  `Approved at` as the date; never invent a name.
- A material plan change sets `Needs replan` in the same edit: a task added,
  removed or rescoped, a dependency or workstream reassignment, a changed
  decision, a changed contract, or a changed verification command. Fixing a typo
  or clarifying wording does not.
- `/build` refuses to dispatch against anything other than `Approved`.
- A task's `Status:` line (`Pending` → `Done`) is build progress, not a plan
  change: flipping it never moves the plan out of `Approved`.

## 2. Spec revision pinning

The pin rules are in `spec-pin.md`. `/plan` records the pin there; `/build`
and `/test` check it.

## 3. Id stability

Three id spaces, one owner each, none reused:

| Id | Lives in | Owner | Meaning |
|---|---|---|---|
| `REQ-###` | spec | `/spec` | A behavior the system must provide |
| `DEC-###` | spec | `/spec` | A material product/domain/contract/lifecycle decision |
| `TD-###` | plan | `/plan` | A technical decision between plausible implementations, or the owner's answer to a pre-authorized stop condition |
| `T###` | plan | `/plan` | A task |
| `CP-###` | plan | `/plan` | A checkpoint |

`TD-###` rather than `DEC-###` in the plan deliberately: the spec already owns
`DEC-###`, and one id space split across two documents makes "see DEC-002"
ambiguous exactly when someone is trying to trace a decision.

Ids are **stable after approval and never renumbered.** `/build`, `/review` and
`/ship` all address work by these ids, so renumbering silently invalidates every
report that referenced the old numbers. A task that is dropped or replaced keeps
its id and is marked superseded (`~~T003~~ superseded by T007`); the next task
takes the next unused number.

## 4. Approval checks before presenting a plan

- Every `REQ-###` maps to at least one task (`check-plan.py` fails one that
  has none). A requirement that existing behavior already satisfies goes on
  the task that could break it. That task's verification proves the behavior
  is preserved. `Unmapped requirements: None`. For a spec with a
  capability map, "every" means every requirement of the modules the plan
  covers; the remaining modules are listed under `Not yet planned`, never
  silently absent.
- **A withdrawn requirement stays in the coverage table**, marked withdrawn,
  rather than being deleted from it. Deleting the row makes a dropped
  requirement indistinguishable from one that was never specified.
- Every task carries requirement ids, under one of exactly two shapes:
  - a **delivery task** names at least one `REQ-###` — the behavior it
    delivers;
  - a **spike** names the `TD-###` it resolves *and* the `REQ-###` ids it
    unblocks, because a spike with no downstream requirement is investigation
    for its own sake.
  A task fitting neither is scope the spec never asked for.
  `Orphan tasks: None`.
- **Every risk mitigation names the task or checkpoint that performs it.** A
  mitigation with no owner is a hope, and a plan whose risk table is entirely
  hopes has not mitigated anything. This fails the approval check.
- **Every task that changes a shared surface lists its whole change surface.**
  A shared surface is a public method or interface, route, event, job, config
  key, schema or serialized shape, or anything the framework wires by
  registration (service bindings, listeners, schedules, policies). The task's
  `Files/areas likely touched` names every consumer and registration point
  found by a repository search, and `Change-surface search` records the search
  so `/build` can rerun it. A location found but deliberately left alone is
  listed as `unchanged — <reason>`. Agents rarely edit the wrong file; they miss
  files that needed editing (LoLBench, arXiv 2609.37143: on 2.4M-line systems
  agents reached only 37–65% of the files the real change touched, and a file
  list raised solve rates by 16–22 points). A surface change without a recorded
  search fails the approval check.
- Every verification command comes from repository evidence — the recon report,
  package manifests, CI config — never guessed.
- **Every external tool a task depends on is probed, not asserted.** The plan's
  External Tool Access table records the probe and its result. Read access
  does not prove write access. An unprobed dependency fails the approval check.
- In a full plan, Open Questions reads `None`; a compact plan omits the section
  when none exist. Anything about feature behavior is a `SPEC CONFLICT`, not an
  open question.

## 5. Bounded technical spikes

Some HOW questions cannot be answered read-only: whether an index supports a
query at real cardinality, whether a library behaves as documented under the
repository's configuration, which of two migration strategies holds a lock.
Leaving these as Open Questions blocks the plan; guessing hides the risk inside
an implementation task, which the planning boundary forbids.

Sanctioned instead: a spike task in the plan, executed by `/build` like any
other task.

```markdown
- [ ] T000 (S, ws-research, deps: —) [TD-002, unblocks REQ-004]: Prove whether
      the proposed index supports the target query
```

Its acceptance criteria state the evidence to produce, the comparison to run,
and the threshold that decides — not "investigate and report back". A spike:

- produces evidence and resolves a named `TD-###`; it does not change production
  behavior, and it is not a licence to start implementing;
- is gated by a checkpoint before any dependent task runs, so the decision is
  made before work is built on it;
- happens during `/build`, not during `/plan`. Planning does not investigate.

**A spike is only for technical uncertainty.** If the outcome could change what
the system must do — an acceptance criterion, a contract, a lifecycle rule —
that is a `SPEC CONFLICT` and goes back to `/spec`, however technical the
question looks. The test: could a reasonable answer to this question change a
`REQ-###`? Then it is not a spike.

## 6. Open items and the ticket ledger

The register and `check-ledger.py` are described in `ticket-ledger.md`.
