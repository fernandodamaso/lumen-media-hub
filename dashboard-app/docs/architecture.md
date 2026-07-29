# Architecture

## Workspace

Single Angular app (`dashboard`) owning the shell, feature boards, design system (`app/ui`), and API boundary (`app/media-stack`).

| Area | Role |
|------|------|
| `app/` shell | Bootstrap, routes, layout, navigation, environment providers |
| `app/ui` | Design tokens, primitives, theme picker, Storybook stories |
| `app/media-stack` | `MediaStackApi` port, mock/HTTP adapters, providers, wire DTOs + mappers |
| Feature folders | Domain/display models, facades, boards/pages for `dashboard`, `downloads`, `reports`, `discover`, `calendar`, `automation`; shared service-health and storage facades feed the home dashboard |

## Frontend organization

The application uses feature-first organization. Component resources are
co-located in folders named after the component rather than grouped into
generic `components`, `pages`, or `widgets` folders:

```text
projects/dashboard/src/app/
  dashboard/
    dashboard-page/
    automation-card/
    metric-card/
    dashboard-refresh.ts
  library/
    library-page/
    library-card/
    library-poster-grid/
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

### Development (Demo / Live serve)

```text
MediaStackApi (port)  ← app/media-stack
        │
        ├── MockMediaStackApi     ← Demo default (npm start)
        └── HttpMediaStackApi     ← live serve only (npm run start:live)
                │
         Feature facades
                │
         Boards / pages  →  app/ui primitives
```

Providers are selected in [media-stack-api.providers.ts](../projects/dashboard/src/app/media-stack/media-stack-api.providers.ts) from [environment.ts](../projects/dashboard/src/environments/environment.ts).

Feature code imports domain models from its own folder and talks to the backend only through `MEDIA_STACK_API`. Wire `*Dto` types stay inside `app/media-stack`.

## Modes

| Mode | How | API | Operational deep links |
|------|-----|-----|------------------------|
| Demo | `npm start` | Mock | Local Jellyfin / Sonarr / Radarr bases from environment |
| Live dev | `npm run start:live` | HTTP → `:8085` via `/api` proxy | Same local bases |
| Production | `docker compose up -d --build dashboard` (repo root) | Same-origin `/api/*` → `homepage-actions:8085` via Nginx | Service deep-links from environment |

Empty calendar bases must not fall back to relative `/series/...` or `/movie/...` URLs. Resolvers treat a missing or blank base as "no link."

### Stack deploy and rollback (`D:\media`)

Image IDs, cutover dates, and rollback commands: `D:\media\docs\fdm-529-cutover-baseline.md`. Staging on `:3001` was used before M4 cutover; production listens on `:3000` only.

```powershell
docker compose --project-directory D:\media up -d dashboard homepage-actions
$env:SMOKE_BASE_URL = 'http://127.0.0.1:3000'
npm run test:smoke
```

Legacy React (`dashboard-react`, profile `legacy-dashboard`) is for rollback only — plain `docker compose up -d` does not start it. Do not set `COMPOSE_PROFILES` in `.env`.

## API endpoints (production-live)

| Endpoint | Method | Backend source |
|---|---|---|
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
| `/api/automation/summary` | GET | Service health and warnings |
| `/api/cron/logs` | GET | Automation run logs |
| `/api/discover/hermes` | GET | Hermes recommendations |
| `/api/discover/jellyseerr` | GET | Jellyseerr discover |
| `/api/discover/trakt` | GET | Trakt discover |
| `/api/discover/request` | POST | Request media (token required) |

Storage uses `/system/resources` (not `/storage/overview`) and labels the volume from the backend mount path (e.g., `Media volume (/data)`). Library stats are derived from concurrent `/jellyfin/movies` and `/jellyfin/series` requests rather than a dedicated stats endpoint.

## Routes

| Path | Feature |
|------|---------|
| `/` | Nocturne ops dashboard: metrics, attention banner, active downloads, recent automation runs, upcoming calendar, service health, storage overview |
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

## Themes

Tokens live in [`app/ui/media-ui.scss`](../projects/dashboard/src/app/ui/media-ui.scss). Three dark themes: Nocturne, Tokyo Night, GitHub Dark Pro.

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
