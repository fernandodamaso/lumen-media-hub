# AGENTS.md

Guidance for coding agents working in the **Angular workspace** (`dashboard-app/`). The monorepo root is the parent directory (`D:\media` on this machine): stack, Live API, installer, and CI live there — see [`../AGENTS.md`](../AGENTS.md).

## First-time install

On Windows, run from the **repo root** (not this folder):

```powershell
.\install.ps1 -Mode both
```

Use `-Mode frontend-dev` if you only need `npm ci` and dev commands. Use `-Mode stack` when Docker + the full compose stack are required for Live work. Prerequisites and flags are documented in [`../README.md`](../README.md) and [`../AGENTS.md`](../AGENTS.md).

After install, **all npm commands still run in `dashboard-app/`**:

```powershell
cd dashboard-app
npm start              # Demo — mock data
npm run start:live     # Live — needs stack + ACTIONS_TOKEN in shell env
```

## Backend location

The Live API **is** in the monorepo: `../config/homepage-actions` (service `homepage-actions` in compose).

- Compose file: `../docker-compose.yml`
- Host port: **`127.0.0.1:8085`**
- Docker network: typically `media_media-net`

When Live endpoints fail, check the stack first (`docker ps`, `http://127.0.0.1:8085/health`) — do not assume the Angular app is miswired.

## Frontend ↔ backend wiring

| Mode | Command | Data source |
|------|---------|-------------|
| Demo | `npm start` | In-process `MockMediaStackApi` (no private API) |
| Live | `npm run dev` / `npm run start:live` | `HttpMediaStackApi` → `/api` → proxy → `http://127.0.0.1:8085` |

Live proxy: [`projects/dashboard/proxy.conf.js`](projects/dashboard/proxy.conf.js) strips `/api` and forwards to `127.0.0.1:8085`. Set `ACTIONS_TOKEN` in the shell env for mutating requests (proxy injects `X-Actions-Token`; the browser must never hold that secret).

Production Angular is the Compose-built local image on the compose network (often `http://127.0.0.1:3000/`). From the repo root, use `../install.ps1 -Mode stack` or **`../install.ps1 -Mode redeploy-dashboard`** after UI edits; Compose runs the single production build in `Dockerfile`. Local Live dev stays on **`http://localhost:4200/`**.

## Applying UI changes on port 3000 (agents)

If the user tests at **`http://localhost:3000/`**, after changing files in this workspace run from the **repo root** (`D:\media`):

```powershell
.\install.ps1 -Mode redeploy-dashboard
```

(From this `dashboard-app/` folder, that is `..\install.ps1 -Mode redeploy-dashboard`.)

For hot reload without rebuilding the Nginx image, use the dev compose override (repo root):

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate dashboard
```

Do not assume `:3000` reflects saved source until one of those commands has been run (or the user is on `npm run start:live` at `:4200`).

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
- Point Live mode at a backend other than the monorepo `homepage-actions` service without updating this file, [`../AGENTS.md`](../AGENTS.md), and the proxy/docs

## Related docs

- [`README.md`](README.md) — quick start and scripts
- [`docs/architecture.md`](docs/architecture.md) — modes, endpoints, security model
