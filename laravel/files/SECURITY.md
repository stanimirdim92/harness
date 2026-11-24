# Security Considerations

- **Authentication**: Breeze-style session controllers (`app/Http/Controllers/Auth`)
  and Sanctum. Web pages and most APIs use `auth:sanctum`; the default guard is
  `web` (`AUTH_GUARD`). `routes/auth.php` enables login, logout, forgot/reset
  password, email verification and password confirmation. Registration stays
  commented out. New accounts arrive only through invitations.

- **Invitations**: `POST /api/v1/invitations` creates an invitation
  (`Modules/Core/app/Services/UserInvitationService.php`). The token is
  64 random characters and only its SHA-256 hash is stored. Guests accept it at
  `/invitations/{token}` (`guest` middleware).

- **Account status**: the `account.active` middleware
  (`Modules/Core/app/Http/Middleware/EnsureAccountIsActive.php`) logs out a
  user whose `status` is not `Active`. It returns 403 for JSON requests and
  redirects to login otherwise. User management can deactivate and reactivate
  users (`Modules/Core/routes/api.php`).

- **Authorization**: two roles, admin and publisher (`User::isAdmin()`,
  `User::isPublisher()`, each cached for one hour). Gates `is-admin` and
  `is-publisher` map to `Modules/Core/app/Policies/UserPolicy.php`.
  Non-admins see only users of their own integration (`UserBuilder`).
  `viewHorizon` requires an admin.

- **Tenant isolation**: `Advertiser::booted()` adds a global `integration_ids`
  scope. It filters every query to the authenticated user's `integration_id`.
  Guests get a never-matching sentinel (`-1`). Code and tests that touch
  `Advertiser` must account for this.

- **API auth toggle**: `REQUIRE_API_AUTH` (`config/leadbuster.php`). It defaults
  to `true` when `APP_ENV=production`, otherwise `false`; `.env.example` sets
  `false`. When it is off, the general API groups run without `auth:sanctum`.
  The user-management and invitation routes always require auth. `phpunit.xml`
  forces it to `true`, so the test suite and CI run the API as production does.

- **Unauthenticated endpoints**:
    - provider webhooks under `/api/v1/socials/*/webhook/{hash}` and the Google/Meta ads webhooks;
    - the public widget posts API (`throttle:120,1`) and the widget embed pages;
    - advertiser and Ticker exports, which check a signed URL
      (`hasValidSignature`) issued to an authenticated user.

- **Rate limiting**: the `api` limiter allows 600 requests/minute per user or
  IP (`AppServiceProvider::configureRateLimiting()`). Route-level throttles:
    - `throttle:6,1` on email verification;
    - `throttle:30,1` on advertiser onboarding;
    - `throttle:10,1` on social-profile retry.

- **Passwords**: in production, `Password::defaults()` requires at least 8
  characters with mixed case, letters and numbers. Other environments set no
  default rule. `BCRYPT_ROUNDS=12` and `SESSION_ENCRYPT=true` in `.env.example`.

- **Secrets**: configuration is env-driven and no secrets are committed.
  Gitleaks runs in the commit hook and in CI on every new commit
  (`.github/workflows/gitleaks.yml`,
  [ADR-0008](docs/adr/0008-shared-quality-hooks-and-ci-gate.md)). CI also runs
  `composer audit` and Yarn audits.

- **Data destruction guard**: `AppServiceProvider::guardDatabase()` calls
  `DB::prohibitDestructiveCommands()` in every environment except a guarded test
  run started by `composer test`. A `testing` environment without that guard
  fails at boot. See [ADR-0004](docs/adr/0004-destructive-commands-prohibited-everywhere.md)
  and [TESTING.md](TESTING.md).

- **Dev-only tooling**: Telescope must stay disabled outside local/dev
  (`TELESCOPE_ENABLED=false` in `.env.example`). Its `viewTelescope` gate allows
  every authenticated user (`app/Providers/TelescopeServiceProvider.php`).
