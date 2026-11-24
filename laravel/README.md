# Laravel quality kit (mirrored from Leadbuster)

`files/` is an exact copy of the Leadbuster quality setup at the commit in
`SOURCE.lock`. `MANIFEST` says which files are in it. Do not edit `files/` by
hand: change Leadbuster, then sync.

The copy is verbatim. It still names Leadbuster: its modules (`Core`,
`Advertisers`, `Socials`), its databases (`leadbuster_*`) and its providers.
Step 3 below lists what to rename in a new project.

## Keep it current

```bash
tools/laravel/sync.py check    # exit 1: Leadbuster main differs from files/
tools/laravel/sync.py apply    # copy from Leadbuster main, update SOURCE.lock
```

- The source is `$LEADBUSTER_DIR`, else `/var/www/html/leadbuster`.
- Only files committed on Leadbuster `main` are copied. Ticket branches and
  uncommitted edits are not.
- A new file in a watched Leadbuster folder fails `check` as `unlisted`.
  Add an `include` or a `skip` line for it to `MANIFEST`.
- After `apply`, read the README lines for the groups it names. Update them
  when the change alters what a part does.
- Commit `laravel/` with the Leadbuster commit in the message.
- A harness session warns at start when `files/` is behind.

## The parts

### static-analysis

| File | What it does |
|---|---|
| `phpstan.neon` | Larastan at level 8 with strict and deprecation rules, Pest plugin, `#[Override]` checks, Octane checks, config type checks. Every `@phpstan-ignore` needs an identifier and a reason. Includes `phpstan-baseline.neon` (not copied). |
| `phpstan.ci.neon` | CI wrapper: unmatched baseline entries do not fail, because CI boots with `.env.example`. |
| `deptrac.php` | Module × ring architecture rules. Core is the shared kernel. Modules talk only through events and notifications. Inside a module, dependencies point inward: Domain ← Model ← Ports ← Application ← entry points. Fails on uncovered classes. |
| `pint.json` | Code style rules for Pint. |
| `phpunit.xml` | Test suites and environment for Pest. |
| `qodana.yaml` | JetBrains Qodana profile. |
| `.editorconfig` | Indentation and line endings. |
| `composer.json` | Dev tools (Larastan, Deptrac, Pest with type coverage and browser plugins, Boost, strict rules) and the scripts `composer test` (→ `bin/worktree-test.sh`) and `composer deptrac`. |

### frontend-quality

| File | What it does |
|---|---|
| `package.json` | `lint`, `format`, `test`, `test:coverage`, `build` (`tsc && vite build`). |
| `eslint.config.js`, `eslint.compat.js` | ESLint flat config and its compatibility layer. |
| `.prettierrc`, `.prettierignore` | Prettier settings. |
| `tsconfig.json` | TypeScript settings that `tsc` checks in the build. |
| `vitest.config.ts` | Vitest with coverage. |

### ci

| File | What it does |
|---|---|
| `.github/workflows/ci.yml` | Jobs: Quality (pre-commit hooks on the changed files), Frontend (Vitest coverage, type check, build), Backend static (PHPStan with a cached result), Dependency audit (Composer and Yarn), Backend tests (Pest with tuned MySQL). |
| `.github/workflows/deptrac.yml` | Deptrac, plus the layer graph as an artifact. |
| `.github/workflows/gitleaks.yml` | Secret scan of the new commits only, with a pinned image. |
| `.github/dependabot.yml`, `pull_request_template.md`, `ISSUE_TEMPLATE/*` | Repository hygiene. |
| `.coderabbit.yaml` | Review instructions for CodeRabbit. |
| `bin/ci-refs.py` | Resolves the base and head commits of a run. A missing ref fails. |
| `bin/ci-quality.py` | Runs the hooks on the tree difference between two commits, force pushes included. |
| `bin/ci-report.py`, `bin/ci-pest-timings.py` | Run-page summaries: Deptrac, coverage, the ten slowest tests. |
| `tests/ci_report_test.py`, `tests/ci_tools_test.py` | Tests of those scripts. |

### hooks

| File | What it does |
|---|---|
| `.pre-commit-config.yaml` | Pint, ESLint, Prettier, a baseline check for missing classes, merge conflicts, gitleaks, actionlint, shellcheck. |
| `.githooks/pre-commit` | Git hook that runs the pinned pre-commit. |
| `bin/pre-commit.py` | Downloads and checksum-checks the pinned pre-commit release. |
| `bin/setup-quality.sh` | Installs the hooks and sets `core.hooksPath=.githooks`. |
| `bin/check-file-size.py` | File size ratchet (hook disabled in Leadbuster). |
| `tests/quality_hooks_test.py` | Tests of the hook scripts. |

### test-runner

One runner gives each checkout its own MySQL databases and each test process
its own Redis block, so worktrees can test in parallel.

| File | What it does |
|---|---|
| `bin/worktree-test.sh` | The only backend test entry point. Per-checkout databases, a shared schema template, Redis leases, parallel Pest, coverage and mutation options. |
| `bin/worktree-setup.sh`, `bin/worktree-doctor.sh`, `bin/worktree-runtime.version` | Set up a checkout's dependencies, check it is ready, and fail a checkout with an older runner. |
| `bin/schema-snapshot.php`, `bin/schema-refresh.sh` | Build and check the schema template from `database/schema/` (not copied). |
| `bin/worktree-databases.php` | Removes test databases of deleted checkouts. Dry run by default. |
| `config/database.php` | Database and Redis connections; the runner sets their `DB_*` and Redis values per checkout. |
| `.worktreeinclude` | Ignored files copied into a new worktree. |
| `tests/TestCase.php`, `tests/Pest.php`, `tests/bootstrap.php`, `tests/Support/*` | Test base class and bootstrap. `TestCase` reuses a worker database when it can repair it to the baseline a clone kept. |
| `tests/Shell/*` | Shell tests of the runner and readiness checks. |
| `tests/Unit/Worktree*Test.php`, `TestSchemaTemplateNameTest.php`, `tests/Feature/{WorktreeIsolation,WorkerDatabaseReset,TestSchemaTemplate,RedisConnectionHost}Test.php` | Tests of the isolation itself. |
| `tests/Unit/ArchitectureTest.php` | Pest architecture rules. |

### agent-docs

| File | What it does |
|---|---|
| `AGENTS.md` | Agent instructions: Boost guidelines, modules, worktrees, static analysis and CI rules. |
| `TESTING.md` | The two test layers and how the runner isolates databases and Redis. |
| `CONVENTIONS.md` | Conventions summary; the path-scoped detail is in `.ai/rules`. |
| `COMMANDS.md`, `bin/README.md` | Every command and script. |
| `REVIEW.md` | What a review reports, skips and always sends to a person. |
| `boost.json`, `.mcp.json`, `.ai/mcp/mcp.json` | Laravel Boost and MCP servers. |
| `.aiignore` | Paths agents do not read. |
| `.claude/settings.json`, `.claude/hooks/*` | Claude Code project hooks: test database cleanup at start, skill reminder. |
| `.ai/workflows/README.md` | Workflow notes. |

### agent-skills

`.ai/skills/*` and `.ai/guidelines/*` are the source. `.agents/skills/` and
`.claude/skills/` hold symlinks into them, plus a few skills of their own.
`infer-conventions` writes `.ai/rules`.

### rules-example

`.ai/rules/*` and `.ai/repo-map.md` are Leadbuster's output of the
`infer-conventions` skill. They describe Leadbuster's code. Do not copy them
into a new project: run the skill there.

## Set up a new Laravel project

1. **Dev tools.** Copy the `require-dev` set and the `test` and `deptrac`
   scripts from `composer.json`. Run `composer install`.
2. **Static analysis.** Copy `phpstan.neon`, `phpstan.ci.neon`, `pint.json`,
   `.editorconfig`. Set `paths` and `configDirectories` to the project. Run
   PHPStan and write a fresh baseline only if you must.
3. **Architecture.** Copy `deptrac.php`. Set `$modules` to the project's
   modules and check `$rings` and `$moves` against its folders.
4. **Test runner.** Copy the test-runner group. Rename `leadbuster_*`
   database names, `LB_*` variables and `/tmp/leadbuster-tests-*` paths.
   Create `database/schema/` with `bin/schema-refresh.sh`. Run
   `composer test`.
5. **Hooks.** Copy the hooks group. Run `bin/setup-quality.sh`.
6. **CI.** Copy the ci group. Change the PHP, Node and MySQL versions to the
   project's.
7. **Frontend.** Copy the frontend-quality group when the project has one.
8. **Agents.** Install Laravel Boost. Copy `.ai/skills`, `.ai/guidelines` and
   the symlinks. Adapt `AGENTS.md`, `TESTING.md` and `COMMANDS.md`. Run
   `infer-conventions` to write `.ai/rules`.
   Write `ARCHITECTURE.md` and `SECURITY.md` with the harness `project-docs`
   skill. Leadbuster's are not mirrored: they describe a private system.
9. **Check.** PHPStan, Deptrac, Pint, the hooks and `composer test` all pass
   on a clean checkout.

This order is not yet proven on a fresh project (plan Step 7).
