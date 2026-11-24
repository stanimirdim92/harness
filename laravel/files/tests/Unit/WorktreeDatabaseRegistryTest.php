<?php

declare(strict_types=1);

use App\Support\{TestSchema, WorktreeDatabaseRegistry};
use Symfony\Component\Filesystem\Filesystem;
use Symfony\Component\Process\Process;

$fixture = new class() {
    public string $fixture;

    public string $repository;

    public string $checkout;

    public string $lockDirectory;

    public WorktreeDatabaseRegistry $registry;

    public string $namespace;

    public string $record;

    /**
     * @var list<string>
     */
    public array $dropped = [];

    /**
     * @var \Closure(list<string>): void
     */
    public \Closure $git;

    /**
     * @param list<string> $databases
     * @param bool $apply
     * @param ?string $checkout
     * @param int $sessions
     *
     * @return list<array{database: string, checkout: ?string, last_used: ?string, status: string}>
     */
    public function inspect(array $databases, bool $apply = false, ?string $checkout = null, int $sessions = 0): array
    {
        return $this->registry->inspect($databases, static fn (): int => $sessions, function (string $database): void {
            $this->dropped[] = $database;
        }, $apply, $checkout);
    }
};

beforeEach(function () use ($fixture): void {
    $fixture->fixture = sys_get_temp_dir().'/lb-registry-'.bin2hex(random_bytes(8));
    mkdir($fixture->fixture, 0o700);
    $fixture->repository = $fixture->fixture.'/main checkout';
    mkdir($fixture->repository, 0o700);
    $fixture->git = function (array $arguments) use ($fixture): void {
        new Process(['git', '-C', $fixture->repository, ...$arguments])->mustRun();
    };
    ($fixture->git)(['init', '-q']);
    ($fixture->git)(['-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-qm', 'Fixture']);
    $fixture->checkout = $fixture->fixture.'/external ticket checkout';
    ($fixture->git)(['worktree', 'add', '--detach', $fixture->checkout]);
    $fixture->lockDirectory = $fixture->fixture.'/locks';
    $fixture->registry = new WorktreeDatabaseRegistry($fixture->repository, $fixture->lockDirectory);
    $fixture->registry->register($fixture->checkout);
    $fixture->namespace = WorktreeDatabaseRegistry::databaseNamespace($fixture->checkout);
    $fixture->record = $fixture->repository.'/.git/leadbuster-databases.json';
    $fixture->dropped = [];

});

afterEach(function () use ($fixture): void {
    new Filesystem()->remove($fixture->fixture);
});

it('records canonical checkout ownership and retains live external git worktrees', function () use ($fixture): void {
    $content = file_get_contents($fixture->record);
    if ($content === false) {
        throw new \RuntimeException('Cannot read fixture registry.');
    }
    $data = json_decode($content, true, flags: JSON_THROW_ON_ERROR);
    expect($data['owners'][$fixture->checkout]['namespace'])->toBe($fixture->namespace)
        ->and(strtotime($data['owners'][$fixture->checkout]['last_used']))->not->toBeFalse();
    expect($fixture->inspect([$fixture->namespace], true)[0]['status'])->toBe('retained')
        ->and($fixture->dropped)->toBe([]);
    new Filesystem()->remove($fixture->checkout);
    expect($fixture->inspect([$fixture->namespace], true)[0]['status'])->toBe('retained')
        ->and($fixture->dropped)->toBe([]);
});

it('does not sweep an unlisted checkout path that still exists', function () use ($fixture): void {
    ($fixture->git)(['worktree', 'remove', $fixture->checkout]);
    mkdir($fixture->checkout);
    expect($fixture->inspect([$fixture->namespace], true)[0]['status'])->toBe('retained')
        ->and($fixture->dropped)->toBe([]);
});

it('dry runs removed owners then drops only exact namespace and worker names', function () use ($fixture): void {
    ($fixture->git)(['worktree', 'remove', $fixture->checkout]);
    $names = ['leadbuster', 'leadbuster_test', $fixture->namespace, $fixture->namespace.'_test_1', $fixture->namespace.'_test_99', $fixture->namespace.'_test_0', $fixture->namespace.'_test_1_backup', 'leadbuster_test_agent_old'];
    $rows = $fixture->inspect($names);
    expect(array_column($rows, 'status'))->toBe(['protected', 'protected', 'would-drop', 'would-drop', 'would-drop', 'unknown', 'unknown', 'unknown'])
        ->and($fixture->dropped)->toBe([]);
    $fixture->inspect($names, true);
    expect($fixture->dropped)->toBe([$fixture->namespace, $fixture->namespace.'_test_1', $fixture->namespace.'_test_99']);
});

it('treats the template databases of a worker as part of the owning checkout', function () use ($fixture): void {
    $names = [
        $fixture->namespace.'_test_0_template',
        $fixture->namespace.'_test_1_template',
        $fixture->namespace.'_test_2_template_source',
        $fixture->namespace.'_test_1_template_other',
        $fixture->namespace.'_test_template',
    ];
    expect(array_column($fixture->inspect($names), 'status'))->toBe(['retained', 'retained', 'retained', 'unknown', 'unknown']);

    ($fixture->git)(['worktree', 'remove', $fixture->checkout]);
    expect(array_column($fixture->inspect($names), 'status'))->toBe(['would-drop', 'would-drop', 'would-drop', 'unknown', 'unknown']);
    $fixture->inspect($names, true);
    expect($fixture->dropped)->toBe(array_slice($names, 0, 3));
});

it('removes the kept baseline of a worker database only when it drops that database', function () use ($fixture): void {
    $worker = $fixture->namespace.'_test_1';
    $kept = $fixture->lockDirectory.'/'.$worker.'.baseline.json';
    $foreign = $fixture->lockDirectory.'/leadbuster_test_other_test_1.baseline.json';
    file_put_contents($kept, '{}');
    file_put_contents($foreign, '{}');

    $fixture->inspect([$worker], false, $fixture->checkout);
    expect(is_file($kept))->toBeTrue();
    $fixture->inspect([$worker], true, $fixture->checkout, 1);
    expect(is_file($kept))->toBeTrue();

    $fixture->inspect([$worker], true, $fixture->checkout);
    expect($fixture->dropped)->toBe([$worker])
        ->and(is_file($kept))->toBeFalse()
        ->and(is_file($foreign))->toBeTrue();
});

it('removes the ownership record once every database of the owner is dropped', function () use ($fixture): void {
    $owners = static fn (): array => json_decode((string) file_get_contents($fixture->record), true, flags: JSON_THROW_ON_ERROR)['owners'];
    $names = [$fixture->namespace, $fixture->namespace.'_test_1'];

    $fixture->inspect($names, true, $fixture->checkout, 1);
    expect($owners())->toHaveKey($fixture->checkout);
    $fixture->inspect($names, false, $fixture->checkout);
    expect($owners())->toHaveKey($fixture->checkout);

    $fixture->inspect($names, true, $fixture->checkout);
    expect($fixture->dropped)->toBe($names)
        ->and($owners())->not->toHaveKey($fixture->checkout);
});

it('sweeps orphaned staging and backup databases only in an idle full sweep', function () use ($fixture): void {
    $stage = 'leadbuster_test_stage_'.str_repeat('a', 16);
    $backup = 'leadbuster_test_backup_'.str_repeat('b', 16);
    $names = [$stage, $backup, 'leadbuster_test_stage_short', 'leadbuster_test_stage_'.str_repeat('A', 16)];

    expect(array_column($fixture->inspect($names), 'status'))->toBe(['would-drop', 'would-drop', 'unknown', 'unknown'])
        ->and(array_column($fixture->inspect($names, true, $fixture->checkout), 'status'))->toBe(['unknown', 'unknown', 'unknown', 'unknown'])
        ->and(array_column($fixture->inspect($names, true, null, 1), 'status'))->toBe(['busy', 'busy', 'unknown', 'unknown'])
        ->and($fixture->dropped)->toBe([]);

    $fixture->inspect($names, true);
    expect($fixture->dropped)->toBe([$stage, $backup]);
});

it('keeps a staging database while any run holds a template lock', function (string $lockName, bool $exclusive) use ($fixture): void {
    $stage = 'leadbuster_test_stage_'.str_repeat('c', 16);
    $lock = fopen($fixture->lockDirectory.'/'.$lockName, 'cb');
    if ($lock === false) {
        throw new \RuntimeException('Cannot open fixture lock.');
    }
    flock($lock, $exclusive ? LOCK_EX : LOCK_SH);
    try {
        expect($fixture->inspect([$stage], true)[0]['status'])->toBe('busy')
            ->and($fixture->dropped)->toBe([]);
    } finally {
        fclose($lock);
    }
})->with([
    'a run holding its template' => ['leadbuster_tpl_aaaaaaaaaaaa_bbbbbbbbbbbb.lock', false],
    'a run building its template' => ['leadbuster_tpl_aaaaaaaaaaaa_bbbbbbbbbbbb.build.lock', true],
]);

it('requires recorded ownership before explicit retirement', function () use ($fixture): void {
    expect(fn () => $fixture->inspect([$fixture->namespace], true, $fixture->repository))->toThrow(\RuntimeException::class, 'no recorded ownership')
        ->and($fixture->dropped)->toBe([]);
});

it('explicitly retires one idle checkout without removing its directory or unrelated databases', function () use ($fixture): void {
    $fixture->registry->register($fixture->repository);
    $fixture->inspect([$fixture->namespace, WorktreeDatabaseRegistry::databaseNamespace($fixture->repository)], true, $fixture->checkout);
    expect($fixture->dropped)->toBe([$fixture->namespace])
        ->and(is_dir($fixture->checkout))->toBeTrue();
});

it('does not drop a database with any active mysql sessions', function () use ($fixture): void {
    expect($fixture->inspect([$fixture->namespace], true, $fixture->checkout, 1)[0]['status'])->toBe('busy')
        ->and($fixture->dropped)->toBe([]);
});

it('retains an entire namespace when one worker has an active session', function () use ($fixture): void {
    $rows = $fixture->registry->inspect(
        [$fixture->namespace, $fixture->namespace.'_test_1'],
        static fn (string $database): int => str_ends_with($database, '_test_1') ? 1 : 0,
        function (string $database) use ($fixture): void {
            $fixture->dropped[] = $database;
        },
        true,
        $fixture->checkout
    );
    expect(array_column($rows, 'status'))->toBe(['busy', 'busy'])
        ->and($fixture->dropped)->toBe([]);
});

it('retains a locked checkout and accepts its inherited runner lock for registration', function () use ($fixture): void {
    $lock = fopen($fixture->lockDirectory.'/'.mb_substr(hash('sha256', $fixture->checkout), 0, 20).'.lock', 'cb');
    if ($lock === false) {
        throw new \RuntimeException('Cannot open fixture lock.');
    }
    flock($lock, LOCK_EX);
    try {
        expect($fixture->inspect([$fixture->namespace], true, $fixture->checkout)[0]['status'])->toBe('busy')
            ->and(fn () => $fixture->registry->register($fixture->checkout))->toThrow(\RuntimeException::class, 'busy');
        $fixture->registry->register($fixture->checkout, $lock);
        expect($fixture->inspect([$fixture->namespace], true, $fixture->checkout)[0]['status'])->toBe('busy')
            ->and($fixture->dropped)->toBe([]);
    } finally {
        fclose($lock);
    }
});

it('keeps the backend lock held until the database drop finishes', function () use ($fixture): void {
    $fixture->registry->inspect([$fixture->namespace], static fn (): int => 0, function () use ($fixture): void {
        expect(fn () => $fixture->registry->register($fixture->checkout))->toThrow(\RuntimeException::class, 'busy');
    }, true, $fixture->checkout);
});

it('rejects malformed or tampered ownership before any cleanup', function (string $mutation) use ($fixture): void {
    $content = file_get_contents($fixture->record);
    if ($content === false) {
        throw new \RuntimeException('Cannot read fixture registry.');
    }
    $data = json_decode($content, true, flags: JSON_THROW_ON_ERROR);
    if ($mutation === 'namespace') {
        $data['owners'][$fixture->checkout]['namespace'] = 'leadbuster_test';
    } elseif ($mutation === 'path') {
        $data['owners'][$fixture->checkout.'/../other'] = $data['owners'][$fixture->checkout];
    } elseif ($mutation === 'version') {
        $data['version'] = 2;
    } elseif ($mutation === 'timestamp') {
        $data['owners'][$fixture->checkout]['last_used'] = 'invalid';
    }
    file_put_contents($fixture->record, $mutation === 'json' ? '{' : json_encode($data, JSON_THROW_ON_ERROR));
    expect(fn () => $fixture->inspect([$fixture->namespace], true, $fixture->checkout))->toThrow($mutation === 'json' ? \JsonException::class : \RuntimeException::class)
        ->and($fixture->dropped)->toBe([]);
})->with(['namespace', 'path', 'version', 'timestamp', 'json']);

it('rejects registry symlinks and unknown directories instead of adopting them', function () use ($fixture): void {
    mkdir($fixture->fixture.'/unknown');
    expect(fn () => $fixture->registry->register($fixture->fixture.'/unknown'))->toThrow(\RuntimeException::class, 'registered Git worktree');
    rename($fixture->record, $fixture->record.'.saved');
    symlink($fixture->record.'.saved', $fixture->record);
    expect(fn () => $fixture->inspect([$fixture->namespace], true, $fixture->checkout))->toThrow(\RuntimeException::class, 'Unsafe database ownership registry');
});

it('sweeps only schema templates that no registered worktree snapshot names', function () use ($fixture): void {
    $fingerprint = str_repeat('a', 64);
    mkdir($fixture->checkout.'/database/schema', 0o700, true);
    file_put_contents($fixture->checkout.'/database/schema/mysql-schema.fingerprint', $fingerprint.PHP_EOL);
    file_put_contents($fixture->checkout.'/database/schema/mysql-schema.sql', 'CREATE TABLE a (id INT);');
    $used = TestSchema::templateName($fingerprint, hash('sha256', 'CREATE TABLE a (id INT);'));
    $unused = 'leadbuster_tpl_'.str_repeat('b', 12).'_'.str_repeat('d', 12);
    $names = [$used, $unused, 'leadbuster_tpl_short'];

    expect(array_column($fixture->inspect($names), 'status'))->toBe(['retained', 'would-drop'])
        ->and(array_column($fixture->inspect($names, true, $fixture->checkout), 'status'))->toBe(['retained', 'retained'])
        ->and($fixture->dropped)->toBe([]);
    $fixture->inspect($names, true);
    expect($fixture->dropped)->toBe([$unused]);
});

it('sweeps a template with the fingerprint of a used snapshot but other SQL, and a legacy template', function () use ($fixture): void {
    $fingerprint = str_repeat('a', 64);
    mkdir($fixture->checkout.'/database/schema', 0o700, true);
    file_put_contents($fixture->checkout.'/database/schema/mysql-schema.fingerprint', $fingerprint.PHP_EOL);
    file_put_contents($fixture->checkout.'/database/schema/mysql-schema.sql', 'CREATE TABLE a (id INT);');
    $sameFingerprintOtherSql = TestSchema::templateName($fingerprint, hash('sha256', 'CREATE TABLE a (id INT); -- comment'));
    $legacy = 'leadbuster_tpl_'.str_repeat('a', 12);

    $fixture->inspect([$sameFingerprintOtherSql, $legacy], true);

    expect($fixture->dropped)->toBe([$sameFingerprintOtherSql, $legacy]);
});

it('keeps an unused schema template while a run holds its lock or a session uses it', function () use ($fixture): void {
    $template = 'leadbuster_tpl_'.str_repeat('c', 12);
    expect($fixture->inspect([$template], true, null, 1)[0]['status'])->toBe('busy');
    $lock = fopen($fixture->lockDirectory.'/'.$template.'.lock', 'cb');
    if ($lock === false) {
        throw new \RuntimeException('Cannot open fixture lock.');
    }
    flock($lock, LOCK_SH);
    try {
        expect($fixture->inspect([$template], true)[0]['status'])->toBe('busy')
            ->and($fixture->dropped)->toBe([]);
    } finally {
        fclose($lock);
    }
});
