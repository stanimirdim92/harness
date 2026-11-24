---
paths:
    - 'Modules/*/app/{Repositories,Console/Commands}/*.php'
---

# Commands

## Explicit per-query eager loading over model $with

Specify eager-loaded relations explicitly via `->with()` at the query call site. Do not set `protected $with` defaults on models.

## Keep casts of argument() and option() values (since 2026-11-24)

Larastan types `$this->argument()` and `$this->option()` from the signature, but `Artisan::call()`, the scheduler and tests pass values of any type. An int passed to `PDO::quote()` broke `MarkAsFranchise` when its `(string)` cast was removed. Cast these values to the type you need. `phpstan.neon` ignores `cast.useless` in console commands for this reason.

## Escape stored values in console output

Before a console command prints a stored or imported value, pass it through `OutputFormatter::escape()` and replace control characters. Stored data is untrusted: unescaped `<href=…>` tags or ESC sequences change what the operator sees.
