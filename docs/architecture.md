# Architecture

## Workspace

Single Angular app (`dashboard`) owning the shell, feature boards, design system (`app/ui`), and API boundary (`app/media-stack`).

| Area | Role |
|------|------|
| `app/` shell | Bootstrap, routes, layout, navigation, environment providers |
| `app/ui` | Design tokens, primitives, theme picker, Storybook stories |
| `app/media-stack` | `MediaStackApi` port, mock/HTTP adapters, providers, wire DTOs + mappers |
| Feature folders | Domain/display models, facades, boards/pages for `dashboard`, `downloads`, `reports`, `discover`, `calendar`, `automation`; shared service-health and storage facades feed the home dashboard |

## Data flow

```text
MediaStackApi (port)  ΓåÉ app/media-stack
        Γöé
        Γö£ΓöÇΓöÇ MockMediaStackApi     ΓåÉ Demo default
        ΓööΓöÇΓöÇ HttpMediaStackApi     ΓåÉ live serve only (`start:live`)
                Γöé
         Feature facades
                Γöé
         Boards / pages  ΓåÆ  app/ui primitives
```

Providers are selected in [media-stack-api.providers.ts](../projects/dashboard/src/app/media-stack/media-stack-api.providers.ts) from [environment.ts](../projects/dashboard/src/environments/environment.ts).

Feature code imports domain models from its own folder and talks to the backend only through `MEDIA_STACK_API`. Wire `*Dto` types stay inside `app/media-stack`.

## Modes

| Mode | How | API | Operational deep links |
|------|-----|-----|------------------------|
| Demo | `npm start` | Mock | Local Jellyfin / Sonarr / Radarr bases from environment |
| Live | `npm run start:live` | HTTP ΓåÆ `:8085` via `/api` proxy | Same local bases |

Empty calendar bases must not fall back to relative `/series/...` or `/movie/...` URLs. Resolvers treat a missing or blank base as ΓÇ£no link.ΓÇ¥

Public static hosting (GitHub Pages) remains deferred and is not packaged from this repo.

## Routes

| Path | Feature |
|------|---------|
| `/` | Nocturne ops dashboard: metrics, attention banner, active downloads, recent automation runs, upcoming calendar, service health, storage overview |
| `/reports` | Cron log triage |
| `/discover` | Hermes / Jellyseerr / Trakt |
| `/dashboard` | Redirects to `/` |

Design-system showcase is Storybook (`npm run storybook`), not an in-app `/ui` route.

## Local API expectations (live mode)

- Service: `homepage-actions` listening on `http://127.0.0.1:8085`
- Browser calls `/api/...`; proxy strips `/api` and forwards
- Optional `ACTIONS_TOKEN` for mutating methods
- Demo mode never requires this service

## Themes

Tokens live in [`app/ui/media-ui.scss`](../projects/dashboard/src/app/ui/media-ui.scss). Three dark themes: Nocturne, Tokyo Night, GitHub Dark Pro.

## Testing strategy

- Contract and facade specs beside each feature
- Shell navigation and home composition specs
- Provider specs proving DemoΓåÆmock and LiveΓåÆHTTP
- Storybook interaction + accessibility via `npm run test:storybook` (after `build:storybook`)
