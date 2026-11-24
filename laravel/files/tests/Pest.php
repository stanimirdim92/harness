<?php

declare(strict_types=1);

use Illuminate\Database\Schema\Blueprint;
use Tests\TestCase;

/*
|--------------------------------------------------------------------------
| Test Case
|--------------------------------------------------------------------------
|
| The closure you provide to your test functions is always bound to a specific PHPUnit test
| case class. By default, that class is "PHPUnit\Framework\TestCase". Of course, you may
| need to change it using the "pest()" function to bind a different classes or traits.
|
*/

pest()->extend(TestCase::class)
    ->in('Feature', 'Browser');

/*
| Test impact analysis runs only with `composer test -- --tia`. Each checkout keeps its own
| graph, because the default directory is shared by every worktree of the repository. The
| watches add the module layout and the schema snapshot to Pest's Laravel defaults.
*/
pest()->tia()
    ->directory('.pest/tia')
    ->watch([
        'database/schema/**' => 'tests',
        'modules_statuses.json' => 'tests',
        'Modules/*/module.json' => 'tests',
        'Modules/*/config/**/*.php' => 'tests',
        'Modules/*/database/migrations/**/*.php' => 'tests',
        'Modules/*/resources/**' => 'tests',
        'Modules/*/app/** !*.php' => 'tests',
    ]);

/*
|--------------------------------------------------------------------------
| Functions
|--------------------------------------------------------------------------
|
| While Pest is very powerful out-of-the-box, you may have some testing code specific to your
| project that you don't want to repeat in every file. Here you can also expose helpers as
| global functions to help you to reduce the number of lines of code in your test files.
|
*/

function ensureAdsScraperTables(): void
{
    $schema = app('db')->connection()->getSchemaBuilder();

    if (!$schema->hasTable('integrations')) {
        $schema->create('integrations', function (Blueprint $table): void {
            $table->id();
            $table->string('name')->nullable();
            $table->string('name_legal')->nullable();
            $table->string('code')->nullable();
            $table->boolean('active')->default(true);
            $table->string('lang')->nullable();
            $table->timestamps();
        });
    }

    if (!$schema->hasTable('advertisers')) {
        $schema->create('advertisers', function (Blueprint $table): void {
            $table->id();
            $table->unsignedBigInteger('integration_id')->nullable();
            $table->string('name')->nullable();
            $table->string('title')->nullable();
            $table->string('website')->nullable();
            $table->string('website_normalized')->nullable();
            $table->unsignedInteger('snapshot_day')->nullable();
            $table->timestamp('time_created')->nullable();
            $table->timestamp('time_modified')->nullable();
            $table->timestamp('time_deleted')->nullable();
        });
    }

    if (!$schema->hasTable('advertisers_socials')) {
        $schema->create('advertisers_socials', function (Blueprint $table): void {
            $table->id();
            $table->unsignedBigInteger('advertiser_id');
            $table->string('facebook')->nullable();
            $table->string('instagram')->nullable();
            $table->string('tiktok')->nullable();
            $table->string('twitter')->nullable();
            $table->string('linkedin')->nullable();
            $table->string('youtube')->nullable();
            $table->string('pinterest')->nullable();
        });
    }

    if (!$schema->hasTable('bright_data_queue')) {
        $schema->create('bright_data_queue', function (Blueprint $table): void {
            $table->id();
            $table->unsignedBigInteger('advertiser_id')->nullable();
            $table->string('url')->nullable();
            $table->unsignedBigInteger('social_id')->default(0);
            $table->string('platform')->nullable();
            $table->string('hash')->nullable()->index();
        });
    }

    if (!$schema->hasTable('serp_api_google_ads')) {
        $schema->create('serp_api_google_ads', function (Blueprint $table): void {
            $table->id();
            $table->unsignedInteger('website_root_id')->nullable();
            $table->string('google_advertiser_id')->nullable();
            $table->string('ad_creative_id');
            $table->string('advertiser_name')->nullable();
            $table->string('ad_format_type')->nullable();
            $table->unsignedBigInteger('impressions_lower')->default(0);
            $table->unsignedBigInteger('impressions_upper')->default(0);
            $table->text('description')->nullable();
            $table->text('headline')->nullable();
            $table->text('target_domain')->nullable();
            $table->text('link')->nullable();
            $table->text('link_preview')->nullable();
            $table->text('link_video')->nullable();
            $table->timestamp('time_created')->nullable();
            $table->timestamp('time_modified')->nullable();
            $table->timestamp('time_shown_first')->nullable();
            $table->timestamp('time_shown_last')->nullable();

            $table->json('category_json')->nullable();
            $table->string('post_summary', 255)->nullable();
            $table->string('value_score', 12)->nullable();
            $table->integer('score')->nullable();
            $table->json('tags')->nullable();

            $table->unique(['website_root_id', 'ad_creative_id'], 'serp_api_google_ads_unique2');
        });
    }

    if (!$schema->hasTable('facebook_profiles_ads')) {
        $schema->create('facebook_profiles_ads', function (Blueprint $table): void {
            $table->id();
            $table->string('ad_archive_id');
            $table->string('publisher_platform', 512)->nullable();
            $table->string('body_text', 3072)->nullable();
            $table->string('caption', 320)->nullable();
            $table->string('cta_text', 150)->nullable();
            $table->char('display_format', 15)->nullable();
            $table->string('link_url')->nullable();
            $table->dateTime('start_date')->nullable();
            $table->dateTime('end_date')->nullable();
            $table->unsignedBigInteger('impressions')->default(0);
            $table->unsignedBigInteger('ad_spend')->default(0);
            $table->char('country_code', 3)->nullable();
            $table->char('currency', 3)->nullable();
            $table->timestamp('time_created')->nullable();
            $table->timestamp('time_modified')->nullable();
            $table->unsignedBigInteger('facebook_profile_id')->nullable();

            $table->json('category_json')->nullable();
            $table->string('post_summary', 255)->nullable();
            $table->string('value_score', 12)->nullable();
            $table->integer('score')->nullable();
            $table->json('tags')->nullable();

            $table->unique(['ad_archive_id', 'facebook_profile_id'], 'uniq_facebook_profiles_ads_archive_profile');
        });
    }
}
