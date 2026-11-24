---
name: laravel-modules-development
description: "Use for any task or question involving nWidart/laravel-modules. Activate if the user mentions modules, module:make, module commands, or a Modules/ directory structure."
license: MIT
metadata:
  author: nWidart
---

# Laravel Modules Development

## Documentation

Use `search-docs` for detailed laravel-modules patterns and documentation.

## Basic Usage

### Creating a Module

```bash
php artisan module:make Blog
```

### Enabling / Disabling a Module

```bash
php artisan module:enable Blog
php artisan module:disable Blog
```

### Listing Modules

```bash
php artisan module:list
```

### Reading Modules Over HTTP

With `nwidart/laravel-actuator` 1.1.0 or later installed, the `modules` actuator endpoint is registered. It is read-only and not exposed by default: publish the actuator config (`php artisan vendor:publish --tag=actuator-config`) and add `modules` to `actuator.exposure.include` in `config/actuator.php`.

- `GET /actuator/modules`: the package version and every module (`name`, `enabled`, `version`, `description`, `priority`, `providers`).
- `GET /actuator/modules/{name}`: one module. The name is case-insensitive (`blog-post` finds `BlogPost`).

Protect it outside local development: set `actuator.modules.middleware` in `config/actuator.php`.

## Module Structure

A generated module lives under `Modules/Blog/` and contains:

```
Modules/Blog/
  app/
    Http/Controllers/
    Providers/
  config/
  database/
    factories/
    migrations/
    seeders/
  resources/
    assets/
    views/
  routes/
    web.php
    api.php
  tests/
    Feature/
    Unit/
  composer.json
  module.json
  package.json
  vite.config.js
```

## Generating Module Components

### Controller

```bash
php artisan module:make-controller BlogController Blog
php artisan module:make-controller BlogController Blog --api
```

### Model

```bash
php artisan module:make-model Post Blog
php artisan module:make-model Post Blog --migration
php artisan module:make-model Post Blog --attributes --fillable=title,slug
```

### Migration

```bash
php artisan module:make-migration create_posts_table Blog
```

### Seeder

```bash
php artisan module:make-seed PostDatabaseSeeder Blog
```

### Request

```bash
php artisan module:make-request StorePostRequest Blog
```

### Provider

```bash
php artisan module:make-provider BlogServiceProvider Blog
```

### Event & Listener

```bash
php artisan module:make-event PostCreated Blog
php artisan module:make-listener SendPostNotification Blog
```

#### Event discovery

Laravel's event discovery finds listeners inside modules, but the package adds no discovery paths. Add the module listener directories in `bootstrap/app.php`:

```php
->withEvents(discover: [
    __DIR__.'/../app/Listeners',
    __DIR__.'/../Modules/*/app/Listeners',
])
```

- Check the result with `php artisan event:list`.
- In production, `php artisan event:cache` (or `optimize`) caches discovery, so nothing is scanned per request.
- The glob also matches disabled modules. Their listeners are still discovered and run if the class autoloads.
- A module `EventServiceProvider` registers only the listeners in its `$listen` array. It does not discover listeners. Use `withEvents` paths for discovery.
- The package maps files under `modules.paths.modules` to module classes (`Modules/Blog/app/Listeners/X.php` becomes `Modules\Blog\Listeners\X`). A `DiscoverEvents::guessClassNamesUsing()` call you make later, for example in `AppServiceProvider`, replaces this mapping.

### Job

```bash
php artisan module:make-job ProcessPost Blog
php artisan module:make-job-middleware RateLimited Blog
```

Job middleware lands in `Modules/Blog/app/Jobs/Middleware` (namespace `Modules\Blog\Jobs\Middleware`).

### Middleware

```bash
php artisan module:make-middleware EnsureUserIsAdmin Blog
```

### Command

```bash
php artisan module:make-command SyncPosts Blog
```

### Policy

```bash
php artisan module:make-policy PostPolicy Blog
```

### Resource

```bash
# Generate a resource
php artisan module:make-resource PostResource Blog

# Generate a resource collection (--collection, or a name ending in "Collection")
php artisan module:make-resource PostCollection Blog
php artisan module:make-resource Posts Blog --collection

# Generate a JSON:API resource (Laravel 13+; --collection wins over --json-api)
php artisan module:make-resource PostResource Blog --json-api
```

### Config

```bash
php artisan module:make-config stripe Blog
```

Creates `Modules/Blog/config/stripe.php`, read as `config('blog.stripe.key')`. Nested names work: `services/stripe` becomes `config('blog.services.stripe')`.

### Health indicator

```bash
php artisan module:make-health-indicator PaymentsHealthIndicator Blog
```

Creates `Modules/Blog/app/Health/PaymentsHealthIndicator.php`. It needs `nwidart/laravel-actuator` (`composer require nwidart/laravel-actuator`). Register it in the module service provider; the command prints the line:

```php
protected array $healthIndicators = [
    'payments' => \Modules\Blog\Health\PaymentsHealthIndicator::class,
];
```

- The component name is `module:{lowercase module}:{key}` (`module:blog:payments`).
- A value is a class name or `[class, [constructor arguments]]`.
- The package registers a `modules` indicator too. `modules.actuator.enabled` set to `false` turns off both the `modules` indicator and the module indicators. It does not affect the `modules` actuator endpoint.
- With a cached config, run `php artisan config:cache` again after changing `$healthIndicators`.

## Running Module Migrations

```bash
php artisan module:migrate Blog
php artisan module:migrate-fresh Blog
php artisan module:migrate-rollback Blog
php artisan module:migrate-refresh Blog
php artisan module:migrate-reset Blog
php artisan module:migrate-status Blog
php artisan module:seed Blog
```

## Inertia Support

When using Inertia.js inside a module (the stubs target Inertia v3; pass at most one of `--vue`, `--react` and `--svelte`, otherwise the command fails):

```bash
# Generate an Inertia-powered module (--inertia flag)
php artisan module:make Blog --inertia

# Generate an Inertia page inside a module
php artisan module:make-inertia-page Index Blog
php artisan module:make-inertia-page Index Blog --react
php artisan module:make-inertia-page Index Blog --vue
php artisan module:make-inertia-page Index Blog --svelte

# Generate an Inertia component inside a module
php artisan module:make-inertia-component Button Blog

# Publish the Inertia app.js entry point
php artisan module:publish-inertia
```

## Key Conventions

- Module classes are namespaced as `Modules\{ModuleName}` (e.g. `Modules\Blog\Http\Controllers\PostController`).
- Module routes are loaded from `Modules/{Name}/routes/web.php` and `api.php`.
- Module views are referenced as `{lowercase-name}::{view}` (e.g. `blog::index`).
- Module configs live in `Modules/{Name}/config/config.php` and are merged at `{name}`. A copy published with `module:publish-config` (`config/{name}.php`) overrides the module's values.
- Module service providers are auto-discovered from `module.json` `providers` key.
- Keep business logic inside the module; avoid coupling modules together — use events/listeners instead.
- Publish module files to the host application with `module:publish` (static assets), `module:publish-config` (configuration), `module:publish-migration` (migrations), or `module:publish-translation` (translations).
