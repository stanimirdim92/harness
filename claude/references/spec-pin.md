# Spec revision pin

How a plan records the spec revision it was planned from, and how that pin is
checked. `/plan` writes the pin; `/build`, `/test` and `check-ledger.py` check
it.

A plan is only valid against the spec it was planned from. `Status: Approved`
on the spec proves a human approved *something*; it does not prove the spec
still says what the plan assumed — a spec can be edited without its status
being updated correctly, which is exactly the case this pin catches.

**The pin must be a commit, not a loose blob.** An earlier version of this rule
used `git hash-object -w`, which writes an object no ref points at: `git prune`
deletes it, and it is never transferred by push or clone. The plan was
unverifiable on a second machine and could become unverifiable on the first
(see `../../docs/adr/0049-durable-spec-pin-and-hook-bypasses.md`).

**When planning starts**, after confirming `Status: Approved`, require the spec
to be committed with no uncommitted edits, then pin the commit that last
touched it:

```bash
git diff --quiet HEAD -- docs/specs/[TICKET]-SPEC.md \
  || echo "spec has uncommitted edits — commit it before planning"
git log -1 --format=%H -- docs/specs/[TICKET]-SPEC.md
```

Record it as `Spec revision: git-commit:<sha>:docs/specs/[TICKET]-SPEC.md`.
Requiring the commit is not extra ceremony: `spec-driven-development`'s
"Handoff after specification" already says the spec belongs in version control.

**When `/build` starts**, retrieve the pinned content and compare:

```bash
git show <sha>:docs/specs/[TICKET]-SPEC.md > /tmp/spec-pinned.md
diff /tmp/spec-pinned.md docs/specs/[TICKET]-SPEC.md
```

Identical means the plan is current; dispatch proceeds.

A **difference is not automatically a stale plan** — an editorial correction
changes the file without changing behavior, and refusing on that alone would
make the gate something people learn to bypass. Resolve it by reading the diff:

- **Editorial only** (typos, formatting, wording that changes no behavior):
  re-pin the new commit, note it, and proceed. The cheap and common path.
- **Behavioral** (a requirement, scenario, contract, invariant, boundary or
  Change Impact entry differs): stop. Set the plan `Needs replan`, and the spec
  `Needs reapproval` if its status does not already say so.
- **A `Status` line change is never editorial.** `Approved` →
  `Needs reapproval` or `Superseded` is the spec telling you the plan's
  foundation moved. Treat it as behavioral, whatever the rest of the diff says.

Report which path was taken. "The revisions differed and I proceeded" without
the diff is the failure this gate exists to prevent.

**If the sha no longer resolves** — the spec commit was rebased, squashed or
amended away — the pin cannot be checked. Do not guess: treat the plan as
`Needs replan` and re-pin against the current committed spec after confirming
with the human that the requirements did not change in the rewrite.
