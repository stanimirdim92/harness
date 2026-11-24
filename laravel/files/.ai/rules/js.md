---
paths:
    - 'resources/js/**'
    - 'resources/js/**/*.test.tsx'
---

# Js

## No defensive wrappers — trust the API data, derive lists from BE props

Access API fields directly (`?? ''` for nullables) and type payloads honestly; do not add asString/toTrimmed-style coercion wrappers, response-shape unwrap guesses, content-type checks, or type predicates that lie. Lists that mirror BE data must come from the data: paid-ads event tokens derive from the `categories_ads` Inertia prop (SocialAdsCategories::values()) via paidAdsEventTokens() — never hardcode BE enum copies. The defensive idiom in older files (post-preview.tsx) is legacy; do not replicate it.

## yarn lint runs on a TS 6 JS API; tsc and the build stay on TypeScript 7

`yarn lint` (eslint resources/js --quiet) works. The repo pins `"typescript": "^7"` (7.0.2) for `tsc` and `vite build`. TS 7 has no JS API, and typescript-eslint 8 supports TypeScript `<6.1` only: it throws `typescript-eslint does not support TS 7.0` when it loads TS 7. Do NOT pin TypeScript back to ^5/^6 (TS 7 is a deliberate choice, in production since ~2026-09-04).

How it works:

- `package.json` devDependency `"eslint-typescript6": "npm:@typescript/typescript6@~6.0.2"` installs the TS 6 JS API. `@typescript/typescript6` is the official TS-team compat package (TS 6.0.3 inside); the alias name is not arbitrary, see the `.bin/tsc` trap below.
- `eslint.compat.js` is the FIRST import of `eslint.config.js`. It puts the TS 6 API into the CommonJS require cache in place of `typescript`, so typescript-eslint gets TS 6. This affects the lint process only. It must run before any plugin loads, so keep it the first import.
- Yarn `packageExtensions` and `yarn patch` cannot do this: a package that lists `typescript` as a peer keeps its peer, and patches cannot change dependencies.
- `eslint.compat.js` also restores `SourceCode#getTokenOrCommentBefore/After`. ESLint 10 removed them and eslint-plugin-import 2.32 (latest, peer `eslint <=9`) still calls them in `import/order`; without the shim the rule crashes mid-run. Remove the shim when eslint-plugin-import supports ESLint 10.

Traps:

- The Yarn node-modules linker puts the bins of hoisted transitive packages into `node_modules/.bin`, and `@typescript/typescript6` pulls in `typescript@6` with its own `tsc` bin. Which `tsc` wins depends on the dependency name (a fresh `yarn install --immutable` with the name `eslint-typescript6` gives TS 7). After any change to these dependencies, check `./node_modules/.bin/tsc --version` prints 7.0.x. Do not rename the alias or add other TypeScript aliases without that check.
- Use `./node_modules/.bin/tsc --noEmit` as the type check; it is unaffected by lint.
- `yarn lint` (and `./node_modules/.bin/eslint resources/js --quiet`) exits 0 since AD-312 cleared the old debt (1cd1a0b4). Keep it clean: a lint error is a new error, not old debt.
- Old note (obsolete): a `ERR_INTERNAL_ASSERTION` stack from ESLint under Node 20/22 was a misleading wrapper around the TS 7 throw. It was never a Node version problem. Vite 8 and `bin/worktree-setup.sh` still need Node 20.19+ or 22.12+; `/usr/bin/node` can be older than `~/.local/bin/node`.

## Figma Light redesign: preserve every existing feature, restyle only what Light covers

Figma file q3aOMT5MH8nrpTovW6sTDt page "03 — Product Screens / Light" (14317:15501) is the visual authority; the existing app is the functional authority. Figma is incomplete: never remove, hide, disable, relocate or restyle a control, state, link, modal or role-gated element because it is missing from Figma; list such code-only elements in the phase inventory instead. Write the feature-preservation inventory and get approval before touching a screen; one phase at a time. Use the lb-* @theme tokens from resources/css/app.css (no hardcoded hex/radius/shadow); keep legacy tailwind.config.js tokens until every call site migrated. Auth pages use the shared auth shell with the Wide Tiles SVG (node 21227:14069), logo above the card; never the old beige/gray fill, blurred circles or sun-ray doodle. Keep Inertia useForm payloads, ids, autoComplete, aria wiring, _token, canResetPassword, read-only invitation email, status-based success cards, and excludedRoutes in components/core/layout.tsx. Preserve EN/DE lang keys/strings and the backend password policy; Figma copy differences are documented in docs/specs/DESIGN-SYSTEM-SPEC.md, not applied. Icons are Figma SVG exports in components/icons imported with ?react (no Unicode/icon libs). Figma is 1440x960 only: do not invent mobile layouts or states. Visual QA: Playwright at 1440x960 in an isolated local/CI env, never browser binaries on the staging server.

Token and component rules come from `00 — Foundations` (21355:13279) and `01 — Components` (21363:15122); when a screen contradicts an explicit rule there, follow the rule and report the conflict, ask when the rule is ambiguous. Typography is Manrope only, sizes 12/14/16/20/28/32. Reuse and extend `components/ui/*` primitives instead of page-local copies; check `components/partials/**` before writing a domain component. After a screen change, verify every existing control is still reachable under the same role conditions; any removal, consolidation, relocation or behaviour change needs explicit approval. Never edit a test to make failing behaviour look correct. Batch workflow and checkpoints: docs/tasks/REDESIGN-plan.md.

## jsdom enforces native input validation on submit-button clicks

Clicking a submit button in jsdom runs the browser's constraint validation: an `<input type="email">` holding `not-an-email` or an empty `required` field blocks the submit event, so component-side validation (e.g. ContactPersonModal's dot-requiring EMAIL_PATTERN) never runs. To exercise the component layer use a value native validation accepts but the component rejects (`jane@localhost`), or fill every `required` field first. Do not switch to `fireEvent.submit(form)` just to bypass it — that hides the native layer users actually hit.

## No hardcoded user-facing copy; every string goes through trans() with an EN fallback and keys in both lang/en and lang/de

All user-visible text (JSX text, aria-label, alt, placeholder, toast titles, error fallbacks) must be `trans('ns.key', 'English fallback')` with the key added to BOTH lang/en/<ns>.php and lang/de/<ns>.php (FrontendTranslations::all() shares those files with Inertia). Keep the fallback identical to the EN value so tests that mock `translations: {}` keep passing. Placeholders use `{name}` + fillTemplate (@/utils/common/fillTemplate) on the FE; `:name` is the Laravel BE style. UI primitives without Inertia context (e.g. ui/forms/password-field) take label props; the page passes trans() values. Audit: 2026-10-19 the "Missing German Translations" ticket came from hardcoded copy (Hide company, hidden/preset toasts, preset success card, modal aria-labels) and DE values left in English (filters.*_organic/_paid, clear_section_filters, ad format names) — grep for bare text lines / aria-label="..." and compare lang/de to lang/en for identical values before shipping copy.

## Frontend tests cover every state, not only the populated success render

A Vitest file with only the success render tests nothing. For each component or hook, list its decisions and test each one:

- loading, empty and error states, and a failed request (rejected promise, 4xx, 5xx, `response.ok === false`);
- a request that is cancelled or answered out of order (stale response);
- disabled and processing states, permission-dependent sections (admin and non-admin), null and undefined props;
- each rule of a multi-rule validator separately (`'short'` breaks all password rules at once, so it tests none of them alone);
- boundaries of formatters: 0, negative, very large, missing dates, malformed URL parameters (`page=abc`);
- every exported helper of a `utils/` module.

Assert what the user sees: text, role, `disabled`, the URL after navigation. Do not assert the `setError` mock call or CSS class names instead of the visible result. Do not write tests that only check the test harness.

Tests must not depend on the time zone or the date of the runner. Freeze time with `vi.useFakeTimers()` and `vi.setSystemTime()`, and give dates with an explicit offset. A fixed date inside a "last N months" window fails when the window moves past it.

Before you trust a new test, break the code it covers and see the test fail.
