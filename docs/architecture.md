# Architecture

## Workspace

| Project | Role |
|---------|------|
| `dashboard` | Shell app: routes, feature facades, mock/HTTP adapters, UI primitives |

## Data flow

```text
MediaStackApi (port)
        │
        ├── MockMediaStackApi     ← Demo default
        └── HttpMediaStackApi     ← live serve only (`start:live`)
                │
         Feature facades
                │
         Boards / pages
```

Providers are registered in [app.config.ts](../projects/dashboard/src/app/app.config.ts) from [environment.ts](../projects/dashboard/src/environments/environment.ts) (Demo) or the live file replacement.

## Modes

| Mode | How | API | Operational deep links |
|------|-----|-----|------------------------|
| Demo | `npm start` | Mock | Local Jellyfin / Sonarr / Radarr bases from environment |
| Live | `npm run start:live` | HTTP → `:8085` via `/api` proxy | Same local bases |

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

Tokens live in Dashboard-owned UI SCSS (`projects/dashboard/src/app/ui`). Three dark themes: Nocturne, Tokyo Night, GitHub Dark Pro.

## Testing strategy

- Contract and facade specs beside each feature
- Shell navigation and home composition specs
- `/ui` catalog plus Vitest coverage for primitive keyboard / theme interaction
