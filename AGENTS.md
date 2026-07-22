# AGENTS.md

Guidance for coding agents working in this repo.

## Backend location

The Live API is **not** in this repository. It runs from the media stack at **`D:\media`**:

- Compose file: `D:\media\docker-compose.yml`
- Service: `homepage-actions` (Python app under `D:\media\config\homepage-actions`)
- Host port: **`127.0.0.1:8085`** (`127.0.0.1:8085->8085/tcp`)
- Docker network: typically `media_media-net` (same network as Jellyfin, Sonarr, qBittorrent, etc.)

When Live endpoints fail, check that stack first (`docker ps`, hit `http://127.0.0.1:8085/health`) — do not assume the Angular app is miswired.

## Frontend ↔ backend wiring

| Mode | Command | Data source |
|------|---------|-------------|
| Demo | `npm start` | In-process `MockMediaStackApi` (no private API) |
| Live | `npm run dev` / `npm run start:live` | `HttpMediaStackApi` → `/api` → proxy → `http://127.0.0.1:8085` |

Live proxy: [`projects/dashboard/proxy.conf.js`](projects/dashboard/proxy.conf.js) strips `/api` and forwards to `127.0.0.1:8085`. Set `ACTIONS_TOKEN` in the shell env for mutating requests (proxy injects `X-Actions-Token`; the browser must never hold that secret).

Production Angular is a separate Docker image/Nginx reverse proxy on the same Compose network as `homepage-actions` (often published on `127.0.0.1:3000`). Local Angular Live remain on **`http://localhost:4200/`**.

## Do not

- Add an Angular interceptor that embeds `ACTIONS_TOKEN`
- Treat SABnzbd as a Live gap (Demo-only catalog capability)
- Point Live mode at a backend other than the `D:\media` `homepage-actions` service without updating this file and the proxy/docs

## Related docs

- [`README.md`](README.md) — quick start and scripts
- [`docs/architecture.md`](docs/architecture.md) — modes, endpoints, security model
