# Documentation Practices

How sessions document projects. Ideas, decisions and memory are separate
records with their own rules, in `records.md`; none of them should become a
copy of the project documentation.

## Project documentation

Keep project facts in the project. The global harness supplies this convention
and the `project-docs` skill; it does not require every repository to contain
the same bundle of files. Reuse equivalent existing documents and split a new
file only when its content warrants a separate home.

| Document | Responsibility | When useful |
|---|---|---|
| `ARCHITECTURE.md` | Current boundaries, important flows, stores, integrations, deployment; pointers to enforced rules | Understanding the system requires more than the README |
| `DESIGN.md` | Cohesive design rationale, with links to specific ADRs | Rationale is substantial enough to separate from architecture |
| `CONVENTIONS.md` | Navigation to project-specific coding rules and meaningful exceptions | Conventions are spread across several sources; avoid duplicating enforced rules |
| `COMMANDS.md` | Exact setup, run, check, and operational commands with prerequisites | Existing scripts/README need a navigable explanation |
| `TESTING.md` | Test layers, fixtures, environment, external boundaries, and known limitations | Running the test command alone does not explain how to verify changes |
| `SECURITY.md` | Project trust boundaries, authentication/authorization, secret handling, and control locations | The project has controls worth explaining; preserve any existing vulnerability-reporting policy |
| `.ai/repo-map.md` | Compact navigation to important entry points and owning directories | A newcomer needs a map beyond the architecture overview; avoid a full file inventory |
| `ONBOARDING.md` | From clone to a first change: prerequisites, setup, run, one test, structure, common issues | New people join often, or setup takes more than the README shows |
| `docs/api.md`, `docs/data.md` | HTTP endpoints (method, path, auth, handler) and the schema from migrations | The project has an API or database that people use without reading its code |
| `docs/adr/` | Accepted decisions and seriously considered alternatives | A durable architectural choice needs its reasoning preserved |

Small projects can keep several roles in their README. Explicit requests for a
full set are valid; keep each document evidence-based rather than filling empty
sections. A directory map, rationale, and architecture narrative should link
to one another rather than repeat the same inventory.

Read relevant sections on demand. Existing project instructions retain their
authority; descriptive docs are evidence, not permission to override a rule.
Cross-check material claims against source, configuration, and accepted ADRs.
Separate current behavior, intentional constraints, observed violations, and
future proposals. Flag stale claims and broken references with source pointers.

Maintenance follows the change:

- **Recon:** read relevant existing docs and compare them with inspected source;
  report contradictions and missing references within the surveyed area.
- **Spec/plan:** identify documents affected by the proposed behavior and carry
  updates into the owning task. Keep current-state docs describing the current
  system until implementation exists; a proposal does not make it implemented.
- **Build:** reconcile affected existing docs with the implemented result and
  verify references/commands before completion. Update only the relevant
  sections; a small code change does not require generating a document bundle.
- **Project documentation request:** use `project-docs` to generate or refresh
  the useful set from repository evidence, with gaps stated explicitly.

Do not assume a recorded command ran, a configured control is enforced in every
agent host, or a deployment blueprint is live. Verify the claimed level of
evidence. Avoid volatile version inventories where manifest/lockfile pointers
suffice; when versions matter, distinguish declared, locked, and installed.
