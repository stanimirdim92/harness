<?php

declare(strict_types=1);

use App\Support\WorktreeTesting;
use Illuminate\Container\Container;
use Illuminate\Foundation\Bootstrap\{LoadConfiguration, LoadEnvironmentVariables};
use Illuminate\Support\Facades\{Config, DB, File, Redis};
use Modules\Core\Helpers\Logging;

it('uses this worker database and its own block of the shared local Redis server', function (): void {
    $token = getenv('TEST_TOKEN');
    expect($token)->not->toBeFalse();
    $expectedDatabase = getenv('LB_TEST_DATABASE').'_test_'.$token;
    expect(DB::connection()->getPdo()->query('SELECT DATABASE()')->fetchColumn())
        ->toBe($expectedDatabase);
    expect((bool) DB::connection()->getPdo()->getAttribute(\PDO::ATTR_PERSISTENT))->toBeFalse();
    expect(config('cache.stores.file.path'))
        ->toBe(getenv('LB_TEST_RUNTIME').'/cache-'.$token);

    // Base indexes from config/database.php, sorted into the slots of the leased block.
    $start = WorktreeTesting::redisBlockStart() ?? throw new \RuntimeException('This process leased no Redis block.');
    $slots = ['cache' => 0, 'widgets' => 1, 'socials' => 2, 'default' => 3];
    expect($start)->toBeGreaterThanOrEqual(WorktreeTesting::REDIS_FIRST_TEST_DATABASE)
        ->and(config('database.redis.options.prefix'))->toBe('test:');
    foreach ($slots as $requiredConnection => $slot) {
        expect(config("database.redis.$requiredConnection.database"))->toBe($start + $slot);
    }
    foreach (array_diff(array_filter(array_keys(Config::array('database.redis')), is_string(...)), ['client', 'options']) as $name) {
        $database = Config::integer("database.redis.$name.database");
        expect(WorktreeTesting::isLocalRedisHost(config("database.redis.$name.host")))->toBeTrue()
            ->and($database)->toBeGreaterThanOrEqual($start)
            ->and($database)->toBeLessThan($start + WorktreeTesting::REDIS_BLOCK_SIZE);
        $client = Redis::connection($name)->client();
        expect($client->getDbNum())->toBe($database);
        $key = 'isolation-check-'.bin2hex(random_bytes(8));
        try {
            $client->setex($key, 10, 'leased');
            expect($client->get($key))->toBe('leased');
        } finally {
            $client->del($key);
        }
    }
});

it('keeps the configuration, route and event caches out of bootstrap/cache', function (): void {
    $runtime = (string) getenv('LB_TEST_RUNTIME');

    expect(app()->getCachedConfigPath())->toBe($runtime.'/config.php')
        ->and(app()->getCachedRoutesPath())->toBe($runtime.'/routes.php')
        ->and(app()->getCachedEventsPath())->toBe($runtime.'/events.php')
        ->and(app()->routesAreCached())->toBeFalse()
        ->and(app()->eventsAreCached())->toBeFalse();
});

it('writes the logs of this worker to a directory that no other worker uses', function (): void {
    $storage = getenv('LB_TEST_RUNTIME').'/storage-'.getenv('TEST_TOKEN');
    $realStorage = base_path('storage');
    $probe = 'worktree_isolation_probe';

    try {
        Logging::log_response($probe)->info('isolation probe');
        $written = File::glob(storage_path("logs/socials/$probe/responses-*.log"));

        expect(storage_path())->toBe($storage)
            ->and(config('logging.channels.single.path'))->toBe($storage.'/logs/laravel.log')
            ->and(config('logging.channels.daily.path'))->toBe($storage.'/logs/laravel.log')
            ->and(config('logging.channels.socials_responses.path'))->toBe($storage.'/logs/socials/')
            ->and(config('filesystems.disks.local.root'))->toBe($storage.'/app/private')
            ->and(config('filesystems.disks.public.root'))->toBe($storage.'/app/public')
            ->and($written)->toHaveCount(1)
            ->and(file_get_contents($written[0]))->toContain('isolation probe')
            ->and(str_starts_with($written[0], $storage.'/logs/socials/'))->toBeTrue()
            ->and(is_dir("$realStorage/logs/socials/$probe"))->toBeFalse();
    } finally {
        File::deleteDirectory(storage_path("logs/socials/$probe"));
    }
});

it('preserves the template foreign keys in each worker', function (): void {
    $foreignKeys = static fn (string $database): array => DB::select(
        'SELECT TABLE_NAME, CONSTRAINT_NAME, REFERENCED_TABLE_NAME, UPDATE_RULE, DELETE_RULE
         FROM information_schema.REFERENTIAL_CONSTRAINTS
         WHERE CONSTRAINT_SCHEMA = ? ORDER BY TABLE_NAME, CONSTRAINT_NAME',
        [$database],
    );

    expect($foreignKeys(DB::connection()->getDatabaseName()))
        ->toEqual($foreignKeys((string) getenv('LB_SCHEMA_TEMPLATE')));
});

/**
 * A client of the shared server with the connection settings of the tests.
 */
function sharedRedisClient(): \Redis
{
    $client = new \Redis();
    $client->connect(Config::string('database.redis.default.host'), (int) Config::string('database.redis.default.port'), 2.0);
    $password = config('database.redis.default.password');
    if (is_string($password) && $password !== '') {
        $client->auth($password);
    }

    return $client;
}

it('empties only the indexes of the leased block', function (): void {
    $client = sharedRedisClient();
    $first = WorktreeTesting::leaseRedisBlock(WorktreeTesting::lockDirectory(), 512);
    $second = WorktreeTesting::leaseRedisBlock(WorktreeTesting::lockDirectory(), 512);
    $key = 'flush-probe-'.bin2hex(random_bytes(6));
    try {
        foreach ([$first['start'], $first['start'] + 7, $second['start']] as $database) {
            $client->select($database);
            $client->set($key, 'probe');
        }

        WorktreeTesting::flushRedisBlock($client, $first['start']);

        $kept = static function (int $database) use ($client, $key): bool {
            $client->select($database);

            return $client->exists($key) === 1;
        };
        expect($kept($first['start']))->toBeFalse()
            ->and($kept($first['start'] + 7))->toBeFalse()
            ->and($kept($second['start']))->toBeTrue();
    } finally {
        $client->select($second['start']);
        $client->del($key);
        $client->close();
        fclose($first['lock']);
        fclose($second['lock']);
    }
});

/**
 * Runs $check with the given environment variables replaced, then restores them.
 *
 * @param array<string, null|string> $overrides null unsets the variable
 * @param \Closure(): mixed $check
 */
function withTestEnvironment(array $overrides, \Closure $check): void
{
    $originals = [];
    foreach ($overrides as $name => $value) {
        $originals[$name] = getenv($name);
        putenv($value === null ? $name : "$name=$value");
    }
    try {
        $check();
    } finally {
        foreach ($originals as $name => $original) {
            putenv($original === false ? $name : "$name=$original");
        }
    }
}

it('refuses a run that the runner did not prepare', function (array $overrides): void {
    withTestEnvironment(
        $overrides,
        static fn () => expect(fn () => WorktreeTesting::assertContext(base_path()))
            ->toThrow(\RuntimeException::class, 'Run backend tests through composer test or bin/worktree-test.sh.'),
    );
})->with([
    'another environment' => [['APP_ENV' => 'local']],
    'no environment' => [['APP_ENV' => null]],
    'another checkout database' => [['LB_TEST_DATABASE' => 'leadbuster_test_00000000000000000000']],
    'runtime outside /tmp/lb-test' => [['LB_TEST_RUNTIME' => '/tmp/other.abcdefghij']],
    'runtime with a short suffix' => [['LB_TEST_RUNTIME' => '/tmp/lb-test.abc']],
    'no runtime' => [['LB_TEST_RUNTIME' => null]],
]);

it('refuses a cached configuration or a redirected configuration cache', function (string $value): void {
    $runtime = (string) getenv('LB_TEST_RUNTIME');
    $created = $runtime.'/config.php';
    try {
        if ($value === 'create') {
            file_put_contents($created, '<?php return [];');
        }
        withTestEnvironment(
            ['APP_CONFIG_CACHE' => $value === 'create' ? $created : $value],
            static fn () => expect(fn () => WorktreeTesting::assertContext(base_path()))
                ->toThrow(\RuntimeException::class, 'Cached configuration is forbidden in this test run.'),
        );
    } finally {
        if (is_file($created)) {
            unlink($created);
        }
    }
})->with([
    'bootstrap/cache' => ['/var/www/bootstrap/cache/config.php'],
    'cached file in the runtime' => ['create'],
]);

it('refuses a template clone with an unsafe name, onto itself or outside this worker', function (string $template, string $target, string $message): void {
    $names = ['{template}' => (string) getenv('LB_SCHEMA_TEMPLATE'), '{worker}' => getenv('LB_TEST_DATABASE').'_test_'.getenv('TEST_TOKEN')];

    expect(fn () => WorktreeTesting::cloneDatabaseFromTemplate(strtr($template, $names), strtr($target, $names)))
        ->toThrow(\RuntimeException::class, $message);
})->with([
    'unsafe template name' => ['{template};x', '{worker}', 'Invalid database identifier for template clone.'],
    'unsafe target name' => ['{template}', '{worker}-x', 'Invalid database identifier for template clone.'],
    'onto itself' => ['{template}', '{template}', 'Refusing to clone the template database onto itself.'],
    'another template' => ['leadbuster_tpl_000000000000', '{worker}', 'Refusing to clone outside this worker database.'],
    'another target' => ['{template}', 'leadbuster_audit_not_this_worker', 'Refusing to clone outside this worker database.'],
]);

it('refuses to clone from a template that holds no tables', function (): void {
    $emptyTemplate = 'leadbuster_tpl_empty_'.bin2hex(random_bytes(6));
    $worker = getenv('LB_TEST_DATABASE').'_test_'.getenv('TEST_TOKEN');

    withTestEnvironment(
        ['LB_SCHEMA_TEMPLATE' => $emptyTemplate],
        static fn () => expect(fn () => WorktreeTesting::cloneDatabaseFromTemplate($emptyTemplate, $worker))
            ->toThrow(\RuntimeException::class, 'Schema template is empty; rerun composer test to rebuild it from the snapshot.'),
    );
});

it('refuses a Redis cluster configuration', function (array $clusters): void {
    $redis = [
        'client' => 'phpredis',
        'default' => ['host' => '127.0.0.1', 'port' => '6379', 'database' => '0'],
        'clusters' => $clusters,
    ];

    expect(fn () => WorktreeTesting::redisConfiguration($redis, 32, []))
        ->toThrow(\RuntimeException::class, 'Redis cluster configuration needs explicit test support.');
})->with([
    'one cluster' => [['default' => [['host' => '127.0.0.1', 'port' => '6379', 'database' => '0']]]],
    'a cluster that points at a remote host' => [['default' => [['host' => 'redis.example.com', 'port' => '6379']]]],
]);

it('drops an empty clusters entry and keeps the connection in the block', function (): void {
    $redis = [
        'client' => 'phpredis',
        'default' => ['host' => '127.0.0.1', 'port' => '6379', 'database' => '0'],
        'clusters' => [],
    ];

    $result = WorktreeTesting::redisConfiguration($redis, 32, []);

    expect($result['config'])->not->toHaveKey('clusters')
        ->and($result['config']['default']['database'])->toBe(32);
});

it('refuses to record or repair a baseline outside this worker database', function (string $target): void {
    $baseline = ['fingerprint' => '', 'tables' => [], 'migrations' => ['max_id' => 0, 'checksum' => ''], 'auto_increments' => []];

    expect(fn () => WorktreeTesting::captureWorkerBaseline($target))
        ->toThrow(\RuntimeException::class, 'Refusing to reset outside this worker database.')
        ->and(fn () => WorktreeTesting::resetWorkerDatabase($baseline, $target))
        ->toThrow(\RuntimeException::class, 'Refusing to reset outside this worker database.');
})->with(['leadbuster', 'leadbuster_test', 'leadbuster_audit_not_this_worker']);

it('refuses a parallel test token that is not a small number', function (string $token): void {
    $current = Container::getInstance();
    $fresh = require base_path('bootstrap/app.php');
    try {
        withTestEnvironment(
            ['TEST_TOKEN' => $token],
            static fn () => expect(fn () => $fresh->bootstrapWith([LoadEnvironmentVariables::class, LoadConfiguration::class]))
                ->toThrow(\RuntimeException::class, 'Unsupported parallel test token.'),
        );
    } finally {
        Container::setInstance($current);
    }
})->with([
    'letters' => ['abc'],
    'leading zero' => ['01'],
    'seven digits' => ['1000000'],
    'a minus sign' => ['-1'],
    'a trailing newline' => ["1\n"],
    'a space' => ['1 '],
]);

it('accepts the smallest and the largest parallel test token', function (string $token): void {
    $current = Container::getInstance();
    $fresh = require base_path('bootstrap/app.php');
    try {
        withTestEnvironment(
            ['TEST_TOKEN' => $token],
            static fn () => expect(fn () => $fresh->bootstrapWith([LoadEnvironmentVariables::class, LoadConfiguration::class]))
                ->not->toThrow(\RuntimeException::class),
        );
    } finally {
        Container::setInstance($current);
    }
})->with(['zero' => '0', 'six digits' => '999999']);
