# FDM-529: Full Angular Dashboard Cutover — Implementation Plan (v2, merged review)

Supersedes the FDM-529 draft and operationalizes [`docs/backend-integration-implementation-plan.md`](docs/backend-integration-implementation-plan.md) milestones 5–8 (milestones 1–4 are done: Angular repo clean at `main`, `build:live`, `Dockerfile`, `nginx.conf.template`, Playwright `SMOKE_BASE_URL` support all present).

Incorporates two independent senior reviews. Key corrections relative to the draft:

1. `validate-core.ps1` is **destructive** (deletes library files, recreates Radarr entries, can restart Jellyfin) — removed from the cutover gate.
2. Angular image moves from `nginx:1.27-alpine` to `nginx:1.28-alpine` (stable line carrying the 2026 security fixes).
3. The `D:\media` worktree is dirty in exactly the files this plan edits — a preservation decision must happen **before** Phase 1.
4. The legacy React service must receive `ACTIONS_TOKEN`, or the rollback drill fails/vacuously passes after fail-closed hardening.
5. The rollback image is tagged by **image ID** (`77b344ef4f65`), not source sha (source tree is dirty; tags are mutable — record resolved IDs).

## Goal and non-goals

Angular replaces React on `http://127.0.0.1:3000`, served by a prebuilt immutable-tagged image. `homepage-actions` becomes fail-closed with per-torrent qBittorrent routes. React survives as a `legacy-dashboard` Compose profile with a *proven* rollback path.

Out of scope: new aggregate APIs, auth redesign, React source deletion (14-day wait, separate change), feature parity work, running the full `validate-core.ps1`, rebuilding React.

## Milestone 0 — Baseline, preservation, image provenance

```powershell
git -C C:\git\media-manager-angular rev-parse HEAD; git -C C:\git\media-manager-angular status --short
git -C D:\media rev-parse HEAD; git -C D:\media status --short
docker inspect media-dashboard:latest --format '{{.Id}} {{.Created}}'
```

1. **Disposition the dirty `D:\media` tree first — decision: separate preservation commit(s).** `main.py`, `docker-compose.yml`, `.env.example`, `scripts/validate-core.ps1`, `README.md`, and the React source are all modified, with unrelated homepage files deleted. These are the same files this plan edits. Review the existing hunks and land them as their own commit(s) *before* Milestone 1, so every FDM-529 commit is clean. No reset, no blanket stash. Use path/hunk-scoped staging for all later commits.
   - The Angular repo is clean — the draft's "Angular WIP library/discover cards" caveat is stale; ignore it.
2. **Tag the running React image by image ID** (verified: `sha256:77b344ef4f65…`, built 2026-07-12):

   ```powershell
   docker tag media-dashboard:latest media-dashboard-react:legacy-77b344ef4f65
   ```

   Record image ID, build date, and both repos' git state in the ops notes. Never rebuild React — the source tree does not match the running image.
3. Verify `ACTIONS_TOKEN` is present in `D:\media\.env` (Compose `:?` guards will make every compose command fail without it; `.env` — not an interactive shell — must be the source).

**Gate:** baselines recorded; dirty-tree disposition decided; legacy tag exists (`docker images | grep legacy-77b344ef4f65`).

## Milestone 1 — Backend hardening (`D:\media\config\homepage-actions`)

Files: `main.py`, new `test_qbt_actions.py`, `scripts/validate-core.ps1`, `docker-compose.yml` (CORS env only).

1. **Fail-closed `_token_valid`:** empty configured token → reject; missing header → reject; compare with `hmac.compare_digest` (stdlib, timing-safe, matches the codebase's stdlib-only style). Only exact match passes. Protected mutations return `401`.
2. **Per-torrent routes** `POST /qbt/torrents/stop` and `/start`, body `{ "id": "<hash>" }`. Full-match validation: exactly 40 *or* 64 hex chars (qBittorrent v4 SHA-1 / v5 SHA-256). Reject empty, `all`, comma-separated, prefixes/suffixes, traversal-like strings, malformed JSON. Response order: disallowed origin `403` → token `401` → body/hash `400` → forward `hashes=<id>` → `200 {"ok": true}` / downstream failure `502` with the existing safe error shape. Keep `/stop-all` / `/start-all` (UI still exposes global actions).
3. **CORS allowlist, single source in Compose** (`CORS_ORIGINS` env on `homepage-actions`): exactly

   ```text
   http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:4200,http://127.0.0.1:4200,http://localhost:5173
   ```

   Keep `:3001` after cutover — it is the legacy profile's default port. Absent `Origin` stays allowed (nginx same-origin proxy).
4. **Tests** (`test_qbt_actions.py`): empty configured token; missing/wrong token; disallowed origin; malformed JSON; invalid IDs incl. `all` and comma-lists; valid 40- and 64-char hashes; correct qBittorrent path/form payload; downstream error → `502`.
5. **`validate-core.ps1`:** add an early, non-destructive `ACTIONS_TOKEN`-empty check wired into the hard-stop/exit-code path (the script's exit code currently only reflects hardlink/GPU failures, line 510–511). **Do not run the full script as a cutover gate** — it deletes library files (`:282`), recreates Radarr entries, downloads media, and may restart Jellyfin (`:458`).

**Gate (non-destructive only):** `python -m unittest discover -p "test_*.py"` green; `docker compose config` valid; restart `homepage-actions`, then through the *still-live React* on `:3000`: page renders, one controlled mutation succeeds with token, `401` missing/wrong token, `403` bad origin, `400` bad hash. This proves the hardened backend before any Angular container exists.

## Milestone 2 — Angular image (this repo)

Files: `Dockerfile`, `nginx.conf.template`.

1. Base image `nginx:1.28-alpine` (current stable line; includes the Feb/Mar 2026 security fixes — CVE-2026-1642 is TLS-upstream-only and not exploitable via our plain-HTTP upstream, but the March batch of 6 fixes matters). Record the resolved digest after build.
2. `NGINX_ENVSUBST_FILTER=^ACTIONS_TOKEN$` (anchored; proven by the React image on the same base).
3. Do **not** add `X-Real-IP` / `X-Forwarded-Proto` — `main.py` never reads them. Keep the template as-is otherwise.
4. Confirm no token lands in `dist/dashboard/browser` (`grep -r`).

**Gate:** `npm run quality` (lint, typecheck, stylelint, duplicates, dead-code, architecture), `npm test -- --watch=false`, `npm run build:live`, `npm run build:storybook`, `npm run test:storybook`, `git diff --check` — all green.

**Then commit** the Angular changes, **then** build once and tag immutably with the resulting commit:

```powershell
docker build -t media-dashboard-angular:<short-sha> -t media-dashboard-angular:local .
docker inspect media-dashboard-angular:<short-sha> --format '{{.Id}}'   # record it
```

## Milestone 3 — Compose staging (`D:\media`)

Files: `docker-compose.yml`.

1. `ACTIONS_TOKEN: ${ACTIONS_TOKEN:?ACTIONS_TOKEN must be set}` on `homepage-actions` and every dashboard service.
2. Expanded `CORS_ORIGINS` per Milestone 1.3.
3. Temporary `dashboard-angular-stage`: prebuilt Angular image, `127.0.0.1:3001:80`, `depends_on: homepage-actions`. React stays on `:3000`.

**Gate:**
- `docker compose config` passes with token, fails clearly without.
- Staged app is verifiably **Angular** (landmark: `Dashboard | Media Manager` title / theme picker), not accidentally React.
- Non-mutating HTTP checks through staging nginx: `/api/health`, `/api/qbt/torrents`, `/api/jellyfin/movies`, `/api/jellyfin/series`, `/api/system/resources` showing the real `/data` totals and path-derived label.
- Auth negatives: `401` missing/wrong token, `403` disallowed origin, `400` invalid hash — none reach qBittorrent.
- Controlled mutation: per-torrent stop/start on **one controlled real torrent** — this proves the full chain including qBittorrent effect. The live queue is currently empty, so the protocol is: add a tiny harmless torrent (e.g. a small Linux ISO) **in paused state**, record its hash, run stop/start against it, confirm state round-trips in `/api/qbt/torrents`, then remove it (no data). **Never** use global stop-all/start-all against the live queue as a test. (Fallback if adding a torrent is not possible: a syntactically valid nonexistent hash, which returns `{"ok":true}` and proves auth+forwarding only.)
- No SABnzbd rendered; deep-link refresh returns the SPA; qBittorrent links to `:8081`.
- `SMOKE_BASE_URL=http://127.0.0.1:3001 npm run test:smoke` (Playwright proves SPA/routing; the HTTP checks above prove Live integration).

## Milestone 4 — Cutover

1. Remove `dashboard-angular-stage` (frees `:3001`).
2. `dashboard` service: replace `build: ./dashboard` with `image: media-dashboard-angular:<short-sha>`, keep `127.0.0.1:${DASHBOARD_PORT:-3000}:80`, token env with `:?`, `depends_on: homepage-actions`.
3. Add `dashboard-react`: `image: media-dashboard-react:legacy-77b344ef4f65`, `profiles: [legacy-dashboard]`, `127.0.0.1:${LEGACY_DASHBOARD_PORT:-3001}:80`, **`ACTIONS_TOKEN: ${ACTIONS_TOKEN:?…}`**, `depends_on: homepage-actions`, **no `build:` key**. (Without the token env, fail-closed backend 401s every React mutation and the drill is meaningless.)

**Gate:** full Milestone 3 verification suite re-run against `http://127.0.0.1:3000`. Record image IDs, container states, results.

## Milestone 5 — Rollback drill, docs, retention clock

Exact drill (never put `COMPOSE_PROFILES` in `.env` — React must not join ordinary `up`):

```powershell
docker compose stop dashboard
$env:LEGACY_DASHBOARD_PORT='3000'; docker compose --profile legacy-dashboard up -d dashboard-react
# verify: React UI identity on :3000, /api/health 200 through React nginx,
#   and a per-torrent stop/start round-trip on the pre-selected controlled torrent
docker compose --profile legacy-dashboard rm -sf dashboard-react
Remove-Item Env:LEGACY_DASHBOARD_PORT
docker compose up -d dashboard
# re-verify Angular on :3000; plain `docker compose up -d` sanity — React stays down
```

The drill is incomplete unless React actually serves *and mutates* on the canonical port.

Docs:
- `D:\media\README.md`, `D:\media\AGENTS.md`: Angular is production; React is the `legacy-dashboard` profile; rollback commands; **cutover date and React-deletion-eligible date (+14 days) written down** — the clock has no other artifact.
- Angular `README.md` / `docs/architecture.md`: staging/cutover/rollback commands if incomplete.

Start the 14-day retention clock only after cutover **and** drill both succeed. Actual React removal is a separate later change.

## Commit boundaries

0. Preservation commit(s) for the pre-existing `D:\media` work (per Milestone 0 decision).
1. Backend: fail-closed token, per-torrent routes, tests, validate-core guard, CORS env.
2. Angular: nginx/Dockerfile polish only (precedes the image build).
3. Compose topology + ops docs.
4. Post-cutover: drop the temporary staging service.

No unrelated changes in any commit; path/hunk-scoped staging throughout.

## Risks

- **Hardest to undo:** a bad backend deploy breaking mutations for the *running* React during Milestone 1 — mitigated by verifying through React on `:3000` before any Angular container exists.
- **Cutover itself** is reversible via the drilled profile path; the drill must run before the retention clock starts.
- **Compose `:?` guards** make every compose command fail without `ACTIONS_TOKEN` in `.env` — checked in Milestone 0.3.

## Resolved decisions (was: open questions)

1. **Dirty `D:\media` disposition:** separate preservation commit(s) before Milestone 1 (Milestone 0.1). The pre-existing hunks must be reviewed to write a truthful commit message — that review is part of Milestone 0.
2. **Drill/staging mutation:** one controlled real torrent (Milestone 3 gate, Milestone 5 drill). The live queue was verified empty on 2026-07-28, so the concrete mechanism is: add a tiny harmless torrent in paused state, record its hash, verify stop/start, remove it afterward. Nonexistent-hash remains the documented fallback only.
