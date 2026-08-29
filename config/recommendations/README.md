# AI Picks recommendation state

`recommendations.json` is mutable, ignored runtime state owned exclusively by
`homepage-actions`. The shipped contracts are `schema-v2.json`, `schema-v3.json`,
`schema-v4.json`, and `recommendations.example.json`.

Schema v4 uses typed identities (`movie:<tmdb_id>` and `tv:<tmdb_id>`), item IDs
`ai-<type>-<tmdb_id>`, `source: "ai"`, an append-only `presented_media_ids`
never-twice set, and one nullable durable `generation` job. The backend validates
every transaction and performs an fsync-backed atomic replace.

At startup, valid v2 state migrates through v3 to v4. Valid v3 state migrates
directly to v4. Before the first migrated write, the backend creates a
non-overwriting sibling `.v2.bak` or `.v3.bak`; failed validation or backup leaves
the source bytes unchanged. Feedback, request state, timestamps, Trakt delivery
events, poster metadata, history, and never-twice identities are preserved.

## Ownership and API

The browser uses:

- `GET /discover/ai-picks`
- `PATCH /discover/ai-picks/{id}`
- `POST /discover/ai-picks/request-more`
- `POST /discover/request` with optional `aiPickId`

The network-internal worker uses actions-token authenticated routes:

- `POST /internal/ai-picks/jobs/claim`
- `POST /internal/ai-picks/jobs/{id}/complete`
- `POST /internal/ai-picks/jobs/{id}/fail`

The public GET includes cards, pending request reconciliation, library/watched
freshness, `generation_enabled`, and the safe generation projection. It never
includes candidates, taste, revisions, exclusion identity sets, lease tokens, or
lease expiry. Dashboard Nginx and the live-development proxy return 404 for all
`/api/internal/*` requests.

`homepage-actions` builds at most 100 candidates from Trakt movie/show
recommendations and Jellyseerr movie/TV discovery, then deduplicates and removes
presented, tracked, playable, and watched identities. It tolerates one source
failure only when another source is usable and all authoritative exclusion
snapshots are available. The worker returns only `{identity, reason}` values;
the backend validates them against the stored pool and joins server-owned
metadata before the atomic commit.

Only one queued/running job is allowed. Claims use an opaque five-minute lease;
expired or stale workers cannot commit. Scheduled generation runs daily at the
configured `AI_PICKS_SCHEDULE_HOUR` (10:00 by default) in container-local time
only when active picks are below the configured target.
On-demand generation uses the configured count.

The Jellyfin collection is named **AI Picks**. If only the legacy collection
exists, the backend reposts its complete item DTO with only `Name` changed. If
both collections exist, it uses AI Picks and logs a warning without deleting
either collection.
