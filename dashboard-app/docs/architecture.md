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
`StatStrip`, three `MediaRail` instances (Continue Watching, Newly Available, and
Trending in Trakt), and the Downloads section. The right rail presents Upcoming
Releases, Recent Activity (Sonarr/Radarr operational history), and Service Health.
Dashboard-owned polling covers Downloads and Newly Available; shell polling
remains with `App`. The former `Recently Added` rail derived from alphabetically
sorted library items was removed — chronology now comes from Jellyfin
`DateCreated` via the dedicated recently-available endpoint.

## Newly Available

The **Newly Available** rail answers which individual movies and episodes became
playable in Jellyfin recently. It is not torrent completion time, not Sonarr/Radarr
import history (that stays in the right-rail Recent Activity feed), and not
alphabetical library sorting.

### Data path

`homepage-actions` `/jellyfin/recently-available` → browser `/api/jellyfin/recently-available`
→ `HttpMediaStackApi.listRecentlyAvailable` → `RecentlyAvailableFacade` →
`DashboardPage` → landscape `MmMediaCard`.

### Backend contract

`GET /jellyfin/recently-available?limit=10` (homepage-actions) returns
`{ "ok": true, "items": [...] }` with strict validation separate from watch-next:

- only `Movie` and `Episode` items with real media paths, valid IDs, and
  explicit-timezone `availableAt` timestamps
- excludes items the configured Jellyfin user has already fully watched
  (`UserData.Played` / `Filters=IsUnplayed`); in-progress but unwatched items may
  still appear here while Continue Watching owns resume playback
- rejects placeholders, virtual items, pathless movies/episodes, and series containers
- newest-first by Jellyfin `DateCreated`; pages Jellyfin until the limit is filled
- never exposes raw filesystem paths; stable `502` message on upstream failure
- no response-envelope cache (Refresh All must not be defeated)

On this stack, FDM-638 validated `UseFileCreationTimeForDateAdded=true` and that
`DateCreated` tracks playable indexing within ±5 minutes for one real episode and
one real movie. That result is stack-specific — `DateCreated` is not universally
equivalent to download completion.

### Frontend lifecycle

`RecentlyAvailableFacade` is `providedIn: 'root'` but Dashboard owns the 60-second
`ScheduledPollController` schedule: `startPolling` on mount, `stopPolling` on destroy,
immediate revalidation on remount without clearing last-good `ready`/`empty` data when
a background refresh fails. Refresh All (`refreshDashboardData`) calls
`recentlyAvailable.refresh()` exactly once alongside other dashboard sources.

Presentation: episode cards show series title, `SxxExx · episode title · Ready …`,
movies show `year · Movie · Ready …` when year is known. `NEW` (success tone) means
younger than 24 hours, not read/unread state. Shared `MmMediaCard` landscape styles
clamp long titles (one line) and subtitles (two lines); Dashboard does not add
private card selectors.

Demo and Live share one `MediaStackApi.listRecentlyAvailable` contract; Demo fixtures
use relative ages (30m, 4h, 30h, 3d, 8d) at call time.

## Data flow

### Production (Docker)

```text
Browser → http://127.0.0.1:3000
  → Angular Nginx container
    /        → Angular static SPA (production-live build)
    /api/*   → homepage-actions:8085/* (Nginx strips /api prefix; private Hermes paths below return 404)
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
| `RecentlyAvailableFacade` | `providedIn: 'root'` | Dashboard Newly Available rail, dashboard refresh | `DashboardPage` `startPolling` | DashboardPage (60s) | `DashboardPage` destroy → `stopPolling` |
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
| `/api/jellyfin/recently-available` | GET | Strictly playable movies and episodes sorted by Jellyfin `DateCreated` (`?limit=1–50`, default 10) |
| `/api/sonarr/calendar` | GET | Upcoming calendar events |
| `/api/arr/library` | GET | Series/movie library index |
| `/api/activity` | GET | Recent activity feed for the right rail |
| `/api/automation/summary` | GET | Service health and warnings |
| `/api/cron/logs` | GET | Automation run logs |
| `/api/discover/hermes` | GET | Browser-safe Hermes recommendations |
| `http://localhost:8085/internal/discover/hermes` | GET | Authenticated Hermes generation snapshot; direct access without token is 401 |
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

#### Operator diagnostic sequence

`watched_exclusion.status = stale` and the dashboard warning `Watched filtering
is using a cached snapshot` describe cache freshness. They are not proof that
the Trakt access token, refresh token, client ID, or client secret is invalid.

After recreating services, wait until both `homepage-actions` and `dashboard`
are ready. Query all five public Discover feeds twice:

- `/api/discover/hermes`
- `/api/discover/trakt?type=movies`
- `/api/discover/trakt?type=shows`
- `/api/discover/jellyseerr?kind=movies`
- `/api/discover/jellyseerr?kind=tv`

Require `watched_exclusion.status = fresh` in both rounds. If the APIs are
fresh but T3 still shows the cached warning, reload or reopen `/discover` and
inspect the new browser state. An earlier DOM snapshot is not an acceptance
failure.

Before recommending reconnection, inspect the configured state without printing
secrets. Confirm required `.env` fields and token-state fields are present,
compare the access-token expiry timestamp with the current time, and make
read-only direct Trakt watched-movies and watched-shows requests. Treat a
missing or expired token as invalid, and do not treat a token with less than 60
seconds of remaining validity as healthy: this is the backend refresh
threshold. Report only presence, expiry metadata, HTTP status, and counts. Do
not call the Trakt token endpoint only to test a refresh token: a refresh
exchange rotates credential state.

Run `install.ps1 -Mode connect-trakt` only when current evidence shows that
reconnection is required, such as `reconnect_required`, a persistent
authenticated `401` after the backend refresh attempt, missing token state, or
failed direct authenticated reads. This is an interactive,
credential-changing recovery step. Never print tokens, client secrets,
token-state contents, raw watched history, or account identifiers.

### Trakt write ownership

Playback completion in Jellyfin is written to Trakt only by the installed
Jellyfin Trakt plugin (`Scrobble`, `PostWatchedHistory`, and `PostSetWatched`
enabled; historical and playback-progress imports disabled). The Live API does
not listen to Jellyfin playback events.

Discover Hermes `watched` feedback is the only Media Manager write path to
Trakt. It persists a private `trakt_history_event` on the Hermes item,
delivers `POST /sync/history` outside the recommendations store lock, and
exposes only `trakt_history_sync.status` (`pending`, `synced`,
`reconnect_required`, or `failed`) to the browser. Show watches require
`confirm_all_aired: true`. Liked, disliked, and skipped feedback never call
Trakt.

The acceptance rule is therefore: both API rounds are fresh, and the browser
state is freshly loaded before any cached-warning decision is made.

Storage uses `/system/resources` (not `/storage/overview`) and labels the volume from the backend mount path (e.g., `Media volume (/data)`). Library stats are derived from concurrent `/jellyfin/movies` and `/jellyfin/series` requests rather than a dedicated stats endpoint.

## Routes

| Path | Feature |
|------|---------|
| `/` | Lumen home: hero, stat strip, Continue Watching, Newly Available, Trending in Trakt, downloads, and shell right rail |
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

The browser and cron routes have separate ownership:

- **Browser public read:** `/api/discover/hermes`
- **Browser queue action:** `/api/discover/hermes/request-more`
- **Browser private attempts:** `/api/internal/*`, `/api/discover/hermes/generations`, and `/api/discover/hermes/sync` → **404**
- **Hermes cron direct API:** `GET http://localhost:8085/internal/discover/hermes`, `POST http://localhost:8085/discover/hermes/generations`, and `POST http://localhost:8085/discover/hermes/sync`

Operational safety: test dashboard denial for the two cron-only routes with non-mutating `HEAD` probes. Never send `POST` to `/api/discover/hermes/generations` or `/api/discover/hermes/sync` during a proxy check.

Hermes uses the direct host routes with a valid `X-Actions-Token` and approved `Origin`; direct requests without the token return 401. Revision, presented identities, watched identities, and generation context remain internal.

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
