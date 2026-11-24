#!/usr/bin/env php
<?php

declare(strict_types=1);

use App\Support\{TestSchema, WorktreeDatabaseRegistry};
use Illuminate\Database\Connectors\ConnectionFactory;
use Illuminate\Database\QueryException;
use Illuminate\Foundation\Application;
use Illuminate\Foundation\Bootstrap\{LoadConfiguration, LoadEnvironmentVariables};

require dirname(__DIR__).'/vendor/autoload.php';
umask(0o077);
$report = false;

try {
    $root = dirname(__DIR__);
    $arguments = array_slice($argv, 1);
    if ($arguments === ['--help']) {
        echo "Usage: php bin/worktree-databases.php [--apply] [--checkout PATH] [--report]\n";
        echo "Default: inventory and dry-run for recorded owners whose checkouts were removed.\n";
        echo "--checkout PATH explicitly retires only that recorded checkout's idle databases.\n";
        echo "Schema templates (leadbuster_tpl_*) that no registered worktree's snapshot uses are swept without --checkout.\n";
        echo "Orphaned schema staging databases (leadbuster_test_stage_*, leadbuster_test_backup_*) are swept without --checkout, only while no test run holds a template lock.\n";
        echo "--register PATH records a Git worktree owner (also used by the test runner).\n";
        echo "--report emits a readable SessionStart message for Claude.\n";
        exit(0);
    }
    $register = null;
    $checkout = null;
    $apply = false;
    while ($arguments !== []) {
        $argument = array_shift($arguments);
        if (in_array($argument, ['--register', '--checkout'], true) && isset($arguments[0]) && !str_starts_with($arguments[0], '--')) {
            if ($argument === '--register' && $register === null) {
                $register = array_shift($arguments);
            } elseif ($argument === '--checkout' && $checkout === null) {
                $checkout = array_shift($arguments);
            } else {
                throw new \RuntimeException('Repeated checkout argument.');
            }
        } elseif ($argument === '--apply' && !$apply) {
            $apply = true;
        } elseif ($argument === '--report' && !$report) {
            $report = true;
        } else {
            throw new \RuntimeException('Invalid arguments; use --help.');
        }
    }
    $registry = new WorktreeDatabaseRegistry($root);
    if ($register !== null) {
        if ($apply || $checkout !== null || $report) {
            throw new \RuntimeException('Registration cannot be combined with cleanup.');
        }
        $inheritedLock = is_file('/proc/self/fd/9') ? fopen('php://fd/9', 'rb') : false;
        $registry->register($register, $inheritedLock === false ? null : $inheritedLock);
        echo 'Registered '.WorktreeDatabaseRegistry::databaseNamespace(realpath($register)).PHP_EOL;
        exit(0);
    }
    if (!is_file($root.'/.env.testing')) {
        throw new \RuntimeException('Missing .env.testing; run worktree setup first.');
    }
    foreach (array_keys(getenv()) as $key) {
        if (str_starts_with($key, 'DB_') || str_starts_with($key, 'LB_TEST_')
            || in_array($key, ['DATABASE_URL', 'APP_ENV', 'APP_CONFIG_CACHE', 'TEST_TOKEN', 'UNIQUE_TEST_TOKEN'], true)) {
            putenv($key);
            unset($_ENV[$key], $_SERVER[$key]);
        }
    }
    $cachePath = sys_get_temp_dir().'/lb-database-config-'.bin2hex(random_bytes(12)).'.php';
    putenv('APP_CONFIG_CACHE='.$cachePath);
    $_ENV['APP_CONFIG_CACHE'] = $_SERVER['APP_CONFIG_CACHE'] = $cachePath;
    $app = new Application($root);
    $app->loadEnvironmentFrom('.env.testing');
    $app->bootstrapWith([LoadEnvironmentVariables::class, LoadConfiguration::class]);
    $config = $app['config'];
    $connectionConfig = $config->get('database.connections.'.$config->get('database.default'), []);
    if (($connectionConfig['driver'] ?? null) !== 'mysql' || !empty($connectionConfig['url'])
        || !empty($connectionConfig['read']) || !empty($connectionConfig['write']) || !empty($connectionConfig['direct'])
        || isset($connectionConfig['options'][1002])) {
        throw new \RuntimeException('Expected direct MySQL configuration without URL, replica, direct or init-command overrides.');
    }
    $connectionConfig['database'] = 'information_schema';
    $connectionConfig['options'][\PDO::ATTR_PERSISTENT] = false;
    $connection = new ConnectionFactory($app)->make($connectionConfig);
    $pdo = $connection->getPdo();
    if ($pdo->query('SELECT DATABASE()')->fetchColumn() !== 'information_schema') {
        throw new \RuntimeException('Unexpected database administration connection.');
    }
    $pdo->exec('SET SESSION lock_wait_timeout = 5');
    $grants = $pdo->query('SHOW GRANTS')->fetchAll(\PDO::FETCH_COLUMN);
    if (!array_any($grants, static fn (string $grant): bool => preg_match('/^GRANT (?:ALL PRIVILEGES|[^\n]*\bPROCESS\b[^\n]*) ON \*\.\* /', $grant) === 1)) {
        throw new \RuntimeException('PROCESS privilege is required to rule out active sessions across all database users.');
    }
    $databases = $pdo->query('SHOW DATABASES')->fetchAll(\PDO::FETCH_COLUMN);
    $sessions = $pdo->prepare('SELECT COUNT(*) FROM information_schema.PROCESSLIST WHERE DB = ?');
    $rows = $registry->inspect(
        $databases,
        static function (string $database) use ($sessions): int {
            $sessions->execute([$database]);

            return (int) $sessions->fetchColumn();
        },
        static function (string $database) use ($pdo): void {
            $pdo->exec("DROP DATABASE `$database`");
        },
        $apply,
        $checkout,
    );
    if ($report) {
        $lines = ['Database cleanup: checked ownership and worktree existence; checked locks and active connections for deletion candidates.'];
        $counts = array_count_values(array_column($rows, 'status'));
        foreach ($rows as $row) {
            $reason = TestSchema::isTemplate($row['database']) ? match ($row['status']) {
                'retained' => $checkout === null
                    ? 'KEPT: schema template of a registered worktree\'s snapshot'
                    : 'KEPT: templates are swept only without --checkout',
                'busy' => 'SKIPPED: a test run holds the template lock or a database connection is active',
                'would-drop' => 'WOULD DELETE: no registered worktree uses this schema snapshot (preview only)',
                'dropped' => 'DELETED: no registered worktree uses this schema snapshot',
            } : (WorktreeDatabaseRegistry::isStagingDatabase($row['database']) && $row['checkout'] === null ? match ($row['status']) {
                'busy' => 'SKIPPED: a test run holds a template lock or a database connection is active',
                'would-drop' => 'WOULD DELETE: orphaned schema staging database, no test run is active (preview only)',
                'dropped' => 'DELETED: orphaned schema staging database, no test run was active',
                default => 'KEPT: orphaned schema staging databases are swept only without --checkout',
            } : match ($row['status']) {
                'protected' => 'PROTECTED: application database or shared test template',
                'unknown' => 'KEPT: no recorded owner; automatic deletion is forbidden',
                'retained' => $checkout === null || $checkout === $row['checkout']
                    ? 'KEPT: worktree still exists or is registered'
                    : 'KEPT: another checkout was selected',
                'busy' => 'SKIPPED: backend lock or database connection is active',
                'would-drop' => 'WOULD DELETE: recorded worktree retired and databases idle (preview only)',
                'dropped' => 'DELETED: recorded worktree retired and databases idle',
            });
            $owner = $row['checkout'] === null ? '' : ' ['.basename($row['checkout']).']';
            $lines[] = $row['database'].$owner.': '.$reason;
        }
        $lines[] = sprintf(
            'Cleanup complete: %d checked, %d deleted, %d kept, %d protected, %d busy, %d eligible in preview.',
            count($rows),
            $counts['dropped'] ?? 0,
            ($counts['retained'] ?? 0) + ($counts['unknown'] ?? 0),
            $counts['protected'] ?? 0,
            $counts['busy'] ?? 0,
            $counts['would-drop'] ?? 0,
        );
        if (!$apply) {
            $lines[] = 'Preview only; no databases were deleted.';
        }
        $message = implode(PHP_EOL, $lines);
        echo json_encode(['systemMessage' => $message, 'hookSpecificOutput' => ['hookEventName' => 'SessionStart', 'additionalContext' => $message]], JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR).PHP_EOL;
    } else {
        foreach ($rows as $row) {
            echo json_encode($row, JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR).PHP_EOL;
        }
        if (!$apply) {
            echo "Dry-run only. Pass --apply to drop eligible recorded databases. Unknown databases are never dropped.\n";
        }
    }
    exit($apply && array_any($rows, static fn (array $row): bool => $row['status'] === 'busy') ? 1 : 0);
} catch (\Throwable $exception) {
    // Connection exceptions can contain usernames and DSNs; keep them out of terminal output.
    $message = $exception instanceof \PDOException || $exception instanceof QueryException
        ? 'Database connection or operation failed; check .env.testing and database privileges.'
        : $exception->getMessage();
    if ($report) {
        echo json_encode(['systemMessage' => 'Database cleanup FAILED: '.$message], JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR).PHP_EOL;
    } else {
        fwrite(STDERR, 'worktree databases: '.$message.PHP_EOL);
    }
    exit(1);
}
