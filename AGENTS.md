# AGENTS.md

Guidance for coding agents working in this repo.

## Repository layout

This is the Media Manager monorepo (checked out at `D:\media`):

- `dashboard-app/` — the Angular 22 workspace (portfolio project). **All npm commands run inside `dashboard-app/`**, not at the repo root.
- `docker-compose.yml`, `.env.example` — the production media stack definition.
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
