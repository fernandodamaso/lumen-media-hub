# Storage Guardian v1

Storage Guardian is an **explicit, read-only cleanup simulator**. It answers which already-watched local physical media files match the configured policy and how much free space the deterministic plan would recover. It does not delete media, call Sonarr/Radarr/Jellyfin removal APIs, schedule work, or execute automatically.

## Data path

```text
Jellyfin physical-file inventory + /system/resources capacity
  → homepage-actions storage_cleanup normalization/policy engine
  → authenticated POST /storage/cleanup-preview
  → StorageGuardianHttpMediaStackApi / StorageGuardianMockMediaStackApi
  → page-scoped CleanupPreviewFacade
  → /storage
  → canonical Lumen UI primitives
```

The existing app-scoped `StorageFacade` remains the 60-second capacity poller used by shell/dashboard storage indicators. `CleanupPreviewFacade` is separate, page-scoped, does **not poll**, and requests a preview only after the user presses **Run preview**.

## Safety boundary

The backend inventory is Jellyfin-first and groups by local physical media source before policy evaluation. Physical paths exist only as internal grouping keys and are never returned. Remote/virtual/placeholder/`.strm` media is excluded. Ambiguous local versions, malformed size/watch metadata, and other uncertain inventory are fail-closed: they are never eligible and appear only as safe unresolved summaries when an item-level result can be represented without private data.

Hard protections always override eligibility:

- never-watched items
- in-progress playback
- favorites
- manually kept candidate IDs
- recent additions inside the grace window
- season-zero specials for the rolling episode rule
- missing or malformed size/watch metadata
- ambiguous multi-version items

Multi-episode physical files are atomic and count once; every represented episode must independently satisfy an enabled rule. Candidate ordering is deterministic: oldest last-played timestamp, largest size, then stable candidate ID. Recommendation selection stops after the configured free-space target is restored; if the target is already met, no candidate is recommended while **All matches** remains inspectable.

## API contract

`POST /storage/cleanup-preview` is authenticated through the existing homepage-actions POST boundary. Schema version is fixed at `1`. Unknown fields, invalid candidate pins, non-finite/non-integer numbers, unsafe inventory, incomplete Jellyfin pagination, and inconsistent capacity fail closed. The endpoint returns browser-safe candidate IDs/titles/subtitles/Jellyfin links, structured rule evidence, aggregate blocked counts, safe unresolved summaries, and warnings. It never returns a filesystem path.

There is intentionally no Storage Guardian DELETE/removal endpoint, no scheduler, and no execution route in v1.

## Frontend lifecycle

`CleanupPreviewFacade` persists only browser-safe settings and candidate pins:

- `lumen.storageGuardian.policy.v1`
- `lumen.storageGuardian.pins.v1`

Corrupt or incompatible values reset to defaults. Policy/pin changes invalidate the last result and mark it stale without automatically refreshing. A new explicit Run preview aborts the previous request. A failed refresh preserves the last successful result and announces that it is stale/unchanged instead of replacing it with unsafe partial data.

The Live adapter strictly validates the response shape and derived totals before exposing it to the feature. Demo mode supports `storage-ready`, `storage-target-met`, `storage-insufficient`, `storage-degraded`, and `storage-error` scenarios.

## UI and shell integration

`/storage` is lazy loaded. The four existing primary navigation items remain unchanged; the existing storage mini-card links to Storage Guardian. Desktop uses the Lumen segmented control and full policy editor. Mobile uses the compact rules summary and canonical tabs. Candidate rows use Lumen status/button primitives and render explanatory text from structured reason evidence rather than backend prose.

No destructive action is rendered in the Storage Guardian DOM.

## Verification

Repository CI covers:

```text
config/homepage-actions: python -m compileall .
config/homepage-actions: python -m unittest discover -v
dashboard-app: npm run quality
dashboard-app: npm test -- --watch=false
dashboard-app: npm run build
dashboard-app: npm run build:storybook
dashboard-app: npm run test:smoke
dashboard-app: npm run test:storybook
```

Focused backend tests cover strict request validation, paginated Movie/Episode inventory, physical-file deduplication, remote/placeholder exclusion, malformed/ambiguous fail-closed behavior, hard protections, episode keep-latest semantics, season-zero handling, multi-episode atomicity, deterministic ordering, target-met and insufficient-capacity behavior, path non-disclosure, and the absence of a Storage Guardian deletion route. Playwright covers desktop/mobile layout, explicit-run behavior, target-met/insufficient/degraded states, browser pin persistence, the unchanged four-item primary navigation, and absence of destructive controls.
