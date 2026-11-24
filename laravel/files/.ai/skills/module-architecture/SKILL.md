---
name: module-architecture
description: "Leadbuster's modular layering rules. MUST be activated for any backend PHP work under Modules/** — creating or modifying controllers, form requests, services, repositories, contracts, models, builders, providers, jobs, listeners, events or routes; adding features or endpoints; deciding where a new class belongs; or making two modules talk to each other. Codifies the Controller → FormRequest → Data DTO → Service → RepositoryInterface → Repository → Builder → Model chain, DI bindings, Core as the shared kernel, deptrac layers, and the documented accepted exceptions."
paths: 'Modules/**/*.php'
---

# Leadbuster Module Architecture

Three nwidart/laravel-modules modules with the same internal layering. Deptrac
(`deptrac.php`) and PHPStan level 8 with strict rules enforce the boundaries.

- `Modules/Core` — the **shared kernel**: base repository contracts, the exception
  hierarchy, mail, middleware, users, integrations, changelog, and every contract,
  event, enum and Data DTO that more than one module uses. Core never depends on
  another module.
- `Modules/Advertisers` — the advertiser domain: CRUD, search and filters, imports and
  exports, widgets.
- `Modules/Socials` — social platform integrations: scrapers (Jobs), profiles, posts,
  ads history, the Ticker backend.

For API Resources, Jobs and enum patterns that are not covered below, see
`references/php-patterns.md`.

## Constraints

### MUST DO

- Give every FormRequest that feeds a Service a `toDto()` that returns a
  `Spatie\LaravelData\Data` DTO, and pass that DTO to the Service.
- Constructor-inject the repository **interface** in services, never the concrete class.
- Constructor-promote and type every dependency (`private readonly AdvertiserService $advertiserService`).
- Bind every new interface in the owning module's `bindContexts()`.
- Keep query composition in the Builder and pagination in the Service.
- Use the Laravel 13 attribute when one exists for what you configure (see
  "Laravel 13 attributes").
- Let Advertisers and Socials talk only through events and notifications, consumed in a
  listener or job (see "Module boundaries"). Shared enums and DTOs live in Core.
- Run the gates at the end of this file before you finish.

### MUST NOT DO

- Import any class from Advertisers in Socials, or from Socials in Advertisers.
- Query another module's tables directly.
- Resolve repositories with `app()` or `resolve()` inside services.
- Put validation in a controller or service. It lives only in the FormRequest.
- Add an `Exceptions/` class to Advertisers or Socials. Throw Core's typed wrappers.
- Add pagination logic to a repository.
- Write `DB::table()`, `DB::raw()`, `DB::statement()`, `DB::select*()` or
  `DB::affectingStatement()` outside a repository or builder. This also applies to
  services, jobs, listeners and console commands, one-off commands included.
  `DB::transaction(fn () => ...)` is allowed everywhere.
- Inject a service into a repository.
- Add a new deptrac violation, or loosen a rule in `deptrac.php`, to make the analysis pass.

## The layer chain

Every persistence-backed feature follows this chain. The canonical example is the
advertiser contact create flow.

**Route** (`Modules/<M>/routes/api.php` or `web.php`) — named routes inside the module's
middleware group:

```php
$router->post('/{advertiser}/contacts', [AdvertiserContactController::class, 'store'])
    ->name('advertisers.contacts.store');
```

**Controller** (`Http/Controllers/Api` or `Http/Controllers/Web`) — thin, ideally one
expression. Constructor-injects the service. Api controllers return `JsonResponse`;
Web controllers return `Inertia::render()`:

```php
public function store(string $advertiser, AdvertiserContactStoreRequest $request): JsonResponse
{
    return new JsonResponse($this->service->create($advertiser, $request->toDto()), 201);
}
```

**FormRequest** (`Http/Requests`) — all validation lives here. Uses
`Modules\Core\Concerns\{IncludeRouteParams, ValidationFailedOverride}` where it needs
route parameters or the JSON failure format. Ends with `toDto()`:

```php
public function toDto(): AdvertiserContactData
{
    return AdvertiserContactData::from($this->safe());
}
```

**Data DTO** (`Modules/<M>/app/Data`) — the typed handoff from the request to the
Service. See "Data DTOs".

**Service** (`Services`) — orchestration. Depends on repository **interfaces**. Owns
pagination, relationship lists and transactions (`DB::transaction(fn () => ...)`).
Converts the DTO to an array at the repository boundary with `$data->toArray()`:

```php
public function create(string $advertiserUuid, AdvertiserContactData $data): AdvertiserContact
```

Pure computation services (generators, resolvers) have no repository. Every service
that touches persistence goes through one.

**Contract** — the module interface (`Contracts/` or `Repositories/*Interface`)
composes the segregated base contracts from `Modules/Core/app/Contracts`
(`BaseIndexRepository`, `BaseShowRepository`, `BaseWriteRepository`,
`BaseUpdateRepository`, `BaseDestroyRepository`):

```php
interface AdvertiserRepositoryInterface extends
    BaseIndexRepository,
    BaseShowRepository,
    BaseUpdateRepository,
    BaseWriteRepository
{
}
```

Extend only the base contracts the repository implements. Known drift: base contracts
declare `array $params`, while implementations accept `array|ValidatedInput`. Declare
new contract methods with the honest union `array|ValidatedInput`.

**Repository** (`Repositories`) — the persistence adapter. Make new repositories
`final`; existing non-final ones may stay. Returns the module's custom Builder so
callers can keep chaining. No pagination here. It constructor-injects only:

- the Eloquent model or models it persists, not their builders (one repository may own
  related tables, for example `AdvertiserWebsiteRepository`: link and website models);
- infrastructure it needs, such as a cache or a connection.

It never injects a service: services call repositories, not the other way round. It
does no work in the constructor (no queries), because a scoped binding builds it once
per request even when no method is called.

```php
final class AdvertiserRepository implements AdvertiserRepositoryInterface
{
    public function __construct(private readonly Advertiser $model) {}

    public function fetchAll(array|ValidatedInput $params): AdvertiserBuilder { /* ... */ }
}
```

**Builder** (`Builders`) — `final`, extends `Modules\Core\Builders\BaseBuilder` (never
Eloquent's `Builder` directly), with chainable, domain-named scopes that return `self`
(`whereSearch(...): self`). Query composition, including raw expressions, lives here.
`BaseBuilder` is generic; name the model so PHPStan types the results:

```php
/**
 * @extends BaseBuilder<UserInvitation>
 */
final class UserInvitationBuilder extends BaseBuilder
```

Older builders still declare `@extends BaseBuilder<Model>`. Typing one with its real
model makes PHPStan check its callers, so do it as its own change.

**Model** (`Models`) — hook the custom builder with the Laravel 13 attribute, not with
`HasBuilder` + `$builder` or a `newEloquentBuilder()` override:

```php
#[UseEloquentBuilder(UserInvitationBuilder::class)]
class UserInvitation extends Model
```

## Data DTOs

Every request DTO extends `Spatie\LaravelData\Data` (`spatie/laravel-data`). It is a
`final` class with constructor-promoted typed properties, in the module's
`app/Data/` directory, with `#[MapName(SnakeCaseMapper::class)]` on the class. The
mapper reads the snake_case request keys and writes snake_case keys from
`toArray()`, so no hand-written mapping is needed:

```php
// Modules/Advertisers/app/Data/AdvertiserContactData.php
#[MapName(SnakeCaseMapper::class)]
final class AdvertiserContactData extends Data
{
    public function __construct(
        public string $fullName,
        public ?string $jobTitle,
        public string $email,
        public ?string $phone,
        public bool $isPrimary = false,
    ) {
    }
}
```

- Build it with `Data::from($this->safe())` in `toDto()`. Do not hand-roll a
  `fromRequest()` or `toArray()` pair.
- Do not declare it `readonly class`: `Data` is not readonly.
- Repository, Contract and Builder signatures stay `array|ValidatedInput`. Call
  `$data->toArray()` at that boundary.
- Older requests still pass `$request->safe()` to the Service. When you change one of
  them, add `toDto()` and move its Service method to the DTO.

Recorded in `.ai/rules/app.md`.

## Laravel 13 attributes

This app runs Laravel 13. Configure classes with PHP attributes, not with properties or
override methods, in new code and in code you change:

- Models (`Illuminate\Database\Eloquent\Attributes`): `#[UseEloquentBuilder]`,
  `#[Table]`, `#[Hidden]`, `#[Visible]`, `#[Appends]`, `#[Touches]`,
  `#[Connection]`, `#[WithoutTimestamps]`, `#[UseFactory]`, `#[UsePolicy]`,
  `#[ScopedBy]`, `#[CollectedBy]`, `#[ObservedBy]`, `#[Scope]` on local scope methods.
  Exceptions from `.ai/rules/models.md`: the allow-list stays `protected $fillable`
  (no `#[Fillable]`), never `#[Guarded]`, and an Observer does only simple work on its
  own model.
- Model accessors and mutators: `Attribute::make()`, never `getXxxAttribute()` or
  `setXxxAttribute()`.
- Console commands (`Illuminate\Console\Attributes`): `#[Signature]`, `#[Description]`,
  `#[Aliases]`, `#[Hidden]`.
- Jobs and queued listeners (`Illuminate\Queue\Attributes`): `#[Queue]`, `#[Tries]`,
  `#[Backoff]`, `#[Timeout]`, `#[MaxExceptions]`, `#[FailOnTimeout]`, `#[UniqueFor]`,
  `#[DebounceFor]`, `#[WithoutRelations]`, `#[DeleteWhenMissingModels]`.

Precedents: `App\Models\User` (`#[Hidden]`, `#[UseFactory]`, `#[UsePolicy]`,
`#[UseEloquentBuilder]`), `DetectExpiredGooglePlaceIds` (`#[Signature]`,
`#[Description]`), `RecomputeAdvertiserAdsMonthlyTotals` (queue attributes). Check
`search-docs` before you use an attribute you have not seen in this codebase.

## DI binding

Each module's main ServiceProvider binds interfaces in a private `bindContexts()`,
called from `boot()`, with scoped bindings (one instance per request):

```php
private function bindContexts(): void
{
    $this->app->scopedIf(AdvertiserRepositoryInterface::class, AdvertiserRepository::class);
}
```

Add every new interface here, including a Core contract that this module implements.
Never resolve repositories with `app()` or `resolve()` inside services.

## Module boundaries

`deptrac.php` enforces these rules (owner ruling 2026-11-24). Core is the shared
kernel. Advertisers and Socials may use Core; Core uses neither.

**Advertisers and Socials reach each other only through events and notifications.**
There is no synchronous call between them, not even through a Core contract.

- The owning module declares the event or notification in its own `app/Events` or
  `app/Notifications` (its Published ring). Name an event as a past-tense business fact.
  Give it only primitive, Core enum or Core DTO properties, never a model or DTO of the
  module. Add `ShouldDispatchAfterCommit` when it fires inside a transaction.
- The reacting module consumes it only in a listener or job (its Queue ring), usually
  `ShouldQueueAfterCommit`. The listener calls a service of its own module.
- Data the reacting module needs to read is copied into its own tables by that listener
  (a local read model), plus a backfill command for existing rows.

Shape to copy: `SocialAdMonthsRecomputed` (fired by `SocialAdHistoryService`) and
`Modules/Advertisers/app/Listeners/RecomputeAdvertiserAdsMonthlyTotals.php` (queued,
debounced, idempotent).

An enum or DTO that both modules use lives in Core. Core holds no domain logic of the
other modules.

### Rings inside a module

Every dependency points inward. `deptrac.php` maps the folders of `Modules/<M>/app/`:

| Ring        | Folders                                               | May use (same module)                 |
| ----------- | ----------------------------------------------------- | ------------------------------------- |
| Domain      | Enums, Data, Exceptions, Helpers                      | nothing                               |
| Published   | Events, Notifications                                 | Domain                                |
| Model       | Models, Builders, Casts, Concerns                     | Domain                                |
| Ports       | Contracts, `Repositories/*Interface`                  | Domain, Model                         |
| Application | Services                                              | Domain, Published, Model, Ports       |
| Adapters    | Repositories, Clients, Mail, Emails, Exports, Imports | Domain, Model, Ports                  |
| Queue       | Jobs, Listeners                                       | Domain, Published, Model, Application |
| Console     | Console                                               | Domain, Queue                         |
| Http        | Http, Policies, Rules, Transformers                   | Domain, Model, Application            |
| Wiring      | Providers                                             | every ring                            |

- A console command dispatches a job, and only the job calls a service. A command never
  calls a service, model or repository directly.
- A service never dispatches a job of its own module; it fires an event, and a listener
  dispatches the job.
- Laravel is split too: `Illuminate\Http` only in Http, the HTTP client and vendor SDKs
  only in Adapters, `Illuminate\Database` not in Domain, facades not in Domain, Model
  or Console.

### Legacy cross-module links — do not copy

These exist today and break the rule above. Do not add new ones.

- The Socials read ports used by Advertisers: `GoogleAdImpressionSummaryInterface`,
  `MetaAdReachSummaryInterface`, `SocialAdMonthlyTotalsInterface` and
  `SocialAdFigureTotalsInterface` (`Modules/Socials/app/Contracts`). Replace each with an
  event and a local read model in Advertisers.
- Eloquent relations between Advertisers and Socials models.
- `composer deptrac` lists every current violation; there is no baseline.

### Legacy layer breaches — do not copy

Fix them when you work on the class. Do not add new ones.

- Raw `DB::table`/`DB::raw`/`DB::statement` outside repositories and builders, for
  example `PaidAdsTickerEventGenerator`, `SocialFeedPostSyncService`, `NewerCrawlUpsert`,
  the payload-processing and categorise jobs, and console commands such as
  `BackfillSocialFeedPostsCommand`, `ExportAdvertisersCsv`, `RefreshAdvertisersAdsStats`
  and `DetectExpiredGooglePlaceIds`. Find the rest with
  `rg -n "DB::(table|raw|statement|select|affectingStatement)" Modules/*/app/{Services,Jobs,Listeners,Console}`.
- Models that hook their builder with `HasBuilder` + `$builder`: move them to
  `#[UseEloquentBuilder]`.

### Documented accepted exception — do not replicate, do not "fix"

- `Modules/Advertisers/app/Http/Controllers/Web/AdvertiserController::index()` runs raw,
  day-cached `DB::selectOne` aggregates against Socials-owned tables. It is annotated
  in the code. Leave it as is. It is the only allowed `DB::` query outside a
  repository or builder.

## Frontend pairing

The React/Inertia app is global (`resources/js`), not per module. Pages group by domain
folder under `resources/js/pages`. A NEW page's folder mirrors the backend module that
owns its data (Ticker backend in Socials → page under `Socials/`). Existing misplaced
pages (for example `pages/Advertisers/Ticker.tsx`) stay where they are. The FE
developer moves them, not agents.

## Tests

- Tests live in the root `tests/` tree (`tests/Feature/<Module>/...`,
  `tests/Unit/Modules/<Module>/...`), not in `Modules/*/tests`.
- Use the factory in `Modules/<M>/database/factories` before you hand-build models.
- A feature test for a module endpoint runs the full chain (route → controller →
  service → repository) with `RefreshDatabase`. Do not mock repositories in feature
  tests.
- Test a cross-module event at both ends: `Event::fake()` plus `assertDispatched` for
  the firing module, and a listener test for the reacting module.

## New-endpoint checklist

1. Route in `Modules/<M>/routes/api.php` or `web.php` (named, correct middleware group).
2. FormRequest with rules, Core concerns and `toDto()`.
3. Data DTO in `Modules/<M>/app/Data`.
4. Controller action (thin, typed, in `Api/` or `Web/`).
5. Service method that takes the DTO (interface-typed dependencies).
6. Contract method (on the module interface or a new segregated base contract).
7. Repository implementation that returns the custom Builder.
8. Builder scopes for new query logic.
9. Binding in `bindContexts()` for each new interface.
10. Feature test per acceptance criterion, with factory states as needed.

## Gates

Run all of them before you finish:

1. `vendor/bin/pint --dirty --format agent`
2. `vendor/bin/phpstan analyse`
3. `composer deptrac` — add no violation in the files you changed. The suite still has
   known violations (no baseline), so compare with the result before your change. New
   classes must land in a folder that a ring covers.
4. `composer test -- <test file or --filter>` for the tests you touched. Never run
   `php artisan test` or `vendor/bin/pest` directly; `tests/bootstrap.php` rejects
   them.
