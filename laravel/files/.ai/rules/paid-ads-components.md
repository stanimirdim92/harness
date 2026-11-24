---
paths:
  - 'resources/js/components/partials/DetailsPage/PaidAdsComponents/**'
---

# Paid Ads Components

## Google preview_url is an image; noise.empty is a BE default, not a categoriser result
- `creative.preview_url` (serp_api_google_ads.link_preview) is always an image URL (tpc.googlesyndication.com/archive/simgad, 2mdn, ytimg) — the rendered ad as a picture. Render it with `<img>`, never an iframe. Text ads stored without headline/description fall back to it (`isSerpAd` requires captured copy).
- Google `["noise.empty"]` categories are stamped by GoogleAdsPayloadProcess (SerpAPIGoogleAds::EMPTY_CONTENT_ATTRIBUTES) on ads with no headline+description; they never went through the categoriser. `category_json IS NULL` means "never categorised" (all Meta ads before 2026-07). Both cases render no category badge: `displayedCategories()` in paidAdsView.helpers drops `noise.empty`, PaidAdCategoryBadges returns null when nothing is left, and the detail modal omits the Categories row. The list view is one CSS grid with `subgrid` header/rows so metric, date and control columns size to content (never truncate) and stay aligned; the title takes the rest.
- Ads sort newest-first on the FE via `DEFAULT_PAID_ADS_SORT` (published desc) because the BE pages by end_date / time_shown_last; keep the default in sync if the BE ordering changes.
- Meta and Google rows must both send `page=` and render the `loadMoreRef` sentinel inside the scroll container — MetaAdsRow.test.tsx guards this.
