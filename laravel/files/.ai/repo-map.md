Quick-scan directory lookup. For _why_ the modules are shaped this way, see ARCHITECTURE.md §1 and DESIGN.md — this file is the mechanical map, not the rationale.

## Root Documentation

- `AGENTS.md` — Agent instructions: Laravel Boost guidelines, worktree/test isolation rules, design-system redesign rules
- `ARCHITECTURE.md` — System architecture and design decisions
- `REVIEW.md` — Code review guidance
- `COMMANDS.md` — Dev-command reference (setup, run, lint, artisan-discovery shell commands)
- `CONVENTIONS.md` — Code conventions and standards
- `DESIGN.md` — Design principles and patterns
- `README.md` — Project overview and getting started
- `SECURITY.md` — Security guidelines and policies
- `TESTING.md` — Testing strategies and best practices

## Modules (Core, Advertisers, Socials)

Each module follows this structure:

### Modules/{Module}/app/

- `Builders/` — Query builder classes for complex queries
- `Console/Commands/` — Artisan console commands
- `Contracts/` — Interfaces and contracts
- `Data/` — `spatie/laravel-data` DTOs
- `Enums/` — Enumeration classes
- `Events/`, `Listeners/` — Cross-module domain events and their handlers
- `Exceptions/` — Custom exception classes
- `Helpers/` — Helper functions and classes
- `Http/Controllers/` — HTTP controllers
- `Http/Middleware/` — HTTP middleware
- `Http/Requests/` — Form request validation
- `Http/Resources/` — API resource formatters
- `Jobs/` — Queueable job classes
- `Models/` — Eloquent model classes
- `Policies/` — Authorization policies
- `Providers/` — Service providers
- `Repositories/` — Data access layer classes
- `Services/` — Business logic and services

### Modules/{Module}/database/

- `migrations/` — Database migration files
- `factories/` — Model factory classes
- `seeders/` — Database seeder classes

### Modules/{Module}/routes/

- `api.php` — API route definitions
- `web.php` — Web route definitions

## Frontend Resources

- `resources/js/pages/` — Inertia page components
- `resources/js/components/` — Reusable React components
- `resources/js/layouts/` — Layout components
- `resources/js/hooks/` — Custom React hooks
- `resources/js/types/` — TypeScript type definitions
- `resources/js/utils/` — Utility functions and helpers
- `resources/js/components/icons/` — SVG icons exported from Figma
- `resources/css/app.css` — Tailwind 4 `@theme` with `lb-*` design tokens

## Tests

- `tests/Feature/` — Feature/integration tests
- `tests/Unit/` — Unit tests
- `tests/Pest.php` — Pest testing configuration
- `tests/TestCase.php` — Base test case class (RefreshDatabase, clones schema template)
- `tests/bootstrap.php` — Rejects test runs not started by `composer test`
- `resources/js/**/*.test.ts(x)` — Vitest frontend tests, next to their source

## Documentation

- `docs/MEMORY.md` — Project memory and decisions index
- `docs/USER-GUIDE.md` — End-user guide
- `docs/adr/` — Architecture Decision Records (ADRs)
- `docs/specs/` — Feature specifications and requirements (incl. `DESIGN-SYSTEM-SPEC.md`)
- `docs/tasks/` — Per-ticket plans and open-work notes
- `docs/structurizr/*.dsl` — Structurizr DSL architecture diagrams

## Project Rules and Skills

- `.ai/rules/` — Path-specific rules and guidelines (index.md maps glob patterns to rule files)
- `.ai/skills/` — Core project skills and domain expertise
- `.ai/mcp/` — MCP server configuration
- `.ai/workflows/` — Workflow definitions and automation

## Agent Skills and Utilities

- `.agents/skills/` — Reusable agent skill definitions (mix of symlinks to .ai/skills and standalone skills)
- `.claude/skills/` — Claude-specific skill implementations (includes symlinks to .ai/skills)

## Infrastructure and Configuration

- `config/` — Laravel configuration files
- `database/migrations/` — Root-level database migrations
- `database/factories/` — Root-level model factories
- `database/seeders/` — Root-level database seeders
- `routes/api.php` — Root-level API route definitions
- `routes/auth.php` — Authentication routes
- `routes/console.php` — Console command route definitions
- `routes/web.php` — Root-level web route definitions
- `database/schema/` — Committed schema snapshot (SQL, fingerprint, checksum) for test templates
- `app/Support/` — Test-isolation helpers (`WorktreeTesting`, `TestSchema`, `WorktreeDatabaseRegistry`)
- `bin/` — Worktree setup/doctor/test runner, schema snapshot/refresh, database cleanup, quality hooks
- `.github/workflows/` — CI (`ci.yml`) and secret scanning (`gitleaks.yml`)
- `.githooks/`, `.pre-commit-config.yaml` — Shared pre-commit hooks (ADR-0008)
- `deptrac.php`, `phpstan.neon`, `pint.json`, `eslint.config.js` — Static-analysis and style config
