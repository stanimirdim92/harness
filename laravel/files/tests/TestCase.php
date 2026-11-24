<?php

declare(strict_types=1);

namespace Tests;

use App\Support\WorktreeTesting;
use Illuminate\Foundation\Testing\{RefreshDatabase, TestCase as BaseTestCase};
use Mockery\MockInterface;
use Override;

abstract class TestCase extends BaseTestCase
{
    use RefreshDatabase;

    /**
     * A test that mocks the DB facade replaces the database manager with a Mockery
     * mock, which has no connections to disconnect and rejects unexpected calls.
     */
    #[Override]
    protected function disconnectDatabaseConnections(): void
    {
        if ($this->app->resolved('db') && $this->app->make('db') instanceof MockInterface) {
            return;
        }

        parent::disconnectDatabaseConnections();
    }

    /**
     * Reuse the worker database when it can be repaired to the baseline that a clone kept, in this
     * run or an earlier one. Otherwise clone its schema from the already-migrated template of this
     * checkout's schema snapshot (including migrations-table history) instead of migrate:fresh's
     * drop-all-then-reimport-the-SQL-file cycle, apply only migrations newer than the template,
     * and keep the result as the new baseline. A test class that seeds always reclones.
     */
    protected function migrateDatabases(): void
    {
        $target = (string) config('database.connections.'.config('database.default').'.database');
        $seeder = $this->seeder();
        $seeds = $this->shouldSeed() || $seeder !== false;
        $seed = $seeder !== false ? 'seeder:'.$seeder : ($seeds ? 'seed' : 'none');
        if (!$seeds) {
            $baseline = WorktreeTesting::loadWorkerBaseline($target, $seed);
            if ($baseline !== null && WorktreeTesting::resetWorkerDatabase($baseline, $target)) {
                return;
            }
        }

        WorktreeTesting::forgetWorkerBaseline($target);
        WorktreeTesting::cloneDatabaseFromTemplate((string) getenv('LB_SCHEMA_TEMPLATE'), $target);

        $this->artisan('migrate', $seeder ? ['--seeder' => $seeder] : ['--seed' => $this->shouldSeed()]);
        $baseline = WorktreeTesting::captureWorkerBaseline($target);
        if (!$seeds && $baseline !== null) {
            WorktreeTesting::storeWorkerBaseline($target, $seed, $baseline);
        }
    }
}
