---
paths:
    - 'Modules/*/app/**/*.php'
---

# App

## Data DTOs for every request that feeds a Service (decided 2026-08-18, laravel-data since 2026-08-21, all requests since 2026-11-21)

Every FormRequest that feeds a Service has a `toDto()` that returns a
`Spatie\LaravelData\Data` DTO, built with `Data::from($this->safe())`. The
Controller passes that DTO to the Service, not raw `ValidatedInput`/array.
DTOs are `final` classes in `Modules/<M>/app/Data/` with promoted constructor
properties and `#[MapName(SnakeCaseMapper::class)]`, so snake_case request keys
and the `toArray()` output for the repository write boundary both use
snake_case. Repository/Contract/Builder signatures stay `array|ValidatedInput`.
Do not hand-roll a `fromRequest()`/`toArray()` pair. Older requests without
`toDto()` get one when you change them. See the `module-architecture` skill.

## Events only for cross-module reactions, declared in Core (decided 2026-08-18, Core since 2026-11-21)

Direct job dispatch (`SomeJob::dispatch(...)` from the Service) stays the
default: same-module trigger, single consumer. Use an event + listener only
when a _different_ module owns the reaction. Advertisers and Socials never
import each other, so the event class lives in `Modules/Core/app/Events`.
The firing module never references the listener; the reacting module wires
its own listener in its `EventServiceProvider`. Name events as past-tense
business facts. See "Module boundaries" in the `module-architecture` skill.

## Constructor injection first, then global helpers, never facades (DI since 2026-11-24)

Inject what a class needs through its constructor, typed by the most specific class or contract that has the methods you call (for example `AuthManager`, then narrow the guard with `instanceof SessionGuard`). Where injection is not practical (static context, a one-line `now()` or `config()` read), use the global helper (`config()`, `auth()`, `response()`, `now()`, `cache()`, `session()`, `request()`). Do not add facade calls; replace one when you change its code. Precedent: `AdvertiserAiSummaryService` (`AuthManager`).

## Casts PHPStan calls useless can still convert (since 2026-11-24)

Before you remove a cast that PHPStan reports as `cast.useless`, check where the value comes from. Keep the cast when the declared type is only a PHPDoc or Larastan guess: MySQL returns `DECIMAL` columns as strings such as `"45.12345600"` (keep `(float)`), and a console argument or option can have any type (see `commands.md`). Keep such a cast with `// @phpstan-ignore cast.useless (reason)`.

## Logging::log_response() for external API/scraper payloads and their processing

When logging a raw response from an external API/scraper, or a diagnostic about processing that payload inside its job (a malformed item, a count of items handled specially), use the job's `Logging::log_response('<folder>')` logger so it lands in the per-source log file — don't route that through the `Log::` facade. Use the `Log::` facade for application warn/error logging unrelated to a scraper payload.

## Exceptions live only in Core, other modules throw Core's, never define their own

Never add an `Exceptions/` class to Advertisers or Socials. Throw one of Core's typed wrappers (`Modules\Core\Exceptions\*`) instead — they're plain namespaced aliases of native SPL/Symfony exceptions with no added behavior, used so no code throws a bare global exception.

## Use DB::transaction() closure form

Wrap multi-statement writes in `DB::transaction(fn () => ...)`. Never call manual `beginTransaction()`/`commit()`/`rollBack()`.

## String helper choice

Use `Str::` static helpers only for semantics native PHP lacks (`Str::slug`, `Str::limit`, `Str::uuid7`, `Str::singular`). Use native PHP string functions (`str_replace`, `sprintf`, `substr`, `trim`) for everything else. Avoid `Str::of()` fluent chains.

## CarbonImmutable for held/passed date values

Type-hint `CarbonImmutable` (not `Carbon`) for date values stored on objects or passed as reference points across methods. Leave transient `now()`/`Carbon::` calls as mutable `Carbon`.

## Role-based authorization, no per-model policies

Authorize with the user's role (`isAdmin()`/`isPublisher()` or the `is-admin`/`is-publisher` gates). Do not create per-model Policy classes or ability methods.

## Place shared traits in Core

Put traits in a `Concerns` directory within their owning module and layer. Place traits shared across modules in the Core shared kernel.

## Prefer the existing data type for simple transformations

For simple transformations, prefer collection methods on collections and `array_map()` on arrays. Use `foreach` for branching, early exit, or explicit key handling. Convert to a collection when its operations make the code clearer. Treat this as guidance when editing existing loops.
