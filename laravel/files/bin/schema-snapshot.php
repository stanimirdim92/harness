<?php

declare(strict_types=1);

use App\Support\TestSchema;
use Dotenv\Dotenv;
use Illuminate\Database\Connectors\ConnectionFactory;
use Illuminate\Database\Schema\MySqlSchemaState;
use Illuminate\Foundation\Application;
use Illuminate\Foundation\Bootstrap\{LoadConfiguration, LoadEnvironmentVariables};

$root = dirname(__DIR__);
require $root.'/vendor/autoload.php';

$command = $argv[1] ?? '';
if (!in_array($command, ['refresh', 'template-check', 'template-build'], true) || !is_file($root.'/.env.testing')
    || ($command === 'refresh' && !is_file($root.'/.env'))) {
    throw new \RuntimeException('Expected refresh, template-check or template-build, and project .env.testing (plus .env for refresh) files.');
}

// Read the project's env files directly, independently of the caller's DB overrides.
// Credentials come from .env.testing, the same account the test runner uses.
// Do not register or boot application/module providers just to read metadata.
foreach (array_keys(getenv()) as $key) {
    if (str_starts_with($key, 'DB_') || str_starts_with($key, 'LB_TEST_')
        || in_array($key, ['DATABASE_URL', 'APP_ENV', 'APP_CONFIG_CACHE', 'TEST_TOKEN', 'UNIQUE_TEST_TOKEN'], true)) {
        putenv($key);
        unset($_ENV[$key], $_SERVER[$key]);
    }
}
$cachePath = sys_get_temp_dir().'/lb-schema-'.bin2hex(random_bytes(12)).'.php';
putenv('APP_CONFIG_CACHE='.$cachePath);
$_ENV['APP_CONFIG_CACHE'] = $_SERVER['APP_CONFIG_CACHE'] = $cachePath;
$directory = $root.'/database/schema';

if ($command !== 'refresh') {
    // Test runs: the template comes from the committed snapshot alone and never
    // reads leadbuster. The runner holds this template's locks. Exit 3 = not ready.
    $app = new Application($root);
    $app->loadEnvironmentFrom('.env.testing');
    $app->bootstrapWith([LoadEnvironmentVariables::class, LoadConfiguration::class]);
    $config = $app['config'];
    $connectionConfig = $config->get('database.connections.'.$config->get('database.default'), []);
    if (($connectionConfig['driver'] ?? null) !== 'mysql' || !empty($connectionConfig['url'])
        || !empty($connectionConfig['read']) || !empty($connectionConfig['write']) || !empty($connectionConfig['direct'])
        || isset($connectionConfig['options'][1002])) {
        throw new \RuntimeException('Expected .env.testing MySQL configuration without URL/replica/direct/init-command overrides.');
    }
    $connectionConfig['database'] = 'information_schema';
    $connectionConfig['options'][\PDO::ATTR_PERSISTENT] = false;
    $connection = new ConnectionFactory($app)->make($connectionConfig, 'mysql');
    $fingerprint = mb_trim((string) file_get_contents($directory.'/mysql-schema.fingerprint'));
    $template = TestSchema::snapshotTemplateName($directory) ?? throw new \RuntimeException('Invalid schema snapshot; run bin/schema-refresh.sh.');
    $ready = TestSchema::templateIsReady($connection, $template, $fingerprint);
    if (!$ready && $command === 'template-build') {
        TestSchema::replaceTemplate($app, $connectionConfig, $template, $directory.'/mysql-schema.sql', $fingerprint);
        echo "Built schema template $template.".PHP_EOL;
        $ready = true;
    }
    $connection->disconnect();
    exit($ready ? 0 : 3);
}

$app = require $root.'/bootstrap/app.php';
$app->loadEnvironmentFrom('.env');
$app->bootstrapWith([LoadEnvironmentVariables::class, LoadConfiguration::class]);
$config = $app['config'];
$default = $config->get('database.default');
$connectionConfig = $config->get("database.connections.$default", []);
if (($connectionConfig['driver'] ?? null) !== 'mysql'
    || ($connectionConfig['database'] ?? null) !== 'leadbuster'
    || !empty($connectionConfig['url']) || !empty($connectionConfig['read'])
    || !empty($connectionConfig['write']) || !empty($connectionConfig['direct'])
    || isset($connectionConfig['options'][1002])) {
    throw new \RuntimeException('Schema source must be .env MySQL database leadbuster without URL/replica/direct/init-command overrides.');
}
$testingEnvironment = Dotenv::parse((string) file_get_contents($root.'/.env.testing'));
$connectionConfig['username'] = $testingEnvironment['DB_USERNAME'] ?? $connectionConfig['username'];
$connectionConfig['password'] = $testingEnvironment['DB_PASSWORD'] ?? $connectionConfig['password'];
$connectionConfig['options'][\PDO::ATTR_PERSISTENT] = false;
$connection = new ConnectionFactory($app)->make($connectionConfig, 'mysql');
if ($connection->getPdo()->query('SELECT DATABASE()')->fetchColumn() !== 'leadbuster') {
    throw new \RuntimeException('Schema source resolved to an unexpected database.');
}

$fingerprint = static fn (): string => TestSchema::fingerprint($connection, 'leadbuster');

TestSchema::tables($connection, 'leadbuster');
$before = $fingerprint();

if (!is_dir($directory) && !mkdir($directory, 0o755, true)) {
    throw new \RuntimeException('Cannot create schema directory.');
}
$temporary = tempnam($directory, '.schema-');
if ($temporary === false) {
    throw new \RuntimeException('Cannot create temporary schema file.');
}
try {
    $state = new class($connection) extends MySqlSchemaState {
        protected function baseDumpCommand()
        {
            return parent::baseDumpCommand().' --single-transaction --skip-lock-tables';
        }
    };
    $migrations = $config->get('database.migrations', 'migrations');
    $state->withMigrationTable(is_array($migrations) ? ($migrations['table'] ?? 'migrations') : $migrations);
    $state->dump($connection, $temporary);
    if ($before !== $fingerprint() || filesize($temporary) === 0) {
        throw new \RuntimeException('Schema changed during dump or dump is empty; previous snapshot retained.');
    }
    $checksum = hash_file('sha256', $temporary);
    if (file_put_contents($temporary.'.fingerprint', $before.PHP_EOL) === false
        || file_put_contents($temporary.'.sha256', $checksum.PHP_EOL) === false) {
        throw new \RuntimeException('Cannot write schema metadata.');
    }

    // Importing the dump into this snapshot's own template proves it reproduces
    // the fingerprint. An existing template of the same name was imported from the
    // same SQL, so it is kept, and test runs of other checkouts that hold its lock
    // shared never block the refresh. Other snapshots' templates are untouched.
    $template = TestSchema::templateName($before, $checksum);
    TestSchema::publishTemplate($app, $connectionConfig, $connection, $template, $temporary, $before, '/tmp/leadbuster-tests-'.posix_geteuid());

    // The checksum is published last; an interrupted update fails verification.
    foreach (['' => 'mysql-schema.sql', '.fingerprint' => 'mysql-schema.fingerprint', '.sha256' => 'mysql-schema.sql.sha256'] as $suffix => $name) {
        if (!rename($temporary.$suffix, $directory.'/'.$name)) {
            throw new \RuntimeException('Cannot publish schema snapshot; run refresh again.');
        }
    }
    echo 'Schema snapshot refreshed ('.mb_substr($before, 0, 12).", template $template).".PHP_EOL;
} finally {
    foreach (['', '.fingerprint', '.sha256'] as $suffix) {
        if (is_file($temporary.$suffix)) {
            unlink($temporary.$suffix);
        }
    }
}
