# The Laravel kit mirrors Leadbuster verbatim

**Context.** On 2026-11-24 the owner reworked the Leadbuster quality setup:
Deptrac, PHPStan, CI, types, coverage, `.ai/rules`, `AGENTS.md` and the test
runner. The setup has many parts that depend on each other. The owner wants a
reference in the harness for two reasons: so no part is forgotten, and so a
new Laravel project can reuse it. Leadbuster will keep changing, and the
reference must follow it. The harness is public. Leadbuster is a private
company repository.

**Decision.** `laravel/files/` is a byte-exact copy of the Leadbuster files
that `laravel/MANIFEST` lists. `tools/laravel/sync.py` copies them from the
committed Leadbuster `HEAD` and writes that commit to `laravel/SOURCE.lock`.
`sync.py check` fails when a copy differs from `HEAD`. It also fails when a
file in a watched Leadbuster folder is in no `include` or `skip` line, so a
new quality file cannot go unnoticed. A project hook in `.claude/settings.json`
warns at session start when the copy is behind. CI runs the sync test on a
fake source repository, because CI cannot read Leadbuster. CI also scans
`laravel/` with a pinned gitleaks image. `laravel/README.md` is the map: each
part, what it does, and the order to set it up in a new project. The owner
chose the verbatim public copy on 2026-11-24 and accepted that module,
database and provider names become public. The owner excluded
`SECURITY.md` and `ARCHITECTURE.md` the same day: they describe the attack
surface, deployment and roadmap of a private system. A verbatim copy keeps sync a plain
compare, with no hand-ported changes to drift.

Affected files: `laravel/`, `tools/laravel/sync.py`,
`tools/tests/test-laravel-sync.py`, `.claude/settings.json`,
`.github/workflows/ci.yml`.

**Rejected — *(sanitized templates in the public harness).*** Placeholders
instead of Leadbuster names would keep company detail private. Every
Leadbuster change would then need a hand port, and the drift check could only
say that the source changed, not that the copy is wrong. The owner declined it.

**Rejected — *(a private repository, or making the harness private).*** Both
keep company detail private with a verbatim copy. The owner declined both and
kept the kit in the public harness.

**Rejected — *(git submodule of Leadbuster).*** It would pull the whole
private application, not only the quality setup. A public clone could not
fetch it.

**Rejected — *(symlinks into the Leadbuster checkout).*** They resolve only on
a machine with that checkout at that path. CI and a fresh clone would see
broken links.

**Revisit if** company detail in `laravel/` causes a problem for the owner's
employer. Then move the kit to a private repository and purge it from this
repository's history.
