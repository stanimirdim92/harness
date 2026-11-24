---
paths:
  - 'resources/js/utils/ticker/*.ts'
---

# Ticker

## Advertising Activity signals filter via srch_category event codes — no BE change needed
Paid-ads event rows store category_json = ["paid_ads", "<event_code>"] (written by PaidAdsTickerEventGenerator), and TickerRepository filters srch_category with JSON_OVERLAPS, so sending an event code (paid_ads_started, paid_ads_stopped, paid_ads_activity_increase, paid_ads_activity_reduced, …) as a srch_category value returns exactly those signal rows and ORs with regular taxonomy codes. TickerRequest does not restrict srch_category values. The dropdown's Signals list is the design-fixed ADVERTISING_ACTIVITY_SIGNALS constant in ticker.page.helpers.ts; signal codes must stay exempt from the legacy paid-ads stripping in Ticker.tsx (isSignalCategoryCode) because they contain the "paidads" token.
