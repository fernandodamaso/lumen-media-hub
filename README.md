# Media Manager Angular

Angular 22 workspace for the Media Manager shell: standalone `dashboard` app with application-owned UI primitives.

This repository is currently a **private local showcase**. Public GitHub Pages is deferred; run Demo mode locally to evaluate the product.

## Quick start (Demo / mock)

```bash
npm ci
npm start
```

Open [http://localhost:4200/](http://localhost:4200/). Default startup uses in-process mock data (**Demo** badge) and makes no private API calls.

| Route | Surface |
|-------|---------|
| `/` | Asymmetric home dashboard (library, downloads, automation, calendar) |
| `/reports` | Status-weighted automation / cron triage |
| `/discover` | Hermes, Jellyseerr, and Trakt recommendations |
| `/ui` | In-app UI catalog and accessibility workbench |

## Live mode (optional)

With a local [`homepage-actions`](https://github.com/fernandodamaso) service on port **8085**:

```bash
npm run start:live
```

- Proxies `/api` → `http://127.0.0.1:8085` via [projects/dashboard/proxy.conf.js](projects/dashboard/proxy.conf.js).
- Set `ACTIONS_TOKEN` in the environment when mutating requests need `X-Actions-Token`.
- Feature components stay unchanged; only the `MediaStackApi` adapter switches.

Live mode is **local-only**. Do not point a static host at the live configuration.

## Scripts

| Script | Purpose |
|--------|---------|
| `npm start` | Demo serve (`:4200`) |
| `npm run start:live` | Live serve with API proxy |
| `npm run lint` | ESLint |
| `npm test -- --watch=false` | Vitest unit / facade / page specs |
| `npm run build:dashboard` | Production dashboard build |
| `npm run build:pages` | Future static-host package: mock-only build, SPA `404.html`, hygiene scan |

## Themes

Dark themes only (light themes are out of scope):

- **Nocturne** (default)
- **Tokyo Night**
- **GitHub Dark Pro**

Switch from the top-bar theme picker; preference persists in `localStorage` (`media-ui-theme`).

## Architecture

See [docs/architecture.md](docs/architecture.md) for the port → adapter → facade → page flow, mock/live/pages modes, and operational link policy.

## Testing

- **Unit / integration:** Vitest via `ng test` (facades, boards, pages, shell navigation, API boundary, UI primitives).
- **Browser acceptance:** Manual desktop checklist in [docs/browser-acceptance.md](docs/browser-acceptance.md). Loading / empty / failure isolation that cannot be selected in Demo UI is covered by named unit specs listed there.
- **Pages packaging:** `build:pages` asserts base href, `404.html`, and absence of localhost / private-service / `/api` strings in the artifact.

## Screenshots

Representative Demo captures (local showcase):

| Home | Discover |
|------|----------|
| ![Home dashboard](docs/screenshots/home.png) | ![Discover](docs/screenshots/discover.png) |

| Reports | Tokyo Night |
|---------|-------------|
| ![Reports](docs/screenshots/reports.png) | ![Tokyo Night theme](docs/screenshots/theme-tokyo-night.png) |

See [docs/screenshots/README.md](docs/screenshots/README.md) to regenerate.

## Non-goals

- Making the repository public or enabling GitHub Pages (deferred by owner decision)
- npm package publication
- Light themes or responsive certification
- Replacing the React deployment
- Backend rewrite or secrets in this repo
- Development-only mock scenario selectors

## Verification

```bash
npm ci
npm start
# in another shell:
npm run lint
npm test -- --watch=false
npm run build:dashboard
npm run build:pages
```
