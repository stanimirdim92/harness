<?php

declare(strict_types=1);

arch('application code passes the PHP preset')
    ->preset()->php();

/*
 | Each ignored class uses a flagged function on purpose:
 | - Advertisers Utils: md5() builds the stored advertiser hash, not a security token.
 | - Socials Utils: exec() runs ffmpeg with escapeshellarg() arguments.
 | - WorktreeDatabaseRegistry, ProcessMetaAdMedia: tempnam() creates private temporary files.
 | - FixEncodedWebsiteUrls: assert() narrows a type for static analysis.
 */
arch('application code passes the security preset')
    ->preset()->security()
    ->ignoring([
        'App\Support\WorktreeDatabaseRegistry',
        'Modules\Advertisers\Console\Commands\FixEncodedWebsiteUrls',
        'Modules\Advertisers\Helpers\Utils',
        'Modules\Socials\Helpers\Utils',
        'Modules\Socials\Jobs\ProcessMetaAdMedia',
    ]);

/*
 | ignoring() above exempts a class from every security function. Each
 | exempt class may still use only the function it is exempt for.
 */
$securityFunctions = [
    'md5', 'sha1', 'uniqid', 'rand', 'mt_rand', 'tempnam', 'str_shuffle', 'shuffle', 'array_rand', 'eval',
    'exec', 'shell_exec', 'system', 'passthru', 'create_function', 'unserialize', 'extract', 'mb_parse_str',
    'dl', 'assert',
];

foreach ([
    'App\Support\WorktreeDatabaseRegistry' => 'tempnam',
    'Modules\Advertisers\Console\Commands\FixEncodedWebsiteUrls' => 'assert',
    'Modules\Advertisers\Helpers\Utils' => 'md5',
    'Modules\Socials\Helpers\Utils' => 'exec',
    'Modules\Socials\Jobs\ProcessMetaAdMedia' => 'tempnam',
] as $exemptClass => $allowedFunction) {
    arch("{$exemptClass} uses no security function except {$allowedFunction}")
        ->expect($exemptClass)
        ->not->toUse(array_values(array_diff($securityFunctions, [$allowedFunction])));
}

arch('application code declares strict types')
    ->expect(['App', 'Modules\Advertisers', 'Modules\Core', 'Modules\Socials'])
    ->toUseStrictTypes();
