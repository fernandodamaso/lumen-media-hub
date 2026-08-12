# Architecture

## Workspace

Single Angular app (`dashboard`) owning the shell, feature boards, design system (`app/ui`), and API boundary (`app/media-stack`).

| Area | Role |
|------|------|
| `app/` shell | Bootstrap, routes, layout, navigation, shell-owned polling, environment providers |
| `app/ui` | Design tokens (single Lumen palette), primitives, Storybook stories |
| `app/media-stack` | `MediaStackApi` port, mock/HTTP adapters, providers, wire DTOs + mappers |
| Feature folders | Domain/display models, facades, and pages for `dashboard`, `library`, `downloads`, `reports`, `discover`, `calendar`, `automation`, and `activity` |
| Shell presentation | `topbar` and `right-rail` own the persistent presentation outside routed page content |

## Frontend organization

The application uses feature-first organization. Component resources are
co-located in folders named after the component rather than grouped into
generic `components`, `pages`, or `widgets` folders:

```text
projects/dashboard/src/app/
  dashboard/
    dashboard-page/
    dashboard-hero/
    media-rail/
    stat-strip/
    dashboard-refresh.ts
  library/
    library-page/
    library-poster-grid/
  topbar/
  right-rail/
  calendar/       flat feature folder
  automation/     flat feature folder
  discover/       flat feature folder
  ui/             shared design-system boundary
  media-stack/    transport/API boundary
```

Each component folder keeps the component TypeScript file, template, styles,
tests, and Storybook story together when present. Facades, models, formatters,
and feature-specific transformations remain with their owning feature.

The application is standalone and does not use NgModules. Do not introduce
generic root-level type folders unless a real architectural boundary requires
one.

## Shell and dashboard composition

`App` owns the persistent sidebar navigation, `Topbar`, `RightRail`, command
palette, and shell-scoped polling. `topbar/` and `right-rail/`
are presentation-owned shell features; they are not route pages.

The home route is composed by `DashboardPage` from the `DashboardHero`,
`StatStrip`, three `MediaRail` instances (Continue Watching, Trending Now, and
Recently Added), and the Downloads section. The right rail presents Upcoming
Releases, Recent Activity, and Service Health. Dashboard-only download polling
is owned and stopped by `DashboardPage`; shell polling remains with `App`.

## Data flow

### Production (Docker)

```text
Browser → http://127.0.0.1:3000
  → Angular Nginx container
    /        → Angular static SPA (production-live build)
    /api/*   → homepage-actions:8085/* (Nginx strips /api prefix)
                  → qBittorrent / Jellyfin / system resources
```

`ACTIONS_TOKEN` lives in the Compose environment and is injected by Nginx's `envsubst` into the `X-Actions-Token` header on proxied requests. The token never appears in Angular source, bundles, source maps, or browser-visible configuration.

### Development (Demo / Live)

```text
MediaStackApi (port)  ← app/media-stack
        │
        ├── MockMediaStackApi     ← Demo default (npm start on :4200)
        └── HttpMediaStackApi     ← Live (Docker hot reload on :3000)
                │
         Feature facades
                │
         Boards / pages  →  app/ui primitives
```

Providers are selected in [media-stack-api.providers.ts](../projects/dashboard/src/app/media-stack/media-stack-api.providers.ts) from [environment.ts](../projects/dashboard/src/environments/environment.ts).

Feature code imports domain models from its own folder and talks to the backend only through `MEDIA_STACK_API`. Wire `*Dto` types stay inside `app/media-stack`.

Library, automation, and service-health facades stay as separate stores. Do not merge them by folder or route: app-wide slices (library count and service health) must remain app-scoped, and dashboard-only polling must stop when the dashboard is destroyed.

### Facade lifetimes

| Facade | Provider scope | Consumers | Init owner | Polling owner | Stop behavior |
|--------|----------------|-----------|------------|---------------|---------------|
| `ServiceHealthFacade` | `providedIn: 'root'` | Right-rail and dashboard service health | App ctor `startPolling` | App (app-wide, 60s) | Runs for app lifetime (no public stop) |
| `LibraryItemsFacade` | `providedIn: 'root'` | App shell count, `/library`, dashboard refresh, command palette | Facade ctor initial `refresh` | None (manual / dashboard refresh) | Request-id bump on newer refresh |
| `WatchNextFacade` | `providedIn: 'root'` | Dashboard hero, Library page, dashboard refresh | Facade ctor initial `refresh` | None | Request-id bump |
| `LibraryStatsFacade` | `app.config` singleton | Stat strip and dashboard refresh | Facade ctor initial `refresh` | None | Request-id bump |
| `DownloadsFacade` | `app.config` singleton | Downloads section, stat strip, dashboard refresh, command palette actions | `DashboardPage` `startPolling` | DashboardPage (10s) | `DashboardPage` destroy → `stopPolling` |
| `StorageFacade` | `app.config` singleton | App shell storage card, stat strip, dashboard refresh | `App` `startPolling` | App (60s) | Runs for app lifetime |
| `CalendarFacade` | `app.config` singleton | Right-rail upcoming releases, dashboard refresh | `App` `startPolling` | App (60s) | Runs for app lifetime |
| `ActivityFacade` | `app.config` singleton | Right-rail recent activity | `App` `startPolling` | App (60s) | Runs for app lifetime |
| `AutomationFacade` | `app.config` singleton | Dashboard refresh and synced state | `App` `startPolling` | App (60s) | Runs for app lifetime |
| `DiscoverFacade` | Page `providers` | Discover page | Page / tab change | Discover page (Hermes 30s / external 60s) | Page destroy → `stopPolling` |
| `ReportsFacade` | Page `providers` | Reports page | Page `load` | None | Request-id bump |

Manual “refresh all” goes through [`dashboard-refresh.ts`](../projects/dashboard/src/app/dashboard/dashboard-refresh.ts) (`refreshDashboardData` / `DashboardRefreshDeps`): one-shot `refresh()` on each dashboard source, no new poll loops. The command palette resolves those deps lazily inside the action so shell boot does not construct dashboard-only facades early.

## Modes

| Mode | How | API | Operational deep links |
|------|-----|-----|------------------------|
| Demo | `npm start` in `dashboard-app/` → `:4200` | Mock | Local Jellyfin / Sonarr / Radarr bases from environment |
| Live development | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate dashboard` (repo root) → `:3000` | HTTP → `homepage-actions:8085` via `/api` proxy inside the override container | Host-published bases from `GET /api/service-links` (Compose `*_PORT` / `*_EXTERNAL_URL`) |
| Production | `docker compose up -d --build dashboard` (repo root) → `:3000` | Same-origin `/api/*` → `homepage-actions:8085` via Nginx | Same `GET /api/service-links` as Live development |

The Live override container runs `npm run start:live` with [`proxy.conf.js`](../projects/dashboard/proxy.conf.js) and Compose-provided `ACTIONS_TOKEN` / `LIVE_API_PROXY_TARGET`. Keep those scripts and the Angular `live` configuration for the container; host Live `ng serve` is not a supported workflow.

Empty calendar bases must not fall back to relative `/series/...` or `/movie/...` URLs. Resolvers treat a missing or blank base as "no link."

### Stack deploy (`D:\media`)

Production dashboard listens on `:3000`.

```powershell
docker compose --project-directory D:\media up -d dashboard homepage-actions
$env:SMOKE_BASE_URL = 'http://127.0.0.1:3000'
npm run test:smoke
```

## API endpoints (production-live)

| Endpoint | Method | Backend source |
|---|---|---|
| `/api/service-links` | GET | Browser deep-link bases from `*_EXTERNAL_URL` (Compose host ports) |
| `/api/system/resources` | GET | Storage volume from `disk.path`, `disk.used`, `disk.total` |
| `/api/qbt/torrents` | GET | Active torrents |
| `/api/qbt/torrents/stop` | POST `{ "id" }` | Per-torrent pause (token required) |
| `/api/qbt/torrents/start` | POST `{ "id" }` | Per-torrent resume (token required) |
| `/api/stop-all` | POST | Global pause (token required) |
| `/api/start-all` | POST | Global resume (token required) |
| `/api/jellyfin/movies` | GET | Movie library items |
| `/api/jellyfin/series` | GET | Series library items |
| `/api/jellyfin/watch-next` | GET | User-specific next episodes and in-progress movies (`progressPercent` 0–100) |
| `/api/sonarr/calendar` | GET | Upcoming calendar events |
| `/api/arr/library` | GET | Series/movie library index |
| `/api/activity` | GET | Recent activity feed for the right rail |
| `/api/automation/summary` | GET | Service health and warnings |
| `/api/cron/logs` | GET | Automation run logs |
| `/api/discover/hermes` | GET | Hermes recommendations |
| `/api/discover/jellyseerr` | GET | Jellyseerr discover |
| `/api/discover/trakt` | GET | Trakt discover |
| `/api/discover/request` | POST | Request media (token required) |

### Trakt authentication and watched cache

`homepage-actions` owns Trakt OAuth. Run `install.ps1 -Mode connect-trakt` once
with the local `TRAKT_CLIENT_ID` and `TRAKT_CLIENT_SECRET`; it atomically saves
the renewable access/refresh-token state in the ignored host directory mounted
as writable `/state`. The backend application mount remains read-only, and no
OAuth credential reaches Angular, Nginx, logs, or browser responses.

The watched cache at `TRAKT_WATCHED_PATH` stores only a refresh timestamp and
typed `movie:<id>` / `tv:<id>` identities. It refreshes within a 15-minute
in-memory freshness window and never persists raw Trakt history. A stale cache
continues filtering with a warning; if no cache exists, filtering fails open
with an unavailable warning. The dashboard uses the public freshness state,
not the private identity set.

Storage uses `/system/resources` (not `/storage/overview`) and labels the volume from the backend mount path (e.g., `Media volume (/data)`). Library stats are derived from concurrent `/jellyfin/movies` and `/jellyfin/series` requests rather than a dedicated stats endpoint.

## Routes

| Path | Feature |
|------|---------|
| `/` | Lumen home: hero, stat strip, Continue Watching, Trending Now, Recently Added, downloads, and shell right rail |
| `/library` | Library poster grid and movie/series filter |
| `/reports` | Cron log triage |
| `/discover` | Hermes / Jellyseerr / Trakt |
| `/dashboard` | Redirects to `/` |

Design-system showcase is Storybook (`npm run storybook`), not an in-app `/ui` route.

## Security

- `ACTIONS_TOKEN` is consumed from the Compose environment via Nginx `envsubst`.
- Nginx injects it into the `X-Actions-Token` header on proxied requests.
- The token never appears in Angular source, bundles, source maps, HTML, or error pages.
- SABnzbd is excluded from the live application shell; only qBittorrent on port `8081` remains as a download client.

Backend security (fail-closed `ACTIONS_TOKEN`, per-torrent qBT routes, CORS allowlist) is implemented in `D:\media\config\homepage-actions` (Milestone 1, commit `f0b4213` on the media stack repo).

## Docker build

```powershell
docker compose up -d --build dashboard
```

Compose builds from `dashboard-app/Dockerfile`; do not run a separate host Angular
production build. The image tag is the local `media-dashboard-angular:local` tag.

Multi-stage build: `node:22-alpine` compiles the production-live Angular build, then `nginx:1.28-alpine` serves the static assets with the reverse-proxy template.

The container must be deployed on the same Docker network as `homepage-actions` (`media_media-net`) for DNS resolution of the upstream service name. The `${ACTIONS_TOKEN}` variable is substituted by the official Nginx entrypoint at container startup.

## Design tokens

Tokens live in [`app/ui/media-ui.scss`](../projects/dashboard/src/app/ui/media-ui.scss). One dark theme: **Lumen** — gold/violet accents on near-black, mapped onto the existing `--mm-*` token names. Fonts are self-hosted via Fontsource (`@fontsource-variable/fraunces`, `@fontsource/inter`, `@fontsource/jetbrains-mono`) through the `styles` arrays in `angular.json`.

## Contribution baseline

- TypeScript `strict` and Angular `strictTemplates` / `strictStandalone` are on for app, unit tests, and Storybook.
- ESLint covers `.ts` and `.html` (including inline templates) via `angular-eslint`.
- Feature components use the `mm-` element prefix; `app-root` is the intentional bootstrap exception.
- Components use `ChangeDetectionStrategy.OnPush` (explicit on the root shell).
- Unit-test discovery excludes `.worktrees` so nested checkouts are never scanned or modified.
- Storybook stories live under `app/**` and are discovered by that glob for both Storybook and the test-runner.

## Testing strategy

- Contract and facade specs beside each feature
- Shell navigation and home composition specs
- Provider specs proving Demo→mock and Live→HTTP
- Storybook interaction + accessibility via `npm run test:storybook` (after `build:storybook`)
- Playwright smoke tests support both local `ng serve` and remote `SMOKE_BASE_URL` targets
