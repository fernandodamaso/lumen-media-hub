# AGENTS.md

Guidance for coding agents working in the **Angular workspace** (`dashboard-app/`). The monorepo root is the parent directory (`D:\media` on this machine): stack, Live API, installer, and CI live there — see [`../AGENTS.md`](../AGENTS.md).

## First-time install

On Windows, run from the **repo root** (not this folder):

```powershell
.\install.ps1 -Mode both
```

Use `-Mode frontend-dev` if you only need `npm ci` and dev commands. Use `-Mode stack` when Docker + the full compose stack are required for Live work. Prerequisites and flags are documented in [`../README.md`](../README.md) and [`../AGENTS.md`](../AGENTS.md).

After install, Demo stays on the host; Live development uses Docker hot reload from the **repo root**:

```powershell
cd dashboard-app
npm start              # Demo — mock data → http://localhost:4200/
```

```powershell
# repo root — Live development (hot reload on :3000)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate dashboard
```

## Backend location

The Live API **is** in the monorepo: `../config/homepage-actions` (service `homepage-actions` in compose).

- Compose file: `../docker-compose.yml`
- Host port: **`127.0.0.1:8085`**
- Docker network: typically `media_media-net`

When Live endpoints fail, check the stack first (`docker ps`, `http://127.0.0.1:8085/health`) — do not assume the Angular app is miswired.

## Frontend ↔ backend wiring

| Mode | How to run | Data source |
|------|------------|-------------|
| Demo | `npm start` → `:4200` | In-process `MockMediaStackApi` (no private API) |
| Live development | Dev Compose override → `:3000` | `HttpMediaStackApi` → `/api` → proxy → `homepage-actions:8085` |
| Production | Compose-built Nginx dashboard → `:3000` | Same-origin `/api/*` → `homepage-actions:8085` via Nginx |

Official Live development is the Docker hot-reload override on **`http://127.0.0.1:3000/`**. Do not start host Live `ng serve` as a workflow.

The override container still runs `npm run start:live` internally. Keep `start:live` / `dev`, [`projects/dashboard/proxy.conf.js`](projects/dashboard/proxy.conf.js), and the Angular `live` serve configuration for that container (`ACTIONS_TOKEN` and `LIVE_API_PROXY_TARGET` come from Compose env). The browser must never hold the token.

Production Angular is the Compose-built local image on the compose network (`http://127.0.0.1:3000/`). From the repo root, use `../install.ps1 -Mode stack` or **`../install.ps1 -Mode redeploy-dashboard`** for the production Nginx image; Compose runs the single production build in `Dockerfile`.

## Applying UI changes on port 3000 (agents)

**Default Live iteration:** keep the hot-reload override running so saves refresh `:3000` without rebuilding:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate dashboard
```

To refresh the **production** Nginx image after UI edits, from the **repo root**:

```powershell
.\install.ps1 -Mode redeploy-dashboard
```

(From this `dashboard-app/` folder, that is `..\install.ps1 -Mode redeploy-dashboard`.)

Do not assume production `:3000` reflects saved source until redeploy has run. For Demo-only work, use `npm start` on `:4200`.

## Quality and tests (run here)

```powershell
npm run quality
npm test -- --watch=false
npm run build
```

CI runs the same gate from repo root `.github/workflows/ci.yml` with `working-directory: dashboard-app`.

## Frontend structure

The Angular app is organized by feature under `projects/dashboard/src/app`.
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
- Point Live mode at a backend other than the monorepo `homepage-actions` service without updating this file, [`../AGENTS.md`](../AGENTS.md), and the proxy/docs

## Related docs

- [`README.md`](README.md) — quick start and scripts
- [`docs/architecture.md`](docs/architecture.md) — modes, endpoints, security model
