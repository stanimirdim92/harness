---
paths:
  - 'Modules/*/app/Http/Controllers/**/*.php'
---

# Controllers

## Plain multi-method controllers, no resource/invokable
Write controllers as plain classes with multiple public action methods. Never use `__invoke` and never `Route::resource`/`apiResource`.

## Primitive route params, manual resolution
Type-hint route params as primitives (int/string), never Eloquent models. Resolve records manually via service/repository (`findOrFail`); skip implicit binding and `Route::bind`.
