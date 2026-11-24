---
paths:
    - 'tests/**'
---

# Tests

## A failing assertion is a question, not a defect — never edit the side that is convenient

When a test and the code it covers disagree, decide which one is right BEFORE changing either. Editing the assertion to match the code turns the suite green without answering the question, and a green suite then actively hides the defect from every later review.

Concretely, in LD-429: a ticker assertion expected `source_post_pk` to be `source_profile_id` (73) while the generator emitted `advertiser_id` (501). The commit that found it deliberately left it red and wrote down why — "which is correct is a semantics question for the owner, not something to settle by editing whichever side is convenient." A later task settled it by changing the assertion to 501. The owner afterwards confirmed 501 was in fact correct, so nothing shipped broken — but the suite had gone green before anyone asked, and the code review that ran in between saw a passing test and had no reason to look.

Rules:

- If you cannot tell which side is right, leave the test failing and surface the question. A known-red test is honest; a green one that asserts whatever the code happens to do is not.
- If you do change an assertion, the commit message must say what made the new expected value correct — not that it now matches the implementation.
- "The test now passes" is never the justification. Matching the code is what the test is supposed to verify, so it cannot also be the evidence.
- This applies with most force to semantics that only a human owner can settle: identifier meaning, business rules, user-visible wording.

## Factories where they exist, raw inserts otherwise

Create test records with the model's factory when one exists. Use `DB::table(...)->insert()` only for tables without a factory, such as pivot tables.

## Run tests only through `composer test`

Run backend tests with `composer test`, and pass selectors after `--`, e.g. `composer test -- --compact --filter=CrmId`. `tests/bootstrap.php` rejects direct Pest and PHPUnit runs. Ignore the `php artisan test` and `vendor/bin/pest` commands in the `pest-testing` skill: Boost overwrites that skill on every update, so this rule is where the project command lives.

## A test file covers every decision of the code it tests, not only the success path

A test file with only success cases tests nothing. The 2026-11-24 audit found 21 such files and 158 with untested decisions. Before you write the tests, read the code under test and list its decisions. Give each decision at least one test that fails when the decision breaks:

- each validation rule, with the value just inside and just outside the limit (`max:255`: 255 passes, 256 fails; `>` vs `>=`);
- each authorization and tenant rule: a guest, a user without the role, a user of another integration, and an allowed user as the control;
- not found, empty, null and malformed input;
- each early return, `continue` and fallback branch;
- each exception path and each failure of an external call (HTTP error, timeout, lock timeout, non-duplicate `QueryException`);
- each option and argument of a command, including an invalid value and its exit code.

## Choose inputs that tell the branches apart

A case must fail when its branch is removed. Check that the input does not also satisfy another rule:

- ids that are equal by chance (a `websites_roots` id equal to a `websites` id) hide which id the code sends;
- two inputs that hash to the same value hide a missing recalculation;
- a row inserted first makes an "earliest row" loop a no-op;
- a value that passes two thresholds (20 → 28 is both +8 and +40%) does not isolate either threshold.

## Assert the effect, not only that the request succeeded

`assertOk()`, `assertRedirect()` without a target, `assertSessionHasErrors()` without a key, `not->toBeNull()`, `toBeArray()`, `toHaveCount()` and `pushedJobs()->not->toBeEmpty()` alone prove almost nothing. Also assert what the action changed: the database row, the JSON path, the redirect target, the error key, the sent notification and its recipient, the session value. A test that says "the password was reset" checks the new password with `Hash::check`.

A negative assertion needs a positive control. `assertNotPushed(X::class)` proves nothing if the code could never push `X`. Assert the job, call or row that the wrong behaviour would produce.

## No tautologies, no mirrors of the implementation

- Do not assert your own setup, a config value or a constant list.
- Do not assert a table or path that the code under test never touches.
- Do not re-declare the query-builder calls of the code (`shouldReceive('where')->...`). Assert the data it writes.
- Do not call private methods through `ReflectionMethod`. Test the public entry point.
- A test name states the behaviour. If the behaviour does not exist, the test must fail.

## Never encode a known defect as the expected result

A "measurement" test that asserts a leak, data loss or wrong status as passing turns green on the defect and red on the fix. A permanently skipped test is not coverage. Write the test for the correct behaviour. If the owner has not ruled what correct is, ask, and record the question in the ticket ledger. Do not merge a test that asserts the defect.

## Each test passes alone, in any order, at any date, in any time zone

- No test reads state that another test wrote, including static variables. Each test must pass with `--filter` alone.
- Freeze time (`$this->travelTo()`, `Carbon::setTestNow()`) when the code compares with now, a window or a cutoff. A fixed date that ages out of a "last 3 months" window is a time bomb.
- Do not count lines in a shared log file. Use `Log::spy()` or `Log::shouldReceive()`.
- Remove temporary files and directories in `finally`.

## Use the real schema; mock only external boundaries

- Do not create tables with `Schema::create()` behind a `hasTable()` guard, and do not shadow real tables with `CREATE TEMPORARY TABLE`. The schema snapshot already holds the real tables; a hand-written copy hides a broken migration.
- A test that opens a second database connection and commits rows must restore what it wrote in `finally`.
- Feature tests mock only external boundaries (AI gateway, Apify and other scrapers, Bright Data, Google, Redis). Do not stub an internal repository. When a stub reason in a comment is no longer true, remove the stub.

## Prove that a new test can fail

Before you trust a new or changed test, break the code it covers and run the test. It must go red. Revert the change. For a test file that declares `mutates()`, run `composer test -- --mutate --covered-only --no-cache <file>` and add a test for each surviving mutant that changes behaviour. For an `arch()` rule, add a probe class that breaks the rule, run the test, and delete the probe. Pest matches an `arch()` target only against a registered namespace prefix: name `Modules\Advertisers`, not `Modules`.

## Fake external binaries whose output depends on their version (since 2026-11-24)

When the code runs an external binary (ffmpeg, for example) and the test needs a specific outcome, put a small fake script for it on `PATH` with `putenv()` and restore `PATH` in `finally`. A real binary gives a different result per version: CI's apt ffmpeg shrank a PNG that local ffmpeg 8 did not. Precedent: `CompressMediaJobTest`. Prove the fake drives the result by making it return the other outcome once.

## Shell tests: no bare `!` under `set -e`

`set -e` ignores a command that starts with `!`, so `! grep -q x file` can never fail the script. Write `if grep -q x file; then exit 1; fi`.
