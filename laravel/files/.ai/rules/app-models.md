---
paths:
    - 'Modules/Advertisers/app/Models/*.php'
---

# App Models

## Cast ad-history zero dates to null

Use Core’s `NullableZeroDateTime` for ad-history fields that can contain a MySQL zero date.
