# Conventions

This is the human-readable _why_/overview of Leadbuster's coding conventions.
The enforced, path-scoped rules agents must read before editing a given path
live in `.ai/rules/` — start at `.ai/rules/index.md`, which maps file globs
to rule files. Don't duplicate a rule from there here; link it.

## Validation

FormRequest classes own validation (see the `module-architecture` skill).
No module controller calls `$request->validate()` inline (checked
2026-11-03); the former exceptions in `AdvertiserPresetController` and
`TickerPresetController` are gone.

## Controllers & routing

Controllers are plain classes with multiple public action methods (never
`__invoke` or `Route::resource`), routes point at `[Controller::class,
'method']` arrays, middleware is assigned via the route group's
`'middleware'` array, and route params are primitives resolved manually
rather than via Eloquent model binding — see `.ai/rules/controllers.md` and
`.ai/rules/routes.md`.

## Models

Models declare an explicit `$fillable` allow-list, DO NOT use the legacy
`getXxxAttribute()`/`setXxxAttribute()` accessors, instead use the new
`Attribute::make()` class style (https://laravel.com/docs/master/eloquent-mutators#accessors-and-mutators),
hook lifecycle logic via `booted()` closures instead of Observers, and leave eager loading to explicit
per-query `->with()` calls rather than a model-level `$with` default — see
`.ai/rules/models.md` and `.ai/rules/commands.md`.

## Architecture

New Controller → Service handoffs go through a typed DTO (`spatie/laravel-data`):
FormRequest builds it via `toDto()`, Controller passes the DTO to the
Service — Repository/Contract/Builder signatures stay `array|ValidatedInput`
(decided 2026-08-18, DTOs via `spatie/laravel-data` since 2026-08-21).
Existing services built directly against `ValidatedInput`/array are
grandfathered; migrate opportunistically. The app has no shared
cross-module base Service; dependencies are injected rather than
service-located, global helpers are preferred over facades, shared traits
live in `Modules/Core/app/Concerns`, and exceptions are thrown from Core's
typed wrappers rather than defined per-module — see `.ai/rules/app.md`,
`.ai/rules/services-jobs.md`, `.ai/rules/services.md`, and
`.ai/rules/core-app.md`.

Domain events (`Modules/<M>/app/Events`) are reserved for cross-module
reactions only — same-module, single-consumer reactions stay a direct job
dispatch from the Service (decided 2026-08-18; see `.ai/rules/app.md`).

`.ai/rules/jobs.md`'s job-naming rule still holds unresolved,
self-contradictory draft text — a heading that says jobs are "never
suffixed 'Job'" while the body says to append one "if appropriate". Don't
trust a one-line paraphrase; read `.ai/rules/jobs.md` directly, and treat
it as unsettled until the repo owner resolves the conflict.

## Frontend

Frontend-specific conventions live in path-scoped rule files, not here:
no defensive value-coercion wrappers on API data (`.ai/rules/js.md`),
paid-ads Ticker signal filtering via `srch_category` event codes
(`.ai/rules/ticker.md`), and paid-ads event detection reading feed data
rather than hardcoded lists (`.ai/rules/ticker-page.md`).

## Database & migrations

Migrations implement real `down()` logic, store enum values as
string/integer columns with a PHP backed-enum cast rather than a DB `enum()`
column, wrap multi-statement writes in `DB::transaction()`'s closure form,
prefer `upsert()`/`updateOrCreate()`/`firstOrCreate()` for idempotent
writes, and use plain `unsignedBigInteger()->index()` (not `->constrained()`)
for FK-like columns inside module migrations — see
`.ai/rules/database-migrations.md`, `.ai/rules/migrations.md`, and
`.ai/rules/jobs-services-console-commands.md`.

## API / Resources

Socials and Core API endpoints wrap responses in dedicated JsonResource
classes; listings use length-aware `paginate()` except the ticker feed,
which uses `cursorPaginate()` — see `.ai/rules/controllers-api.md`,
`.ai/rules/services-repositories.md`, `.ai/rules/repositories.md`, and
`.ai/rules/http.md`.

`.ai/rules/api.md`'s heading ("No API Resource layer in Advertisers") and
its own body ("Introduce Resource classes... whenever possible") currently
disagree on whether Advertisers' API endpoints should use a Resource
layer. Read `.ai/rules/api.md` directly rather than trust a one-sided
paraphrase here.

## Style

String handling favors native PHP functions over `Str::` helpers except
where PHP has no native equivalent, and date values held on objects or
passed as reference points are type-hinted `CarbonImmutable` rather than
mutable `Carbon` — see `.ai/rules/app.md`.

## Testing

Feature tests mock or spy only external-boundary collaborators (AI/LLM
gateway, scraper providers, Redis); internal repositories and services are
exercised for real — see `.ai/rules/feature.md`.

## PHP-wide rules (not path-scoped)

These apply everywhere in the codebase and aren't gated by a file glob, so
they're stated directly here rather than in `.ai/rules/`:

- Always use curly braces for control structures, even single-line bodies.
- Use PHP 8 constructor property promotion (`public function
__construct(public GitHub $github) {}`).
- Use explicit return type declarations and type hints on all method
  parameters.
- Use TitleCase for Enum keys (`FavoritePerson`, `BestLake`, `Monthly`).
- Prefer PHPDoc blocks over inline comments; reserve inline comments for
  exceptionally complex logic.
- Use array shape type definitions in PHPDoc blocks.
- Use descriptive names for variables and methods (`isRegisteredForDiscounts`,
  not `discount()`).

## Enum casing: known drift, not a convention change

A convention sweep found 9 enums using `SCREAMING_SNAKE` case keys against
5 using `TitleCase`. This was ruled aspirational drift, not a change to the
convention: CLAUDE.md's TitleCase rule stands as-is, and nothing was
recorded to codify the `SCREAMING_SNAKE` cases. Don't "fix" the
`SCREAMING_SNAKE` enums under the assumption this is inconsistency to clean
up — it's a known, accepted gap, tracked in `docs/MEMORY.md`.
