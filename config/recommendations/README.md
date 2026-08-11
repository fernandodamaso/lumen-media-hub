# Recommendations store

`recommendations.json` (version 3) is the shared state between the dashboard Discover page and the Hermes agent cron. It is mutable runtime data and is **git-ignored**; the files that ship are:

- `schema-v3.json` — the authoritative current contract (JSON Schema, documentation)
- `schema-v2.json` — the retained historical input contract for migration
- `recommendations.example.json` — a valid example document
- `HERMES_DISCOVER_PROMPT.md` — the Hermes cron prompt
- `README.md` — this file

The schema is enforced on every write by `RecommendationStore.validate_v3` in `config/homepage-actions/recommendations_store.py` (hand-rolled, stdlib-only — no third-party validator is available in the container). Keep the two in sync.

## Storage guarantees

All reads and writes go through `RecommendationStore` (`config/homepage-actions/recommendations_store.py`), the sole in-process abstraction:

- process-wide lock around read-modify-write transactions;
- schema validation before commit — an invalid candidate is rejected and the file is left unchanged;
- write to a sibling `*.tmp` file, flush + fsync, atomic `os.replace`, then a best-effort directory fsync;
- `revision` increments monotonically on every successful mutation;
- callers' objects are never mutated in place (mutators receive a deep copy).

v2 files are migrated in memory on load and persisted as v3 only after the next successful, validated mutation. Legacy v1, unknown, or malformed documents are rejected and leave the on-disk bytes unchanged. Independent `active` / `feedback` / `request_state` fields are never derived from a legacy `status` value. The live file is never edited by the prompt or by this documentation.

## Schema (v3)

```json
{
  "version": 3,
  "revision": 12,
  "updated_at": "2026-07-11T12:00:00Z",
  "presented_media_ids": ["movie:1538"],
  "items": [
    {
      "id": "hermes-movie-1538",
      "identity": "movie:1538",
      "source": "hermes",
      "type": "movie",
      "title": "Collateral",
      "year": 2004,
      "tmdb_id": 1538,
      "reason": "Short Hermes rationale",
      "active": true,
      "feedback": "liked",
      "feedback_at": "2026-07-11T12:05:00Z",
      "request_state": null,
      "requested_at": null,
      "jellyseerr_request_id": null,
      "poster_path": "/...jpg",
      "added_at": "2026-07-11T12:00:00Z"
    }
  ]
}
```

State lives on **independent dimensions** instead of one overloaded `status`:

| Field | Values | Meaning |
|-------|--------|---------|
| `active` | `true` / `false` | Whether the title belongs in the default recommendation feed |
| `feedback` | `null` / `liked` / `disliked` / `watched` / `skipped` | User feedback; `disliked`, `watched`, `skipped` also deactivate |
| `request_state` | `null` / `requested` | Sent to Jellyseerr via the dashboard Request button |
| `feedback_at` / `requested_at` | timestamp or `null` | When the dimension last changed (UTC, `...Z`) |
| `jellyseerr_request_id` | integer or `null` | Jellyseerr request ID when known |

Transition rules: feedback writes never clear request fields; a successful request updates only request fields and preserves feedback. Like leaves `active` unchanged (reactivation happens exclusively through generation acceptance); dislike/watched/skipped and request set `active=false`.

There is no legacy `status` field. Consumers must use the independent v3 fields above; a missing or malformed v3 state is invalid data and is not reconstructed by the API.

## Generations endpoint (the only item writer)

`POST /discover/hermes/generations` (actions-token auth) commits one Hermes generation as a single locked transaction. Hermes no longer writes this file directly; the retired `POST /discover/hermes` upsert returns **410 Gone** and points here.

Request:

```json
{
  "base_revision": 12,
  "candidates": [
    {"type": "movie", "title": "Heat", "year": 1995, "tmdb_id": 949, "reason": "..."},
    {"type": "movie", "title": "Collateral", "year": 2004, "tmdb_id": 1538, "reason": "...", "retain": true}
  ]
}
```

- `base_revision` must equal the store's current `revision` (from `GET /discover/hermes`); a stale value returns **409** `{"ok": false, "error": "stale_base_revision", "current_revision": N}` and commits nothing. Re-read, rebuild, resubmit.
- Candidate fields: `type` (`movie`/`tv`), non-empty `title`, positive integer `tmdb_id`, optional integer `year`, optional `reason` string, optional `"retain": true`.
- `"retain": true` keeps an **already-active** item active and may refresh its `type`/`title`/`year`/`reason`; feedback, request state, all timestamps, and Jellyseerr identifiers are preserved untouched.
- Active items omitted from the batch are **rotated**: `active=false`, everything else preserved, nothing deleted — **except untouched actives** (`feedback` and `request_state` both null) and **liked actives**, which are auto-retained so titles the user has not finished with cannot leave Active. Rotated identities stay in `presented_media_ids`, so they can never be presented as new again. A batch where every candidate is rejected still commits and may rotate other interacted actives (`disliked` / `skipped` / `watched` / requested); Hermes recovers on its next run by submitting a valid batch.
- New candidates whose identity is already in Sonarr/Radarr are rejected as `already_tracked`; identities already playable in Jellyfin are rejected as `already_in_library`. `GET /discover/hermes` exposes both sets under `context` so Hermes can filter before submit.
- Newly accepted items get `identity = movie:<tmdb_id>` or `tv:<tmdb_id>`, `id = hermes-<type>-<tmdb_id>`, `active=true`, null feedback/request fields, `added_at`, and their identity appended to `presented_media_ids` — all in the same commit.

Response (`200`):

```json
{
  "ok": true,
  "revision": 13,
  "accepted": [{"identity": "movie:949", "tmdb_id": 949, "id": "hermes-movie-949"}],
  "retained": ["movie:1538"],
  "rotated": ["movie:550"],
  "rejected": [{"index": 3, "identity": "movie:120", "tmdb_id": 120, "reason": "already_presented"}]
}
```

Every rejection entry carries the candidate's batch `index` (plus `tmdb_id` when one was supplied), so each rejection maps back to its submission. Machine-readable rejection reasons:

| Reason | Meaning |
|--------|---------|
| `invalid_candidate` | Field-level validation failed; `detail` lists the problems |
| `duplicate_in_batch` | Same composite identity submitted twice in one batch |
| `already_active` | Item is currently active but the candidate lacks `"retain": true`; the item is left active and unchanged |
| `already_presented` | Composite identity is in `presented_media_ids` (or on any existing item row) and not currently active — resurrection is permanently blocked |
| `already_tracked` | Title is already in Sonarr (tv) or Radarr (movie) |
| `already_in_library` | Title is already playable in Jellyfin |

Invalid or duplicate candidates are rejected individually; the valid remainder still commits. Batches are capped at 100 candidates (`400` above that).

## Poster enrichment

`GET /discover/hermes` fills `poster_url` on every item before responding. Resolution order: an existing `poster_url`, then the Jellyfin image (in-library items), then a persisted `poster_path` (derived to a TMDB image URL — **zero network calls on warm reads**), and only items missing all of those go to Jellyseerr.

Jellyseerr detail lookups (`/api/v1/{movie|tv}/{tmdb_id}`) run through a worker pool bounded by `POSTER_ENRICH_CONCURRENCY = 4` (`config/homepage-actions/main.py`), so a cold N-card response costs ~ceil(N/4) detail-call latencies instead of N. Results sit in a TTL cache:

| Outcome | TTL |
|---|---|
| Poster path found | 24 hours (`POSTER_CACHE_TTL_SECONDS`) |
| Not found / transient failure | 5 minutes (`POSTER_NEGATIVE_TTL_SECONDS`) |

Failures are never cached forever: after the negative TTL the lookup is retried, so a brief Jellyseerr outage recovers on its own.

During `POST /discover/hermes/generations`, posters for the batch are resolved in the **preparation phase, before the locked commit**, and a successful `poster_path` is persisted on newly accepted items (`poster_url` is always derived, never stored). A metadata outage never fails the GET or the generation: enrichment degrades to no-poster items (the title is always present; the frontend handles poster failure/recovery). Each batch logs one concise line to stdout: `[poster-enrich] items=… hits=… fetched=… failed=… duration=…s` (plus `skipped=… reason=no-api-key` when Jellyseerr is unconfigured, so misconfiguration is distinguishable from an outage).

## v2 → v3 migration

Runtime loading accepts valid v2 and valid v3 only. A valid v2 document is migrated in memory:

- each current item gets `identity = "{type}:{tmdb_id}"` and `id = "hermes-{type}-{tmdb_id}"`;
- numeric `presented_tmdb_ids` become conservative `legacy:<id>` tombstones;
- exact composite identities for current rows are appended to `presented_media_ids`.

A tombstone is checked against both `movie:<id>` and `tv:<id>`, preserving history when old data cannot identify the media type at the cost of possibly blocking one cross-type item. Migration is deterministic, idempotent, and never discards durable deny entries.

Legacy v1 documents (and any unknown/malformed version) are rejected after the cutover. There is no runtime path that reconstructs v3 fields from a legacy `status` value. Offline historical conversion, if ever needed, must be a separate one-shot tool — not part of normal store loading.

## Request reconciliation

If Jellyseerr accepts a Hermes request but dashboard persistence fails, the actions API queues `{hermes_id, jellyseerr_request_id}` in `request-reconciliation.json` (runtime data; git-ignored) next to `recommendations.json`.

Automatic retries:

- one attempt on actions-API startup;
- then every `HERMES_RECONCILE_INTERVAL_SECONDS` seconds (default `30`);
- a single non-overlapping cycle lock; failed entries stay queued;
- malformed queue entries are dropped so they cannot block valid ones.

Manual recovery (ops/tests): `POST /discover/request/reconcile`.

Stale-entry rule: if the item is already `request_state=requested` with a **different** Jellyseerr request ID, the queued entry is treated as superseded/conflict, logged without credentials, removed from the queue, and the newer persisted state is left untouched.

`GET /discover/hermes` exposes pending sync without secrets:

```json
"pending_request_sync": [
  { "id": "hermes-movie-42", "jellyseerr_request_id": 812 }
]
```

The dashboard uses that list (not component-local memory alone) so remount/refresh keeps Request disabled and shows `Requested in Jellyseerr; dashboard synchronization failed.` until reconciliation succeeds.

## Never-twice / history

Root field `presented_media_ids` is the durable, append-only deny set: every composite identity ever presented by Hermes, plus conservative `legacy:<id>` tombstones migrated from v2. The generations endpoint enforces it on every commit: a candidate whose exact identity (or legacy tombstone) is already in the deny set is rejected with `already_presented` unless it is currently active and explicitly retained. Rotated-out rows keep their identities in the deny set so they cannot return later. `movie:123` and `tv:123` are distinct new identities; repeating either exact identity is rejected.

## Dashboard behavior

- **Hermes tab** (default): shows only `source: "hermes"` items from `GET /discover/hermes`. The response also carries `revision`, `presented_media_ids`, optional `generation_request`, and a `context` object (`tracked_media_ids`, `in_library_media_ids`, `required_retain`, `taste`) for generation clients.
- **Request more**: `POST /discover/hermes/request-more` queues an on-demand generation (`generation-request.json`, git-ignored runtime data). The Active grid shows a trailing **Request more recommendations** button. The flag clears automatically after a successful `POST /discover/hermes/generations`. Hermes still runs on its cron (`0 10 * * *`); the queue is a signal for that next run, not an instant agent spawn.
- **Jellyseerr / Trakt tabs**: browse-only proxies; feedback buttons are Hermes-only.
- Feedback writes via `PATCH /discover/hermes/{id}` (dashboard-only, not Jellyfin thumbs).
- Request writes go through **Radarr/Sonarr directly** as unmonitored library entries (`monitored=false`, no search). Movies use Radarr; TV uses Sonarr. If the Arr add succeeds but the dashboard annotation cannot be committed, the API returns `dashboard_state_persisted=false` with the Arr id, queues durable reconciliation, and exposes the Hermes id on `GET /discover/hermes` as `pending_request_sync`. The dashboard shows `Added to Sonarr/Radarr; dashboard synchronization failed.`, keeps Request disabled across refresh/remount, and does not invite an immediate duplicate request.

## Hermes cron

See `HERMES_DISCOVER_PROMPT.md` for the full agent prompt and registration command.

Daily schedule: `0 10 * * *` — job prompt is a **pointer** to that file (do not inline the markdown). Hermes reads `GET /discover/hermes` for the snapshot, revision, and `context` (Arr/Jellyfin excludes + required retain + taste), filters Trakt picks against `presented_media_ids` and `context` exclude sets, submits candidates to `POST /discover/hermes/generations` (retrying a 409 only after a fresh snapshot), treats rejections as authoritative, logs to `tmp/hermes-discover.log`, then `POST /discover/hermes/sync`. It never writes `recommendations.json` directly — the prompt is a quality and workflow specification, not a data-integrity boundary; the API enforces the invariants.

## Trakt credentials

Add to `.env` (not committed):

- `TRAKT_CLIENT_ID` — from https://trakt.tv/oauth/applications
- `TRAKT_CLIENT_SECRET` — local Trakt OAuth application secret used by the refresh client and `install.ps1 -Mode connect-trakt`
- `TRAKT_TOKEN_PATH` — renewable token state path inside the backend (`/state/trakt-token.json` by default)
- `TRAKT_ACCESS_TOKEN` — migration-only bearer fallback while renewable state is created; do not expose it to the browser

Used by Hermes cron and the dashboard Trakt Discover tab (`GET /discover/trakt`).

## Jellyfin collection

`POST /discover/hermes/sync` rebuilds the **Hermes Picks** Jellyfin collection from in-library Hermes items (excludes `disliked` / `skipped` feedback).
