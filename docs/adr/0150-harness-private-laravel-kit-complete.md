# The harness is private; the Laravel kit mirrors the security and architecture docs

**Context.** ADR 0149 put the Leadbuster quality kit in this repository while
it was public. For that reason the owner left out `SECURITY.md` and
`ARCHITECTURE.md`. They describe the attack surface, deployment and roadmap of
a private system. On 2026-11-25 the owner made `stanimirdim92/harness`
private.

**Decision.** The repository is private. `laravel/MANIFEST` includes
`SECURITY.md` and `ARCHITECTURE.md` in the `agent-docs` group, and
`laravel/files/` mirrors them like every other file. A new project gets a
complete example of both documents, and the sync check follows them when
Leadbuster changes them. The rest of ADR 0149 stands: the verbatim copy, the
`main` ref, the drift check, the session warning and the CI secret scan. The
secret scan stays, because a private repository can still be shared or made
public again.

The commits pushed while the repository was public stay in any clone or fork
made then. None of them held Leadbuster files.

Affected files: `laravel/MANIFEST`, `laravel/README.md`,
`laravel/files/SECURITY.md`, `laravel/files/ARCHITECTURE.md`.

**Rejected — *(keep both documents out).*** That choice existed only to keep
private detail out of a public repository. The repository is private now, and
the owner asked for both documents back.

**Rejected — *(edit ADR 0149 in place).*** The ADR rule keeps a reversed
decision on record as written. This file states the change, and the index
marks 0149 as partially superseded.

**Revisit if** the repository becomes public again. Then skip both documents
and purge them from the history first.
