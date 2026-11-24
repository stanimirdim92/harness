---
paths:
  - 'resources/js/components/ui/**'
---

# Ui

## lb-* text-style tokens and tailwind-merge: never mix text-lb-<size> with a text-* colour inside cn()
cn() = twMerge(clsx()). tailwind-merge only knows the default theme, so it classifies an unknown `text-lb-ui` (a font-size token from app.css @theme) as a text COLOUR and may drop it or the real colour class (`text-lb-ink`) when both go through cn(). Inside cva variants and cn() calls use `text-sm leading-5` / `text-xs leading-4` (identical values to LB/UI Small and LB/Caption) and keep `text-lb-<size>` tokens for standalone class strings only, until utils/common/utils.ts extends twMerge with the lb font-size group (needs its own approval). Same caution for `rounded-lb-*` and `shadow-lb-*` next to `rounded-md`/`shadow`: verify the merge result in a test when a base class of the same property exists.
