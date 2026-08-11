<div align="center">

# ✦ Lumen Media Hub

**A modern self-hosted media command center built with Angular.**

Discover what to watch, manage your library, follow downloads, monitor automation, and operate a complete media stack from one polished interface.

![Angular](https://img.shields.io/badge/Angular-22-DD0031?logo=angular&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-6-3178C6?logo=typescript&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![Storybook](https://img.shields.io/badge/Storybook-10-FF4785?logo=storybook&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-tested-2EAD33?logo=playwright&logoColor=white)
![Vitest](https://img.shields.io/badge/Vitest-tested-6E9F18?logo=vitest&logoColor=white)

</div>

---

## What is Lumen?

**Lumen Media Hub** is the front door to a self-hosted media environment.

Instead of jumping between Jellyfin, Sonarr, Radarr, qBittorrent, recommendation tools, automation logs, and service dashboards, Lumen brings the information and actions that matter most into a single responsive application.

It is also a portfolio-grade Angular project designed to demonstrate production-minded frontend architecture: standalone Angular, strict TypeScript, a local design system, explicit API boundaries, facade-based state, Docker deployment, automated quality gates, accessibility checks, and browser-level testing.

### At a glance

| | Capability | What Lumen does |
|---|---|---|
| 🎬 | **Watch & browse** | Continue watching, trending titles, recently added media, movies and series |
| 🔎 | **Discover** | Combines Hermes, Jellyseerr and Trakt recommendation sources |
| ➕ | **Request media** | Sends supported requests through the Live API |
| ⬇️ | **Downloads** | Shows active qBittorrent transfers with pause/resume controls |
| 📅 | **Upcoming releases** | Surfaces Sonarr calendar data directly in the shell |
| ⚙️ | **Automation** | Summarizes automation state and exposes cron/report triage |
| ❤️ | **Health** | Tracks service status, storage, warnings and recent activity |
| 🧩 | **Design system** | Reusable Lumen primitives documented and tested in Storybook |
| 🐳 | **Self-hosting** | Ships alongside the media stack through Docker Compose |

---

## The experience

Lumen is organized around a persistent application shell with focused feature surfaces.

| Route | Experience |
|---|---|
| `/` | Home dashboard with hero, stats, Continue Watching, Trending Now, Recently Added and downloads |
| `/library` | Poster-based movie and series library with filtering |
| `/discover` | Recommendations from Hermes, Jellyseerr and Trakt |
| `/reports` | Status-weighted automation and cron-log triage |
| Storybook | Interactive design-system showcase on port `6006` |

The shell keeps high-value operational information visible without turning the product into an admin panel: upcoming releases, recent activity, service health, storage and command actions remain close at hand.

---

## How it works

Lumen deliberately separates **product UI**, **application state**, and **transport details**.

```text
                              LUMEN MEDIA HUB

┌──────────────────────────────── Browser ────────────────────────────────┐
│                                                                         │
│  Angular shell → feature pages → facades → MediaStackApi port          │
│                                          │                              │
│                           ┌──────────────┴──────────────┐               │
│                           │                             │               │
│                    Demo / mock mode               Live / HTTP mode      │
│                           │                             │               │
└───────────────────────────┼─────────────────────────────┼───────────────┘
                            │                             │
                       local fixtures               same-origin /api/*
                                                          │
                                                     Nginx proxy
                                                          │
                                                  homepage-actions
                                                          │
                  ┌───────────────────────────────────────┼──────────────┐
                  │             │             │           │              │
               Jellyfin      Sonarr        Radarr    qBittorrent    system data
```

### Demo mode

The default development experience runs entirely with in-process mock data. No private APIs, tokens, or media services are required.

```bash
cd dashboard-app
npm ci
npm start
```

Open `http://localhost:4200`.

This makes the project easy to review as a frontend application without reproducing the complete home-media environment first.

### Live mode

The production application is served by Nginx. Browser requests to `/api/*` are proxied to the local `homepage-actions` service, which talks to the underlying media services.

```text
Browser → :3000
  → Angular / Nginx
    /        → Angular SPA
    /api/*   → homepage-actions:8085
                  → Jellyfin / Sonarr / Radarr / qBittorrent / system
```

The browser never needs direct credentials for those services.

---

## Architecture

The Angular workspace lives in [`dashboard-app/`](dashboard-app/) and contains one standalone application named `dashboard`.

```text
projects/dashboard/src/app/
├── dashboard/       home composition and dashboard widgets
├── library/         media browsing
├── discover/        recommendation sources and requests
├── reports/         automation / cron triage
├── calendar/        upcoming media
├── automation/      automation state
├── activity/        recent activity
├── topbar/          persistent shell presentation
├── right-rail/      health, activity and upcoming releases
├── media-stack/     API port, adapters, DTOs and mappers
└── ui/              Lumen design system and shared primitives
```

### Port → adapter → facade → page

Feature code does not talk directly to backend services.

```text
MediaStackApi
    │
    ├── MockMediaStackApi   → Demo mode
    └── HttpMediaStackApi   → Live mode
            │
         Facades
            │
      Feature pages
            │
      Lumen UI primitives
```

This keeps transport DTOs inside the API boundary and lets the same UI run against mock or real data without scattering environment checks through components.

The codebase is feature-first: templates, styles, tests and Storybook stories stay with the components they describe rather than being split into generic global folders.

For the deeper architecture, facade lifetimes, polling ownership, API endpoints and data-flow rules, see [`dashboard-app/docs/architecture.md`](dashboard-app/docs/architecture.md).

---

## Media stack

A plain `docker compose up -d` starts the core stack.

### Core services

| Service | Role |
|---|---|
| **Lumen dashboard** | Unified Angular experience |
| **Jellyfin** | Playback and media-library source |
| **Sonarr** | Series management and release calendar |
| **Radarr** | Movie management |
| **Prowlarr** | Indexer management |
| **qBittorrent** | Download client and transfer controls |
| **homepage-actions** | Lumen's authenticated backend/API boundary |

### Optional profiles

| Compose profile | Services |
|---|---|
| `subtitles` | Bazarr |
| `requests` | Jellyseerr |
| `maintenance` | Maintainerr, Recyclarr, Unpackerr |
| `indexer-tools` | FlareSolverr |

Example:

```powershell
docker compose `
  --profile subtitles `
  --profile requests `
  --profile maintenance `
  --profile indexer-tools `
  up -d
```

Optional capabilities are enabled explicitly. An intentionally disabled service is not treated as broken; an enabled but unreachable service is surfaced as degraded/down.

---

## First-time setup

### Requirements

- Docker Desktop
- Node.js 20+
- PowerShell 7+
- Optional NVIDIA GPU + NVIDIA container tooling for hardware transcoding

### Install frontend + stack

From the repository root:

```powershell
.\install.ps1 -Mode both
```

Available modes:

| Mode | Purpose |
|---|---|
| `frontend-dev` | Installs the Angular workspace for Demo development |
| `stack` | Creates environment configuration and starts the Docker media stack |
| `both` | Runs frontend setup, then stack setup |

Useful flags:

```powershell
.\install.ps1 -Mode both -Force
.\install.ps1 -Mode both -Gpu
```

The installer intentionally does **not** configure indexers, libraries or third-party API keys inside the individual media applications. Those remain explicit first-run service setup steps.

---

## Development workflows

### Frontend-only Demo

```bash
cd dashboard-app
npm ci
npm start
```

Runs on `http://localhost:4200` with mock data.

### Live development with Docker hot reload

From the repository root, with the media stack configured:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate dashboard
```

Runs on `http://127.0.0.1:3000` and hot-reloads Angular source while using the real Live API.

### Production

```bash
docker compose up -d --build dashboard
```

The production image uses a multi-stage build: Node compiles the Angular application and Nginx serves the optimized static output while proxying the Live API.

---

## Security model

Lumen is designed so secrets stay outside the browser bundle.

```text
Compose environment
      │
      └── ACTIONS_TOKEN
              │
         Nginx envsubst
              │
      X-Actions-Token header
              │
        homepage-actions
```

- `ACTIONS_TOKEN` lives in the Docker environment.
- Nginx injects the token into proxied `/api/*` requests.
- The token is never emitted into Angular source, HTML, JavaScript bundles or source maps.
- The browser talks to the same-origin Lumen API instead of directly authenticating against the underlying services.
- Mutating actions such as media requests and torrent controls are handled through authenticated backend routes.

---

## Engineering quality

This repository treats quality checks as a build gate rather than optional cleanup.

```bash
cd dashboard-app
npm run quality
```

The gate runs six independent checks in parallel:

| Check | Tool | Protects against |
|---|---|---|
| Typed linting | ESLint + angular-eslint | TypeScript and template issues |
| Type checking | TypeScript | Invalid application types |
| Styles | Stylelint | CSS/SCSS quality regressions |
| Duplication | jscpd | Excessive copy/paste |
| Dead code | Knip | Unused dependencies and exports |
| Architecture | Dependency Cruiser | Invalid module boundaries |

TypeScript strictness, Angular strict templates and standalone constraints are enabled across the application.

---

## Testing strategy

Lumen uses multiple layers of tests because each catches a different class of failure.

| Layer | Tooling | Focus |
|---|---|---|
| Unit / integration | **Vitest** | Facades, domain behavior, providers and feature composition |
| Component system | **Storybook** | UI states, interaction and accessibility |
| Browser acceptance | **Playwright** | Routes, responsive shell behavior and assembled application flows |
| Static quality | **ESLint / TypeScript / Stylelint** | Code, template, type and style correctness |
| Structural quality | **Knip / jscpd / Dependency Cruiser** | Dead code, duplication and architectural boundaries |

Useful commands:

```bash
npm run quality
npm test -- --watch=false
npm run test:smoke
npm run build:storybook
npm run test:storybook
npm run build
```

Playwright coverage includes narrow mobile layouts and wide desktop layouts, while Storybook runs interaction and accessibility checks against the shared component system.

---

## Lumen design system

The product uses one intentional visual identity rather than a generic component-library theme.

**Lumen** combines:

- near-black surfaces
- warm gold and violet accents
- Fraunces for expressive display typography
- Inter for interface text
- JetBrains Mono for technical/data treatments
- self-hosted fonts through Fontsource
- reusable local primitives under `app/ui`

Run the component showcase with:

```bash
cd dashboard-app
npm run storybook
```

Open `http://localhost:6006`.

---

## Repository layout

```text
lumen-media-hub/
├── dashboard-app/              Angular 22 workspace
│   ├── projects/dashboard/     Lumen application
│   └── docs/architecture.md    Detailed frontend architecture
├── config/
│   ├── homepage-actions/       Live API boundary
│   └── recommendations/        Hermes recommendation contract
├── docker-compose.yml          Core + optional media services
├── docker-compose.dev.yml      Live Angular hot-reload override
├── docker-compose.gpu.yml      Optional NVIDIA configuration
└── install.ps1                 First-time Windows setup
```

> **Run npm commands from `dashboard-app/`.** Docker and stack commands run from the repository root.

---

## Command reference

From `dashboard-app/`:

| Command | Purpose |
|---|---|
| `npm start` | Start Demo mode on `:4200` |
| `npm run start:live` | Live Angular server used by the Docker dev container |
| `npm run quality` | Run the full six-part quality gate |
| `npm test -- --watch=false` | Run Vitest tests once |
| `npm run test:smoke` | Run Playwright browser acceptance tests |
| `npm run storybook` | Start Storybook on `:6006` |
| `npm run test:storybook` | Run Storybook interaction/a11y tests |
| `npm run build` | Build the Demo production configuration |
| `npm run build:live` | Build the optimized Live application |

---

## Project goals

Lumen is intentionally more than a skin over existing media apps.

The goal is to create a cohesive **media experience layer** that answers the questions that matter most without exposing every knob from every underlying service:

- **What should I watch next?**
- **What is new in my library?**
- **What is downloading right now?**
- **What releases are coming up?**
- **Is the stack healthy?**
- **Did automation fail somewhere?**
- **Can I act on it without opening five different dashboards?**

That product focus drives the architecture as much as the technology does.

---

<div align="center">

**Built as a self-hosted media hub and an exploration of production-grade Angular application architecture.**

</div>
