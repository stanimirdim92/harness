---
paths:
  - 'Modules/*/app/{Jobs,Services,Console/Commands}/*.php'
---

# Jobs Services Console Commands

## Use upsert/updateOrCreate/firstOrCreate for idempotent writes
In import, sync, webhook, and crawling write paths, use `upsert()`/`updateOrCreate()`/`firstOrCreate()` instead of a manual find-then-save.

## Preserve-on-conflict is not a bug to "upgrade" to upsert
`insertOrIgnore()`/`insertOrIgnoreUsing()` and `upsert()` are both atomic, but
they are not interchangeable: `upsert` overwrites an existing row, `insertOrIgnore`
leaves it untouched. Where a path deliberately preserves already-written rows —
`PaidAdsTickerEventGenerator::persistEvents()` is the reference case — the ignore
is required behaviour, not a missed update. Do not convert it to an upsert.

The trade-off is accepted and known: rows written by an earlier run keep their
original values, so a later change to how a value is computed does not reach them.
Backfilling those rows is a separate, explicit migration — never a side effect of
the write path.
