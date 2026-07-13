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

## Out of scope (intentional)

Light themes, responsive certification below 960px, and per-torrent download controls remain product non-goals.
