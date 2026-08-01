# Media Manager Angular

Angular 22 workspace for the Media Manager shell: a single `dashboard` app with local design system (`app/ui`) and API boundary (`app/media-stack`). Containerized with Nginx reverse proxy for Docker deployment.

## Repository layout

This is a monorepo. The Angular workspace lives in [`dashboard-app/`](dashboard-app/) — **run all npm commands there**. The repo root carries the production media stack: `docker-compose.yml`, the `homepage-actions` Live API under `config/homepage-actions/`, and the Hermes recommendation contract under `config/recommendations/`.

## First-time install

On a blank Windows machine (PowerShell 7+):

```powershell
.\install.ps1 -Mode both
```

| Mode | What it does |
|------|--------------|
| `frontend-dev` | Checks Node 20+, runs `npm ci` in `dashboard-app/`, prints Demo and Docker Live-dev commands |
| `stack` | Checks Docker, creates `.env` from `.env.example` (generated `ACTIONS_TOKEN`, prompted paths/password), pulls service images, Compose-builds the dashboard, starts the stack, and prints the API-key checklist |
| `both` | `frontend-dev`, then `stack` |

Flags: `-Force` recreates `.env`; `-Gpu` merges `docker-compose.gpu.yml` (NVIDIA transcoding).

Prerequisites: Docker Desktop, Node.js 20+, PowerShell 7+. Optional: NVIDIA GPU + nvidia-container-toolkit for `-Gpu`.

After `stack` mode, enable any selected optional profiles before opening those service UIs, copy each service API key into `.env`, then rerun Compose with the same profile flags to apply. The installer intentionally does not configure indexers, libraries, or service API keys — those need each app's first-run UI.

## Compose profiles

Plain `docker compose up -d` starts only the core stack: Jellyfin, qBittorrent, Sonarr, Radarr, Prowlarr, homepage-actions, and the Angular dashboard. Optional services use these profiles:

| Profile | Services |
|---------|----------|
| `subtitles` | Bazarr |
| `requests` | Jellyseerr |
| `maintenance` | Maintainerr, Recyclarr, Unpackerr |
| `indexer-tools` | FlareSolverr |

Start selected profiles with:

```powershell
docker compose --profile subtitles --profile requests --profile maintenance --profile indexer-tools up -d
```

Set `BAZARR_ENABLED=true` and/or `JELLYSEERR_ENABLED=true` only after the matching service is configured. Disabled or unconfigured optional capabilities are omitted from actionable health; configured but unreachable services remain degraded/down. Keep normal host profile values in ignored local operational docs, not in `.env.example` or committed configuration.

Existing hosts upgrading from the key-only setup must explicitly add `BAZARR_ENABLED=true` and/or `JELLYSEERR_ENABLED=true` to `.env` for each optional service they use, enable the matching Compose profiles, and run `docker compose up -d` again. API keys alone no longer enable these capabilities; leave the flags false for intentionally disabled services.

## Quick start (Demo / mock)

```bash
cd dashboard-app
npm ci
npm start
```

Open [http://localhost:4200/](http://localhost:4200/). Default startup uses in-process mock data (**Demo** badge) and makes no private API calls.

| Route | Surface |
|-------|---------|
| `/` | Lumen home: dashboard hero, stat strip, Continue Watching, Trending Now, Recently Added, downloads, and shell rails |
| `/library` | Library poster grid with movie/series filtering |
| `/reports` | Status-weighted automation / cron triage |
| `/discover` | Hermes, Jellyseerr, and Trakt recommendations |
| Storybook | Design-system showcase — `npm run storybook` → [http://localhost:6006/](http://localhost:6006/) |

## Production deployment (Docker)

The production-live build is containerized with Nginx as reverse proxy. It must run on the same Docker network as the `homepage-actions` backend (typically `media_media-net`).

```bash
docker compose up -d --build dashboard
```

Compose uses [`dashboard-app/Dockerfile`](dashboard-app/Dockerfile) for the single production-live build.

The image is deployed through Docker Compose alongside the backend services. For local verification with an existing Compose setup:

```bash
docker run --rm -p 3000:80 \
  --network media_media-net \
  -e ACTIONS_TOKEN=... \
  media-dashboard-angular:local
```

Open [http://127.0.0.1:3000/](http://127.0.0.1:3000/).

### Media stack cutover (`D:\media`)

Production dashboard on the stack is the Compose-built local Angular image; the Dockerfile remains the single production-live build path.

| Phase | Command / check |
|-------|-----------------|
| Build and deploy | `docker compose up -d --build dashboard` |
| Staging (done) | Compose service `dashboard-angular-stage` on `127.0.0.1:3001` — removed after M4 |
| Production | `dashboard` service uses the Compose-built `media-dashboard-angular:local` image on `:3000` |
| Smoke against stack | `SMOKE_BASE_URL=http://127.0.0.1:3000 npm run test:smoke` (from this repo; does not start `ng serve`) |

**Request flow:**

```
Browser → http://127.0.0.1:3000
  → Angular Nginx
    /        → Angular static files
    /api/*   → homepage-actions:8085/* (with X-Actions-Token header)
```

- Nginx strips `/api` via trailing-slash `proxy_pass`.
- `ACTIONS_TOKEN` is injected by Compose/Nginx from the container environment and never emitted into JavaScript, HTML, or source maps.
- The browser never sees the token and never connects directly to backend services.

## Live development (Docker hot reload)

Official Live development uses the Compose override so `ng serve` runs in Docker and publishes on **`:3000`** (same URL as production). From the **repo root**, with the stack already up and `ACTIONS_TOKEN` in `.env` (requires Docker Compose **2.24.4+** for `ports: !override` / `build: !reset`):

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate dashboard
```

Open [http://127.0.0.1:3000/](http://127.0.0.1:3000/). SCSS/TS/HTML edits under `dashboard-app/` hot-reload without rebuilding the Nginx image.

The override container still runs `npm run start:live` internally (with `proxy.conf.js` and the Angular `live` configuration). Keep those scripts for the container; do not treat host `npm run start:live` as a supported workflow.

## Scripts

| Script | Purpose |
|--------|---------|
| `npm start` | Demo serve (`:4200`) |
| `npm run start:live` | Live serve with API proxy (**dev-container only**; used by `docker-compose.dev.yml`) |
| `npm run lint` | Rigorous ESLint (typed + strict, used by `quality` gate) |
| `npm run lint:fast` | Fast ESLint (day-to-day editing, used by `lint:agent`) |
| `npm run lint:fix` | Rigorous ESLint with auto-fix |
| `npm run lint:styles:fix` | Stylelint with auto-fix |
| `npm run quality` | **Full gate** — lint + typecheck + styles + duplicates + dead-code + architecture in parallel |
| `npm test -- --watch=false` | Vitest unit / facade / page specs |
| `npm run test:smoke` | Playwright direct-route and assembled-app smoke checks (auto-starts dev server) |
| `npm run build` | Canonical production (Demo mode) build |
| `npm run build:live` | Production-live Docker build (optimized, no source maps, live backend) |
| `npm run storybook` | Interactive Storybook (includes a11y addon / play functions) |
| `npm run build:storybook` | Compile Storybook static output |
| `npm run test:storybook` | Serve `storybook-static` and run interaction/a11y checks (`@storybook/test-runner`) |

## Quality gate

`npm run quality` runs all six checks in parallel via `concurrently`:

| Tool | Command | Exit | Expected |
|------|---------|------|----------|
| **ESLint** (typed + strict) | `npm run lint` | **FAIL** on errors | Auto-fix with `npm run lint:fix` |
| **TypeScript** | `npm run typecheck` | **FAIL** on errors | Fix type errors |
| **Stylelint** | `npm run lint:styles` | **FAIL** on errors | Auto-fix with `npm run lint:styles:fix` |
| **jscpd** (duplication) | `npm run quality:duplicates` | **FAIL** ≥3% | Refactor — do not add ignores |
| **Knip** (dead code) | `npm run quality:dead-code` | **FAIL** on unused | Remove or justify exports |
| **Dependency Cruiser** | `npm run quality:architecture` | **FAIL** on violations | Respect module boundaries |

**PASS** = zero exit. **WARN / INFO** = tool-specific warnings that do not block. **FAIL** = non-zero exit.

**Rules:**
- Do not add ignore comments or abstractions solely to silence the gate.
- Ponytail (lazy/simplification mindset) remains a review principle for agents, not a lint rule.
- `no-orphans` is removed from Dependency Cruiser; Knip owns unused-code detection.
- jscpd clones below 3% are informational — address during refactors.

All six checks run independently: one failure does not kill the others. Commit hook and CI both enforce `npm run quality`. Tests and build run after quality in CI.

## Appearance

The application uses one dark theme: **Lumen**, with gold and violet accents on a near-black surface. Fonts (Fraunces, Inter, and JetBrains Mono) are self-hosted via Fontsource. There is no user theme selection or persisted theme state.

## Architecture

See [dashboard-app/docs/architecture.md](dashboard-app/docs/architecture.md) for the port → adapter → facade → page flow, Demo/Live modes, and operational link policy.

## Testing

- **Unit / integration:** Vitest via `ng test` (facades, boards, pages, shell navigation, API boundary).
- **Storybook:** Interactive review via `npm run storybook`. CI runs `build:storybook` then `test:storybook` (play functions + a11y).
- **Browser acceptance:** Playwright verifies direct routes, fallback routing, titles, the Lumen palette, responsive shell navigation, and the 390px, 1440px, and 1600px layouts via `npm run test:smoke`. Loading / empty / failure isolation that cannot be selected in Demo UI is covered by the named unit specs beside each feature.

## Non-goals

- Published to npm/hosting (private self-hosted Docker deployment)
- Backend rewrite or secrets in this repo

## Verification

```bash
npm ci
npm start
# in another shell:
npm run quality
npm test -- --watch=false
npm run test:smoke
npm run build
npm run build:storybook
npm run test:storybook
```
