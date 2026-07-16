# UI/UX design review

Media Manager Angular — Dashboard, Reports, Discover, UI catalog.

Reviewed against Demo screenshots (~1440×900) and current shell / media-ui code. Scoped as a desktop dark product UI, not a marketing landing page.

| | |
|---|---|
| **Verdict** | Solid ops shell |
| **Constraints** | Dark-only · desktop-first |
| **Status** | Unified review fixes 1–16 applied |

## Fixes applied (unified review 1–16)

| # | Fix |
|---|-----|
| 1 | Hover + focus-visible on tabs, chips, feedback buttons, library switcher, MmButton, Reports summaries |
| 2 | Discover feedback collapsed to Lucide icon-button row |
| 3 | Poster gradient scrim + overlay title `aria-hidden` |
| 4 | Reports expand chevron on run / quiet `<details>` |
| 5 | Tabs vs chips visual hierarchy (size / padding) |
| 6 | Active states use accent tint fill (not color alone) |
| 7 | Discover sources use `radiogroup` / `radio` |
| 8 | `MmStatus` has `role="status"` |
| 9 | Compact library posters (~140px) + tighter home gaps for fold |
| 10 | `prefers-reduced-motion` on library disclosure |
| 11 | `MmStateCard` uses Lucide kinds (`loading` / `empty` / `error`) |
| 12 | Spacing, text-size, and transition tokens in `media-ui.scss` |
| 13 | Discover card `meta` / `art` / `requestAction` → `computed()` |
| 14 | External-link cue + SR text on Jellyfin / calendar links |
| 15 | Interactive transitions via `--mm-transition-*` |
| 16 | Ops-tone page ledes |

Also: ThemeService redundant `applyTheme` removed; Sass `@import` → `@use` in dashboard `styles.scss`.

## Fixes applied (premium pass 17–25)

| # | Fix |
|---|-----|
| 17 | Home grid `align-items: start` + Library posters `auto-fit minmax(108px, 1fr)` — kills dead space |
| 18 | ~~Dashboard page header~~ — reverted in feedback round 3 (user: no header on Dashboard) |
| 19 | `color-scheme: dark` on tokyo-night and github-dark-pro (was nocturne-only) |
| 20 | Demo badge quieted (muted pill, no accent border) |
| 21 | Upcoming rows dedupe per-row date cells; group date headings carry the date |
| 22 | Shell layering: topbar / sidebar transparent, cards get gradient + inset top highlight |
| 23 | `--mm-text-heading: 17px` token for card titles; KPI speeds / percents bumped to display weight |
| 24 | Discover sources restyled as segmented control; feedback buttons get `title` tooltips |
| 25 | Mobile: `WORKSPACE` nav label hidden ≤900px |

Two style-assertion specs updated to the new intended CSS (poster `auto-fit`, calendar compact rail). 221/221 unit tests pass; eslint clean.

## Fixes applied (user feedback round 26–29)

| # | Fix |
|---|-----|
| 26 | Download controls get icons + color: Pause all (warning/pause icon), Resume all (primary/play icon); `MmButton` gains an `icon` input |
| 27 | Dashboard page header removed (back to sr-only h1) |
| 28 | Topbar removed; brand + demo badge moved into sidebar header — reclaims 68px of vertical space |
| 29 | Sidebar is `position: sticky; height: 100dvh` — theme picker pinned in view, no page-scroll to reach it |

`app.spec.ts` nav-link assertion scoped to `.sidebar__nav a` (brand link now lives inside `<nav>`). 221/221 unit tests pass; eslint clean.

## Fixes applied (round 4: 30–34)

| # | Fix |
|---|-----|
| 30 | Card header icons on all boards (Library / Upcoming / Downloads); headers flex with accent-colored icon |
| 31 | Home grid back to `stretch`; poster grid `align-content: safe center` — equal row heights, no void |
| 32 | Downloads items 3 rows → 2 (progress bar + meta inline); torrents grouped by status (`groupTorrents`), headings only when >1 state |
| 33 | Calendar date-heading `margin: 18px 0 0` (bottom margin removed) |
| 34 | Sidebar 236px; brand 15px nowrap on one line; footer top border anchors the theme picker |

## UX subagent verification loop (fixes 35–43)

Loop: coder subagent reviewed screenshots of all pages at 1920/1440/390 → triage + apply → re-verify. 3 iterations to `VERDICT: SATISFIED`.

| # | Fix |
|---|-----|
| 35 | Mobile nav: right-edge fade mask ≤900px; DEMO badge hidden ≤560px (Discover item was clipped off-screen) |
| 36 | `.content` centered (`margin: 0 auto`) — killed the right-side void at 1920 |
| 37 | Discover grid `auto-fit` + 320px cap + `mm-poster` width override — fills the row, constant 18px gutters, right edge aligns with header actions |
| 38 | Discover chips unified into the segmented-control language (`.filters:has(> .chip)`) |
| 39 | Discover "Request" CTA → accent primary when enabled |
| 40 | Reports "repaired" tone warning → success |
| 41 | Downloads Pause/Resume smart-disabled by queue state (`hasActive` / `hasPaused`) |
| 42 | Automation "Up next" → "Recent runs" (data is latest run per job) |
| 43 | Mobile Library posters 2-up; sidebar WORKSPACE label removed |

Skipped with reasons: Reports/Discover sparse-data emptiness (KPI strip deferred feature), "3 actionable runs" pill (deliberate ops summary), Library footer count (footer alignment), "Untitled Cut" year (deliberate demo case). Specs updated for repaired tone, 2-up grid, and Pause/Resume state disabling. 221/221 tests pass; eslint clean.

## Out of scope (intentional)

Light themes, responsive certification below 960px, and per-torrent download controls remain product non-goals. Deferred premium ideas: route view transitions, theme-picker swatches, poster art direction (hash-based duotone mesh gradients), URL-synced filter state, Reports KPI strip.
