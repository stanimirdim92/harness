<?php

declare(strict_types=1);

use App\Models\User;
use App\Support\WorktreeTesting;
use Illuminate\Database\Connection;
use Illuminate\Foundation\Application;
use Illuminate\Foundation\Testing\RefreshDatabaseState;
use Illuminate\Support\Facades\{DB, File, Schema};
use PHPUnit\Framework\Attributes\Small;
use Tests\TestCase;

/**
 * DDL makes MySQL commit the test transaction, so RefreshDatabase cannot roll the test back.
 * The next test then repairs the worker database with WorktreeTesting::resetWorkerDatabase()
 * and falls back to a reclone when the repair fails. Each test here calls the repair itself and
 * asserts its result: true means the repair ran, false means the caller reclones.
 */
function workerDatabaseName(): string
{
    return DB::connection()->getDatabaseName();
}

/**
 * The baseline of the worker database as it is now. The worker holds no rows between tests.
 *
 * @return array{fingerprint: string, tables: array<string, string>, migrations: array{max_id: int, checksum: string}, auto_increments: array<string, ?int>}
 */
function workerBaseline(): array
{
    return WorktreeTesting::captureWorkerBaseline(workerDatabaseName())
        ?? throw new \RuntimeException('The worker database is not clean: no baseline can be recorded.');
}

/**
 * @param array{fingerprint: string, tables: array<string, string>, migrations: array{max_id: int, checksum: string}, auto_increments: array<string, ?int>} $baseline
 * @param string $table
 */
function workerCounter(array $baseline, string $table): int
{
    return $baseline['auto_increments'][$table] ?? throw new \RuntimeException("Table $table has no AUTO_INCREMENT counter.");
}

/**
 * A second real connection to this worker's database, configured like the default one.
 *
 * @param string $name
 */
function workerSecondConnection(string $name): Connection
{
    $default = (string) config('database.default');
    config()->set("database.connections.$name", config("database.connections.$default"));
    DB::purge($name);

    return DB::connection($name);
}

test('repairs the rows, columns, tables and migration rows a DDL test committed without a reclone', function (): void {
    $baseline = workerBaseline();

    User::factory()->create();
    DB::table('migrations')->insert(['migration' => 'worker_reset_probe', 'batch' => 999]);
    Schema::table('users', fn ($table) => $table->string('worker_reset_probe')->nullable());
    Schema::drop('advertisers_presets');
    Schema::create('worker_reset_probe', fn ($table) => $table->id());
    expect(DB::connection()->getPdo()->inTransaction())->toBeFalse();

    expect(WorktreeTesting::resetWorkerDatabase($baseline, workerDatabaseName()))->toBeTrue()
        ->and(Schema::hasTable('worker_reset_probe'))->toBeFalse()
        ->and(Schema::hasTable('advertisers_presets'))->toBeTrue()
        ->and(Schema::hasColumn('users', 'worker_reset_probe'))->toBeFalse()
        ->and(DB::table('migrations')->where('migration', 'worker_reset_probe')->exists())->toBeFalse()
        ->and(DB::table('users')->exists())->toBeFalse()
        ->and(workerBaseline())->toBe($baseline);
});

test('restores the AUTO_INCREMENT counters that deleted rows advanced', function (): void {
    $baseline = workerBaseline();

    User::factory()->create();
    DB::table('users')->delete();
    DB::table('migrations')->insert(['migration' => 'worker_reset_probe', 'batch' => 999]);
    $damaged = workerBaseline();
    expect(workerCounter($damaged, 'users'))->toBeGreaterThan(workerCounter($baseline, 'users'))
        ->and(workerCounter($damaged, 'migrations'))->toBeGreaterThan(workerCounter($baseline, 'migrations'));

    expect(WorktreeTesting::resetWorkerDatabase($baseline, workerDatabaseName()))->toBeTrue()
        ->and(User::factory()->create()->id)->toBe(workerCounter($baseline, 'users'))
        ->and(DB::table('migrations')->insertGetId(['migration' => 'worker_reset_probe', 'batch' => 999]))->toBe(workerCounter($baseline, 'migrations'));
});

test('refuses to record a baseline while a table holds rows', function (): void {
    expect(WorktreeTesting::captureWorkerBaseline(workerDatabaseName()))->not->toBeNull();

    User::factory()->create();

    expect(WorktreeTesting::captureWorkerBaseline(workerDatabaseName()))->toBeNull();
});

test('records no baseline when a view makes the schema unsupported', function (): void {
    try {
        DB::statement('CREATE VIEW worker_reset_probe AS SELECT 1 AS id');

        expect(WorktreeTesting::captureWorkerBaseline(workerDatabaseName()))->toBeNull();
    } finally {
        DB::statement('DROP VIEW IF EXISTS worker_reset_probe');
    }
});

test('reports a repair that cannot finish so the caller reclones, and the reclone removes a leftover trigger', function (): void {
    $baseline = workerBaseline();
    DB::unprepared('CREATE TRIGGER worker_reset_probe BEFORE INSERT ON users FOR EACH ROW SET @worker_reset_probe = 1');

    expect(WorktreeTesting::resetWorkerDatabase($baseline, workerDatabaseName()))->toBeFalse();

    $this->migrateDatabases();

    expect(DB::selectOne('SELECT COUNT(*) AS n FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = ?', [workerDatabaseName()])->n)->toBe(0)
        ->and(workerBaseline()['fingerprint'])->toBe($baseline['fingerprint']);
});

test('reports a repair that fails on a view standing in for a table, and the reclone restores the table', function (): void {
    $baseline = workerBaseline();
    Schema::drop('advertisers_presets');
    DB::statement('CREATE VIEW advertisers_presets AS SELECT 1 AS id');

    expect(WorktreeTesting::resetWorkerDatabase($baseline, workerDatabaseName()))->toBeFalse();

    $this->migrateDatabases();

    expect(DB::selectOne("SELECT TABLE_TYPE FROM information_schema.TABLES WHERE TABLE_SCHEMA = ? AND TABLE_NAME = 'advertisers_presets'", [workerDatabaseName()])->TABLE_TYPE)->toBe('BASE TABLE')
        ->and(workerBaseline()['fingerprint'])->toBe($baseline['fingerprint']);
});

test('a test class that seeds the database never takes the repair path', function (): void {
    $seeding = new
    #[Small]
    class('worker-reset-seeding') extends TestCase {
        protected bool $seed = true;

        public function useApplication(Application $app): void
        {
            $this->app = $app;
        }

        public function prepareDatabase(): void
        {
            $this->migrateDatabases();
        }
    };
    $seeding->useApplication($this->app);

    $seeding->prepareDatabase();

    expect(DB::table('users')->count())->toBe(10)
        ->and(workerBaselineIsKept())->toBeFalse();
});

test('a repair that waits on a lock held by another connection gives up and reports false', function (): void {
    $baseline = workerBaseline();
    Schema::table('users', fn ($table) => $table->string('worker_reset_probe')->nullable());
    $other = workerSecondConnection('worker_reset_lock_holder');

    try {
        $other->beginTransaction();
        $other->table('users')->first();

        $started = microtime(true);
        $repaired = WorktreeTesting::resetWorkerDatabase($baseline, workerDatabaseName(), 1);

        expect($repaired)->toBeFalse()
            ->and(microtime(true) - $started)->toBeLessThan(8.0);
    } finally {
        $other->rollBack();
        DB::purge('worker_reset_lock_holder');
    }

    $this->migrateDatabases();
    expect(Schema::hasColumn('users', 'worker_reset_probe'))->toBeFalse();
});

test('a clone that waits on a lock held by another connection fails instead of hanging', function (): void {
    $other = workerSecondConnection('worker_reset_lock_holder');

    try {
        $other->beginTransaction();
        $other->table('users')->first();

        $started = microtime(true);

        expect(fn () => WorktreeTesting::cloneDatabaseFromTemplate((string) getenv('LB_SCHEMA_TEMPLATE'), workerDatabaseName(), 1))
            ->toThrow(\PDOException::class, 'Lock wait timeout exceeded')
            ->and(microtime(true) - $started)->toBeLessThan(8.0);
    } finally {
        $other->rollBack();
        DB::purge('worker_reset_lock_holder');
    }
});

test('opening a second connection to the worker database marks it for repair', function (): void {
    expect(RefreshDatabaseState::$migrated)->toBeTrue();

    workerSecondConnection('worker_reset_second');
    DB::purge('worker_reset_second');

    expect(RefreshDatabaseState::$migrated)->toBeFalse();
});

test('reconnecting the default connection does not mark the worker database for repair', function (): void {
    expect(RefreshDatabaseState::$migrated)->toBeTrue();

    DB::reconnect();

    expect(RefreshDatabaseState::$migrated)->toBeTrue();
});

test('rows a second connection committed are repaired before the next test', function (): void {
    $other = workerSecondConnection('worker_reset_second');
    $other->table('users')->insert(User::factory()->raw());
    DB::purge('worker_reset_second');
    expect(RefreshDatabaseState::$migrated)->toBeFalse();

    $this->migrateDatabases();

    expect(DB::table('users')->count())->toBe(0);
});

/**
 * Whether a kept baseline for this worker database matches the current key.
 */
function workerBaselineIsKept(): bool
{
    return WorktreeTesting::loadWorkerBaseline(workerDatabaseName(), 'none') !== null;
}

/**
 * Rewrite the kept baseline file of this worker database.
 *
 * @param \Closure(array<string, mixed>): array<string, mixed> $change
 *
 * @return \Closure(string): void
 */
function workerBaselineFileChange(\Closure $change): \Closure
{
    return static function (string $path) use ($change): void {
        $kept = json_decode((string) file_get_contents($path), true, 16, JSON_THROW_ON_ERROR);
        file_put_contents($path, json_encode($change($kept), JSON_THROW_ON_ERROR));
    };
}

test('a new run reuses the worker database that the kept baseline describes instead of recloning', function (): void {
    expect(workerBaselineIsKept())->toBeTrue();
    $clones = WorktreeTesting::databaseClones();

    $this->migrateDatabases();

    expect(WorktreeTesting::databaseClones())->toBe($clones)
        ->and(workerBaselineIsKept())->toBeTrue();
});

test('a new run repairs the rows, tables and counters that a crashed earlier run left behind', function (): void {
    $baseline = workerBaseline();
    $clones = WorktreeTesting::databaseClones();
    User::factory()->create();
    Schema::create('worker_reset_probe', fn ($table) => $table->id());
    DB::table('migrations')->insert(['migration' => 'worker_reset_probe', 'batch' => 999]);
    DB::statement('ALTER TABLE users AUTO_INCREMENT = 5000');
    expect(DB::connection()->getPdo()->inTransaction())->toBeFalse();

    $this->migrateDatabases();

    expect(WorktreeTesting::databaseClones())->toBe($clones)
        ->and(Schema::hasTable('worker_reset_probe'))->toBeFalse()
        ->and(DB::table('users')->exists())->toBeFalse()
        ->and(DB::table('migrations')->where('migration', 'worker_reset_probe')->exists())->toBeFalse()
        ->and(workerBaseline())->toBe($baseline);
});

test('a kept baseline that does not match this run makes the worker reclone and keep a new one', function (\Closure $spoil): void {
    $path = WorktreeTesting::workerBaselinePath(workerDatabaseName());
    expect(workerBaselineIsKept())->toBeTrue();
    $spoil($path);
    expect(workerBaselineIsKept())->toBeFalse();
    $clones = WorktreeTesting::databaseClones();

    $this->migrateDatabases();

    expect(WorktreeTesting::databaseClones())->toBe($clones + 1)
        ->and(workerBaselineIsKept())->toBeTrue();
})->with([
    'another template' => workerBaselineFileChange(fn (array $kept): array => array_replace_recursive($kept, ['key' => ['template' => 'leadbuster_tpl_000000000000_000000000000']])),
    'other migration files' => workerBaselineFileChange(fn (array $kept): array => array_replace_recursive($kept, ['key' => ['migrations' => str_repeat('0', 64)]])),
    'another seed setting' => workerBaselineFileChange(fn (array $kept): array => array_replace_recursive($kept, ['key' => ['seed' => 'seed']])),
    'another worker database' => workerBaselineFileChange(fn (array $kept): array => array_replace_recursive($kept, ['key' => ['database' => 'leadbuster_test_other_test_1']])),
    'a baseline of the wrong shape' => workerBaselineFileChange(fn (array $kept): array => array_replace_recursive($kept, ['baseline' => ['migrations' => ['max_id' => '7']]])),
    'unreadable contents' => static function (string $path): void {
        file_put_contents($path, '{"key":');
    },
    'no file' => static function (string $path): void {
        unlink($path);
    },
]);

test('a kept baseline that the database no longer matches makes the worker reclone', function (): void {
    DB::unprepared('CREATE TRIGGER worker_reset_probe BEFORE INSERT ON users FOR EACH ROW SET @worker_reset_probe = 1');
    expect(workerBaselineIsKept())->toBeTrue();
    $clones = WorktreeTesting::databaseClones();

    $this->migrateDatabases();

    expect(WorktreeTesting::databaseClones())->toBe($clones + 1)
        ->and(DB::selectOne('SELECT COUNT(*) AS n FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = ?', [workerDatabaseName()])->n)->toBe(0);
});

test('the migration checksum changes when a migration file is added or changed', function (): void {
    $directory = getenv('LB_TEST_RUNTIME').'/migrations-'.getenv('TEST_TOKEN');
    mkdir($directory);
    try {
        $before = WorktreeTesting::migrationsChecksum();
        app('migrator')->path($directory);
        expect(WorktreeTesting::migrationsChecksum())->toBe($before);

        file_put_contents("$directory/2099_01_01_000000_probe.php", '<?php return 1;');
        $added = WorktreeTesting::migrationsChecksum();
        file_put_contents("$directory/2099_01_01_000000_probe.php", '<?php return 2;');

        expect($added)->not->toBe($before)
            ->and(WorktreeTesting::migrationsChecksum())->not->toBe($added);
    } finally {
        File::deleteDirectory($directory);
    }
});

test('refuses to keep a baseline for another database', function (): void {
    expect(fn () => WorktreeTesting::workerBaselinePath('leadbuster'))
        ->toThrow(\RuntimeException::class, 'Refusing to keep a baseline outside this worker database.');
});
