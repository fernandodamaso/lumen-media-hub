# Architecture

## Workspace

| Project | Role |
|---------|------|
| `dashboard` | Shell app: routes, feature facades, mock/HTTP adapters |
| `media-ui` | Shared theme tokens, primitives, theme picker, Storybook stories |

## Data flow

```text
MediaStackApi (port)
        │
        ├── MockMediaStackApi     ← Demo default / Pages packaging
        └── HttpMediaStackApi     ← live serve only (`start:live`)
                │
         Feature facades
                │
         Boards / pages
```

Providers are selected in [media-stack-api.providers.ts](../projects/dashboard/src/app/downloads/media-stack-api.providers.ts) from [environment.ts](../projects/dashboard/src/environments/environment.ts). The Pages configuration file-replaces providers with a mock-only module so the HTTP client adapter is not bundled.

## Modes

| Mode | How | API | Operational deep links |
|------|-----|-----|------------------------|
| Demo | `npm start` | Mock | Local Jellyfin / Sonarr / Radarr bases from environment |
| Live | `npm run start:live` | HTTP → `:8085` via `/api` proxy | Same local bases |
| Pages package | `npm run build:pages` | Mock only | **Disabled** (empty bases → `href: null`) |

Empty calendar bases must not fall back to relative `/series/...` or `/movie/...` URLs. Resolvers treat a missing or blank base as “no link.”

## Routes

| Path | Feature |
|------|---------|
| `/` | Asymmetric home: library hero, operations column, calendar rail |
| `/reports` | Cron log triage |
| `/discover` | Hermes / Jellyseerr / Trakt |
| `/ui` | Component catalog inside the shell |
| `/dashboard` | Redirects to `/` |

## Local API expectations (live mode)

- Service: `homepage-actions` listening on `http://127.0.0.1:8085`
- Browser calls `/api/...`; Vite proxy strips `/api` and forwards
- Optional `ACTIONS_TOKEN` for mutating methods
- Demo mode never requires this service

## Themes

Tokens live in `media-ui` SCSS. Three dark themes: Nocturne, Tokyo Night, GitHub Dark Pro.

## Testing strategy

- Contract and facade specs beside each feature
- Shell navigation and home composition specs
- Storybook for primitive keyboard / theme interaction (manual)
- `build:pages` hygiene scan for static packaging readiness
