# Hermes Discover — agent cron prompt

You maintain personalized media recommendations for the D:\media stack dashboard Discover page. All state changes go through the actions API (`http://localhost:8085`, header `X-Actions-Token` from `.env` `ACTIONS_TOKEN`). **Never write `config/recommendations/recommendations.json` directly** — the API is the only writer and enforces the never-twice deny list; direct writes are data corruption.

Do **not** paste or rewrite this whole prompt into the cron job; the job should say: follow this file.

## Workflow

If `GET /discover/hermes` includes `"generation_request": {"status":"pending",...}`, the dashboard user asked for **more** recommendations — add about **8–12 new** candidates while retaining every required keeper (untouched actives not in an authoritative exclusion set). Do not replace or thin the Active list. A successful `POST /discover/hermes/generations` clears the flag automatically.

### 1. Read the current snapshot

`GET http://localhost:8085/discover/hermes` with the token header. Note:

- `revision` — required as `base_revision` when you submit;
- `presented_media_ids` — durable deny list: every composite `movie:<id>` or `tv:<id>` identity ever presented. A `legacy:<id>` entry is a conservative v2 tombstone that blocks both types;
- `items[]` — active picks plus history with `feedback` (`liked` / `disliked` / `watched` / `skipped`) and `request_state`;
- `context` — **use this; do not curl Sonarr, Radarr, or Jellyfin yourself**:
  - `tracked_media_ids` — already in Sonarr/Radarr;
  - `in_library_media_ids` — already playable in Jellyfin;
  - `watched_media_ids` — authoritative typed Trakt watched deny list (`movie:<id>` / `tv:<id>`); never submit these as new candidates or as `retain: true` keepers;
  - `required_retain` — active, untouched identities you **must** submit with `"retain": true`; library and watched identities are omitted;
  - `taste` — compact `liked` / `disliked` / `skipped` / `watched` title lists;
  - optional `context_errors` — Arr/Jellyfin fetch degraded; still proceed with the lists returned (may be empty).

Build a compact taste index from `context.taste` (and skim active `items` only if needed). Do not dump giant JSON into reasoning:

- `liked` → positive keep-in-Active taste signal;
- `disliked` / `skipped` → hard negatives (same composite identity never again; avoid obvious near-clones);
- `watched` → done / history; a sequel/spin-off with a **different** `tmdb_id` is OK only when intentional;
- `request_state: "requested"` / identities in `tracked_media_ids` → already owned; do not duplicate.

**Cron-mode note:** `execute_code` is blocked in cron jobs. Use `terminal` with `curl` + `python -c` for JSON parsing, or `jq` if available. Save intermediate JSON to `*.tmp.json` files in `D:\media` and clean them up after.

### 2. Pull Trakt personalization (input only)

Trakt is an input signal, not a tab dump. Hermes items are curated picks, not a Trakt mirror.

- `GET https://api.trakt.tv/recommendations/movies?limit=25&ignore_collected=true&extended=full`
- `GET https://api.trakt.tv/recommendations/shows?limit=25&ignore_collected=true&extended=full`
- Headers: `Content-Type: application/json`, `trakt-api-version: 2`, `trakt-api-key: {TRAKT_CLIENT_ID}`, `Authorization: Bearer {TRAKT_ACCESS_TOKEN}`
- Credentials from `.env`: `TRAKT_CLIENT_ID`, `TRAKT_ACCESS_TOKEN`

Optional weak popularity prior: use the actions API proxy (`GET http://localhost:8085/discover/jellyseerr?kind=movies` and `?kind=tv` with the `X-Actions-Token` header). Do **not** hit Jellyseerr directly — its API key is scoped to the Docker network and returns 403 from outside. The actions API proxy is the only supported path. Do **not** copy wholesale.

**Empty Trakt is not a stop.** If Trakt errors, returns nothing, or every hit is already denied/tracked/in-library, proceed with the Jellyseerr proxy plus your own curated picks aligned to `context.taste`. Do **not** abort the run, skip the POST, or go silent — still submit keepers (`required_retain`) and whatever new usable candidates you can assemble.

### 3. Build the candidate batch

Target roughly **15–25 active recommendations** after the commit when starting from a small Active list. If many required keepers must be retained, the Active list may exceed 25 — that is correct; never rotate keepers just to hit a count. On a pending `generation_request`, prefer **+8–12 new** accepts on top of keepers rather than rebuilding the whole slate.

- Drop any Trakt hit whose typed identity (`movie:<ids.tmdb>` or `tv:<ids.tmdb>`) is already in `presented_media_ids` — the API will reject it anyway; filtering first is just efficient. A matching `legacy:<ids.tmdb>` tombstone also blocks the candidate.
- Drop any candidate whose typed identity is in `context.tracked_media_ids` or `context.in_library_media_ids`. The API also rejects these as `already_tracked` / `already_in_library` if you forget.
- Drop any candidate whose typed identity is in `context.watched_media_ids`. The API rejects a new watched candidate as `already_watched`, preserving its typed identity in the rejection response.
- Include **every** identity in `context.required_retain` with `"retain": true`. **Interacted** actives you omit (`liked` / `disliked` / `skipped` / `watched`, or `request_state` set) are rotated to history and can never return as new picks — omit those only when rotation is intentional. Untouched active rows outside the authoritative exclusion sets are auto-retained by the API even if omitted; still include them via `required_retain`.
- Each candidate: `type` (`"movie"` or `"tv"`), `title`, `year`, `tmdb_id` (real IDs only — from Trakt `ids.tmdb` or TMDB search; never invent), `reason` (one short sentence why *this user* will like it, referencing liked patterns / Trakt signals). Optional `"retain": true`.
- Prefer 4K-friendly mainstream releases aligned with this stack's quality goals.
- Never modify feedback, request, or timestamp fields — you cannot; the API preserves them for retained items.

**Retain discipline (hard rules):**

1. **Submit every `context.required_retain` identity** with `"retain": true`. That list is the server’s view of untouched active rows outside library and watched deny sets. Never omit them. The API also refuses to rotate these even if you forget.
2. **Never retain excluded identities.** Library, tracked, and watched typed identities are authoritative deny sets. The server excludes library and watched identities from `required_retain`; if an excluded active row is present, a successful generation rotates it to History while preserving its metadata.
3. **Do not resurrect history.** Rows that are already `active=false` (typically `disliked` / `skipped` / `watched` / `requested`) stay in history — omit them from the batch. Never try to bring them back with `"retain": true` (the API rejects resurrection).
4. After retaining all required keepers, add **new** candidates (no `retain`) to refresh the slate. Prefer quality over filling a quota.

Do not “thin” the Active list by rotating titles the user has not finished with.

### 4. Submit the generation

`POST http://localhost:8085/discover/hermes/generations` with the token header:

```json
{
  "base_revision": <revision from step 1>,
  "candidates": [
    {"type": "movie", "title": "Heat", "year": 1995, "tmdb_id": 949, "reason": "..."},
    {"type": "movie", "title": "Collateral", "year": 2004, "tmdb_id": 1538, "reason": "...", "retain": true}
  ]
}
```

- Required keepers (`context.required_retain`) **must** appear in `candidates` with `"retain": true` before you POST. Do not submit an empty batch or a new-only batch that forgets keepers.
- **200**: `accepted` / `retained` / `rotated` / `rejected` are authoritative. Do not try to force a rejected candidate through; `already_presented` / `already_tracked` / `already_in_library` / `already_watched` mean that title is done for this pipeline. If `rotated` includes an identity that was not excluded or intentionally interacted, or required keepers are missing from `retained`, treat the run as failed — fix the batch and do not “fix” it with another thin commit. An all-rejected commit can still rotate interacted actives (`disliked` / `skipped` / `watched` / requested); that is why keepers must be explicit.
- **409** (`stale_base_revision`): feedback or a request landed while you worked. Re-run step 1 for a fresh snapshot and revision, rebuild the batch (re-check retain choices against new feedback), and resubmit once. Never retry a 409 blindly.

### 5. Refresh Jellyfin

`POST http://localhost:8085/discover/hermes/sync` with the token header to rebuild the **Hermes Picks** collection (in-library items only).

### 6. Log

One line to `tmp/hermes-discover.log`: `accepted=N retained=N rotated=N rejected=N revision=R`.

### 7. Clean up

Delete any `*.tmp.json` scratch files created during the run (e.g. `snap.tmp.json`, `trakt_*.tmp.json`, `actions_jelly_*.tmp.json`, `payload.tmp.json`, `result.tmp.json`, `sync.tmp.json`).

## Cron registration (media-ops profile)

```powershell
$env:HERMES_HOME = "$env:LOCALAPPDATA\hermes\profiles\media-ops"
hermes cron create "0 10 * * *" `
  --name "Hermes Discover Recommendations" `
  --workdir "D:\media" `
  "Follow the instructions in config/recommendations/HERMES_DISCOVER_PROMPT.md exactly."
```

`workdir D:\media` injects repo `AGENTS.md` and scopes file tools. Hermes needs network access to `localhost:8085` (actions API) and Trakt. Sonarr/Radarr/Jellyfin exclusion data comes from the actions API `context` — do not curl those services. Jellyseerr popularity (if used) goes only through the actions API proxy. Hermes must not write `recommendations.json`.

If the job already exists, **edit the prompt file only** (this job already points at the file). Do not paste the full markdown into `jobs.json`.

Ensure the Hermes gateway is running (`hermes gateway install`) for the schedule to fire.
