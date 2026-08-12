# AGENTS.md

Guidance for coding agents working in this repo.

## First-time install (Windows)

Prerequisites: **PowerShell 7+**, **Node.js 20+**, **Docker Desktop** (Compose v2). Optional: NVIDIA GPU + `nvidia-container-toolkit` for Jellyfin transcoding.

From the **repo root** (installer sets CWD to `$PSScriptRoot` automatically):

```powershell
.\install.ps1 -Mode both
```

| Mode | What it does |
|------|--------------|
| `frontend-dev` | `npm ci` in `dashboard-app/`, prints Demo and Docker Live-dev commands |
| `stack` | Creates `.env` from `.env.example`, pulls service images, Compose-builds the dashboard, starts the stack, and health-checks `homepage-actions` |
| `both` | `frontend-dev` then `stack` (`npm ci` runs once) |
| `up` | Self-heals stale compose containers (worktree-rot guard), then `docker compose up -d` with optional `-Dev` / `-Gpu` / `-Profile` flags |

Flags: `-Force` recreates `.env`; `-Gpu` adds `-f docker-compose.gpu.yml`.

Non-interactive: set `ROOT_PATH`, `DOWNLOADS_PATH`, and `STACK_PASSWORD` in the environment before running.

After `stack`, copy each service API key into `.env` (installer prints URLs), then rerun Compose with the same optional profile flags you selected. The installer does not configure indexers, libraries, or *arr first-run wizards.

## Compose profiles

Plain `docker compose up -d` starts core services only. Optional services are explicitly grouped:

| Profile | Services |
|---------|----------|
| `subtitles` | Bazarr |
| `requests` | Jellyseerr |
| `maintenance` | Maintainerr, Recyclarr, Unpackerr |
| `indexer-tools` | FlareSolverr |

Enable profiles with `docker compose --profile subtitles --profile requests up -d` (add the other profiles as needed). Set `BAZARR_ENABLED=true` and/or `JELLYSEERR_ENABLED=true` only when the matching service is intentionally enabled and configured; an unreachable configured service remains degraded/down. Do not add optional profiles to `.env.example`; host-specific normal profiles belong only in ignored local operational docs.

Upgrade existing hosts by adding the enable flag for every optional service already represented by an API key, enabling its Compose profile, and rerunning `docker compose up -d`. Keys without `BAZARR_ENABLED=true` or `JELLYSEERR_ENABLED=true` no longer activate those capabilities after upgrade.

**Manual path** (no installer): copy `.env.example` → `.env`, set `ROOT_PATH` / `DOWNLOADS_PATH` (forward slashes), then run `docker compose up -d --build` from the repo root. Compose uses `dashboard-app/Dockerfile` for the single production-live build.

## How to use this project

| Goal | Where | Command / check |
|------|--------|------------------|
| Demo UI (no stack) | `dashboard-app/` | `npm ci` → `npm start` → http://localhost:4200/ |
| Live development (hot reload) | Repo root | Stack up → `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate dashboard` → http://127.0.0.1:3000/ (Compose 2.24.4+) |
| Production dashboard in stack | Docker | `docker compose up -d --build dashboard` → http://127.0.0.1:3000/ (Compose-built image `media-dashboard-angular:local`) |
| Refresh production `:3000` after UI edits | Repo root | `.\install.ps1 -Mode redeploy-dashboard` |
| Live API | `config/homepage-actions/` | http://127.0.0.1:8085/health |
| Full quality gate | `dashboard-app/` | `npm run quality` |
| Angular unit tests | `dashboard-app/` | `npm test -- --watch=false` |
| Backend unit tests | `config/homepage-actions/` | `python -m unittest discover -v` |
| CI | `.github/workflows/ci.yml` | `verify` (Angular) + `backend-tests` (Python) on push/PR |

Tracked product docs live under **`dashboard-app/docs/`** (e.g. architecture, quality gates). Root **`docs/`** is gitignored host ops notes — do not commit.

## Repository layout

This is the Media Manager monorepo (checked out at `D:\media`):

- `dashboard-app/` — the Angular 22 workspace (portfolio project). **All npm commands run inside `dashboard-app/`**, not at the repo root.
- `install.ps1` — first-time Windows bootstrap (`stack` / `frontend-dev` / `both`).
- `docker-compose.yml`, `docker-compose.gpu.yml` (optional merge), `.env.example` — production media stack.
- `config/homepage-actions/` — the Live API (Python, stdlib-only HTTP service).
- `config/recommendations/` — Hermes recommendation contract files (runtime JSON is ignored).
- `docs/` — **local-only, git-ignored** ops notes and stack documentation (contains host-specific detail; do not commit).

Never commit `.env` or anything under `config/` other than the whitelisted paths above — app configs contain API keys.

## Backend location

The Live API **is** in this repository: the `homepage-actions` service (`config/homepage-actions`, Python app run as `python main.py` in its container).

- Compose file: `docker-compose.yml` (repo root)
- Host port: **`127.0.0.1:8085`** (`127.0.0.1:8085->8085/tcp`)
- Docker network: `media_media-net` (same network as Jellyfin, Sonarr, qBittorrent, etc.)

When Live endpoints fail, check the stack first (`docker ps`, hit `http://127.0.0.1:8085/health`) — do not assume the Angular app is miswired.

## Frontend ↔ backend wiring

| Mode | How to run | Data source |
|------|------------|-------------|
| Demo | `npm start` in `dashboard-app/` → `:4200` | In-process `MockMediaStackApi` (no private API) |
| Live development | Dev Compose override → `:3000` | `HttpMediaStackApi` → `/api` → proxy → `homepage-actions:8085` |
| Production | Compose-built Nginx dashboard → `:3000` | Same-origin `/api/*` → `homepage-actions:8085` via Nginx |

Official Live development is the Docker hot-reload override (`docker-compose.yml` + `docker-compose.dev.yml`) on **`http://127.0.0.1:3000/`**. Do not start host Live `ng serve` as a workflow.

The dev container still runs `npm run start:live` internally. Keep `start:live` / `dev`, [`proxy.conf.js`](dashboard-app/projects/dashboard/proxy.conf.js), and the Angular `live` serve configuration — they are implementation details for that container (`ACTIONS_TOKEN` and `LIVE_API_PROXY_TARGET` come from Compose env). The browser must never hold the token.

Production Angular is the Compose-built local image `media-dashboard-angular:local` (Nginx reverse proxy on the Compose network, published on `127.0.0.1:3000`). Compose runs the single production build in `dashboard-app/Dockerfile`.

## Trakt freshness and reconnection checks

`watched_exclusion.status = stale` and the dashboard warning `Watched filtering is using a cached snapshot` are freshness signals. They do not prove that the Trakt access token, refresh token, client ID, or client secret is invalid.

After recreating services, wait for both `homepage-actions` and `dashboard` to be ready. Query each public Discover feed twice and require `watched_exclusion.status = fresh` in both rounds:

- `/api/discover/hermes`
- `/api/discover/trakt?type=movies`
- `/api/discover/trakt?type=shows`
- `/api/discover/jellyseerr?kind=movies`
- `/api/discover/jellyseerr?kind=tv`

If the APIs are fresh but T3 still shows the cached warning, reload or reopen `/discover` and inspect the new browser state. Do not fail acceptance from an earlier DOM snapshot.

Before recommending `install.ps1 -Mode connect-trakt`, check the configured state without printing secrets: confirm required `.env` and token-state fields are present, confirm access-token expiry metadata, and make read-only direct Trakt watched-movies and watched-shows requests. Report only presence, expiry metadata, HTTP status, and counts. Do not call the Trakt token endpoint only to test a refresh token: a refresh exchange rotates credential state. Use `connect-trakt` only for evidence such as `reconnect_required`, a persistent authenticated `401` after backend refresh, missing token state, or failed direct authenticated reads. It is an interactive credential-changing recovery step. Never print tokens, client secrets, token-state contents, raw watched history, or account identifiers.

## Applying changes the user can see (agents)

**Default Live iteration uses the hot-reload override on `:3000`.** Without that override, `:3000` is the static Nginx image and UI edits need a rebuild.

| What changed | User URL | What to run (repo root) |
|--------------|----------|-------------------------|
| `dashboard-app/**` (UI, hot reload) | `:3000` | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate dashboard` |
| `dashboard-app/**` (production image) | `:3000` | `.\install.ps1 -Mode redeploy-dashboard` |
| `config/homepage-actions/**` (Live API) | `:8085` / `:3000` via `/api` | `docker compose restart homepage-actions` (bind-mounted; no image rebuild) |

For long agent sessions on `:3000`, keep the `docker-compose.dev.yml` override so file saves trigger `ng serve` reloads without repeated image builds. Mention `:4200` only for Demo (`npm start`).

## Worktree hygiene (agents)

Bringing the stack up from a git worktree bakes the worktree's absolute paths into the containers' bind mounts. If the worktree is later removed, those containers survive with dead mount sources and come back empty on the next daemon restart or `docker start` — symptom: `homepage-actions` exits 2 (`can't open file '/app/main.py'`), `dashboard` exits 254 (`npm ci` ENOENT on `/app/package.json`).

Before abandoning or removing a worktree, tear down its stack so no stale containers remain:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

For subsequent stack starts from the repo root, prefer the self-healing wrapper over raw `docker compose up` — before starting, it removes any of this stack's containers whose compose `working_dir` is no longer a live checkout (i.e. the worktree they were launched from is gone):

```powershell
.\install.ps1 -Mode up [-Dev] [-Gpu] [-Profile subtitles,requests]
```

`-Dev` adds the hot-reload override (`:3000`); `-Profile` enables optional service profiles. If you hit the stale-mount symptom, running `-Mode up` once clears it.

## Frontend structure

The Angular app is organized by feature under `dashboard-app/projects/dashboard/src/app`.
Component resources stay co-located in folders named after the component:

```text
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
```

Keep each component's `.ts`, `.html`, `.scss`, `.spec.ts`, and Storybook story together when present. Keep facades, models, formatters, and tests with their owning feature. Smaller features such as `calendar`, `automation`, and `discover` may remain flat. `ui` is the shared design-system boundary, and `media-stack` owns transport/API concerns.

Do not create generic root-level `components/`, `services/`, `models/`, `pages/`, or `widgets/` folders, and do not introduce NgModules into this standalone Angular application.

## Do not

- Add an Angular interceptor that embeds `ACTIONS_TOKEN`
- Treat SABnzbd as a Live gap (Demo-only catalog capability)
- Point Live mode at a backend other than this repo's `homepage-actions` service without updating this file and the proxy/docs
- Commit `docs/`, `scripts/`, `dashboard/`, `.env`, or non-whitelisted `config/` paths (see `.gitignore`)

## Related docs

- [`README.md`](README.md) — quick start and scripts
- [`dashboard-app/docs/architecture.md`](dashboard-app/docs/architecture.md) — modes, endpoints, security model
