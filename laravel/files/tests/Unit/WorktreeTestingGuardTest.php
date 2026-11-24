<?php

declare(strict_types=1);

use App\Support\WorktreeTesting;
use Symfony\Component\Process\Process;

it('accepts only the explicitly allowed mysql database', function (): void {
    expect(fn () => WorktreeTesting::assertDatabaseConfig(
        ['driver' => 'mysql', 'database' => 'leadbuster_test_example', 'url' => '', 'read' => [], 'options' => []],
        ['leadbuster_test_example'],
    ))->not->toThrow(\RuntimeException::class);
});

it('rejects a missing or null database name', function (array $connection): void {
    expect(fn () => WorktreeTesting::assertDatabaseConfig($connection, ['leadbuster_test_example']))
        ->toThrow(\RuntimeException::class, 'Unsafe test DB configuration');
})->with([
    'null' => [['driver' => 'mysql', 'database' => null]],
    'missing' => [['driver' => 'mysql']],
    'missing driver' => [['database' => 'leadbuster_test_example']],
]);

it('rejects a run context that the runner did not prepare', function (string $variable, ?string $value): void {
    $original = getenv($variable);
    $runtime = (string) getenv('LB_TEST_RUNTIME');

    try {
        putenv($value === null ? $variable : $variable.'='.str_replace('{runtime}', $runtime, $value));

        expect(fn () => WorktreeTesting::assertContext(dirname(__DIR__, 2)))
            ->toThrow(\RuntimeException::class, 'Run backend tests through composer test or bin/worktree-test.sh.');
    } finally {
        putenv($original === false ? $variable : $variable.'='.$original);
    }
})->with([
    'not the testing environment' => ['APP_ENV', 'local'],
    'no environment' => ['APP_ENV', null],
    'database of another checkout' => ['LB_TEST_DATABASE', 'leadbuster_test_00000000000000000000'],
    'no runtime' => ['LB_TEST_RUNTIME', null],
    'runtime outside the runner pattern' => ['LB_TEST_RUNTIME', '/tmp/lb-test.short'],
    'runtime pattern with a suffix' => ['LB_TEST_RUNTIME', '{runtime}x'],
    'runtime that does not exist' => ['LB_TEST_RUNTIME', '/tmp/lb-test.0000000000'],
]);

it('rejects a prepared runtime directory whose name only starts like the runner pattern', function (): void {
    $runtime = (string) getenv('LB_TEST_RUNTIME');
    $suffixedRuntime = $runtime.'x';
    $root = (string) realpath(dirname(__DIR__, 2));

    try {
        mkdir($suffixedRuntime);
        file_put_contents($suffixedRuntime.'/checkout', $root);
        putenv('LB_TEST_RUNTIME='.$suffixedRuntime);

        expect(fn () => WorktreeTesting::assertContext($root))
            ->toThrow(\RuntimeException::class, 'Run backend tests through composer test or bin/worktree-test.sh.');
    } finally {
        putenv('LB_TEST_RUNTIME='.$runtime);
        if (is_file($suffixedRuntime.'/checkout')) {
            unlink($suffixedRuntime.'/checkout');
        }
        if (is_dir($suffixedRuntime)) {
            rmdir($suffixedRuntime);
        }
    }
});

it('rejects a run context of another checkout', function (): void {
    expect(fn () => WorktreeTesting::assertContext(sys_get_temp_dir()))
        ->toThrow(\RuntimeException::class, 'Run backend tests through composer test or bin/worktree-test.sh.');
});

it('rejects a runtime whose checkout file names another checkout', function (): void {
    $runtime = (string) getenv('LB_TEST_RUNTIME');
    $checkoutFile = $runtime.'/checkout';
    $original = (string) file_get_contents($checkoutFile);

    try {
        file_put_contents($checkoutFile, '/var/www/another-checkout');

        expect(fn () => WorktreeTesting::assertContext(dirname(__DIR__, 2)))
            ->toThrow(\RuntimeException::class, 'Run backend tests through composer test or bin/worktree-test.sh.');
    } finally {
        file_put_contents($checkoutFile, $original);
    }
});

it('rejects a cached configuration file or a configuration cache that points elsewhere', function (?string $value): void {
    $runtime = (string) getenv('LB_TEST_RUNTIME');
    $original = getenv('APP_CONFIG_CACHE');
    $created = $runtime.'/config.php';

    try {
        putenv($value === null ? 'APP_CONFIG_CACHE' : 'APP_CONFIG_CACHE='.str_replace('{runtime}', $runtime, $value));
        if ($value === '{runtime}/config.php') {
            file_put_contents($created, '<?php return [];');
        }

        expect(fn () => WorktreeTesting::assertContext(dirname(__DIR__, 2)))
            ->toThrow(\RuntimeException::class, 'Cached configuration is forbidden in this test run.');
    } finally {
        if (is_file($created)) {
            unlink($created);
        }
        putenv($original === false ? 'APP_CONFIG_CACHE' : 'APP_CONFIG_CACHE='.$original);
    }
})->with([
    'unset' => [null],
    'in bootstrap/cache' => ['/var/www/bootstrap/cache/config.php'],
    'file exists' => ['{runtime}/config.php'],
]);

it('refuses to clone the template outside this worker database before any statement runs', function (string $template, string $target, string $message): void {
    $template = str_replace('{template}', (string) getenv('LB_SCHEMA_TEMPLATE'), $template);
    $target = str_replace(
        ['{template}', '{worker}'],
        [(string) getenv('LB_SCHEMA_TEMPLATE'), getenv('LB_TEST_DATABASE').'_test_'.getenv('TEST_TOKEN')],
        $target,
    );

    expect(fn () => WorktreeTesting::cloneDatabaseFromTemplate($template, $target))
        ->toThrow(\RuntimeException::class, $message);
})->with([
    'invalid template identifier' => ['bad-name', '{worker}', 'Invalid database identifier for template clone.'],
    'invalid target identifier' => ['{template}', 'leadbuster`; DROP', 'Invalid database identifier for template clone.'],
    'template onto itself' => ['{template}', '{template}', 'Refusing to clone the template database onto itself.'],
    'the local database as target' => ['{template}', 'leadbuster', 'Refusing to clone outside this worker database.'],
    'another template' => ['leadbuster', '{worker}', 'Refusing to clone outside this worker database.'],
]);

it('shares the backend lock across different launcher environments', function (string|false $runtime): void {
    $root = dirname(__DIR__, 2);
    $process = new Process(['bash', 'bin/worktree-test.sh', '--filter=WorktreeIsolation'], $root, ['XDG_RUNTIME_DIR' => $runtime]);
    $process->setTimeout(10)->run();

    expect($process->getExitCode())->toBe(1);
    expect($process->getErrorOutput())->toContain('another backend test run, setup, or schema refresh is active');
})->with(['/tmp/different-launcher-runtime', false]);

it('accepts the run context that the runner prepares', function (): void {
    expect(fn () => WorktreeTesting::assertContext(dirname(__DIR__, 2)))->not->toThrow(\RuntimeException::class);
});

it('rejects a cached route or event file, or a redirect that points elsewhere', function (string $variable, string $file, ?string $value): void {
    $runtime = (string) getenv('LB_TEST_RUNTIME');
    $original = getenv($variable);
    $created = $runtime.'/'.$file;

    try {
        putenv($value === null ? $variable : $variable.'='.str_replace('{runtime}', $runtime, $value));
        if ($value === 'create') {
            putenv($variable.'='.$created);
            file_put_contents($created, '<?php return [];');
        }

        expect(fn () => WorktreeTesting::assertContext(dirname(__DIR__, 2)))
            ->toThrow(\RuntimeException::class, 'forbidden in this test run');
    } finally {
        if (is_file($created)) {
            unlink($created);
        }
        putenv($original === false ? $variable : $variable.'='.$original);
    }
})->with([
    'routes unset' => ['APP_ROUTES_CACHE', 'routes.php', null],
    'routes in bootstrap/cache' => ['APP_ROUTES_CACHE', 'routes.php', '/var/www/bootstrap/cache/routes-v7.php'],
    'routes file exists' => ['APP_ROUTES_CACHE', 'routes.php', 'create'],
    'events unset' => ['APP_EVENTS_CACHE', 'events.php', null],
    'events in bootstrap/cache' => ['APP_EVENTS_CACHE', 'events.php', '/var/www/bootstrap/cache/events.php'],
    'events file exists' => ['APP_EVENTS_CACHE', 'events.php', 'create'],
]);

it('rejects unsafe database configuration', function (array $override): void {
    $configuration = array_replace(['driver' => 'mysql', 'database' => 'leadbuster_test_example'], $override);
    expect(fn () => WorktreeTesting::assertDatabaseConfig($configuration, ['leadbuster_test_example']))
        ->toThrow(\RuntimeException::class);
})->with([
    'production' => [['database' => 'leadbuster']],
    'old shared test database' => [['database' => 'leadbuster_test']],
    'another checkout' => [['database' => 'leadbuster_test_other']],
    'another driver' => [['driver' => 'sqlite']],
    'connection url' => [['url' => 'mysql://user:password@localhost/leadbuster']],
    'read override' => [['read' => ['database' => 'leadbuster']]],
    'write override' => [['write' => ['database' => 'leadbuster']]],
    'direct override' => [['direct' => ['database' => 'leadbuster']]],
    'pdo init command' => [['options' => [1002 => 'USE leadbuster']]],
]);
