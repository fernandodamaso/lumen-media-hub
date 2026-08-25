# Calendar contract

Upcoming Releases uses the existing `MediaStackApi.listCalendarEvents` boundary in both Demo and Live modes.

## Live route

`GET /api/calendar` is the neutral browser-facing calendar endpoint. Nginx/dev proxy strips the `/api` prefix before forwarding it to `homepage-actions`, where `GET /calendar` combines:

- monitored Sonarr episodes
- monitored Radarr movie releases

The backend fetches both providers concurrently with a bounded provider timeout, merges healthy results, sorts before truncation, and returns source health alongside the events. A single provider failure is a partial success; the route fails completely only when neither provider is usable.

Successful responses use this envelope shape:

```json
{
  "ok": true,
  "generatedAt": "2026-08-25T10:00:00Z",
  "sources": {
    "sonarr": "ok",
    "radarr": "error"
  },
  "events": []
}
```

Source status is one of `ok`, `error`, or `unconfigured`. Error responses expose only stable calendar error text and source status; raw upstream bodies, ARR API keys, and the actions token are never returned to the browser.

## Event identity

Episode events use `kind: "episode"`, a stable `id` in the form `sonarr:episode:<episodeId>`, and include `episodeId` plus `seriesId` when known.

Movie events use `kind: "movie"`, a stable `id` in the form `radarr:movie:<movieId>`, include `movieId`, and include Radarr's `titleSlug` when available. Movie actions prefer that event-specific slug for deep links so duplicate movie titles cannot resolve through a different title-keyed library entry.

When timestamps tie, ordering is deterministic by date, time, kind, title, then stable ID. Event actions are kind-aware: episodes resolve only to Sonarr and movies resolve only to Radarr.

## Compatibility alias

`GET /api/sonarr/calendar` remains a compatibility alias for the combined calendar during migration. New Live clients must use `GET /api/calendar`; do not add new callers to the Sonarr-specific alias.

The right rail exposes distinct Sonarr and Radarr calendar actions instead of treating Sonarr as the universal calendar destination.
