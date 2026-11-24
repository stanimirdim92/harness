<?php

declare(strict_types=1);

use App\Support\TestSchema;
use Illuminate\Database\{Connection, QueryException};
use Illuminate\Database\Connectors\ConnectionFactory;
use Illuminate\Support\Facades\{DB, File};

it('publishes a complete template or retains the previous one', function (string $scenario): void {
    $target = getenv('LB_TEST_DATABASE').'_test_'.getenv('TEST_TOKEN').'_template';
    $source = $target.'_source';
    $configuration = DB::connection()->getConfig();
    $factory = new ConnectionFactory(app());
    $admin = $factory->make(array_replace($configuration, ['database' => 'information_schema']));
    $file = getenv('LB_TEST_RUNTIME').'/template-'.getenv('TEST_TOKEN').'.sql';
    $statements = [
        'CREATE TABLE parents (id BIGINT UNSIGNED PRIMARY KEY) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci',
        'CREATE TABLE children (id BIGINT UNSIGNED PRIMARY KEY, parent_id BIGINT UNSIGNED, amount INT, CONSTRAINT child_parent FOREIGN KEY (parent_id) REFERENCES parents(id) ON DELETE CASCADE, CONSTRAINT positive_amount CHECK (amount > 0)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci',
    ];
    try {
        foreach ([$source, $target] as $database) {
            $admin->statement("CREATE DATABASE `$database` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
        }
        $fixture = $factory->make(array_replace($configuration, ['database' => $source]));
        foreach ($statements as $sql) {
            $fixture->statement($sql);
        }
        $fixture->disconnect();
        $admin->statement("CREATE TABLE `$target`.previous (id INT PRIMARY KEY) ENGINE=InnoDB");
        $admin->statement("INSERT INTO `$target`.previous VALUES (42)");
        $before = TestSchema::fingerprint($admin, $target);
        $expected = TestSchema::fingerprint($admin, $source);
        file_put_contents($file, implode(';', $statements).';'.($scenario === 'invalid SQL' ? 'INVALID SQL;' : ''));

        if ($scenario !== 'success') {
            expect(fn () => TestSchema::replaceTemplate(app(), $configuration, $target, $file, $scenario === 'mismatch' ? str_repeat('0', 64) : $expected))
                ->toThrow(\RuntimeException::class);
            expect(TestSchema::fingerprint($admin, $target))->toBe($before);
            expect($admin->selectOne("SELECT id FROM `$target`.previous")->id)->toBe(42);
        } else {
            TestSchema::replaceTemplate(app(), $configuration, $target, $file, $expected);
            expect(TestSchema::fingerprint($admin, $target))->toBe($expected);
            expect(fn () => $admin->statement("INSERT INTO `$target`.children VALUES (1, 999, 1)"))->toThrow(QueryException::class);
            $admin->statement("INSERT INTO `$target`.parents VALUES (1)");
            $admin->statement("INSERT INTO `$target`.children VALUES (1, 1, 1)");
            $admin->statement("DELETE FROM `$target`.parents WHERE id = 1");
            expect($admin->selectOne("SELECT COUNT(*) AS n FROM `$target`.children")->n)->toBe(0);
        }
    } finally {
        foreach ([$target, $source] as $database) {
            $admin->statement("DROP DATABASE IF EXISTS `$database`");
        }
        $admin->disconnect();
        if (is_file($file)) {
            unlink($file);
        }
    }
})->with(['success', 'invalid SQL', 'mismatch']);

it('refuses to replace the protected source or shared template from a test', function (string $database): void {
    expect(fn () => TestSchema::replaceTemplate(app(), DB::connection()->getConfig(), $database, '/nonexistent.sql', ''))
        ->toThrow(\RuntimeException::class, 'Refusing to replace an unowned schema template.');
})->with(['leadbuster', 'leadbuster_test', 'some_other_database']);

it('rejects source events before a dump can silently omit them', function (): void {
    $database = getenv('LB_TEST_DATABASE').'_test_'.getenv('TEST_TOKEN').'_template';
    $admin = new ConnectionFactory(app())->make(array_replace(DB::connection()->getConfig(), ['database' => 'information_schema']));
    try {
        $admin->statement("CREATE DATABASE `$database`");
        $admin->statement("CREATE EVENT `$database`.unused ON SCHEDULE AT CURRENT_TIMESTAMP + INTERVAL 1 DAY DISABLE DO SELECT 1");
        expect(fn () => TestSchema::tables($admin, $database))
            ->toThrow(\RuntimeException::class, 'does not support triggers, routines, or events');
    } finally {
        $admin->statement("DROP DATABASE IF EXISTS `$database`");
        $admin->disconnect();
    }
});

it('uses the template that TestSchema names for the committed snapshot', function (): void {
    expect(getenv('LB_SCHEMA_TEMPLATE'))->toBe(TestSchema::snapshotTemplateName(base_path('database/schema')));
});

it('publishes a snapshot only under the name of its fingerprint and SQL checksum', function (): void {
    $worker = (string) getenv('LB_TEST_DATABASE');
    $source = $worker.'_test_'.getenv('TEST_TOKEN').'_template_source';
    $configuration = DB::connection()->getConfig();
    $factory = new ConnectionFactory(app());
    $admin = $factory->make(array_replace($configuration, ['database' => 'information_schema']));
    $file = getenv('LB_TEST_RUNTIME').'/snapshot-name-'.getenv('TEST_TOKEN').'.sql';
    $statement = 'CREATE TABLE parents (id BIGINT UNSIGNED PRIMARY KEY) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci';
    $created = [$source];
    try {
        $admin->statement("CREATE DATABASE `$source` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
        $fixture = $factory->make(array_replace($configuration, ['database' => $source]));
        $fixture->statement($statement);
        $fixture->disconnect();
        $expected = TestSchema::fingerprint($admin, $source);
        file_put_contents($file, $statement.';');
        $template = TestSchema::templateName($expected, (string) hash_file('sha256', $file));
        $created[] = $template;
        $legacy = 'leadbuster_tpl_'.mb_substr($expected, 0, 12);

        // The ownership check applies outside a test run, as bin/schema-snapshot.php runs it.
        putenv('LB_TEST_DATABASE');
        expect(fn () => TestSchema::replaceTemplate(app(), $configuration, $legacy, $file, $expected))
            ->toThrow(\RuntimeException::class, 'Refusing to replace an unowned schema template.');
        TestSchema::replaceTemplate(app(), $configuration, $template, $file, $expected);
        putenv("LB_TEST_DATABASE=$worker");

        expect(TestSchema::fingerprint($admin, $template))->toBe($expected);
    } finally {
        putenv("LB_TEST_DATABASE=$worker");
        foreach ($created as $database) {
            $admin->statement("DROP DATABASE IF EXISTS `$database`");
        }
        $admin->disconnect();
        if (is_file($file)) {
            unlink($file);
        }
    }
});

/**
 * Run a schema refresh's template step against a template of this worker while a lock is held
 * like another process holds it: 'shared' like a test run of another checkout, 'exclusive' like a
 * database cleanup. Returns what publishTemplate returned and how long it took.
 *
 * @param bool $templateExists
 * @param string $heldLock
 *
 * @return array{built: bool, seconds: float, fingerprint: string, expected: string}
 */
function publishTemplateWhileLocked(bool $templateExists, string $heldLock): array
{
    $template = getenv('LB_TEST_DATABASE').'_test_'.getenv('TEST_TOKEN').'_template';
    $configuration = DB::connection()->getConfig();
    $admin = new ConnectionFactory(app())->make(array_replace($configuration, ['database' => 'information_schema']));
    $directory = getenv('LB_TEST_RUNTIME').'/template-locks-'.getenv('TEST_TOKEN');
    $file = $directory.'/snapshot.sql';
    mkdir($directory);
    $held = fopen("$directory/$template.lock", 'cb');
    if ($held === false) {
        throw new \RuntimeException('Cannot open the template lock.');
    }
    try {
        file_put_contents($file, 'CREATE TABLE parents (id BIGINT UNSIGNED PRIMARY KEY) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;');
        $admin->statement("CREATE DATABASE `{$template}_source` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
        $admin->statement("CREATE TABLE `{$template}_source`.parents (id BIGINT UNSIGNED PRIMARY KEY) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");
        $expected = TestSchema::fingerprint($admin, "{$template}_source");
        if ($templateExists) {
            TestSchema::replaceTemplate(app(), $configuration, $template, $file, $expected);
        }
        flock($held, $heldLock === 'shared' ? LOCK_SH : LOCK_EX);
        $started = microtime(true);
        try {
            $built = TestSchema::publishTemplate(app(), $configuration, $admin, $template, $file, $expected, $directory, 2);
        } finally {
            $seconds = microtime(true) - $started;
        }

        return ['built' => $built, 'seconds' => $seconds, 'fingerprint' => TestSchema::fingerprint($admin, $template), 'expected' => $expected];
    } finally {
        fclose($held);
        foreach ([$template, "{$template}_source"] as $database) {
            $admin->statement("DROP DATABASE IF EXISTS `$database`");
        }
        $admin->disconnect();
        File::deleteDirectory($directory);
    }
}

it('keeps a matching template while a test run of another checkout holds its lock', function (): void {
    $result = publishTemplateWhileLocked(true, 'shared');

    expect($result['built'])->toBeFalse()
        ->and($result['seconds'])->toBeLessThan(1.0)
        ->and($result['fingerprint'])->toBe($result['expected']);
});

it('builds a missing template while a test run of another checkout holds its lock', function (): void {
    $result = publishTemplateWhileLocked(false, 'shared');

    expect($result['built'])->toBeTrue()
        ->and($result['fingerprint'])->toBe($result['expected']);
});

it('gives up on a template that a cleanup holds exclusively', function (): void {
    expect(fn () => publishTemplateWhileLocked(true, 'exclusive'))
        ->toThrow(\RuntimeException::class, 'Timed out waiting for a cleanup of');
});

/**
 * Runs $check against a scratch database in this worker's namespace, built by $setup, and drops
 * it (and its "_ref" sibling) afterwards.
 *
 * @param \Closure(Connection, string): mixed $setup
 * @param \Closure(Connection, string): mixed $check
 */
function withScratchSchema(\Closure $setup, \Closure $check): void
{
    $database = getenv('LB_TEST_DATABASE').'_test_'.getenv('TEST_TOKEN').'_template';
    $admin = new ConnectionFactory(app())->make(array_replace(DB::connection()->getConfig(), ['database' => 'information_schema']));
    try {
        $admin->statement("CREATE DATABASE `$database` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
        $setup($admin, $database);
        $check($admin, $database);
    } finally {
        // The scratch databases may reference each other; this session only.
        $admin->statement('SET FOREIGN_KEY_CHECKS = 0');
        $admin->statement("DROP DATABASE IF EXISTS `{$database}_ref`");
        $admin->statement("DROP DATABASE IF EXISTS `$database`");
        $admin->disconnect();
    }
}

it('lists the ordinary InnoDB tables of a schema', function (): void {
    withScratchSchema(
        static function ($admin, string $database): void {
            $admin->statement("CREATE TABLE `$database`.beta (id INT PRIMARY KEY) ENGINE=InnoDB");
            $admin->statement("CREATE TABLE `$database`.alpha (id INT PRIMARY KEY) ENGINE=InnoDB");
        },
        static fn ($admin, string $database) => expect(TestSchema::tables($admin, $database))->toBe(['alpha', 'beta']),
    );
});

it('refuses a schema that is not made of ordinary InnoDB tables, triggers or same-database keys', function (string $sql, string $message): void {
    withScratchSchema(
        static function ($admin, string $database) use ($sql): void {
            $admin->statement("CREATE TABLE `$database`.plain (id INT PRIMARY KEY) ENGINE=InnoDB");
            $admin->statement("CREATE DATABASE `{$database}_ref` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
            $admin->statement("CREATE TABLE `{$database}_ref`.target (id INT PRIMARY KEY) ENGINE=InnoDB");
            $admin->statement(str_replace(['{db}', '{ref}'], [$database, $database.'_ref'], $sql));
        },
        static fn ($admin, string $database) => expect(fn () => TestSchema::tables($admin, $database))
            ->toThrow(\RuntimeException::class, $message),
    );
})->with([
    'view' => ['CREATE VIEW `{db}`.plain_view AS SELECT id FROM `{db}`.plain', 'requires ordinary InnoDB tables'],
    'MyISAM table' => ['CREATE TABLE `{db}`.other (id INT PRIMARY KEY) ENGINE=MyISAM', 'requires ordinary InnoDB tables'],
    'trigger' => ['CREATE TRIGGER `{db}`.plain_insert BEFORE INSERT ON `{db}`.plain FOR EACH ROW SET NEW.id = NEW.id', 'does not support triggers, routines, or events'],
    'routine' => ['CREATE PROCEDURE `{db}`.noop() SELECT 1', 'does not support triggers, routines, or events'],
    'cross-database foreign key' => ['CREATE TABLE `{db}`.linked (id INT PRIMARY KEY, target_id INT, FOREIGN KEY (target_id) REFERENCES `{ref}`.target(id)) ENGINE=InnoDB', 'refuses cross-database foreign keys'],
]);

it('refuses a malformed fingerprint or SQL checksum in a template name', function (string $fingerprint, string $checksum, string $message): void {
    expect(fn () => TestSchema::templateName($fingerprint, $checksum))->toThrow(\RuntimeException::class, $message);
})->with([
    'short fingerprint' => [str_repeat('a', 63), str_repeat('b', 64), 'Invalid schema fingerprint'],
    'upper-case fingerprint' => [str_repeat('A', 64), str_repeat('b', 64), 'Invalid schema fingerprint'],
    'fingerprint with a newline' => [str_repeat('a', 64)."\n", str_repeat('b', 64), 'Invalid schema fingerprint'],
    'long checksum' => [str_repeat('a', 64), str_repeat('b', 65), 'Invalid schema SQL checksum'],
]);

it('names a template after the first 12 characters of the fingerprint and the checksum', function (): void {
    $name = TestSchema::templateName(str_repeat('a', 12).str_repeat('c', 52), str_repeat('b', 12).str_repeat('d', 52));

    expect($name)->toBe('leadbuster_tpl_aaaaaaaaaaaa_bbbbbbbbbbbb')
        ->and(TestSchema::isTemplate($name))->toBeTrue()
        ->and(TestSchema::isTemplate('leadbuster_tpl_aaaaaaaaaaaa'))->toBeTrue()
        ->and(TestSchema::isTemplate('leadbuster_tpl_aaaaaaaaaaa'))->toBeFalse()
        ->and(TestSchema::isTemplate('leadbuster_tpl_aaaaaaaaaaaa_bbbbbbbbbbbb_x'))->toBeFalse()
        ->and(TestSchema::isTemplate('leadbuster'))->toBeFalse();
});

it('has no snapshot template name when the schema directory lacks a valid fingerprint or SQL file', function (?string $fingerprint, bool $withSql): void {
    $directory = getenv('LB_TEST_RUNTIME').'/schema-name-'.getenv('TEST_TOKEN');
    mkdir($directory);
    try {
        if ($fingerprint !== null) {
            file_put_contents($directory.'/mysql-schema.fingerprint', $fingerprint);
        }
        if ($withSql) {
            file_put_contents($directory.'/mysql-schema.sql', 'SELECT 1;');
        }

        expect(TestSchema::snapshotTemplateName($directory))->toBeNull();
    } finally {
        foreach (['mysql-schema.fingerprint', 'mysql-schema.sql'] as $name) {
            if (is_file($directory.'/'.$name)) {
                unlink($directory.'/'.$name);
            }
        }
        rmdir($directory);
    }
})->with([
    'no files' => [null, false],
    'no SQL file' => [str_repeat('a', 64), false],
    'malformed fingerprint' => ['not-a-fingerprint', true],
]);

it('reads the snapshot template name from a trimmed fingerprint file', function (): void {
    $directory = getenv('LB_TEST_RUNTIME').'/schema-name-ok-'.getenv('TEST_TOKEN');
    mkdir($directory);
    try {
        file_put_contents($directory.'/mysql-schema.fingerprint', str_repeat('a', 64)."\n");
        file_put_contents($directory.'/mysql-schema.sql', 'SELECT 1;');

        expect(TestSchema::snapshotTemplateName($directory))
            ->toBe(TestSchema::templateName(str_repeat('a', 64), (string) hash_file('sha256', $directory.'/mysql-schema.sql')));
    } finally {
        foreach (['mysql-schema.fingerprint', 'mysql-schema.sql'] as $name) {
            if (is_file($directory.'/'.$name)) {
                unlink($directory.'/'.$name);
            }
        }
        rmdir($directory);
    }
});

it('refuses an empty dump and keeps the previous template', function (): void {
    $file = getenv('LB_TEST_RUNTIME').'/empty-dump-'.getenv('TEST_TOKEN').'.sql';
    withScratchSchema(
        static function ($admin, string $database): void {
            $admin->statement("CREATE TABLE `$database`.previous (id INT PRIMARY KEY) ENGINE=InnoDB");
        },
        static function ($admin, string $database) use ($file): void {
            file_put_contents($file, '/* nothing */;');
            try {
                $emptyFingerprint = TestSchema::fingerprint($admin, 'leadbuster_no_such_database');
                expect(fn () => TestSchema::replaceTemplate(app(), DB::connection()->getConfig(), $database, $file, $emptyFingerprint))
                    ->toThrow(\RuntimeException::class, 'previous template retained');
                expect(TestSchema::tables($admin, $database))->toBe(['previous']);
            } finally {
                unlink($file);
            }
        },
    );
});

it('refuses an unsafe charset or collation', function (string $key): void {
    $target = getenv('LB_TEST_DATABASE').'_test_'.getenv('TEST_TOKEN').'_template';
    $configuration = array_replace(DB::connection()->getConfig(), [$key => 'utf8mb4; DROP DATABASE x']);

    expect(fn () => TestSchema::replaceTemplate(app(), $configuration, $target, '/nonexistent.sql', ''))
        ->toThrow(\RuntimeException::class, 'Invalid schema identifier or encoding.');
})->with(['charset', 'collation']);

it('changes the fingerprint for every kind of schema difference', function (string $variant): void {
    withScratchSchema(
        static function ($admin, string $database) use ($variant): void {
            $admin->statement("CREATE DATABASE `{$database}_ref` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
            foreach ([$database, $database.'_ref'] as $schema) {
                $admin->statement("CREATE TABLE `$schema`.parents (id INT PRIMARY KEY) ENGINE=InnoDB");
                // parent_id is indexed up front, so adding the foreign key changes no index.
                $admin->statement("CREATE TABLE `$schema`.children (id INT PRIMARY KEY, parent_id INT, amount INT, INDEX children_parent (parent_id)) ENGINE=InnoDB");
            }
            $admin->statement(str_replace('{db}', $database.'_ref', $variant));
        },
        static fn ($admin, string $database) => expect(TestSchema::fingerprint($admin, $database.'_ref'))
            ->not->toBe(TestSchema::fingerprint($admin, $database)),
    );
})->with([
    'table' => ['CREATE TABLE `{db}`.extra (id INT PRIMARY KEY) ENGINE=InnoDB'],
    'table collation only' => ['ALTER TABLE `{db}`.children COLLATE utf8mb4_bin'],
    'column' => ['ALTER TABLE `{db}`.children MODIFY amount BIGINT'],
    'index' => ['CREATE INDEX children_amount ON `{db}`.children (amount)'],
    'foreign key' => ['ALTER TABLE `{db}`.children ADD CONSTRAINT child_parent FOREIGN KEY (parent_id) REFERENCES `{db}`.parents(id)'],
    'check constraint' => ['ALTER TABLE `{db}`.children ADD CONSTRAINT positive_amount CHECK (amount > 0)'],
]);

it('gives two identical schemas the same fingerprint', function (): void {
    withScratchSchema(
        static function ($admin, string $database): void {
            $admin->statement("CREATE DATABASE `{$database}_ref` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
            foreach ([$database, $database.'_ref'] as $schema) {
                $admin->statement("CREATE TABLE `$schema`.parents (id INT PRIMARY KEY) ENGINE=InnoDB");
            }
        },
        static fn ($admin, string $database) => expect(TestSchema::fingerprint($admin, $database.'_ref'))
            ->toBe(TestSchema::fingerprint($admin, $database)),
    );
});

it('refuses to replace a template that another database references', function (): void {
    $file = getenv('LB_TEST_RUNTIME').'/referenced-dump-'.getenv('TEST_TOKEN').'.sql';
    $statement = 'CREATE TABLE parents (id INT PRIMARY KEY) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci';
    withScratchSchema(
        static function ($admin, string $database) use ($statement): void {
            $admin->statement(str_replace('CREATE TABLE parents', "CREATE TABLE `$database`.parents", $statement));
            $admin->statement("CREATE DATABASE `{$database}_ref` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
            $admin->statement("CREATE TABLE `{$database}_ref`.children (id INT PRIMARY KEY, parent_id INT, FOREIGN KEY (parent_id) REFERENCES `$database`.parents(id)) ENGINE=InnoDB");
        },
        static function ($admin, string $database) use ($file, $statement): void {
            file_put_contents($file, $statement.';');
            try {
                $expected = TestSchema::fingerprint($admin, $database);
                expect(fn () => TestSchema::replaceTemplate(app(), DB::connection()->getConfig(), $database, $file, $expected))
                    ->toThrow(\RuntimeException::class, 'Refusing to replace a template referenced by another database.');
                expect(TestSchema::tables($admin, $database))->toBe(['parents']);
            } finally {
                unlink($file);
            }
        },
    );
});
