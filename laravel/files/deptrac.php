<?php

declare(strict_types=1);

use Deptrac\Deptrac\Contract\Config\{AnalyserConfig, DeptracConfig, EmitterType, Layer, Ruleset};
use Deptrac\Deptrac\Contract\Config\Collector\{BoolConfig, ClassLikeConfig, DirectoryConfig, PhpInteralConfig};
use Deptrac\Deptrac\Contract\Config\Formatter\{GraphvizConfig, MermaidJsConfig};

/*
 * Module boundaries (owner ruling 2026-11-24):
 * - Core is the shared kernel. Advertisers and Socials may use Core; Core uses neither.
 * - Advertisers and Socials reach each other only through events and notifications:
 *   a listener or job of one module may use the Published ring of the other. Nothing else.
 * - Inside a module every dependency points inward (DDD bounded contexts, hexagonal rings):
 *     Domain <- Model <- Ports <- Application <- entry points (Queue, Console, Http)
 *                              Ports <- Adapters (implementations)
 * - A console command dispatches a job, and only the job calls a service:
 *   Console may use Queue, never Application.
 * Deptrac forbids every dependency that no rule below allows.
 */
return static function (DeptracConfig $config): void {
    $modules = ['Core', 'Advertisers', 'Socials'];

    /** Folders under Modules/<Module>/app/ that make up each ring. */
    $rings = [
        'Domain' => 'Enums|Data|Exceptions|Helpers',
        'Published' => 'Events|Notifications',
        'Model' => 'Models|Builders|Casts|Concerns',
        'Ports' => 'Contracts',
        'Application' => 'Services',
        'Adapters' => 'Repositories|Clients|Mail|Emails|Exports|Imports',
        'Queue' => 'Jobs|Listeners',
        'Console' => 'Console',
        'Http' => 'Http|Policies|Rules|Transformers',
        'Wiring' => 'Providers',
    ];

    /** Classes whose folder puts them in the wrong ring. */
    $moves = [
        // Repository interfaces live next to their implementations.
        '^Modules\[A-Za-z]+\Repositories\.+Interface$' => ['from' => 'Adapters', 'to' => 'Ports'],
        // Form request traits in Core/Concerns.
        '^Modules\Core\Concerns\(IncludeRouteParams|ValidationFailedOverride)$' => ['from' => 'Model', 'to' => 'Http'],
    ];

    $framework = [
        'Framework_Facades' => '^Illuminate\Support\Facades\.*',
        'Framework_Database' => '^Illuminate\Database\.*',
        'Framework_HttpClient' => '^(Illuminate\Http\Client|GuzzleHttp)\.*',
        'Framework_Http' => '^(Illuminate\(Http|Routing|Validation|Foundation\Http|Auth\Access|Session|Cookie)|Inertia|Symfony\Component\HttpFoundation)\.*',
        'Framework_Console' => '^(Illuminate\Console|Symfony\Component\Console)\.*',
    ];
    $specific = '(Illuminate\Support\Facades|Illuminate\Database|Illuminate\Http|GuzzleHttp|Illuminate\Routing|Illuminate\Validation|Illuminate\Foundation\Http|Illuminate\Auth\Access|Illuminate\Session|Illuminate\Cookie|Inertia|Symfony\Component\HttpFoundation|Illuminate\Console|Symfony\Component\Console)\\';

    $layers = [];
    foreach ($framework as $name => $regex) {
        $layers[$name] = Layer::withName($name)->collectors(ClassLikeConfig::create($regex));
    }
    // The HTTP client is not part of Framework_Http: a class belongs to exactly one layer.
    $layers['Framework_Http'] = Layer::withName('Framework_Http')->collectors(
        BoolConfig::create()
            ->must(ClassLikeConfig::create($framework['Framework_Http']))
            ->mustNot(ClassLikeConfig::create($framework['Framework_HttpClient'])),
    );
    // Framework pieces every ring may use: collections, contracts, Carbon, laravel-data, events, queue traits.
    $layers['Framework_Base'] = Layer::withName('Framework_Base')->collectors(
        BoolConfig::create()
            ->must(ClassLikeConfig::create('^(Illuminate|Laravel|Symfony|Carbon|Spatie|Psr)\.*'))
            ->mustNot(ClassLikeConfig::create('^'.$specific.'.*')),
    );
    // Third-party SDKs: only adapters and providers talk to them.
    $layers['Vendor'] = Layer::withName('Vendor')->collectors(
        BoolConfig::create()
            ->must(ClassLikeConfig::create('^(?!(Modules|App|Tests|Illuminate|Laravel|Symfony|Carbon|Spatie|Psr|Inertia|GuzzleHttp)\)[A-Za-z0-9_]+\.*'))
            ->mustNot(PhpInteralConfig::create('.*')),
    );
    // Namespaced PHP classes (Random\RandomException, Dom\...) are part of PHP, not vendor code.
    $layers['PhpInternal'] = Layer::withName('PhpInternal')->collectors(PhpInteralConfig::create('.*'));
    // Model factories (database/factories, outside the analysed paths) that models name in #[UseFactory].
    $layers['Factories'] = Layer::withName('Factories')->collectors(ClassLikeConfig::create('^Modules\[A-Za-z]+\Database\Factories\.*'));
    // Deptrac reads a PHPStan type alias (@phpstan-type Row array{...}) in a docblock as a class
    // of the current namespace. Collect the alias names so they are covered and usable everywhere.
    $aliases = [];
    foreach (new \RecursiveIteratorIterator(new \RecursiveDirectoryIterator(__DIR__.'/Modules', \FilesystemIterator::SKIP_DOTS)) as $file) {
        if ($file->isFile() && 'php' === $file->getExtension() && preg_match_all('/@phpstan-type\s+(\w+)/', (string) file_get_contents($file->getPathname()), $found)) {
            array_push($aliases, ...$found[1]);
        }
    }
    $aliases = array_values(array_unique($aliases));
    $layers['TypeAliases'] = Layer::withName('TypeAliases')->collectors(
        ClassLikeConfig::create('^Modules\.+\('.([] === $aliases ? 'NoAlias' : implode('|', $aliases)).')$'),
    );
    // The application's own User model and support classes (app/), shared like Core models.
    $layers['App'] = Layer::withName('App')->collectors(ClassLikeConfig::create('^App\.*'));

    foreach ($modules as $module) {
        foreach ($rings as $ring => $folders) {
            $directory = DirectoryConfig::create("Modules/$module/app/($folders)/.*");
            $collector = BoolConfig::create()->must($directory);
            foreach ($moves as $regex => $move) {
                if ($move['from'] === $ring) {
                    $collector->mustNot(ClassLikeConfig::create($regex));
                }
            }
            $collectors = [$collector];
            foreach ($moves as $regex => $move) {
                if ($move['to'] === $ring) {
                    $collectors[] = BoolConfig::create()
                        ->must(ClassLikeConfig::create($regex))
                        ->must(DirectoryConfig::create("Modules/$module/app/.*"));
                }
            }
            $layers["{$module}_$ring"] = Layer::withName("{$module}_$ring")->collectors(...$collectors);
        }
    }

    $layer = static fn (string $name): Layer => $layers[$name];

    $rulesets = [
        Ruleset::forLayer($layer('Framework_Base')),
        Ruleset::forLayer($layer('Vendor'))->accesses($layer('Framework_Base')),
        Ruleset::forLayer($layer('App'))->accesses($layer('Framework_Base'), $layer('Framework_Database'), $layer('Framework_Facades'), $layer('Framework_Http'), $layer('Vendor'), $layer('Core_Domain'), $layer('Core_Model')),
    ];
    foreach (array_keys($framework) as $name) {
        $rulesets[] = Ruleset::forLayer($layer($name))->accesses($layer('Framework_Base'));
    }

    $rulesets[] = Ruleset::forLayer($layer('TypeAliases'));
    $rulesets[] = Ruleset::forLayer($layer('PhpInternal'));

    foreach ($modules as $module) {
        $own = static fn (string ...$rings): array => array_map(static fn (string $ring): Layer => $layer("{$module}_$ring"), $rings);
        // Advertisers and Socials see Core's shared kernel; Core sees only itself.
        $kernel = static fn (string ...$rings): array => 'Core' === $module ? [] : array_map(static fn (string $ring): Layer => $layer("Core_$ring"), $rings);
        $framework = static fn (string ...$names): array => array_map(static fn (string $name): Layer => $layer("Framework_$name"), $names);
        // The other feature module's events and notifications.
        $peer = match ($module) {
            'Advertisers' => [$layer('Socials_Published')],
            'Socials' => [$layer('Advertisers_Published')],
            default => [],
        };

        $allowed = [
            'Domain' => [...$kernel('Domain'), ...$framework('Base')],
            'Published' => [...$own('Domain'), ...$kernel('Domain'), ...$framework('Base')],
            'Model' => [...$own('Domain'), ...$kernel('Domain', 'Model'), $layer('App'), $layer('Factories'), ...$framework('Base', 'Database')],
            'Ports' => [...$own('Domain', 'Model'), ...$kernel('Domain', 'Model', 'Ports'), $layer('App'), ...$framework('Base', 'Database')],
            'Application' => [...$own('Domain', 'Published', 'Model', 'Ports'), ...$kernel('Domain', 'Published', 'Model', 'Ports'), $layer('App'), ...$framework('Base', 'Database', 'Facades')],
            'Adapters' => [...$own('Domain', 'Model', 'Ports'), ...$kernel('Domain', 'Model', 'Ports'), $layer('App'), $layer('Vendor'), ...$framework('Base', 'Database', 'Facades', 'HttpClient')],
            'Queue' => [...$own('Domain', 'Published', 'Model', 'Application'), ...$kernel('Domain', 'Published', 'Model'), ...$peer, $layer('App'), ...$framework('Base', 'Database', 'Facades')],
            'Console' => [...$own('Domain', 'Queue'), ...$kernel('Domain'), ...$framework('Base', 'Console')],
            'Http' => [...$own('Domain', 'Model', 'Application'), ...$kernel('Domain', 'Model', 'Http'), $layer('App'), ...$framework('Base', 'Database', 'Facades', 'Http')],
            'Wiring' => [...$own(...array_keys($rings)), ...$kernel('Domain', 'Ports', 'Wiring'), $layer('App'), $layer('Vendor'), ...$framework('Base', 'Database', 'Facades', 'HttpClient', 'Http', 'Console')],
        ];
        foreach ($allowed as $ring => $targets) {
            $rulesets[] = Ruleset::forLayer($layer("{$module}_$ring"))->accesses($layer('TypeAliases'), $layer('PhpInternal'), ...$targets);
        }
    }

    // Graphs (mermaidjs, graphviz-*): one box per module, without the framework and vendor layers.
    $hidden = array_map($layer, ['Framework_Base', 'Framework_Facades', 'Framework_Database', 'Framework_HttpClient', 'Framework_Http', 'Framework_Console', 'Vendor', 'App', 'Factories', 'TypeAliases', 'PhpInternal']);
    $mermaid = MermaidJsConfig::create()->direction('LR')->hiddenLayers(...$hidden);
    $graphviz = GraphvizConfig::create()->hiddenLayers(...$hidden);
    foreach ($modules as $module) {
        $ringLayers = array_map(static fn (string $ring): Layer => $layer("{$module}_$ring"), array_keys($rings));
        $mermaid->groups($module, ...$ringLayers);
        $graphviz->groups($module, ...$ringLayers);
    }

    $config
        ->formatters($mermaid, $graphviz)
        ->paths('./Modules/Core/app', './Modules/Advertisers/app', './Modules/Socials/app')
        ->excludeFiles('#/tests?/.*#i', '#/(resources|lang|routes|config)/.*#', '#/database/(migrations|factories|seeders)/.*#')
        ->analyser(AnalyserConfig::create([
            EmitterType::USE_TOKEN,
            EmitterType::CLASS_TOKEN,
            EmitterType::FUNCTION_TOKEN,
            EmitterType::FILE_TOKEN,
            EmitterType::CLASS_SUPERGLOBAL_TOKEN,
            EmitterType::FUNCTION_SUPERGLOBAL_TOKEN,
            EmitterType::FUNCTION_CALL,
        ]))
        ->layers(...array_values($layers))
        ->rulesets(...$rulesets);
};
