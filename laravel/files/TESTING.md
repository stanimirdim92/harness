# Testing

Leadbuster has two test layers. Run each from the checkout root.

| Layer    | Command         | Runs                                          |
| -------- | --------------- | --------------------------------------------- |
| Backend  | `composer test` | All Pest tests in the Unit and Feature suites |
| Frontend | `yarn test`     | All Vitest tests under `resources/js`         |

Run `bin/worktree-setup.sh` once in each new checkout first.

## Backend command reference

Always use `composer test`. It calls `bin/worktree-test.sh`. Put Pest options after Composer's `--`.
`tests/bootstrap.php` rejects direct `vendor/bin/pest` and `php artisan test` runs.

### Select tests

```bash
composer test                                   # whole suite, workers: half the CPU count
composer test -- --compact                      # whole suite, print failures only
composer test -- --testsuite=Unit               # one suite (Unit or Feature)
composer test -- tests/Feature/Core/UserInvitationAcceptanceTest.php     # one file
composer test -- tests/Unit/Modules/Advertisers/Services/DataQuality     # one directory
composer test -- --filter='rejects malformed localities'                 # tests whose name matches
composer test -- tests/Unit/Modules/Advertisers/Services/DataQuality/LocationNormalizerTest.php --filter='rejects malformed localities'
composer test -- --group=concurrency            # one group
composer test -- tests/Unit/ArchitectureTest.php                         # architecture rules
```

A run accepts one path. To run several files, run the command once per file or use `--filter`.

### Workers, CI mode and speed

```bash
composer test -- --processes=1 --compact        # one worker (default: half the CPU count, split between concurrent runs)
composer test -- --ci                           # CI mode: ignores a stray ->only() and runs every test
composer test -- --tia                          # test impact analysis: run only tests affected by changes
composer test -- --update-shards                # record class timings in tests/.pest/shards.json
composer test -- --shard=1/2                    # run one time-balanced part of the suite
```

### Coverage, mutation and static scans

```bash
composer test -- --type-coverage --compact --min=90   # PHP type coverage, fails below 90%, no database needed
composer test -- --coverage-text=/tmp/leadbuster-backend-coverage.txt    # line coverage (needs PCOV or Xdebug)
composer test -- --coverage-text=/tmp/lb-cov.txt tests/Unit/Modules/Core/WebsiteUrlsTest.php   # per-class line coverage of one test file
composer test -- --mutate --covered-only --no-cache tests/Unit/Modules/Core/WebsiteUrlsTest.php
composer test -- --mutate --covered-only --no-cache \
  --class='Modules\Advertisers\Services\DataQuality\LocationNormalizer' \
  tests/Unit/Modules/Advertisers/Services/DataQuality/LocationNormalizerTest.php
composer test -- --profanity --compact --exclude=sheet,bbc              # profanity scan of the source
```

### Browser tests

`tests/Browser/` holds real-browser smoke tests (Pest browser plugin and Playwright). They are a separate suite: `composer test` without `--testsuite=Browser` does not run them.

```bash
corepack yarn playwright install chromium       # once per machine
yarn build                                      # the tests load public/build
composer test -- --testsuite=Browser            # run the browser tests
```

A failing browser test saves a screenshot to `tests/Browser/Screenshots/` (git-ignored). `assertNoSmoke()` fails on `console.log` output and uncaught JavaScript errors. It does not see `console.error`.

CI line coverage writes HTML, Clover and text reports:

```bash
composer test -- --ci --processes=2 --colors=never \
  --coverage-clover=test-results/coverage/backend/clover.xml \
  --coverage-html=test-results/coverage/backend/html \
  --coverage-text=test-results/coverage/backend/summary.txt --only-summary-for-coverage-text
```

### Notes on each check

- **Architecture tests** (`tests/Unit/ArchitectureTest.php`, `tests/Unit/Modules/Socials/SocialsDataArchitectureTest.php`) enforce Pest's `php` and `security` presets and `declare(strict_types=1)` in `App` and `Modules`. The file lists each class that may use a flagged function and the reason.
- **`--ci`** makes Pest ignore `->only()`, so a focused test that was committed by mistake cannot shrink the CI run.
- **`--tia`** records a dependency graph on the first run (about 15% slower than a plain run), then reruns only affected tests. It needs PCOV. Each checkout stores its graph in `.pest/tia/` (git-ignored). A change to `composer.lock` or `phpunit.xml` records a new graph. A change in `database/schema/` reruns the whole suite (measured: 3,781 of 3,781 tests). A change to `module.json` reruns most of it (measured: 3,356 tests). Use it while you work. Before you finish, run `composer test` without `--tia`.
- **Shards** split the suite by the timings in `tests/.pest/shards.json`. Rerun `--update-shards` after large test changes. Pest warns when the file is out of date.
- **Type coverage** reads the source directories in `phpunit.xml`. Pest skips traits. CI fails below 90% (`--min=90`); the measured value is 97.5%.
- **Line coverage** (every `--coverage*` option): the runner loads PCOV with `pcov.directory` set to the checkout root, so modules are included. You set nothing. Without PCOV the runner falls back to Xdebug and you set `XDEBUG_MODE=coverage`. The text report lists a class only when a test covers some of it. `--only-summary-for-coverage-text` drops the per-class lines and keeps only the totals over all classes, so omit it when you need the numbers of one class.
- **Mutation testing** needs PCOV and runs one worker. A test file that declares `mutates(Class::class)` needs no `--class`. Otherwise name the class with `--class`. The runner rejects `--everything`, because it makes Pest ignore `--class`. It also rejects the path `tests` and the Browser suite: each mutant's child run would start a Playwright server and leave it running, until RAM runs out. To mutate against the whole suite, give no path; the default suites are Unit and Feature.
- **Profanity** scans comments, constants and properties. `sheet` and `bbc` are false positives of the English word list.

The runner needs `php` with the phpredis extension, `flock`, `timeout` and `setpriv`, plus `vendor/`, `.env.testing`, `phpunit.xml` and the shared local Redis server of `.env.testing`.
It rejects options that would bypass the guard: `--env`, `--configuration`, `--bootstrap`, `--parallel` (also `--parallel=...`, `-p` and `-pN`), `--runner`, `--without-databases` and `-d`.
It starts Pest with `setpriv --pdeathsig=KILL`, so Pest stops when the runner dies. It removes every `DB_*`, `REDIS_*` and `DATABASE_URL` variable from the environment before it starts, so only `.env.testing` and the per-checkout values decide the database and the Redis server. It stops a Playwright server only when that server carries this run's `LB_TEST_RUNTIME`.

### What one run does

1. Runs `bin/worktree-doctor.sh --infrastructure`.
2. Derives a per-checkout database name, `leadbuster_test_<hash of checkout path>`.
3. Verifies the committed schema snapshot in `database/schema/` (`mysql-schema.sql`, `.fingerprint`, `.sql.sha256`).
4. Takes a shared lock on the template `leadbuster_tpl_<first 12 of fingerprint>_<first 12 of the SQL checksum>` and builds it from `mysql-schema.sql` if it is missing (`bin/schema-snapshot.php`). The fingerprint ignores comments, table options and migration rows, so the checksum of the SQL file is part of the name.
5. A full suite waits for one of three machine-wide slots (`LB_FULL_SUITE_SLOTS`). A run with a path, `--filter`, `--group`, `--testsuite` or `--mutate` never waits.
6. Uses the shared Redis server of `.env.testing` (see [Redis in tests](#redis-in-tests)). The cached configuration, route and event files point to the run directory, and `WorktreeTesting::assertContext()` rejects a run where they do not. Each worker also uses `<run directory>/storage-<worker>` as `storage_path()`, so its logs and its `local` and `public` disk files do not go to `storage/`. The run directory is removed when the run ends.
7. Uses half the CPU count as workers, split evenly between this run and every other checkout that runs tests at the same time (at least 1).
8. Runs `vendor/bin/pest --parallel` with Laravel's parallel runner. Laravel appends `_test_<worker>` to the database name.

The runner calls Pest directly instead of `php artisan test`. Collision checks every option against ParaTest and rejects Pest-only options such as `--ci`, `--tia` and `--shard`.

`Tests\TestCase` uses `RefreshDatabase` and overrides `migrateDatabases()`. Worker databases stay between runs. The first test of a worker repairs the database to the baseline that the last clone kept, and reuses it. It clones the worker database from the template and applies only migrations newer than the template when one of these is true:

- there is no kept baseline, or the file cannot be read;
- the baseline was kept for another template, other migration file contents, another seed setting or another worker database;
- the repair fails;
- the test class seeds (`$seed` or `$seeder`).

After a clone and `migrate`, the worker keeps the new baseline in `/tmp/leadbuster-tests-<uid>/<worker database>.baseline.json`. That directory already holds the per-checkout lock, and the run directory is removed after each run. A reboot clears `/tmp`, so the next run clones once. Only one run per checkout can use the worker databases: the runner holds the per-checkout lock, and a worker whose runner was killed starts no more tests. Tests never read or write the local `leadbuster` database.

DDL (`CREATE`, `ALTER`, `DROP`) makes MySQL commit the test transaction, so `RefreshDatabase` cannot roll it back. The next test then repairs the worker database instead of recloning it. The repair drops extra tables, recreates changed ones, truncates committed rows, and restores `migrations` rows and `AUTO_INCREMENT` counters. The repair also removes what a crashed earlier run left behind. If the result does not match the kept baseline, the worker reclones. `tests/Feature/WorkerDatabaseResetTest.php` covers this path. Before this change, about 80 reclones of about 1.1 s each made the suite take 101 s. It now takes 63 s.

### Redis in tests

All sessions, test runs and agents share the one local Redis server of `.env.testing`. `WorktreeTesting` refuses a host that is not a loopback address or a Unix socket.

- Each PHP process that boots the test application leases one block of 8 consecutive database indexes: 32-39, 40-47 and so on, up to the `databases` setting of the server. Indexes 0-31 belong to the dev app.
- The lease is an exclusive lock on `/tmp/leadbuster-tests-<uid>/redis-databases-<first index>.lock`. The process holds it until it ends, so a crash releases it. When no block is free, the test fails with "No free block of Redis databases".
- On lease, the process empties each index of its block with `FLUSHDB`. It never uses `FLUSHALL` and never touches indexes 0-31.
- Each distinct base index of the Redis connections in `config/database.php` (today 1, 14, 15 and 16) takes one slot of the block, in ascending order. More than 8 distinct indexes fail the run. The key prefix is `test:`.
- A child process, such as a command a test starts with `Process`, leases its own block and does not see the Redis keys of its parent. A forked process (`pcntl_fork`) shares the block of its parent.
- Pub/sub channels and keyspace notifications are server-wide, not per index. A test that uses them can see the messages of other runs.
- The server needs at least 40 databases. A run takes one block for each process that boots the test application: each worker, and each child PHP process that a test starts.

### Schema changes

A ticket that changes the schema must run `bin/schema-refresh.sh` and commit the three snapshot files together. This is the only step that reads the local `leadbuster` database. The new fingerprint gives the ticket its own template, so other checkouts are not affected. When a template of the same name exists already, the refresh keeps it. A test run of another checkout that uses that template does not block the refresh. Full rules are in `AGENTS.md`.

### Destructive commands in tests

`AppServiceProvider::guardDatabase()` allows destructive DB commands only in a guarded test run (`APP_ENV=testing` and `worktree_testing.guarded`). Everywhere else they stay prohibited ([ADR-0004](docs/adr/0004-destructive-commands-prohibited-everywhere.md)). A `testing` environment without the guard throws at boot.

## Frontend command reference

Vitest runs in `jsdom` (`vitest.config.ts`). It resolves `@/` to `resources/js` and loads `resources/js/test/setup.ts`.

```bash
yarn test                                       # all frontend tests
yarn test resources/js/pages/Auth/AcceptInvitation.test.tsx                     # one file
yarn test resources/js/pages/Auth/AcceptInvitation.test.tsx -t 'blocks submission'   # one test by name
yarn test resources/js/pages/Auth                # one directory
yarn vitest                                     # watch mode
yarn test:coverage                              # all tests with V8 coverage
yarn lint                                       # ESLint on resources/js
yarn format                                     # Prettier check (yarn format:write to fix)
yarn build                                      # TypeScript check and Vite build
```

Open `test-results/coverage/frontend/index.html` for the coverage report.
Vitest excludes `.claude/` from test discovery and coverage.

## Static analysis

```bash
vendor/bin/pint --dirty                         # PHP formatting
vendor/bin/phpstan analyse                      # PHPStan, including the Pest plugin rules for tests
composer deptrac   # module and layer boundaries (deptrac.php)
composer deptrac -- --formatter=graphviz-image --output=/tmp/layers.svg   # layer graph, violations in red
python3 bin/pre-commit.py run --hook-stage manual --files path/to/file    # the commit hooks on chosen files
```

## Test infrastructure

Run these when you change CI tooling, quality hooks or worktree setup.

```bash
python3 -m unittest discover -s tests -p ci_tools_test.py
python3 -m unittest discover -s tests -p quality_hooks_test.py
bash tests/Shell/worktree-readiness.sh
bash tests/Shell/worktree-runner.sh     # runs bin/worktree-test.sh against a stub Pest; about 40 s
```

## Test locations

Tests do not live inside modules.

- **Feature tests** (route → controller → service → repository chain): `tests/Feature/<Module>/`, plus `tests/Feature/{Auth,Jobs}/` and a few top-level files such as `WorktreeIsolationTest.php`.
- **Unit tests**: `tests/Unit/Modules/<Module>/`, plus test-infrastructure tests at `tests/Unit/*.php` and `tests/Unit/Support/`.
- **Snapshots**: `tests/.pest/snapshots/`. Regenerate with `composer test -- --update-snapshots <path>`.
- **Frontend tests** sit next to the code they cover as `*.test.ts` or `*.test.tsx`.

`tests/Pest.php` binds `Tests\TestCase` to `tests/Feature` only. Unit tests that need the application call `uses(TestCase::class)` themselves.

## Factory-first approach

Create test models with factories:

```php
use Modules\Advertisers\Models\Advertiser;

test('advertiser search finds by name', function () {
    $user = User::factory()->create();
    Advertiser::factory()->create(['name' => 'Acme Corp']);

    $response = $this->actingAs($user)->getJson('/api/v1/advertisers/search?q=Acme');

    $response->assertJsonFragment(['name' => 'Acme Corp']);
});
```

Factories live in `Modules/<Module>/database/factories/`. Use factory states instead of assumptions about database state.

`Advertiser` has a global `integration_ids` scope. A guest sees no advertisers, so authenticate a user with a matching `integration_id` (see [SECURITY.md](SECURITY.md)).

## Feature test requirements

Feature tests exercise the full request lifecycle: route, controller, FormRequest, service, repository, database. `RefreshDatabase` comes from `Tests\TestCase`, so feature tests do not opt in themselves.

### Mockery scoped to external boundaries only

Feature tests use real repositories and services through the container. Mock or spy only external-boundary collaborators: the AI/LLM gateway, Apify and other scraper providers, and Redis. Never mock internal repositories or services. This rule is enforced in [`.ai/rules/feature.md`](.ai/rules/feature.md).

```php
// Allowed: external boundary
$this->instance(ApifyAPIService::class, Mockery::mock(ApifyAPIService::class));

// Avoid in feature tests: hides whether the real queries work
Mockery::mock(AdvertiserRepository::class);
```

A test that mocks the `DB` facade replaces the database manager. `Tests\TestCase` then skips Laravel's disconnect step at teardown, because the mock has no connections.

## Legacy `Schema::create()` blocks

Legacy tables such as `advertisers` predate the migration history. Before the schema snapshot existed, tests created minimal copies of them with ad-hoc `Schema::create()` blocks. Examples:

- `tests/Feature/Advertisers/AdsRefreshTriggerServiceTest.php`
- `tests/Feature/Advertisers/AdvertiserDetailsAdsSyncPropTest.php`
- `tests/Feature/Advertisers/AdvertiserSearchByExternalIdTest.php`
- the shared `ensureAdsScraperTables()` helper in `tests/Pest.php`

The snapshot (`database/schema/mysql-schema.sql`) now contains these tables. The helper's `hasTable()` guards therefore create nothing in a normal run. The blocks remain in the code; no decision record covers removing them.

## Pest syntax and advanced patterns

The `pest-testing` skill (`.ai/skills/`, linked into `.claude/skills/` and `.agents/skills/`) is the reference for Pest syntax, datasets, `expect()`, HTTP helpers and mocking. The `testing-best-practices` skill covers test design.
