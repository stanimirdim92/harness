<?php

declare(strict_types=1);

use App\Support\WorktreeTesting;

require dirname(__DIR__).'/vendor/autoload.php';

// Reject direct Pest/PHPUnit invocations before loading application tests.
WorktreeTesting::assertContext(dirname(__DIR__));
