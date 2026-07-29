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
| `frontend-dev` | `npm ci` in `dashboard-app/`, prints Demo/Live dev commands |
| `stack` | Creates `.env` from `.env.example`, builds/tags dashboard image, `docker compose up -d`, health-checks `homepage-actions` |
| `both` | `frontend-dev` then `stack` (`npm ci` runs once) |

Flags: `-Force` recreates `.env`; `-Gpu` adds `-f docker-compose.gpu.yml`; `-SkipBuild` skips dashboard image build (local pin must already exist).

Non-interactive: set `ROOT_PATH`, `DOWNLOADS_PATH`, and `STACK_PASSWORD` in the environment before running.

After `stack`, copy each service API key into `.env` (installer prints URLs), then `docker compose up -d` from the repo root. The installer does not configure indexers, libraries, or *arr first-run wizards.

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

**Manual path** (no installer): copy `.env.example` → `.env`, set `ROOT_PATH` / `DOWNLOADS_PATH` (forward slashes), run `npm ci` and `npm run build:live` in `dashboard-app/`, `docker build` + retag to the pin in `docker-compose.yml`, then `docker compose up -d`.

## How to use this project

| Goal | Where | Command / check |
|------|--------|------------------|
| Demo UI (no stack) | `dashboard-app/` | `npm ci` → `npm start` → http://localhost:4200/ |
| Live UI against stack | `dashboard-app/` | Stack up + `ACTIONS_TOKEN` in shell → `npm run start:live` → http://localhost:4200/ |
| Production dashboard in stack | Docker | http://127.0.0.1:3000/ (image `media-dashboard-angular:<pin>` in compose) |
| Refresh `:3000` after UI edits | Repo root | `.\install.ps1 -Mode redeploy-dashboard` |
| Hot reload on `:3000` (agent/dev) | Repo root | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate dashboard` (Compose 2.24.4+; uses `ports: !override`) |
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
- `dashboard/` — **local-only, git-ignored** legacy React source, retained until 2026-08-11 (FDM-529 retention), then deleted. History: private `media-stack` backup repo.

Never commit `.env` or anything under `config/` other than the whitelisted paths above — app configs contain API keys.

## Backend location

The Live API **is** in this repository: the `homepage-actions` service (`config/homepage-actions`, Python app run as `python main.py` in its container).

- Compose file: `docker-compose.yml` (repo root)
- Host port: **`127.0.0.1:8085`** (`127.0.0.1:8085->8085/tcp`)
- Docker network: `media_media-net` (same network as Jellyfin, Sonarr, qBittorrent, etc.)

When Live endpoints fail, check the stack first (`docker ps`, hit `http://127.0.0.1:8085/health`) — do not assume the Angular app is miswired.

## Frontend ↔ backend wiring

| Mode | Command (in `dashboard-app/`) | Data source |
|------|---------|-------------|
| Demo | `npm start` | In-process `MockMediaStackApi` (no private API) |
| Live | `npm run dev` / `npm run start:live` | `HttpMediaStackApi` → `/api` → proxy → `http://127.0.0.1:8085` |

Live proxy: [`dashboard-app/projects/dashboard/proxy.conf.js`](dashboard-app/projects/dashboard/proxy.conf.js) strips `/api` and forwards to `127.0.0.1:8085`. Set `ACTIONS_TOKEN` in the shell env for mutating requests (proxy injects `X-Actions-Token`; the browser must never hold that secret).

Production Angular is the immutable-tagged Docker image `media-dashboard-angular:<sha>` (Nginx reverse proxy on the Compose network, published on `127.0.0.1:3000`). Build it from `dashboard-app/` after committing; update the tag in `docker-compose.yml`. Local Angular Live remains on **`http://localhost:4200/`**.

## Applying changes the user can see (agents)

**`http://localhost:3000/` is the Docker Nginx image, not `ng serve`.** Edits under `dashboard-app/` do not appear there until the image is rebuilt and the `dashboard` container is recreated.

| What changed | User URL | What to run (repo root) |
|--------------|----------|-------------------------|
| `dashboard-app/**` (UI) | `:3000` | `.\install.ps1 -Mode redeploy-dashboard` |
| `config/homepage-actions/**` (Live API) | `:8085` / `:3000` via `/api` | `docker compose restart homepage-actions` (bind-mounted; no image rebuild) |
| UI iteration with hot reload on `:3000` | `:3000` | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate dashboard` |

After UI fixes, **always** redeploy (or switch to the dev compose override) before telling the user to refresh `:3000`. Mention `:4200` only if you started `npm run start:live` on the host.

For long agent sessions on `:3000`, prefer `docker-compose.dev.yml` so file saves trigger `ng serve` reloads without repeated image builds.

## Frontend structure

The Angular app is organized by feature under `dashboard-app/projects/dashboard/src/app`.
Component resources stay co-located in folders named after the component:

```text
dashboard/
  dashboard-page/
  automation-card/
  metric-card/
  dashboard-refresh.ts

library/
  library-page/
  library-card/
  library-poster-grid/
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
