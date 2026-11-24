# Pest

- This project uses Pest. Create tests with `php artisan make:test --pest {name}`. Do not include the suite directory in `{name}`.
- Read the `testing-best-practices` skill for coverage, naming, structure and isolation.
- Do not delete tests or test files without approval.
- Run tests only with `composer test` and pass the narrowest selector: `composer test -- --filter=testName` or a file path. Direct `php artisan test` and `vendor/bin/pest` runs are rejected.
- Rerun a test after each change to it. After the targeted tests pass, ask the user to run the full suite with `composer test`.
