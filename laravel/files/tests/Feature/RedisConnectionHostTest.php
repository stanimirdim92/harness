<?php

declare(strict_types=1);

/**
 * Every Redis connection must reach the server that REDIS_HOST names. A hard-coded host
 * splits the app across two servers when REDIS_HOST is not 127.0.0.1.
 */
test('every redis connection uses the REDIS_HOST server', function (): void {
    $previous = getenv('REDIS_HOST');
    putenv('REDIS_HOST=10.20.30.40');
    $_ENV['REDIS_HOST'] = $_SERVER['REDIS_HOST'] = '10.20.30.40';

    try {
        $redis = (require config_path('database.php'))['redis'];
    } finally {
        $previous === false ? putenv('REDIS_HOST') : putenv("REDIS_HOST=$previous");
        unset($_ENV['REDIS_HOST'], $_SERVER['REDIS_HOST']);
    }

    $hosts = collect($redis)->except(['client', 'options', 'clusters'])->map(fn (array $connection): ?string => $connection['host'] ?? null);

    expect($hosts->keys()->all())->toContain('default', 'cache', 'widgets', 'socials')
        ->and($hosts->unique()->values()->all())->toBe(['10.20.30.40']);
});
