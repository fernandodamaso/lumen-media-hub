# Browser acceptance (Demo, desktop)

Run against `npm start` at 1920├ù1080 and 1440├ù900. Check only behaviors reachable in the default Demo UI.

Verified 2026-07-16 during the Nocturne ops-console redesign on the main dashboard branch.

## Navigation

- [x] Sidebar: Dashboard, Reports, Discover
- [x] Each destination loads with the expected title / primary content
- [x] Browser Back / Forward restores the previous route without a blank shell
- [x] Design-system review uses Storybook (`npm run storybook`), not an in-app catalog

## Home hierarchy

- [x] Header, metric cards, attention banner, and 3-column grid (downloads/runs, calendar, health/storage) render at 1920├ù1080
- [x] Layout adapts cleanly at 1440├ù900 without header wrapping or clipped controls
- [x] Grid remains readable with representative mock content
- [x] Theme picker is usable from the sidebar footer

## Themes

- [x] Switch Nocturne ΓåÆ Tokyo Night ΓåÆ GitHub Dark Pro; UI tokens update
- [x] Reload keeps the selected theme (`media-ui-theme`)
- [ ] Light themes remain out of scope; only dark themes are implemented

## Keyboard focus

- [x] Tab order follows the visual layout on home (library ΓåÆ operations ΓåÆ calendar) ΓÇö covered by `dashboard-page.spec.ts` focus-order assertion; spot-checked `:focus-visible` styles in Demo
- [x] Focus rings are visible (`:focus-visible`) on nav and primary controls
- [x] No keyboard trap in Discover tabs or Reports expanders

## Feature states (reachable Demo)

- [x] Reports: actionable runs are prioritized; quiet runs can be inspected
- [x] Discover: source tabs (Hermes / Jellyseerr / Trakt) swap content without leaking filters
- [x] Library kind toggle (movies / series) updates the grid
- [x] Downloads board shows torrents with pause/resume affordances in Demo

## States covered by unit tests (not manually selectable in Demo)

| Concern | Spec |
|---------|------|
| Home keeps other regions usable when one feature fails | `dashboard-page.spec.ts` ΓÇö ΓÇ£keeps other regions usable when one feature failsΓÇ¥ |
| Home stays unambiguous when a feature is empty | `dashboard-page.spec.ts` ΓÇö ΓÇ£keeps the grid unambiguous when a feature is emptyΓÇ¥ |
| Reduced motion suppresses nonessential enter animation | `dashboard-page.spec.ts` ΓÇö ΓÇ£declares reduced-motion suppressionΓÇªΓÇ¥ |
| Calendar empty / error | `calendar.facade.spec.ts`, `calendar-board.spec.ts` |
| Library empty / error | `library.facade.spec.ts` |
| Automation partial / error | `automation.facade.spec.ts` |
| Downloads loading / empty / error | `downloads-board.spec.ts` |
| Reports refresh failure retains prior data | reports facade / page specs |
| Discover source isolation / disabled request reasons | discover facade / page specs |

## Live-mode smoke test

- [x] `npm run start:live` proxies `/api` to `http://127.0.0.1:8085`
- [x] Home loads with `Live` badge and real backend data (read-only inspection only)
- [x] Library, Downloads, and Calendar regions render from the live service

## Local showcase gate

- [x] Clean instructions in README suffice for `npm ci` + `npm start`
- [x] Screenshots in `docs/screenshots/` match home, Discover, Reports, Storybook, and a non-default theme
- [x] `npm run lint`, unit tests, canonical `npm run build`, `build:storybook`, and `test:storybook` succeed
- [x] Obsolete `build:pages` target/script/provider removed
