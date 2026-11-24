# PHP Patterns Reference

Leadbuster patterns that sit next to the layer chain in `SKILL.md`. This app has no
Swoole, ReactPHP or fiber dependency, and routes with `$router->get(...)->name(...)`,
not attribute routing.

## API Resource

Not part of the layer chain in `SKILL.md` but used at the Controller →
response boundary. One resource per model, `@mixin` for IDE support on
`$this->`:

```php
namespace Modules\Advertisers\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

/**
 * @mixin \Modules\Advertisers\Models\Advertiser
 */
final class AdvertiserResource extends JsonResource
{
    public function toArray(Request $request): array
    {
        return [
            'id' => $this->id,
            'name' => $this->name,
            'website_status' => $this->website_status->value,
            'created_at' => $this->created_at->toIso8601String(),

            // conditional relationship
            'ads' => AdResource::collection($this->whenLoaded('ads')),

            // conditional attribute
            'is_verified' => $this->when($this->verified_at !== null, true),
        ];
    }
}
```

## Jobs & Queues

`Modules/<M>/app/Jobs` — used heavily in `Socials` for scrapers. Constructor
takes primitives/IDs (never a model instance, so the payload serializes
small), re-fetches inside `handle()`:

```php
namespace Modules\Socials\Jobs;

use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;

final class RunApifyAdScraper implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $tries = 3;
    public int $timeout = 120;

    public function __construct(private readonly int $advertiserId) {}

    public function handle(): void
    {
        // re-fetch by ID here, don't serialize the model itself
    }

    public function failed(\Throwable $exception): void
    {
        Log::error('Apify ad scrape failed', [
            'advertiser_id' => $this->advertiserId,
            'error' => $exception->getMessage(),
        ]);
    }
}

// Dispatching
RunApifyAdScraper::dispatch($advertiser->id);
RunApifyAdScraper::dispatch($advertiser->id)->onQueue('scrapers');
```

## Event & Listener

Cross-module events go through Core. See "Module boundaries" in `SKILL.md`.

## Enum with a behavior method

When an enum needs a display name, implement Core's `HasName` contract with the
`FormatName` trait instead of a hand-rolled `match` label switch:

```php
namespace Modules\Advertisers\Enums;

use Modules\Core\Concerns\FormatName;
use Modules\Core\Enums\Contracts\HasName;

enum WebsiteStatus: string implements HasName
{
    use FormatName;

    case Active = 'ACTIVE';
    case Inactive = 'INACTIVE';
    case Pending = 'PENDING';

    public function name(): string
    {
        return self::format($this->name);
    }
}
```

Validate an enum-backed field with `new Enum(WebsiteStatus::class)` in the
FormRequest's `rules()`, same as any other rule.

## Modern PHP building blocks

- **Readonly class** (8.2+) — use it for value objects and events
  (`final readonly class SocialAdMonthsRecomputed`). Request DTOs extend
  `Spatie\LaravelData\Data` instead and are not readonly; see "Data DTOs" in `SKILL.md`.
- **Match expression** — prefer it over `switch` or if-chains for anything that returns a value:
    ```php
    return match ($status) {
        WebsiteStatus::Active => 'green',
        WebsiteStatus::Inactive => 'red',
        WebsiteStatus::Pending => 'yellow',
    };
    ```
- **First-class callable syntax** (8.1+) — `$finder = $this->advertiserRepository->fetchAll(...)` instead of `fn ($x) => $this->advertiserRepository->fetchAll($x)`.
- **`never` return type** — for a method that always throws or exits.
