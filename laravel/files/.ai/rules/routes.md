---
paths:
  - 'Modules/*/routes/*.php'
---

# Routes

## Controller-class array handlers only
Route endpoints must use `[Controller::class, 'method']`. Reserve closures for `Route::group()` wrapping, never as the handler itself.

## Group-array middleware assignment
Assign middleware via the route group's `'middleware' => [...]` array. Never use controller `HasMiddleware` or `#[Middleware]` attributes.
