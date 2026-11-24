# Commands Reference

This guide covers essential commands for developing, testing, and maintaining Leadbuster.

## Setup

Commands in this section come from the repository scripts. They were not run
while this document was written.

PHP dependencies, Node via Corepack (`packageManager: yarn@4.18.1`), MySQL and
Redis are required. See [README.md](README.md#setup) for the
environment variables.

```bash
cp .env.example .env && php artisan key:generate
bin/worktree-setup.sh            # composer install --no-scripts + yarn install, checked against lockfiles
bin/worktree-setup.sh --build    # also build and verify public/build (needed for browser checks)
bin/setup-quality.sh             # pinned pre-commit hooks; sets core.hooksPath=.githooks
```

`bin/worktree-setup.sh` needs `.env`, `.env.testing`, `composer.lock` and
`yarn.lock`. Run it in every new checkout or worktree.

Check that a checkout is ready:

```bash
bin/worktree-doctor.sh --infrastructure   # runner version against the main checkout
bin/worktree-doctor.sh --frontend         # complete Vite build present
```

The local `leadbuster` database is a schema-only template. Do not migrate,
seed or write to it as part of test or AI work (see `AGENTS.md`).

## Run

Start the app server, queue listener, log tail (`pail`) and Vite together:

```bash
composer run dev
```

Run Horizon instead of the queue listener in staging/production:

```bash
php artisan horizon
```

## Format, Lint and Analyse

```bash
vendor/bin/pint --dirty                 # PHP formatting
vendor/bin/phpstan analyse              # static analysis (CI uses phpstan.ci.neon)
composer deptrac   # module/layer boundaries (deptrac.php)
yarn lint                               # ESLint on resources/js
yarn format                             # Prettier check (format:write to fix)
yarn build                              # tsc + vite build
```

Run the shared hooks on chosen files without committing:

```bash
python3 bin/pre-commit.py run --hook-stage manual --files path/to/file
```

The hooks are defined in `.pre-commit-config.yaml`: Pint, ESLint, Prettier,
merge-conflict check, Gitleaks, actionlint and shellcheck. See
[ADR-0008](docs/adr/0008-shared-quality-hooks-and-ci-gate.md).

## Test

```bash
composer test -- --compact                  # backend, via bin/worktree-test.sh
composer test -- --compact --filter=Name    # backend, filtered
yarn test                                   # frontend (Vitest)
```

Direct `vendor/bin/pest` and `php artisan test` runs are rejected. See
[TESTING.md](TESTING.md) for every test command, coverage and the runner.

## Schema Snapshot and Test Databases

```bash
bin/schema-refresh.sh                       # after an intentional schema change; commit the 3 files in database/schema/
php bin/worktree-databases.php              # list test databases and preview cleanup
php bin/worktree-databases.php --checkout /abs/path/to/checkout          # preview one checkout
php bin/worktree-databases.php --checkout /abs/path/to/checkout --apply  # drop its idle databases
```

## Artisan Discovery

### List all available Artisan commands

```bash
php artisan list
```

Check parameters for a specific command:

```bash
php artisan [command] --help
```

### Inspect routes

Display all registered routes:

```bash
php artisan route:list
```

Filter routes by HTTP method:

```bash
php artisan route:list --method=GET
```

Filter routes by name:

```bash
php artisan route:list --name=users
```

Filter routes by path:

```bash
php artisan route:list --path=api
```

Exclude vendor routes:

```bash
php artisan route:list --except-vendor
```

Show only vendor routes:

```bash
php artisan route:list --only-vendor
```

### Read configuration values

Display a configuration value using dot notation:

```bash
php artisan config:show app.name
```

Display the default database configuration:

```bash
php artisan config:show database.default
```

## Advertiser Website Recovery

`advertisers:recover-shared-websites` finds active, non-franchise advertisers linked to a website record that is shared by multiple advertisers. Candidate reports are database-only; recovery runs use each advertiser's Google Place ID to recover its full website URL.

When a recovered website has a different root, the command handles it automatically. It reuses an existing `websites_roots` row or creates one, creates or reuses the full website, and relinks only the selected advertiser.

### List all candidates

Print every candidate as `ID | UUID | Name | Address | Website | Website root`, followed by the total distinct advertiser count. This makes no Google requests and does not apply the recovery batch limit.

```bash
php artisan advertisers:recover-shared-websites --list-candidates
```

List candidates sharing a specific website record:

```bash
php artisan advertisers:recover-shared-websites --list-candidates --website-id=18561
```

List candidates from one integration:

```bash
php artisan advertisers:recover-shared-websites --list-candidates --integration-id=12
```

List specific advertisers. Repeat array options to provide multiple values:

```bash
php artisan advertisers:recover-shared-websites --list-candidates \
  --advertiser-id=201162 \
  --advertiser-id=339867
```

Candidate filters can be combined. `--after-id` is also available when a partial report is needed:

```bash
php artisan advertisers:recover-shared-websites --list-candidates \
  --integration-id=12 \
  --website-id=18561 \
  --after-id=201162
```

### Dry-run recovery

Check the first 10 eligible candidates with Google without changing the database:

```bash
php artisan advertisers:recover-shared-websites
```

Dry-run one shared website group:

```bash
php artisan advertisers:recover-shared-websites --website-id=18561
```

Dry-run specific advertisers:

```bash
php artisan advertisers:recover-shared-websites \
  --advertiser-id=201162 \
  --advertiser-id=339867
```

When `--advertiser-id` is supplied, the command checks those advertisers even if their current website record is no longer shared. This is useful after applying a dry-run allow-list in batches, because earlier batches can split a shared website group before later advertiser IDs are processed.

Use a custom batch size:

```bash
php artisan advertisers:recover-shared-websites --limit=25
```

Continue from the cursor printed by the previous batch:

```bash
php artisan advertisers:recover-shared-websites --after-id=339867
```

### Apply recovery

Recover and persist the first 10 eligible candidates:

```bash
php artisan advertisers:recover-shared-websites --apply
```

Apply recovery to one shared website group:

```bash
php artisan advertisers:recover-shared-websites --website-id=18561 --apply
```

Continue applying from the previous batch cursor:

```bash
php artisan advertisers:recover-shared-websites --after-id=339867 --apply
```

Apply recovery to specific advertisers:

```bash
php artisan advertisers:recover-shared-websites \
  --advertiser-id=201162 \
  --advertiser-id=339867 \
  --apply
```

### Recovery options

`--advertiser-id=<id>` restricts processing to an advertiser ID. It can be repeated. Explicit advertiser IDs are processed even when their website is no longer shared.

`--website-id=<id>` restricts processing to advertisers currently linked to a shared website ID. It can be repeated.

`--integration-id=<id>` restricts processing to an integration ID. It can be repeated.

`--after-id=<id>` processes only advertisers with a greater ID. Use the value printed as `Next after-id` to continue batching.

`--limit=<number>` controls the maximum number of Google requests in one recovery run. The default is `10`; `--limit=0` processes all eligible candidates and may be expensive.

`--sleep=<milliseconds>` controls the delay between Google requests. The default is `300` milliseconds.

`--apply` persists recovered websites. Without it, recovery is a dry run.

Unresolved rows are printed as:

```text
UNRESOLVED | reason | detail | ID | UUID | Name | Address | Current website
```

Reasons are `place_not_found`, `place_id_mismatch`, `invalid_website`, `google_request_failed`, or `swap_failed`. The final summary also breaks unresolved totals down by reason.

All recovery filters can be combined:

```bash
php artisan advertisers:recover-shared-websites \
  --integration-id=12 \
  --website-id=18561 \
  --after-id=201162 \
  --limit=10 \
  --sleep=500 \
  --apply
```

## Expired Google Place ID Detection

`advertisers:detect-expired-google-place-ids` checks active advertisers that have a stored `google_place_id`, no `google_place_id_status` yet, and no check in the last 365 days (`google_place_id_checked_at`; change with `--recheck-after-days`, `0` checks all). Google recommends refreshing Place IDs older than 12 months. The check asks Google only for the `id` field, which Google documents as free.

For each candidate:

- Google returns the same ID: the Place ID is valid.
- Google returns a different ID: the stored ID is replaced. The previous ID is kept in `google_place_id_old`.
- Google returns `NOT_FOUND`: the Place ID is expired.

With `--refresh-expired`, the command also checks every advertiser already marked expired, whatever its check date. For each expired Place ID it runs a Google Places Text Search for "name, address, postcode, city". It replaces the ID only when exactly one place has the same name and a matching location. The location matches when the found address contains the advertiser's postcode as whole words, or the found place is within 250 metres of the advertiser's `latitude`/`longitude`. The city name is compared (as whole words) only when the advertiser has neither a postcode nor coordinates, because a stored city such as "Munich" may not match Google's "München". Otherwise the advertiser stays expired and the output shows `NO REPLACEMENT | no_match` or `NO REPLACEMENT | ambiguous_match`. Text Search is billed per request, also in a dry run. Expired advertisers with no match are searched again on every `--refresh-expired` run, so limit batches with `--limit` and `--after-id`.

A replacement ID that already belongs to another live advertiser in the same integration is never written. The output shows `DUPLICATE | <new id> | <other advertiser id>`.

The command is dry-run by default. With `--apply` it writes the check date on every successful check, `google_place_id_status = expired`, and replacement Place IDs. A failed Google request writes nothing, so the advertiser is checked again on the next run. Successful status and Place ID changes are also written to a dedicated daily log file (kept for 40 days):

```text
storage/logs/socials/advertisers_google_place_ids/responses-YYYY-MM-DD.log
```

Each log entry includes the advertiser ID, UUID, name, integration ID, Google Place ID, old Google Place ID, old status and new status. The main application log is not used for these change records.

### Verified versions

This command documentation was verified with:

```text
PHP 8.4.24
Laravel Framework 13.26.1
inertiajs/inertia-laravel 3.3.1
laravel/boost 2.5.5
nwidart/laravel-modules 13.0.0
pestphp/pest 4.7.8
laravel/pint 1.30.5
larastan/larastan 3.10.0
phpstan/phpstan 2.2.9
```

### List candidates

Print candidates without calling Google or changing the database:

```bash
php artisan advertisers:detect-expired-google-place-ids --list-candidates
```

Use `--limit=0` to list every candidate:

```bash
php artisan advertisers:detect-expired-google-place-ids --list-candidates --limit=0
```

### Dry-run detection

Check the first 10 candidates with Google without changing any advertiser rows:

```bash
php artisan advertisers:detect-expired-google-place-ids
```

Restrict a dry run to one integration:

```bash
php artisan advertisers:detect-expired-google-place-ids --integration-id=12
```

Restrict a dry run to specific advertisers. Repeat array options to provide multiple values:

```bash
php artisan advertisers:detect-expired-google-place-ids \
  --advertiser-id=201162 \
  --advertiser-id=339867
```

Continue from the cursor printed by a previous batch:

```bash
php artisan advertisers:detect-expired-google-place-ids --after-id=339867
```

### Apply expired statuses

Persist expired statuses for the first 10 candidates:

```bash
php artisan advertisers:detect-expired-google-place-ids --apply
```

Apply a larger batch:

```bash
php artisan advertisers:detect-expired-google-place-ids --limit=100 --apply
```

Apply every current candidate. This may be expensive because it calls Google once per candidate:

```bash
php artisan advertisers:detect-expired-google-place-ids --limit=0 --apply
```

### Refresh expired Place IDs

Search Google for a replacement Place ID for expired advertisers and write unambiguous matches:

```bash
php artisan advertisers:detect-expired-google-place-ids --refresh-expired --limit=50 --apply
```

### Email changed statuses

Send a summary email after the command finishes. The email contains only advertisers whose status actually changed during that `--apply` run:

```bash
php artisan advertisers:detect-expired-google-place-ids \
  --apply \
  --email=ops@example.com
```

Send to multiple recipients by repeating `--email`:

```bash
php artisan advertisers:detect-expired-google-place-ids \
  --apply \
  --email=ops@example.com \
  --email=admin@example.com
```

Override the email subject:

```bash
php artisan advertisers:detect-expired-google-place-ids \
  --apply \
  --email=ops@example.com \
  --email-subject="Google Place ID changes"
```

If no statuses changed, no email is sent and the command prints `No status changes to email.` Invalid email recipients make the command exit with failure after any status changes have already been applied.

### Detection options

`--advertiser-id=<id>` restricts processing to an advertiser ID. It can be repeated.

`--integration-id=<id>` restricts processing to an integration ID. It can be repeated.

`--after-id=<id>` processes only advertisers with a greater ID. Use the value printed as `Next after-id` to continue batching.

`--limit=<number>` controls the maximum number of Google requests in one detection run. The default is `10`; `--limit=0` processes all eligible candidates and may be expensive.

`--sleep=<milliseconds>` controls the delay between Google requests. The default is `300` milliseconds.

`--recheck-after-days=<days>` skips advertisers checked within this many days. The default is `365`; `0` checks all.

`--refresh-expired` also processes advertisers already marked expired and runs a billed Text Search for each expired Place ID.

`--apply` persists check dates, expired statuses and replacement Place IDs. Without it, detection is a dry run.

`--email=<address>` sends an end-of-run changed-status email. It can be repeated.

`--email-subject=<subject>` overrides the changed-status email subject.

Output lines for expired Place IDs look like:

```text
WOULD EXPIRE | ID | UUID | Name | Google Place ID
EXPIRED | ID | UUID | Name | Google Place ID
STILL EXPIRED | ID | UUID | Name | Google Place ID
```

Replacement lines look like:

```text
WOULD REPLACE | ID | UUID | Name | old Place ID -> new Place ID
REPLACED | ID | UUID | Name | old Place ID -> new Place ID
DUPLICATE | new Place ID | other advertiser ID | ID | UUID | Name | Google Place ID
NO REPLACEMENT | no_match or ambiguous_match or no_name | match count | ID | UUID | Name | Google Place ID
```

Unresolved rows are printed as:

```text
UNRESOLVED | reason | detail | ID | UUID | Name | Google Place ID
```

The final summary prints candidate totals, checked rows, expired rows, valid rows, marked rows, replaced rows, replacements blocked by a duplicate, rows changed by another writer before update, failures, remaining unchecked rows and actual status changes logged.
