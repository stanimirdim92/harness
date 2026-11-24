<laravel-boost-guidelines>
=== foundation rules ===

# Laravel Boost Guidelines

## Foundational Context

This application is a Laravel application running on PHP 8.5. Always use the APIs that match the installed major version of each package — do not assume a version.

Before relying on a package's API, confirm its installed version:

- PHP packages: run `composer show --direct` to list direct dependencies with versions, or `composer show <vendor/package>` for a single package.
- JS packages: check `package.json` for the installed versions.

## Skills Activation

This project has domain-specific skills available in `**/skills/**`. You MUST activate the relevant skill whenever you work in that domain—don't wait until you're stuck.

## Conventions

- You must follow all existing code conventions used in this application. When creating or editing a file, check sibling files for the correct structure, approach, and naming.
- Use descriptive names for variables and methods. For example, `isRegisteredForDiscounts`, not `discount()`.
- Check for existing components to reuse before writing a new one.

## Verification Scripts

- Do not create verification scripts or tinker when tests cover that functionality and prove they work. Unit and feature tests are more important.

## Application Structure & Architecture

- Stick to existing directory structure; don't create new base folders without approval.
- Do not change the application's dependencies without approval.

## Frontend Bundling

- If a frontend change doesn't show in the UI or you get a "Unable to locate file in Vite manifest" error, run `yarn run build` or ask the user to run `yarn run dev` or `composer run dev`.

## Documentation Files

- You must only create documentation files if explicitly requested by the user.

=== boost rules ===

# Laravel Boost

## Tools

- Laravel Boost is an MCP server with tools designed specifically for this application. Prefer Boost tools over manual alternatives like shell commands or file reads.
- Use `database-query` to run read-only queries against the database instead of writing raw SQL in tinker.
- Use `database-schema` to inspect table structure before writing migrations or models.
- Use `get-absolute-url` to resolve the correct scheme, domain, and port for project URLs. Always use this before sharing a URL with the user.
- Use `browser-logs` to read browser logs, errors, and exceptions. Only recent logs are useful, ignore old entries.

## Searching Documentation (IMPORTANT)

- Use `search-docs` before changes that depend on Laravel ecosystem APIs, behavior, configuration, or version-specific syntax. Skip it for copy-only edits and other changes where package documentation is irrelevant. Reuse sufficient results already in context instead of searching again.
- Pass a `packages` array to scope results when you know which packages are relevant.
- Use multiple broad, topic-based queries: `['rate limiting', 'routing rate limiting', 'routing']`. Expect the most relevant results first.
- Do not add package names to queries because package info is already shared. Use `test resource table`, not `filament 4 test resource table`.

### Search Syntax

1. Use words for auto-stemmed AND logic: `rate limit` matches both "rate" AND "limit".
2. Use `"quoted phrases"` for exact position matching: `"infinite scroll"` requires adjacent words in order.
3. Combine words and phrases for mixed queries: `middleware "rate limit"`.
4. Use multiple queries for OR logic: `queries=["authentication", "middleware"]`.

## Project Rules

- This project contains committed, area-grouped rules in `.ai/rules` when that directory exists, including path-scoped framework guidelines under `.ai/rules/boost`. Before you enter plan mode or create/edit any file, you MUST first: open @.ai/rules/index.md (it maps file globs to rule files), read every rule file whose globs cover the path(s) in scope, and run `grep -rin 'keyword' .ai/rules` to catch what a path match alone misses. Do not write code until you have read and are following every matching rule. If `.ai/rules` does not exist, continue without it.

## Artisan

- Run Artisan commands directly via the command line (e.g., `php artisan route:list`). Use `php artisan list` to discover available commands and `php artisan [command] --help` to check parameters.
- Inspect routes with `php artisan route:list`. Filter with: `--method=GET`, `--name=users`, `--path=api`, `--except-vendor`, `--only-vendor`.
- Read configuration values using dot notation: `php artisan config:show app.name`, `php artisan config:show database.default`. Or read config files directly from the `config/` directory.

## Tinker

- Execute PHP in app context for debugging and testing code. Do not create models without user approval, prefer tests with factories instead. Prefer existing Artisan commands over custom tinker code.
- Always use single quotes to prevent shell expansion: `php artisan tinker --execute 'Your::code();'`
    - Double quotes for PHP strings inside: `php artisan tinker --execute 'User::where("active", true)->count();'`

=== php rules ===

# PHP

- Always use curly braces for control structures, even for single-line bodies.
- Use PHP 8 constructor property promotion: `public function __construct(public GitHub $github) { }`. Do not leave empty zero-parameter `__construct()` methods unless the constructor is private.
- Use explicit return type declarations and type hints for all method parameters: `function isAccessible(User $user, ?string $path = null): bool`
- Use TitleCase for Enum keys: `FavoritePerson`, `BestLake`, `Monthly`.
- Prefer PHPDoc blocks over inline comments. Only add inline comments for exceptionally complex logic.
- Use array shape type definitions in PHPDoc blocks.

=== inertia-laravel/core rules ===

# Inertia

- This app uses Inertia v3 with React. Pages live in `resources/js/pages`. Use `Inertia::render()` for server-side routing instead of Blade views.
- Activate `inertia-react-development` before client-side Inertia work. Use `search-docs` for version-specific Inertia APIs.

=== laravel/core rules ===

# Do Things the Laravel Way

- Use `php artisan make:` commands to create new files (i.e. migrations, controllers, models, etc.). You can list available Artisan commands using `php artisan list` and check their parameters with `php artisan [command] --help`.
- If you're creating a generic PHP class, use `php artisan make:class`.
- Pass `--no-interaction` to all Artisan commands to ensure they work without user input. You should also pass the correct `--options` to ensure correct behavior.

### Model Creation

- When creating new models, create useful factories and seeders for them too. Ask the user if they need any other things, using `php artisan make:model --help` to check the available options.

## APIs & Eloquent Resources

- For APIs, default to using Eloquent API Resources and API versioning unless existing API routes do not, then you should follow existing application convention.

## URL Generation

- When generating links to other pages, prefer named routes and the `route()` function.

## Testing

- When creating models for tests, use the factories for the models. Check if the factory has custom states that can be used before manually setting up the model.
- Faker: Use methods such as `$this->faker->word()` or `fake()->randomDigit()`. Follow existing conventions whether to use `$this->faker` or `fake()`.
- When creating tests, make use of `php artisan make:test [options] {name}` to create a feature test, and pass `--unit` to create a unit test. Most tests should be feature tests.

=== pint/core rules ===

# Laravel Pint Code Formatter

- If you have modified any PHP files, you must run `vendor/bin/pint --dirty --format agent` before finalizing changes to ensure your code matches the project's expected style.
- Do not run `vendor/bin/pint --test --format agent`, simply run `vendor/bin/pint --format agent` to fix any formatting issues.

=== pest/core rules ===

# Pest

- This project uses Pest. Create tests with `php artisan make:test --pest {name}`. Do not include the suite directory in `{name}`.
- Read the `testing-best-practices` skill for coverage, naming, structure and isolation.
- Do not delete tests or test files without approval.
- Run tests only with `composer test` and pass the narrowest selector: `composer test -- --filter=testName` or a file path. Direct `php artisan test` and `vendor/bin/pest` runs are rejected.
- Rerun a test after each change to it. After the targeted tests pass, ask the user to run the full suite with `composer test`.

=== nwidart/laravel-modules/core rules ===

# Laravel Modules

- Laravel Modules is a package for managing large Laravel applications using a modular architecture.
- Each module is an independent unit with its own controllers, models, views, routes, migrations, and configuration.
- Use `module:make ModuleName` to scaffold a new module. Modules live in the `Modules/` directory by default.
- Module namespaces follow the pattern `Modules\ModuleName` (e.g. `Modules\Blog\Http\Controllers\BlogController`).
- Always place module-specific logic inside the module directory, not in the application's `app/` folder.
- With `nwidart/laravel-actuator` installed, a module registers health indicators in the `$healthIndicators` property of its service provider. They appear as `module:{lowercase module}:{key}`. Generate one with `module:make-health-indicator`.
- With `nwidart/laravel-actuator` 1.1.0+ installed, the package also registers the read-only `modules` actuator endpoint (`GET /actuator/modules`, `GET /actuator/modules/{name}`); add `modules` to `actuator.exposure.include` to expose it.

</laravel-boost-guidelines>

# Parallel Builds & Worktrees

Run `composer test` for the full backend suite and `yarn test` for the full frontend suite.
See [TESTING.md](TESTING.md) for focused runs, coverage, mutation testing, and infrastructure tests.

The general per-ticket worktree workflow is in the global harness rules. Leadbuster adds:

- The local `leadbuster` database is a schema-only template. Never migrate, seed, truncate or write fixtures to it. Tests use per-checkout clones. Do not run migrations or writes from providers before Laravel switches to its worker database.
- `composer test` runs `bin/worktree-test.sh`. `--processes=N` sets the worker count (default: half the CPU count).
- While you work, run `composer test -- --tia`. It reruns only the tests your change affects and refreshes their graph links. Before you report completion, run the full `composer test` without `--tia`. A Tia run is not evidence that the suite passes.
- Run `composer test -- --type-coverage --compact` for PHP type coverage. This static check reads the source directories in `phpunit.xml` and needs no database or Redis.
- A full suite waits for one of three machine-wide slots (`LB_FULL_SUITE_SLOTS`) and prints "waiting for a full-suite slot". The wait is expected, not a failure. A run with a path, `--filter`, `--group`, `--testsuite` or `--mutate` never waits.
- The runner uses half the CPU count as workers, split evenly between the checkouts that run tests at the same time (it prints `workers:`). Several agents testing at once otherwise exhaust CPU and RAM. Vitest is capped at 4 workers in `vitest.config.ts`.
- Run `bin/worktree-setup.sh` in each new checkout, with `--build` when browser checks need assets. Run `bin/worktree-doctor.sh --infrastructure` before implementation or tests, and `--frontend` to check frontend readiness.
- After an intentional schema change, run `bin/schema-refresh.sh` and commit its three snapshot files together.
- Mutation testing needs the PHP `pcov` extension. Use the [mutation command in TESTING.md](TESTING.md#coverage-mutation-and-static-scans). The runner selects one worker and rejects `--everything` to preserve the class filter.
- Tests use the one shared local Redis server of `.env.testing` (loopback or Unix socket only) and the phpredis extension. Each test process leases its own block of 8 database indexes from 32 up; indexes 0-31 belong to the dev app. Use Redis in tests only through that leased block, and never `FLUSHALL`. Pub/sub and keyspace notifications are server-wide, not per index.
- Cached test configuration is forbidden. A disabled migration command returns failure outside guarded testing; it is not success.
- Before you remove a checkout, run `php bin/worktree-databases.php --checkout /absolute/checkout/path`, then repeat it with `--apply`.

# Static analysis and CI

- PHPStan: CI runs `phpstan.ci.neon` (with `.env.example`), and that run is the gate. Regenerate `phpstan-baseline.neon` only with that config, then check that `vendor/bin/phpstan analyse` also passes locally.
- Fix an error before you baseline it. Never baseline `class.notFound`; the pre-commit hook blocks it.
- Every `@phpstan-ignore` names its identifiers and gives a reason: `@phpstan-ignore id (reason)`.
- Do not run `phpstan analyse --fix-ignored`. It rewrites code: it once replaced the user that `GenerateTickerExportLinks` restores.
- Mark every overriding method and property with `#[Override]` (`use Override;`). In a test file without a namespace, write `#[\Override]` and no `use`.
- `composer test -- --type-coverage` checks type coverage. PHPStan does not.
- `composer deptrac` checks module boundaries (`deptrac.php`). Advertisers and Socials use each other only through events and notifications. Fix a new violation in the code.
- `bin/ci-report.py` writes the Deptrac and coverage summaries to the CI run page, and annotates only the changed lines.

# Design System Redesign (Figma Light)

Frontend rules are in `.ai/rules/js.md`, `css.md` and `ui.md`. Workflow and phases: `docs/tasks/REDESIGN-plan.md`. Spec: `docs/specs/DESIGN-SYSTEM-SPEC.md`. Never commit, deploy, change environment configuration or touch the database as part of redesign work.
