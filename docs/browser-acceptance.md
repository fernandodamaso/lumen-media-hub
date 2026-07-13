# Browser acceptance (Demo, desktop)

Run against `npm start` at ~1440×900. Check only behaviors reachable in the default Demo UI.

Verified 2026-07-13 during FDM-493 Path B (local showcase) hand-off.

## Navigation

- [x] Sidebar: Dashboard, Reports, Discover, UI catalog
- [x] Each destination loads with the expected title / primary content
- [x] Browser Back / Forward restores the previous route without a blank shell

## Home hierarchy

- [x] Library is the hero region; downloads + automation sit in operations; calendar is the supporting rail
- [x] Grid remains readable with representative mock content
- [x] Theme picker is usable from the top bar

## Themes

- [x] Switch Nocturne → Tokyo Night → GitHub Dark Pro; UI tokens update
- [x] Reload keeps the selected theme (`media-ui-theme`)

## Keyboard focus

- [x] Tab order follows the visual layout on home (library → operations → calendar) — covered by `dashboard-page.spec.ts` focus-order assertion; spot-checked `:focus-visible` styles in Demo
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
| Home keeps other regions usable when one feature fails | `dashboard-page.spec.ts` — “keeps other regions usable when one feature fails” |
| Home stays unambiguous when a feature is empty | `dashboard-page.spec.ts` — “keeps the grid unambiguous when a feature is empty” |
| Reduced motion suppresses nonessential enter animation | `dashboard-page.spec.ts` — “declares reduced-motion suppression…” |
| Calendar empty / error | `calendar.facade.spec.ts`, `calendar-board.spec.ts` |
| Library empty / error | `library.facade.spec.ts` |
| Automation partial / error | `automation.facade.spec.ts` |
| Downloads loading / empty / error | `downloads-board.spec.ts` |
| Reports refresh failure retains prior data | reports facade / page specs |
| Discover source isolation / disabled request reasons | discover facade / page specs |

## Local showcase gate (Path B)

- [x] Clean instructions in README suffice for `npm ci` + `npm start`
- [x] Screenshots in `docs/screenshots/` match home, Discover, Reports, Storybook, and a non-default theme
- [x] `npm run lint`, unit tests, `build:dashboard`, `build:media-ui`, `build:storybook`, and `build:pages` succeed
