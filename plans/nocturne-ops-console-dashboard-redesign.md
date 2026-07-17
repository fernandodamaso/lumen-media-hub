# Redesign home dashboard to the "Nocturne ops console" spec

Treat the pasted image-generation prompt as the design spec and rebuild the `/` home dashboard + app shell in `projects/dashboard` to match it: 285px sidebar with WORKSPACE/SERVICES groups, dashboard page header (search, Request media, Open Jellyfin, avatar), 4 metric cards, attention banner, and a 3-column grid (Active downloads + Recent automation runs | Upcoming | Service health + Storage overview).

Working tree note: branch `feat/architecture-api-ready` has uncommitted refactor work; this redesign builds on top of it as-is. No git mutations.

## Data reality vs spec (drives the work)

| Spec wants | Exists today | Plan |
|---|---|---|
| 8-service health + latency | `AutomationSummary.services` (mock: 4 services, no latency; live: 4, no latency) | Extend `AutomationService` with optional `latencyMs`; mock ships all 8 w/ latency; live shows what backend returns |
| Storage overview + 78% metric | nothing | New port method `getStorageOverview()`; mock fixtures; live `GET /api/storage/overview` with graceful "unavailable" fallback |
| Library metric 504 (428 movies · 76 series) | `listLibraryItems` (12 fixtures) | New port method `getLibraryStats()` → `{movies, series}`; mock 428/76; live `GET /api/jellyfin/stats` w/ fallback to item counts |
| Per-torrent pause buttons | only pause-all/resume-all | New port methods `pauseTorrent(id)` / `resumeTorrent(id)`; live `POST /api/qbt/torrents/stop|start`; failure surfaces via existing `notice` pattern |
| Upcoming chips Available/Monitored/Premieres | status `available`/`pending` only | Extend `CalendarEvent.status` union + optional `art`; live mapper best-effort from `monitored`/premiere flags |
| Search field w/ ⌘K | no search anywhere | Submit opens Jellyfin search externally (`jellyfinBase`); ⌘K focuses field. No fake backend search |
| Downloads/Upcoming posters, spec demo values | no art on torrents/events | Deterministic gradient thumbs (same approach as `MmPoster` default art); rewrite demo fixtures to spec values |

## Explicit decisions / deviations from spec (veto at approval)

1. **Library poster wall leaves the home page** — the spec's home has no poster grid; the Library metric card replaces it. `library-board.*` + `library.facade.ts` are deleted; a small `LibraryStatsFacade` replaces them.
2. **Nav**: WORKSPACE = Dashboard/Reports/Discover (existing routes only). "Requests", "Settings", "Users" omitted — no routes/features exist; dead nav is worse than missing nav.
3. **SERVICES nav rows** link externally to each service UI when a base URL is configured (new optional env bases `prowlarrBase`, `sabnzbdBase`, `qbittorrentBase`, `bazarrBase` alongside existing jellyfin/sonarr/radarr); no base ⇒ plain row, per existing operational-link policy. Status dots: muted for healthy, prominent amber/red for problem states only.
4. **"Demo data" toggle**: rendered but `aria-disabled` (Demo/Live is build-time config) with an explanatory title; not a fake interactive control.
5. **Avatar "FD"**: decorative initials circle, no dropdown (no account system exists).
6. **No three-dot overflow menus / no new dropdown component** — no real actions exist to put in them. Real actions kept: per-torrent pause, chevron links, View all links.
7. **Pause all vs Resume all becomes one contextual button** (spec: never show both): Pause all when anything is downloading, else Resume all when anything is paused.
8. **Storage card footer link omitted** (no storage-details target); all other footers get real targets: View all runs → `/reports`, Manage services → `/reports`, View issues → `/reports`, Open qBittorrent → external, View calendar → Sonarr external, Open Jellyfin → external.
9. **Font stays Geist Variable** (spec lists it as an approved alternative; already loaded). **Nocturne token values updated to the spec palette** (page `#080D17`, sidebar `#080C15`, card `#101827`, nested `#172133`, line `#263247`, accent `#6857F5`/`#7586FF`, success `#4DDC91`, warning `#F4BB43`, danger `#FF5964`, text `#F4F7FC`/`#A9B4C8`/`#748199`); add `--mm-color-info: #5EA0FF` and `--mm-color-premiere: #9B78FF` semantic tokens. `radius-lg` 14→12px; flatten card shadow + remove hover lift; add `tabular-nums` for metric/speed values.

## Phases

### 1. Tokens & global styles
- `app/ui/media-ui.scss`: Nocturne palette per decision 9; new info/premiere tokens through all three alias layers (semantic + component); radius/shadow adjustments. Other two themes: add the two new tokens with theme-appropriate values (they must keep working).
- `styles.scss`: keep `.page-intro` etc. for Reports/Discover; no global font change.

### 2. Data layer (port + both adapters, Demo/Live parity)
- `media-stack/media-stack-api.ts`: add `getStorageOverview()`, `getLibraryStats()`, `pauseTorrent(id)`, `resumeTorrent(id)`; extend `AutomationService.latencyMs`; extend `CalendarEvent` status/art.
- New models: `StorageOverview { volumes: StorageVolume[]; availability }`, `StorageVolume { id, label, kind: 'library'|'downloads'|'cache', usedBytes, totalBytes }`, `LibraryStats { movies, series }`. Wire DTOs confined to `app/media-stack/wire/`.
- `mock-media-stack-api.ts`: fixtures rewritten to spec values — 8 services w/ latency (Prowlarr degraded 350ms + warning count, SABnzbd down "last seen 18m"); storage 4.8/7.2TB, 324GB/1TB, 68/500GB; torrents Afterlight 68% 4.7/6.9GB ↓4.0MB/s ↑312KB/s 9min, The Blue Hour 31% 620MB/2.0GB ↓1.7 ↑78KB/s 13min, Orbit Station seeding 100% 5.4GB ↑117KB/s; calendar Cowboy Bebop S1E5 available 18:00, The Blue Hour S2E3 monitored 21:30, Dune premiere 00:00, The Expanse S4E2 monitored Wed; cron runs Hardlink cleanup completed "42 files hardlinked, 18.7 GB saved" 3m, Stale metadata failed "3 items failed to refresh" 18m, Watchdog completed 35m; library stats 428/76. Stateful per-torrent pause/resume.
- `http-media-stack-api.ts` + `live-api.mappers.ts`: implement new endpoints; tolerate missing backend support (unavailable/empty per existing availability pattern).
- `environments/*.ts` + `media-stack-api.providers.ts`: new optional service link bases → extend `provideOperationalLinkBases()`.
- Update/add specs: `mock-media-stack-api.spec.ts`, `http-media-stack-api.spec.ts`, `media-stack-api.providers.spec.ts`, model/format specs.

### 3. Facades
- New root `ServiceHealthFacade` (providedIn root, 60s poll): owns `getAutomationSummary()` — services, problems, generatedAt, health counts. Consumed by sidebar, attention banner, Service health card, Services metric.
- `AutomationFacade` (page-scoped): stops fetching summary; reads it from `ServiceHealthFacade`; keeps `listCronLogs()` for the runs table.
- New page-scoped `StorageFacade`; new `LibraryStatsFacade` (replaces `LibraryFacade`).
- `DownloadsFacade`: add `runTorrentAction(id, 'pause'|'resume')`, contextual pause/resume-all computed.
- `CalendarFacade`: pass through new statuses/art.
- Facade specs for all of the above.

### 4. Shell (`app.html/scss/ts`, theme picker)
- Sidebar 236→285px; nav groups "WORKSPACE" (3 router links, active = soft indigo bg + 2px left indicator) and "SERVICES" (7 external-link rows w/ right-aligned status dots; healthy dots muted).
- Footer: restyle `mm-theme-picker` to full-width selector (already select+chevron — adjust styling); add "Demo data" row with aria-disabled enabled-state toggle.
- `app.ts`: inject `ServiceHealthFacade` + link-base tokens; build services nav model; start polling.
- Update `app.spec.ts` (nav groups, service rows, badge, routes unchanged).

### 5. Dashboard page composition (`dashboard/`)
- `dashboard-page.html/scss`: `mm-dashboard-header` → metrics row (4 × `mm-metric-card`) → `mm-attention-banner` → 12-col grid, gap 20px: downloads `1/span 5` row 1, automation-runs `1/span 5` row 2, upcoming `6/span 3` row `1 / span 2`, service-health `9/span 4` row 1, storage `9/span 4` row 2 (≈42/27/31). Keep `container-type: inline-size` per region + 1279px single-column collapse.
- New components: `dashboard-header.*` (title/subtitle, green dot + "Synced {relative}" from health `generatedAt` + refresh button, search → Jellyfin external + ⌘K focus shortcut, Request media → `/discover`, Open Jellyfin → external, avatar), `metric-card.*` (icon container, label, value, meta, optional progress bar, right chevron; links: Library → Jellyfin external, others → in-page anchors), `attention-banner.*` (hidden when 0 problems; subtle red tint, "View issues" → `/reports`).
- Rework in place: `downloads-board.*` (thumbs, per-item pause, contextual pause/resume-all, seeding subsection w/ green indicator, "Open qBittorrent" footer), `calendar-board.*` → upcoming layout (time col, thumbs, status chips via `MmStatus` incl. new `premiere` tone, TODAY/TOMORROW/THIS WEEK groups, "View calendar" → Sonarr external, "View all upcoming" footer → Sonarr/Radarr external).
- Split `automation-board.*` into `service-health-card.*` (8 rows: icon, name, textual status, latency/last-seen, chevron; "8 services" badge; "Manage services" footer → `/reports`) + `automation-runs-card.*` (3-row JOB/STATUS/DETAILS/TIME table, status icon+text, "View all" → `/reports`). Delete `automation-board.*`.
- New `storage-card.*` (3 rows: icon, label, used/total, %, `mm-progress`; unavailable → `mm-state-card`).
- Delete `library-board.*`, `library.facade.ts`, `library-board.spec.ts`; `MmStatus` gains `premiere` tone (+ `status.stories.ts` update).
- Rewrite `dashboard-page.spec.ts`; rework board specs into the new card specs.

### 6. Storybook & docs
- `status.stories.ts`: premiere tone. Verify no other stories break (tokens changed globally).
- Update `README.md` (route table home description), `docs/architecture.md` (home composition, new port methods/endpoints, new link bases).
- `docs/ui-ux-design-review.md`: append the new review round after phase 7, with its findings/fixes.

### 7. Mandatory browser UX/UI review loop (blocking — not optional)

Tooling: `npm start` (Demo mode) driven by Playwright, as previously used in this repo (see `.playwright-cli/` artifacts). Primary viewport **1920×1080** (spec target), secondary **1440×900**.

Each round:
1. **Capture**: home full page; per-section close-ups (sidebar, page header, metric cards, attention banner, active downloads + seeding, upcoming, service health, storage, automation runs); hover states (nav item, metric card, download row, buttons, service rows); focus-visible states (search, buttons, nav, theme select); Reports and Discover (regression — tokens/radii changed globally); home in all three themes (Nocturne primary).
2. **Review against the spec checklist**: 285px sidebar + group labels + muted-healthy/prominent-problem status dots + footer theme selector and Demo-data row; header (title/subtitle, synced indicator, 360–420px search w/ ⌘K, Request media primary, Open Jellyfin secondary, avatar); 4 equal-height metric cards w/ icon containers, values, chevrons, storage bar; banner (subtle red tint, thin border, not saturated); 3-col ≈42/27/31 grid w/ 16–20px gaps; downloads rows (55×78 thumbs, right-aligned %, speeds/ETA, seeding subsection w/ green indicator, single contextual Pause/Resume-all); upcoming (TODAY/TOMORROW/THIS WEEK labels, times, chips right-aligned); service health (8 rows, textual status + latency/last-seen, chevrons); storage (3 bars w/ % + used/total); runs table (3 rows, JOB/STATUS/DETAILS/TIME); typography scale, tabular numerals, 1px `#263247` borders, 10–12px radii, no heavy shadows/gradients, no horizontal overflow, alignment across cards.
3. **Triage → fix → re-capture → re-review.** Repeat until the review verdict is satisfied, mirroring the fixes 35–43 loop documented in `docs/ui-ux-design-review.md`. Use a fresh reviewer subagent per round for independent eyes, as done previously.
4. **Keyboard/a11y pass**: tab order through header/sidebar/cards, visible focus rings, and contrast spot-checks of the new Nocturne values (e.g. muted `#748199` on card `#101827`, secondary `#A9B4C8` on page `#080D17`).

Blocking rules:
- At least one full review round happens after all code phases; iterations continue until satisfied. Work is not "done" without it.
- Findings and fixes per round are documented in `docs/ui-ux-design-review.md`.

### 8. Final verification (must pass before done)
```
npm run lint
npm test -- --watch=false
npm run build
npm run build:storybook
npm run test:storybook
```
Then regenerate `docs/screenshots/home.png` (plus any other affected captures) **after** the review loop converges, per `docs/screenshots/README.md` (Demo mode only, no live hostnames).
