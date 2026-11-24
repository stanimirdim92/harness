---
paths:
    - 'resources/js/components/partials/TickerPage/**'
---

# Ticker Page

## Paid ads event detection reads feed data, not hardcoded lists
Every ticker row carries `post.type` (social_feed_posts.type, shipped by TickerExportResource): `'paid_ads_event'` is a paid-ads EVENT, `'paid_ads'` is a single ad (CategoriseAds), `'social_post'` is an organic post. Test for the exact value; never infer a kind from a missing type. The event subtype comes from the 4th source_post_id segment (`paid-ads:{profileId}:{date}:{eventType}`, written by PaidAdsTickerEventGenerator). Do not reintroduce badge-text or paid_ads_event_type field detection — those fields are dead. PAID_ADS_EVENT_TOKENS (ticker.page.helpers) exists only because feed categories carry display names without codes; single source, do not duplicate it per component.
