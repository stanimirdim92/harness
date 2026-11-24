<?php

declare(strict_types=1);

use App\Support\WorktreeTesting;
use Symfony\Component\Process\Process;

/**
 * Tests share one local Redis server. Each test process leases a block of database indexes by
 * holding a lock file. These tests use a private lock directory and never talk to the server.
 */
function redisLockDirectory(): string
{
    $directory = sys_get_temp_dir().'/lb-redis-locks-'.bin2hex(random_bytes(6));
    mkdir($directory, 0o700);

    return $directory;
}

function removeRedisLockDirectory(string $directory): void
{
    $files = glob($directory.'/*');
    foreach ($files === false ? [] : $files as $file) {
        unlink($file);
    }
    rmdir($directory);
}

/**
 * A Redis configuration like config/database.php: base indexes 16, 1, 14 and 15.
 *
 * @param array<string, mixed> $override
 *
 * @return array<string, mixed>
 */
function appRedisConfiguration(array $override = []): array
{
    $connection = ['url' => null, 'host' => '127.0.0.1', 'password' => null, 'port' => '6379'];

    return array_replace([
        'client' => 'phpredis',
        'options' => ['cluster' => 'redis', 'prefix' => 'app-', 'persistent' => true],
        'default' => [...$connection, 'database' => '16'],
        'cache' => [...$connection, 'database' => '1'],
        'widgets' => [...$connection, 'database' => '14'],
        'socials' => [...$connection, 'database' => '15', 'prefix' => 'socials-'],
    ], $override);
}

it('leases the first block of eight indexes from 32 and skips a block another process holds', function (): void {
    $directory = redisLockDirectory();
    try {
        $first = WorktreeTesting::leaseRedisBlock($directory, 512);
        $second = WorktreeTesting::leaseRedisBlock($directory, 512);
        fclose($first['lock']);
        $third = WorktreeTesting::leaseRedisBlock($directory, 512);

        expect($first['start'])->toBe(32)
            ->and($second['start'])->toBe(40)
            ->and($third['start'])->toBe(32);
        fclose($second['lock']);
        fclose($third['lock']);
    } finally {
        removeRedisLockDirectory($directory);
    }
});

it('never gives two processes the same block', function (): void {
    $directory = redisLockDirectory();
    try {
        $lease = WorktreeTesting::leaseRedisBlock($directory, 512);
        $child = new Process(['php', '-r', 'require $argv[1]; $lease = App\Support\WorktreeTesting::leaseRedisBlock($argv[2], 512); echo $lease["start"];', dirname(__DIR__, 2).'/vendor/autoload.php', $directory]);
        $child->setTimeout(10)->mustRun();

        expect($lease['start'])->toBe(32)
            ->and($child->getOutput())->toBe('40');
        fclose($lease['lock']);
    } finally {
        removeRedisLockDirectory($directory);
    }
});

it('releases a block when its process closes the lease, even while a child process runs', function (): void {
    $directory = redisLockDirectory();
    $child = new Process(['sleep', '30']);
    try {
        $lease = WorktreeTesting::leaseRedisBlock($directory, 512);
        $child->start();
        fclose($lease['lock']);
        $next = WorktreeTesting::leaseRedisBlock($directory, 512);

        expect($next['start'])->toBe($lease['start']);
        fclose($next['lock']);
    } finally {
        $child->stop(0);
        removeRedisLockDirectory($directory);
    }
});

it('fails loudly when no block is free', function (int $databases, int $held): void {
    $directory = redisLockDirectory();
    $locks = [];
    try {
        for ($index = 0; $index < $held; $index++) {
            $locks[] = WorktreeTesting::leaseRedisBlock($directory, $databases)['lock'];
        }

        expect(fn () => WorktreeTesting::leaseRedisBlock($directory, $databases))
            ->toThrow(\RuntimeException::class, "No free block of Redis databases: the shared server has $databases databases");
    } finally {
        array_map(fclose(...), $locks);
        removeRedisLockDirectory($directory);
    }
})->with([
    'a server with the default 16 databases' => [16, 0],
    'a server one index short of a block' => [39, 0],
    'every block held' => [48, 2],
]);

it('maps each base index of the connections to a slot of the block in sorted order', function (): void {
    $configured = WorktreeTesting::redisConfiguration(appRedisConfiguration(), 40, []);

    expect($configured['slots'])->toBe([1 => 0, 14 => 1, 15 => 2, 16 => 3])
        ->and(array_map(fn (array $connection): int => $connection['database'], array_diff_key($configured['config'], array_flip(['client', 'options']))))
        ->toBe(['default' => 43, 'cache' => 40, 'widgets' => 41, 'socials' => 42])
        ->and($configured['config']['options'])->toBe(['prefix' => 'test:'])
        ->and($configured['config']['default']['persistent'])->toBeFalse()
        ->and($configured['config']['default'])->not->toHaveKey('url')
        ->and($configured['config']['socials']['host'])->toBe('127.0.0.1');
});

it('keeps every index when it runs again and appends an index that a later connection adds', function (): void {
    $first = WorktreeTesting::redisConfiguration(appRedisConfiguration(), 40, []);
    $again = WorktreeTesting::redisConfiguration($first['config'], 40, $first['slots']);
    $later = WorktreeTesting::redisConfiguration(
        [...$again['config'], 'horizon' => $again['config']['default'], 'reports' => ['host' => '127.0.0.1', 'port' => '6379', 'database' => 0]],
        40,
        $again['slots'],
    );

    expect($again['config'])->toBe($first['config'])
        ->and($later['slots'])->toBe([1 => 0, 14 => 1, 15 => 2, 16 => 3, 0 => 4])
        ->and($later['config']['horizon']['database'])->toBe(43)
        ->and($later['config']['reports']['database'])->toBe(44)
        ->and($later['config']['default']['database'])->toBe(43);
});

it('fails loudly when the connections use more distinct indexes than a block holds', function (): void {
    $connections = [];
    foreach (range(0, 8) as $database) {
        $connections["c$database"] = ['host' => '127.0.0.1', 'port' => '6379', 'database' => $database];
    }

    expect(fn () => WorktreeTesting::redisConfiguration(['client' => 'phpredis', 'options' => [], ...$connections], 40, []))
        ->toThrow(\RuntimeException::class, 'The Redis connections use 9 distinct database indexes; a test block holds 8.');
    expect(WorktreeTesting::redisConfiguration(['client' => 'phpredis', 'options' => [], ...array_slice($connections, 0, 8)], 40, [])['slots'])->toHaveCount(8);
});

it('refuses a base index inside the range of the test blocks', function (): void {
    expect(fn () => WorktreeTesting::redisConfiguration(appRedisConfiguration(['cache' => ['host' => '127.0.0.1', 'port' => '6379', 'database' => 32]]), 40, []))
        ->toThrow(\RuntimeException::class, 'Redis connection "cache" has a database index outside 0-31.');
});

it('refuses a Redis host that is not this machine', function (string $host): void {
    expect(WorktreeTesting::isLocalRedisHost($host))->toBeFalse()
        ->and(fn () => WorktreeTesting::redisConfiguration(appRedisConfiguration(['widgets' => ['host' => $host, 'port' => '6379', 'database' => 14]]), 40, []))
        ->toThrow(\RuntimeException::class, 'Redis connection "widgets" does not point at a loopback address or a Unix socket');
})->with(['10.0.0.5', 'redis.example.com', '0.0.0.0', '::2', 'tcp://192.168.1.10', '']);

it('accepts loopback addresses, localhost and Unix sockets', function (string $host): void {
    expect(WorktreeTesting::isLocalRedisHost($host))->toBeTrue();
})->with(['127.0.0.1', '127.0.0.2', 'localhost', '::1', '[::1]', 'tcp://127.0.0.1', '/run/redis/redis.sock', 'unix:///run/redis/redis.sock']);

it('refuses connections that point at different servers', function (): void {
    expect(fn () => WorktreeTesting::redisConfiguration(appRedisConfiguration(['widgets' => ['host' => '127.0.0.1', 'port' => '6380', 'database' => 14]]), 40, []))
        ->toThrow(\RuntimeException::class, 'Redis connection "widgets" uses another server than the other connections');
});

it('refuses to flush an index that does not start a test block', function (int $start): void {
    // An unconnected client throws a RedisException on any command, so only the guard can pass.
    expect(fn () => WorktreeTesting::flushRedisBlock(new \Redis(), $start))
        ->toThrow(\RuntimeException::class, "Refusing to flush Redis databases from index $start");
})->with([0, 16, 31, 33, 39]);

/**
 * Run a callback with PEST_MUTATION_TESTING and LB_TEST_REDIS_BLOCK set as given (null unsets),
 * and restore both afterwards.
 *
 * @param array{mutation: ?string, block: ?string} $environment
 * @param \Closure $callback
 */
function withMutationEnvironment(array $environment, \Closure $callback): mixed
{
    $names = ['mutation' => 'PEST_MUTATION_TESTING', 'block' => WorktreeTesting::REDIS_BLOCK_ENV];
    $previous = array_map(static fn (string $name): string|false => getenv($name), $names);
    foreach ($names as $key => $name) {
        putenv($environment[$key] === null ? $name : "$name={$environment[$key]}");
    }

    try {
        return $callback();
    } finally {
        foreach ($names as $key => $name) {
            putenv($previous[$key] === false ? $name : "$name={$previous[$key]}");
        }
    }
}

test('a normal test process leases its own block and ignores an exported block', function (): void {
    $lease = withMutationEnvironment(['mutation' => null, 'block' => '40'], WorktreeTesting::inheritedMutationLease(...));

    expect($lease)->toBeNull();
});

test('a mutation test process reuses the block of its parent without a lock', function (): void {
    $lease = withMutationEnvironment(['mutation' => '/app/Example.php', 'block' => '40'], WorktreeTesting::inheritedMutationLease(...));

    expect($lease)->toBe(['start' => 40, 'lock' => null]);
});

test('a mutation test process without a valid parent block fails instead of waiting for a lock', function (?string $block): void {
    expect(fn () => withMutationEnvironment(['mutation' => '/app/Example.php', 'block' => $block], WorktreeTesting::inheritedMutationLease(...)))
        ->toThrow(\RuntimeException::class, 'found no Redis block from its parent');
})->with([
    'missing' => [null],
    'not a number' => ['abc'],
    'a dev app index' => ['16'],
    'not aligned to a block' => ['41'],
]);
