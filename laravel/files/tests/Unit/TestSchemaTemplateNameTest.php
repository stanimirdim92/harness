<?php

declare(strict_types=1);

use App\Support\TestSchema;
use Symfony\Component\Filesystem\Filesystem;

it('names a template after the fingerprint and the SQL checksum of its snapshot', function (): void {
    expect(TestSchema::templateName(str_repeat('a', 64), str_repeat('1', 64)))->toBe('leadbuster_tpl_aaaaaaaaaaaa_111111111111');
});

it('gives two snapshots with one fingerprint and different SQL two templates', function (): void {
    expect(TestSchema::templateName(str_repeat('a', 64), str_repeat('1', 64)))
        ->not->toBe(TestSchema::templateName(str_repeat('a', 64), str_repeat('2', 64)));
});

it('rejects a fingerprint or checksum that is not 64 hexadecimal characters', function (string $fingerprint, string $checksum): void {
    expect(fn () => TestSchema::templateName($fingerprint, $checksum))->toThrow(\RuntimeException::class);
})->with([
    'short fingerprint' => [str_repeat('a', 63), str_repeat('1', 64)],
    'uppercase fingerprint' => [str_repeat('A', 64), str_repeat('1', 64)],
    'short checksum' => [str_repeat('a', 64), str_repeat('1', 63)],
    'checksum with a symbol' => [str_repeat('a', 64), str_repeat('1', 63).'-'],
    'empty checksum' => [str_repeat('a', 64), ''],
]);

it('recognises a current or legacy template name and nothing else', function (string $database, bool $expected): void {
    expect(TestSchema::isTemplate($database))->toBe($expected);
})->with([
    'current name' => ['leadbuster_tpl_aaaaaaaaaaaa_111111111111', true],
    'legacy name with the fingerprint only' => ['leadbuster_tpl_aaaaaaaaaaaa', true],
    'short checksum part' => ['leadbuster_tpl_aaaaaaaaaaaa_1111', false],
    'long checksum part' => ['leadbuster_tpl_aaaaaaaaaaaa_1111111111111', false],
    'uppercase' => ['leadbuster_tpl_AAAAAAAAAAAA_111111111111', false],
    'worker database' => ['leadbuster_test_aaaaaaaaaaaaaaaaaaaa_test_1', false],
    'application database' => ['leadbuster', false],
]);

it('names the template of a snapshot directory from its fingerprint file and SQL file', function (): void {
    $directory = sys_get_temp_dir().'/lb-snapshot-'.bin2hex(random_bytes(8));
    mkdir($directory, 0o700);
    try {
        file_put_contents($directory.'/mysql-schema.fingerprint', str_repeat('a', 64).PHP_EOL);
        file_put_contents($directory.'/mysql-schema.sql', 'CREATE TABLE a (id INT);');
        $first = TestSchema::snapshotTemplateName($directory);
        file_put_contents($directory.'/mysql-schema.sql', 'CREATE TABLE a (id INT); -- comment');
        $second = TestSchema::snapshotTemplateName($directory);

        expect($first)->toBe('leadbuster_tpl_aaaaaaaaaaaa_'.mb_substr(hash('sha256', 'CREATE TABLE a (id INT);'), 0, 12))
            ->and($second)->toBe('leadbuster_tpl_aaaaaaaaaaaa_'.mb_substr(hash('sha256', 'CREATE TABLE a (id INT); -- comment'), 0, 12))
            ->and($first)->not->toBe($second);
    } finally {
        new Filesystem()->remove($directory);
    }
});

it('names no template for a snapshot directory that lacks a valid fingerprint or an SQL file', function (string $scenario): void {
    $directory = sys_get_temp_dir().'/lb-snapshot-'.bin2hex(random_bytes(8));
    mkdir($directory, 0o700);
    try {
        if ($scenario !== 'no fingerprint file') {
            file_put_contents($directory.'/mysql-schema.fingerprint', $scenario === 'invalid fingerprint' ? 'not-a-fingerprint' : str_repeat('a', 64));
        }
        if ($scenario !== 'no SQL file') {
            file_put_contents($directory.'/mysql-schema.sql', 'CREATE TABLE a (id INT);');
        }

        expect(TestSchema::snapshotTemplateName($directory))->toBeNull();
    } finally {
        new Filesystem()->remove($directory);
    }
})->with(['no fingerprint file', 'invalid fingerprint', 'no SQL file']);
