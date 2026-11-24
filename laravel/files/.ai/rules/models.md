---
paths:
    - 'Modules/*/app/Models/*.php'
---

# Models

## Fillable allow-list for mass assignment

Declare an explicit allow-list on every model with `protected $fillable = [...]`. Do not use the `#[Fillable]` attribute. Never use `$guarded` or `#[Guarded]`.

## Accessors and mutators with Attribute::make() (since 2026-11-21)

Define accessors and mutators as a protected camelCase method that returns `Illuminate\Database\Eloquent\Casts\Attribute` built with `Attribute::make(get: ..., set: ...)`, typed `@return Attribute<TGet, TSet>`. Never add `getXxxAttribute()`/`setXxxAttribute()` magic methods. Refactor any legacy one you find.

## Model events: booted() closures or a simple Observer (since 2026-11-21)

Register model lifecycle logic in a protected static `booted()` method with `static::creating()`/`addGlobalScope()` closures, or in an Observer class attached with `#[ObservedBy(XObserver::class)]`. An Observer only does simple work on its own model: defaults, derived columns, cache keys. Multi-step work, other models, external calls or another module's reaction go to a Service, a Job or a Core event, not to an Observer.

## Integration scoping is bespoke, not shared

Only `Advertiser` applies the `integration_ids` global scope, hand-rolled in its own `booted()`. Don't assume other models are tenant-scoped, and don't extract a shared trait for this without discussing it — it's currently a deliberate one-off.

## Attach custom builders with #[UseEloquentBuilder] (since 2026-11-21)

Wire a model's custom builder with the Laravel 13 attribute `#[UseEloquentBuilder(XBuilder::class)]`. Do not use `HasBuilder` + `$builder` or override `newEloquentBuilder()`. Models that still use `HasBuilder` move to the attribute when you change them.

## @property where Larastan reads a cast wrong (since 2026-11-24)

Larastan types some cast attributes from the column, not from `casts()`: a `boolean` cast on a tinyint column comes out as `int`, and an `AsCollection` cast as `string|null`. Declare the cast type in a class `@property` tag (`@property bool $is_primary`, `@property null|Collection<int, string> $tags`). Add tags only for attributes Larastan gets wrong; do not mirror the whole schema.

## Map legacy timestamp columns

Map Eloquent’s timestamp constants to `time_created` and `time_modified` when the table uses those columns. Map the soft-delete constant to `time_deleted` where applicable.
