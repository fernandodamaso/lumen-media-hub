# Angular Dashboard to Docker Backend — Final Implementation Plan

Status: implementation-ready  
Repositories: `C:\git\media-manager-angular` and `D:\media`  
Reviewed baselines: Angular `fb79901`; backend `35b72db`  

Reconfirm both HEADs and worktree states immediately before implementation. Do not reset, clean, format, or overwrite unrelated user changes.

## 1. Goal

Replace the React dashboard at `http://127.0.0.1:3000` with the Angular dashboard while reusing the existing `homepage-actions` backend and preserving a tested React rollback path.

The browser must communicate only with the Angular container's same-origin `/api/*` path. Nginx owns backend routing and the action token; Angular never receives the token or connects directly to Docker service names.

```text
Browser
  -> http://127.0.0.1:3000
  -> Angular Nginx
       /           -> Angular static files
       /api/*      -> homepage-actions:8085/*
                       -> qBittorrent / Jellyfin / system resources
```

## 2. Fixed decisions

1. Nginx strips `/api` with a trailing-slash `proxy_pass`:

   ```nginx
   location /api/ {
     proxy_pass http://homepage-actions:8085/;
   }
   ```

2. SABnzbd is retired. Remove it from live Angular configuration and UI. Mock and Storybook examples may retain SAB-specific fixture data.
3. The canonical operational URL is `http://127.0.0.1:3000`.
4. Storage comes from `GET /system/resources`; there is no new storage endpoint.
5. The storage card represents the mounted Docker volume and must be labelled from the returned path, for example `Media volume (/data)`.
6. Mutation authentication becomes fail-closed in this change.
7. React remains available through the `legacy-dashboard` Compose profile for 14 days after cutover and a successful rollback drill.

## 3. Scope boundaries

### Included

- Angular live API contract corrections.
- Removal of SABnzbd from live UI/configuration.
- Angular production-live build configuration.
- Angular Docker image and Nginx reverse proxy.
- Per-torrent qBittorrent start/stop backend endpoints.
- Fail-closed token handling, exact CORS allowlist, and validation.
- Compose staging, cutover, rollback, and documentation.
- Unit, build, smoke, proxy, and rollback verification.

### Explicitly excluded

- No new aggregate backend endpoint for library or storage data.
- No new frontend data layer, repository abstraction, state library, or dependency.
- No general authentication system, user accounts, or remote-access redesign.
- No cleanup or refactor of unrelated dirty files in `D:\media`.
- No redesign of demo mocks or Storybook stories beyond changes required to keep them compiling.

## 4. Milestone 0 — Safety checkpoint

Before editing either repository, record:

```powershell
git -C C:\git\media-manager-angular rev-parse --show-toplevel
git -C C:\git\media-manager-angular branch --show-current
git -C C:\git\media-manager-angular rev-parse HEAD
git -C C:\git\media-manager-angular status --short

git -C D:\media rev-parse --show-toplevel
git -C D:\media branch --show-current
git -C D:\media rev-parse HEAD
git -C D:\media status --short
```

Acceptance gate:

- Both worktree states are captured before the first edit.
- Every planned file that is already modified is reviewed before patching.
- Unrelated changes remain untouched throughout implementation.

## 5. Milestone 1 — Correct the Angular live contract

### Primary files

- `projects/dashboard/src/app/media-stack/http-media-stack-api.ts`
- `projects/dashboard/src/app/media-stack/http-media-stack-api.spec.ts`
- `projects/dashboard/src/app/media-stack/live-api.mappers.ts`
- `projects/dashboard/src/app/media-stack/wire/storage.ts`
- `projects/dashboard/src/app/media-stack/wire/library.ts`
- Existing mapper tests associated with those files

### Storage

- Change `getStorageOverview()` from `/storage/overview` to `/system/resources`.
- Keep the raw backend shape behind the existing wire/mapping boundary.
- Map `disk.path`, `disk.total`, `disk.used`, `disk.free`, and `disk.percent` into the existing storage model.
- Use a stable volume ID and a label derived from the backend path: `Media volume (${disk.path})`.
- Treat missing, null, non-numeric, or otherwise malformed disk data as a failed load. Do not display zero usage.
- Do not expose container CPU/RAM as host-level metrics unless the UI already labels them as container data.

### Library

- Replace `/jellyfin/stats` with concurrent requests to `/jellyfin/movies` and `/jellyfin/series` using `Promise.all`.
- Reuse the existing movie and series DTOs/mappers.
- Derive aggregate counts from the returned collections without adding a backend endpoint.
- Reject the aggregate load if either required request fails; the existing facade owns the visible error state.

### Download actions

The Angular client already calls:

- `POST /qbt/torrents/stop` with `{ id }`
- `POST /qbt/torrents/start` with `{ id }`

Do not add another client abstraction. Update only tests or response handling required by the finalized backend contract.

Acceptance gate:

- No live Angular call targets `/storage/overview` or `/jellyfin/stats`.
- `/system/resources`, `/jellyfin/movies`, and `/jellyfin/series` map into the current domain models.
- Null disk data and either library-request failure reach the current error UI.
- Components remain unaware of backend DTOs.

## 6. Milestone 2 — Remove SABnzbd from live Angular behavior

### Files to inspect and minimally edit

- `projects/dashboard/src/environments/environment.ts`
- `projects/dashboard/src/environments/environment.live.ts`
- `projects/dashboard/src/app/app.ts`
- `projects/dashboard/src/app/media-stack/media-stack-api.providers.ts`
- Any live mapper/navigation reference found by `rg -i sabnzbd`

Remove:

- `sabnzbdBase` from environment/provider configuration.
- SABnzbd from live service navigation and service-health data.
- Stale live comments or mappings that claim SABnzbd is available.

Keep:

- Mock and Storybook fixtures when they are isolated from the live build and still useful for component states.

Also correct qBittorrent's browser-facing link to `http://127.0.0.1:8081`.

Acceptance gate:

- The production-live dashboard shows no SABnzbd service or link.
- qBittorrent links to port `8081`.
- Mock/Storybook compilation remains green.

## 7. Milestone 3 — Add a real production-live build

### Files

- `angular.json`
- `package.json`
- `projects/dashboard/src/environments/environment.live.ts`

Add `production-live` by restating the production configuration and adding the live environment file replacement. Do not inherit from the current development-like `live` configuration.

Required behavior:

- Production optimization enabled.
- Source maps disabled unless already required by the production policy.
- Output hashing enabled.
- Existing production bundle budgets preserved.
- `environment.ts` replaced by `environment.live.ts`.

Add:

```json
"build:live": "ng build dashboard --configuration production-live"
```

Acceptance gate:

- `npm run build:live` succeeds.
- Output lands in `dist/dashboard/browser`.
- Production budgets still enforce the existing limits.

## 8. Milestone 4 — Containerize Angular and proxy the backend

### New files

- `Dockerfile`
- `.dockerignore`
- `nginx.conf.template`

### Dockerfile

Use two stages only:

1. `node:22-alpine`
   - Copy package manifests and `.npmrc`.
   - Run `npm ci`.
   - Copy Angular workspace sources/configuration.
   - Run `npm run build:live`.
2. `nginx:1.27-alpine`
   - Copy `dist/dashboard/browser` into the Nginx web root.
   - Copy the Nginx template.
   - Let the official Nginx entrypoint substitute `ACTIONS_TOKEN` at container startup.

`.dockerignore` must exclude at least:

```text
node_modules
dist
.angular
.worktrees
storybook-static
.playwright-cli
.git
docs
tests
```

### Nginx behavior

- Serve the Angular SPA.
- Use `try_files $uri $uri/ /index.html` for deep links.
- Proxy `/api/` to `http://homepage-actions:8085/`.
- Send `X-Actions-Token: ${ACTIONS_TOKEN}` upstream.
- Forward the browser `Origin` header unchanged.
- Do not emit the token into JavaScript, HTML, source maps, logs, or error pages.

Build tags:

```text
media-dashboard-angular:<short-angular-sha>
media-dashboard-angular:local
```

Acceptance gate:

- Container starts and serves the Angular application.
- Refreshing an Angular route returns the SPA, not Nginx 404.
- `GET /api/health` reaches backend `/health`.
- The built browser assets contain no action token.

## 9. Milestone 5 — Harden and complete the backend

### Files

- `D:\media\config\homepage-actions\main.py`
- `D:\media\config\homepage-actions\test_qbt_actions.py` (new focused test file)
- `D:\media\scripts\validate-core.ps1`

### Fail-closed token validation

Change the shared token validator once so all protected mutations use the same rule:

- Empty server `ACTIONS_TOKEN` is invalid.
- Missing request token is invalid.
- Incorrect request token is invalid.
- Only an exact configured token is accepted.

Protected mutations return `401`; read-only endpoints keep their current behavior unless they are already protected.

### Per-torrent routes

Add:

- `POST /qbt/torrents/stop`
- `POST /qbt/torrents/start`

Request body:

```json
{ "id": "40-or-64-character-hex-hash" }
```

Use the standard library for exact validation. The ID must fully match either 40 or 64 hexadecimal characters. Reject empty IDs, `all`, comma-separated values, prefixes/suffixes, traversal-like strings, and malformed JSON.

Validation order and responses:

1. Disallowed origin: `403`.
2. Missing, empty, or incorrect token: `401`.
3. Invalid body/hash: `400`.
4. Forward to qBittorrent using `hashes=<validated-id>`.
5. Accepted downstream request: `200 {"ok": true}`.
6. qBittorrent error, timeout, or unusable response: `502` with the existing safe error shape.

Do not remove the existing global start-all/stop-all routes in this change; the Angular UI still exposes global actions.

### Focused backend checks

The new test file must cover:

- Empty configured token.
- Missing and incorrect request token.
- Disallowed origin.
- Malformed JSON.
- Invalid IDs, including `all` and comma-separated hashes.
- Valid 40- and 64-character hashes.
- Correct qBittorrent path/form payload.
- Downstream error mapped to `502`.

`validate-core.ps1` must fail when `ACTIONS_TOKEN` is absent or empty.

Acceptance gate:

- Invalid IDs never reach qBittorrent.
- A backend started without a token cannot accept protected mutations.
- Both per-torrent routes work through the same validation and forwarding path.
- Existing global actions and read endpoints remain compatible.

## 10. Milestone 6 — Compose migration and CORS

### Files

- `D:\media\docker-compose.yml`
- `D:\media\.env.example`
- Backend CORS configuration in `D:\media\config\homepage-actions\main.py`

### CORS allowlist

Allow exactly:

```text
http://localhost:3000
http://127.0.0.1:3000
http://localhost:3001
http://127.0.0.1:3001
http://localhost:4200
http://127.0.0.1:4200
http://localhost:5173
```

Continue allowing an absent `Origin` for same-origin server-to-server proxy requests.

### Token configuration

Use Compose `:?` guards for every service that consumes `ACTIONS_TOKEN`:

```yaml
ACTIONS_TOKEN: ${ACTIONS_TOKEN:?ACTIONS_TOKEN must be set}
```

### Image safety

Before changing the current React service, record its image ID and tag it:

```text
media-dashboard-react:legacy-<react-sha>
```

Do not rebuild React during this migration.

### Temporary staging topology

- Existing running React dashboard remains on port `3000`.
- Add temporary `dashboard-angular-stage` using the Angular image on port `3001`.
- Verify the complete Angular/backend integration at `http://127.0.0.1:3001`.

### Final topology

Angular:

```text
service: dashboard
container: dashboard
port: ${DASHBOARD_PORT:-3000}
```

Legacy React:

```text
service: dashboard-react
container: dashboard-react
profile: legacy-dashboard
port: ${LEGACY_DASHBOARD_PORT:-3001}
image: media-dashboard-react:legacy-<react-sha>
```

Delete the temporary staging service after cutover verification.

Acceptance gate:

- `docker compose config` succeeds with a token and fails clearly without one.
- Angular staging uses the actual Docker backend and token injection.
- React is not started by ordinary `docker compose up -d`.
- Both dashboard images are locally identifiable by immutable tags.

## 11. Milestone 7 — Playwright and end-to-end verification

### Files

- `playwright.config.ts`
- `tests/smoke/app-routes.smoke.ts` only if an app-specific assertion is missing

Add `SMOKE_BASE_URL` support:

- When set, Playwright targets that URL and does not start `ng serve`.
- When absent, preserve the current isolated local-server behavior.
- Keep `reuseExistingServer: false` for the locally managed server.

The smoke suite must verify an Angular-specific landmark before accepting route checks. A generic HTTP 200 is insufficient.

### Angular verification

```powershell
Push-Location C:\git\media-manager-angular
npm run lint
npm test -- --watch=false
npm run build:live
npm run build:storybook
npm run test:storybook
git diff --check
Pop-Location
```

### Backend verification

```powershell
Push-Location D:\media\config\homepage-actions
python -m unittest discover -p "test_*.py"
Pop-Location

Push-Location D:\media
docker compose config
.\scripts\validate-core.ps1
Pop-Location
```

### Staging verification

```powershell
$env:SMOKE_BASE_URL = 'http://127.0.0.1:3001'
npm run test:smoke
Remove-Item Env:SMOKE_BASE_URL
```

Additionally verify manually or by HTTP checks:

- `/api/health` returns backend health through Nginx.
- Downloads load from `/api/qbt/torrents`.
- Movies and series load through their existing endpoints.
- Storage shows the real `/data` totals and path-derived label.
- Global pause/resume still works.
- Per-torrent pause/resume works with a real torrent hash.
- Missing/wrong token and disallowed-origin mutations fail.
- No SABnzbd live entry is rendered.
- Deep-link refresh works.

A syntactically valid nonexistent torrent hash may return `{"ok":true}` because qBittorrent accepts the idempotent request. That proves validation and forwarding, not torrent existence.

## 12. Milestone 8 — Cutover and rollback drill

### Cutover

1. Confirm the React rollback image tag exists.
2. Stop and remove `dashboard-angular-stage` to free port `3001`.
3. Recreate Compose service `dashboard` from the immutable Angular image.
4. Verify `http://127.0.0.1:3000` with health checks and Playwright.
5. Record image IDs, container health, and verification results.

### Real rollback drill

1. Stop Angular `dashboard`.
2. Start `dashboard-react` with the `legacy-dashboard` profile and `LEGACY_DASHBOARD_PORT=3000`.
3. Verify the React application and proxied backend at `http://127.0.0.1:3000`.
4. Stop/remove `dashboard-react`.
5. Restore Angular `dashboard` on port `3000`.
6. Repeat Angular health and smoke checks.

The rollback drill is incomplete unless the old application actually serves successfully on the canonical port.

### Legacy removal

Start the 14-day retention clock only after:

- Angular cutover succeeds.
- The rollback drill succeeds.
- Angular is restored and reverified.

After 14 consecutive stable days, remove the React service/profile and legacy image in a separate cleanup change.

## 13. Documentation and commit boundaries

### Documentation files

- `C:\git\media-manager-angular\README.md`
- `C:\git\media-manager-angular\docs\architecture.md`
- `D:\media\README.md`

Document:

- Browser → Angular Nginx → `homepage-actions` request flow.
- Why `/api` is stripped.
- Where `ACTIONS_TOKEN` exists and where it must never exist.
- Canonical URL and supported development origins.
- Build, staging, cutover, and rollback commands.
- Storage `/data` semantics.
- React retirement date calculation.

Preferred focused commits:

1. Angular API contract corrections and SAB removal.
2. Angular live build, Docker, Nginx, and Playwright changes.
3. Backend actions, fail-closed security, tests, and validation.
4. Compose staging/final topology and operational documentation.
5. Post-cutover removal of temporary staging configuration.

Do not mix unrelated pre-existing changes into these commits.

## 14. Definition of done

Implementation is complete only when all statements are true:

- Angular is the dashboard served at `http://127.0.0.1:3000`.
- The browser makes backend requests only through same-origin `/api/*`.
- `/api` is stripped before requests reach `homepage-actions`.
- No secret token exists in Angular source, bundles, source maps, or browser-visible configuration.
- Storage uses `/system/resources` and accurately identifies `/data` as a mounted volume.
- Library totals use the existing movies and series endpoints.
- SABnzbd is absent from live configuration and UI.
- qBittorrent uses port `8081` for browser navigation.
- Global and per-torrent actions work through the backend.
- Empty/missing/wrong tokens fail closed and invalid hashes never reach qBittorrent.
- Angular lint, unit tests, production-live build, Storybook, and smoke tests pass.
- Backend unit tests, Compose validation, and core validation pass.
- A real React rollback succeeds on port `3000`, followed by successful Angular restoration.
- Unrelated user changes in both repositories remain untouched.

