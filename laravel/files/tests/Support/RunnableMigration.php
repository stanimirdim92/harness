<?php

declare(strict_types=1);

namespace Tests\Support;

/**
 * The up() and down() methods of an anonymous migration class. Tests use it in
 * PHPDoc only, to type the object that `require` returns for such a migration file.
 */
interface RunnableMigration
{
    public function up(): void;

    public function down(): void;
}
