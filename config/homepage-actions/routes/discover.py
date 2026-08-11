"""Discover / Hermes route handlers."""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

import config as settings
from clients.arr import _add_to_arr_unmonitored, _arr_get
from clients.jellyfin import (
    JELLYFIN_PAGE_SIZE,
    _jellyfin_image_url,
    _jellyfin_item_is_playable,
    _jellyfin_items_path,
    jellyfin_get,
    jellyfin_post,
)
from clients.jellyseerr import _jellyseerr_get, _trakt_get, _trakt_get_page
from clients.trakt import TraktAuthError
from trakt_history import TraktWatchedService, WatchedSnapshot, WatchedSnapshotStore
from http_support import (
    _BodyTooLarge,
    _read_json_body,
    _reject_mutating,
    send_json,
)
from recommendations_store import (
    ITEM_TYPES,
    RecommendationError,
    apply_feedback,
    apply_request,
    media_identity,
    utc_now,
)
from reconciliation import (
    HermesItemNotFound,
    AlreadyReconciled,
    RequestSyncConflict,
    StaleBaseRevision,
    _clear_generation_request,
    _enqueue_request_reconciliation,
    _generation_request_public,
    _pending_request_sync_public,
    _request_hermes_generation,
    run_reconciliation_cycle,
)
from shared import (
    _find_hermes_item,
    _hermes_identity,
    _hermes_items,
    _is_int,
    _normalize_tmdb_id,
)


VALID_FEEDBACK_STATUSES = frozenset({"liked", "disliked", "watched", "skipped"})


@dataclass(frozen=True)
class LibraryExclusionSnapshot:
    """Last known playable Jellyfin identities used by all Discover sources."""

    movie: dict
    tv: dict
    status: str
    last_successful_refresh_at: str | None

    @classmethod
    def from_maps(cls, movie, tv, *, status, last_successful_refresh_at):
        return cls(dict(movie or {}), dict(tv or {}), status, last_successful_refresh_at)

    @property
    def identities(self):
        return {
            f"movie:{normalized}"
            for tmdb_id in self.movie
            for normalized in [_normalize_tmdb_id(tmdb_id)]
            if normalized
        } | {
            f"tv:{normalized}"
            for tmdb_id in self.tv
            for normalized in [_normalize_tmdb_id(tmdb_id)]
            if normalized
        }

    def contains(self, item_type, tmdb_id):
        kind = "tv" if item_type == "tv" else "movie"
        normalized = _normalize_tmdb_id(tmdb_id)
        return bool(normalized and normalized in self._map(kind))

    def jellyfin_id(self, item_type, tmdb_id):
        kind = "tv" if item_type == "tv" else "movie"
        normalized = _normalize_tmdb_id(tmdb_id)
        return self._map(kind).get(normalized) if normalized else None

    def _map(self, kind):
        return self.tv if kind == "tv" else self.movie

    def public(self):
        return {
            "status": self.status,
            "last_successful_refresh_at": self.last_successful_refresh_at,
        }


_TMDB_LIBRARY_CACHE = {
    "expires": 0.0,
    "movie": {},
    "tv": {},
    "status": "unavailable",
    "last_successful_refresh_at": None,
}
_TMDB_LIBRARY_CACHE_TTL = 90.0
_TMDB_LIBRARY_CACHE_LOCK = threading.Lock()
_TRAKT_WATCHED_SERVICE = None
_TRAKT_WATCHED_SERVICE_LOCK = threading.Lock()


def _trakt_watched_snapshot():
    global _TRAKT_WATCHED_SERVICE
    with _TRAKT_WATCHED_SERVICE_LOCK:
        if _TRAKT_WATCHED_SERVICE is None:
            _TRAKT_WATCHED_SERVICE = TraktWatchedService(
                _trakt_get_page,
                store=WatchedSnapshotStore(settings.TRAKT_WATCHED_PATH),
            )
        return _TRAKT_WATCHED_SERVICE.snapshot()


def _filter_watched_items(items, snapshot):
    if snapshot.status == "unavailable":
        return items
    return [item for item in items if not snapshot.contains(item.get("type"), item.get("tmdb_id"))]


def _provider_tmdb_id(raw):
    providers = raw.get("ProviderIds") or {}
    value = providers.get("Tmdb") or providers.get("tmdb")
    return _normalize_tmdb_id(value)


def _fetch_tmdb_map_for_type(item_type):
    mapping = {}
    start = 0
    while True:
        data = jellyfin_get(
            _jellyfin_items_path(),
            {
                "Recursive": "true",
                "IncludeItemTypes": item_type,
                "StartIndex": str(start),
                "Limit": str(JELLYFIN_PAGE_SIZE),
                "Fields": "Path,IsPlaceHolder,ProviderIds",
            },
        )
        batch = data.get("Items", [])
        for raw in batch:
            if not _jellyfin_item_is_playable(raw, item_type):
                continue
            tmdb_id = _provider_tmdb_id(raw)
            jf_id = raw.get("Id")
            if tmdb_id and jf_id and tmdb_id not in mapping:
                mapping[tmdb_id] = jf_id
        total = data.get("TotalRecordCount", start + len(batch))
        start += len(batch)
        if not batch or start >= total:
            break
    return mapping


def _tmdb_library_maps():
    if not settings.JELLYFIN_API_KEY:
        with _TMDB_LIBRARY_CACHE_LOCK:
            has_last_good = _TMDB_LIBRARY_CACHE["last_successful_refresh_at"] is not None
            if has_last_good:
                _TMDB_LIBRARY_CACHE["status"] = "stale"
                return {
                    "movie": _TMDB_LIBRARY_CACHE["movie"],
                    "tv": _TMDB_LIBRARY_CACHE["tv"],
                }
            _TMDB_LIBRARY_CACHE["status"] = "unavailable"
            return {"movie": {}, "tv": {}}
    now = time.time()
    with _TMDB_LIBRARY_CACHE_LOCK:
        if now < _TMDB_LIBRARY_CACHE["expires"]:
            return {
                "movie": _TMDB_LIBRARY_CACHE["movie"],
                "tv": _TMDB_LIBRARY_CACHE["tv"],
            }
        previous_movie_map = _TMDB_LIBRARY_CACHE["movie"]
        previous_tv_map = _TMDB_LIBRARY_CACHE["tv"]
        try:
            refreshed_movie_map = _fetch_tmdb_map_for_type("Movie")
            refreshed_tv_map = _fetch_tmdb_map_for_type("Series")
            _TMDB_LIBRARY_CACHE["movie"] = refreshed_movie_map
            _TMDB_LIBRARY_CACHE["tv"] = refreshed_tv_map
            _TMDB_LIBRARY_CACHE["expires"] = now + _TMDB_LIBRARY_CACHE_TTL
            _TMDB_LIBRARY_CACHE["status"] = "fresh"
            _TMDB_LIBRARY_CACHE["last_successful_refresh_at"] = datetime.now(
                timezone.utc
            ).isoformat(timespec="seconds")
        except Exception:
            _TMDB_LIBRARY_CACHE["status"] = (
                "stale"
                if _TMDB_LIBRARY_CACHE["last_successful_refresh_at"] is not None
                else "unavailable"
            )
            return {"movie": previous_movie_map, "tv": previous_tv_map}
        return {"movie": refreshed_movie_map, "tv": refreshed_tv_map}


def _library_exclusion_snapshot():
    """Return the cached library exclusion set and its refresh health."""
    maps = _tmdb_library_maps()
    with _TMDB_LIBRARY_CACHE_LOCK:
        status = _TMDB_LIBRARY_CACHE["status"]
        refreshed_at = _TMDB_LIBRARY_CACHE["last_successful_refresh_at"]
    return LibraryExclusionSnapshot.from_maps(
        maps.get("movie"),
        maps.get("tv"),
        status=status,
        last_successful_refresh_at=refreshed_at,
    )


# Explicit name for callers that prefer the getter convention.
_get_library_exclusion_snapshot = _library_exclusion_snapshot


def _enrich_hermes_library_flags(items, snapshot=None):
    if not items:
        for item in items:
            item.setdefault("in_library", False)
            item.setdefault("jellyfin_id", None)
        return items
    snapshot = snapshot or _library_exclusion_snapshot()
    for item in items:
        tmdb_id = _normalize_tmdb_id(item.get("tmdb_id"))
        jf_id = snapshot.jellyfin_id(item.get("type"), tmdb_id)
        item["in_library"] = bool(jf_id)
        item["jellyfin_id"] = jf_id
    return items


def _tmdb_poster_url(poster_path):
    if not poster_path or not isinstance(poster_path, str):
        return None
    path = poster_path if poster_path.startswith("/") else f"/{poster_path}"
    return f"https://image.tmdb.org/t/p/w342{path}"


# Poster enrichment (PR 4): bounded Jellyseerr detail lookups behind a TTL
# cache. Successful paths are cached for 24h; misses and transient failures
# for 5 minutes so a brief Jellyseerr outage recovers without a restart.
POSTER_ENRICH_CONCURRENCY = 4
POSTER_CACHE_TTL_SECONDS = 24 * 60 * 60
POSTER_NEGATIVE_TTL_SECONDS = 5 * 60

# (kind, tmdb_id) -> (poster_path_or_None, monotonic expiry)
_poster_path_cache = {}
_poster_path_cache_lock = threading.Lock()


def _now():
    """Clock used for cache expiry; tests monkeypatch this with a fake clock."""
    return time.monotonic()


def _poster_cache_get(key):
    """Return (hit, value); expired entries are evicted lazily."""
    with _poster_path_cache_lock:
        entry = _poster_path_cache.get(key)
        if entry is None:
            return False, None
        value, expiry = entry
        if _now() >= expiry:
            del _poster_path_cache[key]
            return False, None
        return True, value


def _poster_cache_put(key, value, ttl):
    with _poster_path_cache_lock:
        _poster_path_cache[key] = (value, _now() + ttl)


def _fetch_poster_path(kind, tmdb_id):
    """One Jellyseerr detail call; returns the poster path or None. Raises on error."""
    payload = _jellyseerr_get(f"/api/v1/{kind}/{tmdb_id}")
    return payload.get("posterPath") or payload.get("poster_path")


def _lookup_and_cache_poster(kind, tmdb_id):
    """Fetch one poster path and cache it under the matching TTL.

    Returns (path_or_None, found). Never raises: not-found and transient
    failures are cached under the negative TTL, after which the lookup becomes
    eligible for retry.
    """
    try:
        path = _fetch_poster_path(kind, tmdb_id)
    except Exception:
        path = None
    found = isinstance(path, str) and bool(path)
    if not found:
        # Covers not-found, failures, and malformed (non-string) payloads:
        # never cache or persist anything but a real path.
        path = None
    _poster_cache_put(
        (kind, tmdb_id),
        path,
        POSTER_CACHE_TTL_SECONDS if found else POSTER_NEGATIVE_TTL_SECONDS,
    )
    return path, found


def _log_poster_batch(items, hits, fetched, failed, duration, skipped=0, reason=None):
    line = (
        f"[poster-enrich] items={items} hits={hits} fetched={fetched} "
        f"failed={failed} duration={duration:.3f}s"
    )
    if skipped:
        line += f" skipped={skipped}"
    if reason:
        line += f" reason={reason}"
    print(line, flush=True)


def _resolve_poster_paths(requests):
    """Resolve poster paths for a batch of (media_type, tmdb_id) pairs.

    Cache hits need no network call; misses are fetched through a worker pool
    bounded by POSTER_ENRICH_CONCURRENCY. Returns
    {(kind, tmdb_id): path_or_None} for every resolvable request. Never raises:
    on any failure the unresolved keys map to None (no poster).
    """
    resolved = {}
    pending = {}
    hits = 0
    for media_type, tmdb_id in requests:
        tmdb_id = _normalize_tmdb_id(tmdb_id)
        if not tmdb_id:
            continue
        kind = "tv" if media_type == "tv" else "movie"
        key = (kind, tmdb_id)
        if key in resolved or key in pending:
            continue
        hit, value = _poster_cache_get(key)
        if hit:
            resolved[key] = value
            hits += 1
        else:
            pending[key] = kind
    if not pending:
        if resolved:
            _log_poster_batch(len(resolved), hits, 0, 0, 0.0)
        return resolved

    fetched = len(pending)
    failed = 0
    if not settings.JELLYSEERR_ENABLED or not settings.JELLYSEERR_API_KEY:
        for key in pending:
            resolved[key] = None
        reason = "disabled" if not settings.JELLYSEERR_ENABLED else "no-api-key"
        _log_poster_batch(
            hits + fetched, hits, 0, 0, 0.0, skipped=fetched, reason=reason
        )
        return resolved

    started = time.monotonic()

    def _worker(item):
        key, kind = item
        path, found = _lookup_and_cache_poster(kind, key[1])
        return key, path, found

    try:
        with ThreadPoolExecutor(
            max_workers=POSTER_ENRICH_CONCURRENCY,
            thread_name_prefix="poster-enrich",
        ) as pool:
            for key, path, found in pool.map(_worker, pending.items()):
                resolved[key] = path
                if not found:
                    failed += 1
    except Exception as e:
        # Degrade, never fail the caller: unresolved keys get no poster.
        print(f"[poster-enrich] batch aborted: {e}", flush=True)
        for key in pending:
            resolved.setdefault(key, None)
        return resolved
    _log_poster_batch(hits + fetched, hits, fetched, failed, time.monotonic() - started)
    return resolved


def _jellyseerr_poster_path(media_type, tmdb_id):
    """Single cached lookup kept for non-batched callers (Trakt mapping)."""
    tmdb_id = _normalize_tmdb_id(tmdb_id)
    if not tmdb_id or not settings.JELLYSEERR_ENABLED or not settings.JELLYSEERR_API_KEY:
        return None
    kind = "tv" if media_type == "tv" else "movie"
    hit, value = _poster_cache_get((kind, tmdb_id))
    if hit:
        return value
    path, _found = _lookup_and_cache_poster(kind, tmdb_id)
    return path


def _poster_url_for_item(item):
    """Derive a poster URL from data already on the item; no network calls."""
    existing = item.get("poster_url")
    if existing:
        return existing
    jf_id = item.get("jellyfin_id")
    if jf_id:
        return _jellyfin_image_url(jf_id)
    return _tmdb_poster_url(item.get("poster_path"))


def _enrich_hermes_posters(items):
    """Fill poster_url on Hermes items.

    Items that already carry poster_url/poster_path (or a Jellyfin ID) need no
    network call; the remaining misses are resolved in one bounded batch.
    Failures degrade to no-poster items — the frontend recovers on its own.
    """
    pending = []
    for item in items:
        url = _poster_url_for_item(item)
        if url:
            item["poster_url"] = url
        else:
            pending.append(item)
    if not pending:
        return items
    resolved = _resolve_poster_paths(
        [(item.get("type"), item.get("tmdb_id")) for item in pending]
    )
    for item in pending:
        kind = "tv" if item.get("type") == "tv" else "movie"
        key = (kind, _normalize_tmdb_id(item.get("tmdb_id")))
        item["poster_url"] = _tmdb_poster_url(resolved.get(key))
    return items





def _jellyfin_id_for_tmdb(media_type, tmdb_id):
    tmdb_id = _normalize_tmdb_id(tmdb_id)
    if not tmdb_id or not settings.JELLYFIN_API_KEY:
        return None
    bucket = "tv" if media_type == "tv" else "movie"
    maps = _tmdb_library_maps()
    cached = maps.get(bucket, {}).get(tmdb_id)
    if cached:
        return cached
    item_type = "Series" if media_type == "tv" else "Movie"
    provider_key = f"tmdb.{tmdb_id}"
    try:
        data = jellyfin_get(
            _jellyfin_items_path(),
            {
                "Recursive": "true",
                "IncludeItemTypes": item_type,
                "AnyProviderIdEquals": provider_key,
                "Limit": "10",
                "Fields": "Path,IsPlaceHolder",
            },
        )
        for raw in data.get("Items", []):
            if _jellyfin_item_is_playable(raw, item_type):
                return raw.get("Id")
    except Exception:
        return None
    return None


def _find_hermes_collection_id():
    try:
        data = jellyfin_get(
            _jellyfin_items_path(),
            {
                "Recursive": "true",
                "IncludeItemTypes": "BoxSet",
                "SearchTerm": settings.HERMES_COLLECTION_NAME,
                "Limit": "20",
            },
        )
        for item in data.get("Items", []):
            if item.get("Name") == settings.HERMES_COLLECTION_NAME:
                return item.get("Id")
    except Exception:
        return None
    return None


def _collection_item_ids(collection_id):
    try:
        data = jellyfin_get(
            f"/Items/{collection_id}/Children",
            {"Fields": "Path"},
        )
        ids = []
        for item in data.get("Items", []):
            path = item.get("Path") or ""
            if "jellynext-virtual" in path:
                continue
            if item.get("Id"):
                ids.append(item["Id"])
        return ids
    except Exception:
        return []


def sync_hermes_collection():
    if not settings.JELLYFIN_API_KEY:
        raise RuntimeError("JELLYFIN_API_KEY not configured")

    data = settings.RECOMMENDATIONS_STORE.load()

    target_ids = []
    for item in _hermes_items(data):
        if item.get("feedback") in ("disliked", "skipped"):
            continue
        jf_id = item.get("jellyfin_id") if item.get("in_library") else None
        if not jf_id:
            jf_id = _jellyfin_id_for_tmdb(item.get("type"), item.get("tmdb_id"))
        if jf_id:
            target_ids.append(jf_id)

    target_ids = list(dict.fromkeys(target_ids))
    collection_id = _find_hermes_collection_id()

    if not target_ids:
        if collection_id:
            current = _collection_item_ids(collection_id)
            if current:
                jellyfin_post(
                    f"/Collections/{collection_id}/Items",
                    {"ids": ",".join(current)},
                    method="DELETE",
                )
        return {"ok": True, "collectionId": collection_id, "added": 0, "removed": 0, "total": 0}

    if not collection_id:
        created = jellyfin_post(
            "/Collections",
            {"name": settings.HERMES_COLLECTION_NAME, "ids": ",".join(target_ids)},
        )
        collection_id = created.get("Id")
        return {
            "ok": True,
            "collectionId": collection_id,
            "added": len(target_ids),
            "removed": 0,
            "total": len(target_ids),
        }

    current = _collection_item_ids(collection_id)
    to_add = [item_id for item_id in target_ids if item_id not in current]
    to_remove = [item_id for item_id in current if item_id not in target_ids]

    if to_add:
        jellyfin_post(
            f"/Collections/{collection_id}/Items",
            {"ids": ",".join(to_add)},
        )
    if to_remove:
        jellyfin_post(
            f"/Collections/{collection_id}/Items",
            {"ids": ",".join(to_remove)},
            method="DELETE",
        )

    return {
        "ok": True,
        "collectionId": collection_id,
        "added": len(to_add),
        "removed": len(to_remove),
        "total": len(target_ids),
    }


def _sync_hermes_collection_best_effort():
    if not settings.JELLYFIN_API_KEY:
        return None
    try:
        return sync_hermes_collection()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _hermes_item_for_client(item, snapshot=None):
    """Project exclusions for a read without writing the recommendation store."""
    projected = dict(item)
    if projected.get("feedback") is not None:
        projected["active"] = False
    if snapshot and snapshot.contains(projected.get("type"), projected.get("tmdb_id")):
        projected["active"] = False
        projected["in_library"] = True
        projected["jellyfin_id"] = snapshot.jellyfin_id(
            projected.get("type"), projected.get("tmdb_id")
        )
        projected["excluded_reason"] = "in_library"
    return projected


def _filter_library_items(items, snapshot):
    """Filter external cards by typed TMDB identity only."""
    return [
        item for item in items
        if not snapshot.contains(item.get("type"), item.get("tmdb_id"))
    ]


def handle_discover_hermes_get(handler):
    try:
        data = settings.RECOMMENDATIONS_STORE.load()
    except RecommendationError as e:
        send_json(handler, 500, {"ok": False, "error": f"Store load failed: {e}"})
        return
    snapshot = _library_exclusion_snapshot()
    items = [_hermes_item_for_client(item, snapshot) for item in _hermes_items(data)]
    items = _enrich_hermes_posters(_enrich_hermes_library_flags(items, snapshot))
    send_json(
        handler,
        200,
        {
            "ok": True,
            "version": data.get("version", 3),
            "revision": data.get("revision", 0),
            "updated_at": data.get("updated_at", ""),
            "presented_media_ids": data.get("presented_media_ids", []),
            "pending_request_sync": _pending_request_sync_public(),
            "generation_request": _generation_request_public(),
            "context": _hermes_generation_context(data, snapshot),
            "library_exclusion": snapshot.public(),
            "items": items,
        },
    )


def handle_discover_hermes_patch(handler, item_id):
    try:
        body = _read_json_body(handler)
    except _BodyTooLarge:
        send_json(handler, 413, {"ok": False, "error": "Request body too large"})
        return
    except json.JSONDecodeError:
        send_json(handler, 400, {"ok": False, "error": "Invalid JSON body"})
        return

    status = (body.get("status") or "").strip()
    # PATCH writes feedback only. Request lifecycle is owned by
    # POST /discover/request so a feedback call can never fabricate a
    # request_state=requested annotation without a real Jellyseerr request.
    if status not in VALID_FEEDBACK_STATUSES - {"suggested", "requested"}:
        send_json(handler, 400, {"ok": False, "error": "Invalid feedback status"})
        return

    def _apply(doc):
        item = _find_hermes_item(doc, item_id)
        if not item:
            raise HermesItemNotFound()
        # Feedback and request state are independent dimensions: a feedback
        # write never clears request fields, a request write keeps feedback.
        apply_feedback(item, status)
        if "notes" in body:
            item["notes"] = body.get("notes") or ""

    try:
        settings.RECOMMENDATIONS_STORE.update(_apply)
    except HermesItemNotFound:
        send_json(handler, 404, {"ok": False, "error": "Item not found"})
        return
    except RecommendationError as e:
        send_json(handler, 500, {"ok": False, "error": f"Store rejected update: {e}"})
        return

    payload = {"ok": True, "id": item_id, "status": status}
    send_json(handler, 200, payload)


def handle_discover_hermes_post(handler):
    # Retired in PR 2: this unrestricted upsert could create or reactivate
    # items without checking the deny list or holding a base revision, so it
    # bypassed the never-twice invariant. Item creation/activation now happens
    # exclusively through POST /discover/hermes/generations. Feedback and
    # requests still use PATCH /discover/hermes/{id} and POST /discover/request.
    send_json(
        handler,
        410,
        {
            "ok": False,
            "error": "Endpoint retired: direct item upserts are no longer accepted",
            "use": "POST /discover/hermes/generations",
        },
    )


def _validate_generation_candidate(raw, index):
    """Normalize one generation candidate. Returns (candidate, rejection).

    ``candidate`` is a dict with type/title/year/tmdb_id/identity/reason/retain on
    success; ``rejection`` is a machine-readable entry for the response on
    failure. Exactly one of the two is non-None.
    """
    if not isinstance(raw, dict):
        return None, {"index": index, "reason": "invalid_candidate", "detail": "expected object"}
    tmdb_id = raw.get("tmdb_id")
    label = {"index": index}
    if raw.get("type") in ITEM_TYPES and _is_int(tmdb_id) and tmdb_id > 0:
        label["identity"] = media_identity(raw["type"], tmdb_id)
    if _is_int(tmdb_id):
        label["tmdb_id"] = tmdb_id
    errors = []
    if raw.get("type") not in ITEM_TYPES:
        errors.append(f"type must be one of {list(ITEM_TYPES)}")
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("title must be a non-empty string")
    if not _is_int(tmdb_id) or tmdb_id <= 0:
        errors.append("tmdb_id must be a positive integer")
    year = raw.get("year")
    if year is not None and not _is_int(year):
        errors.append("year must be an integer or null")
    reason = raw.get("reason", "")
    if not isinstance(reason, str):
        errors.append("reason must be a string")
    retain = raw.get("retain", False)
    if not isinstance(retain, bool):
        errors.append("retain must be a boolean")
    if errors:
        label.update({"reason": "invalid_candidate", "detail": "; ".join(errors)})
        return None, label
    return (
        {
            "index": index,
            "type": raw["type"],
            "title": title.strip(),
            "year": year,
            "tmdb_id": tmdb_id,
            "reason": reason,
            "retain": retain,
        },
        None,
    )


def _is_untouched_hermes_item(item):
    """True when the user has not given feedback or requested the title."""
    return item.get("feedback") is None and item.get("request_state") is None


def _should_auto_retain_hermes_item(item):
    """True when omission must not rotate the active item to history.

    Only untouched picks (no feedback, no request) are protected. Liked,
    disliked, watched, skipped, and requested actives may rotate when omitted
    so feedbacked titles settle in History.
    """
    return _is_untouched_hermes_item(item)


HERMES_TASTE_CAP = 50
TRACKED_MEDIA_CACHE_TTL = float(os.environ.get("TRACKED_MEDIA_CACHE_TTL", "60"))
_tracked_media_cache = {"expires": 0.0, "ids": []}
_tracked_media_cache_lock = threading.Lock()


def _build_tracked_media_ids():
    """Return sorted movie:/tv: identities currently in Radarr/Sonarr."""
    ids = set()
    errors = []
    if settings.RADARR_API_KEY:
        try:
            for movie in _arr_get(settings.RADARR_URL, settings.RADARR_API_KEY, "/api/v3/movie"):
                tmdb_id = _normalize_tmdb_id(movie.get("tmdbId"))
                if tmdb_id:
                    ids.add(f"movie:{tmdb_id}")
        except Exception as e:
            errors.append(f"radarr: {e}")
    if settings.SONARR_API_KEY:
        try:
            for series in _arr_get(settings.SONARR_URL, settings.SONARR_API_KEY, "/api/v3/series"):
                tmdb_id = _normalize_tmdb_id(series.get("tmdbId"))
                if tmdb_id:
                    ids.add(f"tv:{tmdb_id}")
        except Exception as e:
            errors.append(f"sonarr: {e}")
    return sorted(ids), errors


def _get_tracked_media_ids():
    """Cached Arr tracked identities; soft-fail to empty on errors."""
    now = time.monotonic()
    with _tracked_media_cache_lock:
        if now < _tracked_media_cache["expires"]:
            return list(_tracked_media_cache["ids"]), []
    ids, errors = _build_tracked_media_ids()
    with _tracked_media_cache_lock:
        _tracked_media_cache["ids"] = list(ids)
        # Cache successes longer; on errors keep a short empty cache so polls
        # do not hammer a down Arr, but recover within the TTL window.
        ttl = TRACKED_MEDIA_CACHE_TTL if not errors else min(TRACKED_MEDIA_CACHE_TTL, 15.0)
        _tracked_media_cache["expires"] = time.monotonic() + ttl
        return list(_tracked_media_cache["ids"]), errors


def _in_library_media_ids_from_maps(maps):
    ids = []
    for kind in ("movie", "tv"):
        for tmdb_id in (maps or {}).get(kind, {}):
            normalized = _normalize_tmdb_id(tmdb_id)
            if normalized:
                ids.append(f"{kind}:{normalized}")
    return sorted(set(ids))


def _get_in_library_media_ids():
    """Jellyfin-backed playable identities; soft-fail to empty."""
    if not settings.JELLYFIN_API_KEY:
        return [], []
    try:
        maps = _tmdb_library_maps()
        return _in_library_media_ids_from_maps(maps), []
    except Exception as e:
        return [], [f"jellyfin: {e}"]


def _hermes_required_retain(items):
    """Active identities Hermes must keep (untouched only)."""
    retain = []
    for item in items:
        if not item.get("active"):
            continue
        if not _should_auto_retain_hermes_item(item):
            continue
        identity = item.get("identity") or _hermes_identity(item)
        if identity:
            retain.append(identity)
    return retain


def _hermes_taste_entry(item):
    return {
        "identity": item.get("identity") or _hermes_identity(item),
        "title": item.get("title"),
        "type": item.get("type"),
        "year": item.get("year"),
    }


def _hermes_taste_summary(items, cap=HERMES_TASTE_CAP):
    buckets = {
        "liked": [],
        "disliked": [],
        "skipped": [],
        "watched": [],
    }
    for item in items:
        feedback = item.get("feedback")
        if feedback not in buckets:
            continue
        entry = _hermes_taste_entry(item)
        if len(buckets[feedback]) < cap:
            buckets[feedback].append(entry)
        # Liked also counts as watched for History / taste consumers.
        if feedback == "liked" and len(buckets["watched"]) < cap:
            identity = entry["identity"]
            if not any(existing["identity"] == identity for existing in buckets["watched"]):
                buckets["watched"].append(entry)
    return buckets


def _hermes_exclusion_sets():
    """Live exclude sets for generation commits (fresh enough via caches)."""
    tracked, tracked_errors = _get_tracked_media_ids()
    in_library, library_errors = _get_in_library_media_ids()
    return set(tracked), set(in_library), tracked_errors + library_errors


def _hermes_generation_context(data, snapshot=None):
    """Server-built helpers so Hermes need not curl Arr/Jellyfin itself."""
    items = list(_hermes_items(data))
    tracked, tracked_errors = _get_tracked_media_ids()
    in_library, library_errors = _get_in_library_media_ids()
    snapshot = snapshot or _library_exclusion_snapshot()
    errors = tracked_errors + library_errors
    context = {
        "tracked_media_ids": tracked,
        "in_library_media_ids": in_library,
        "library_exclusion": snapshot.public(),
        "required_retain": _hermes_required_retain(items),
        "taste": _hermes_taste_summary(items),
    }
    if errors:
        context["context_errors"] = errors
    return context


def handle_discover_hermes_generations(handler):
    """Commit one Hermes generation: the only writer of recommendation items.

    Candidates with ``retain: true`` keep an already-active item active; any
    other candidate whose composite identity is already in
    ``presented_media_ids`` is rejected (never-twice). New candidates already in
    Sonarr/Radarr or Jellyfin are rejected as ``already_tracked`` /
    ``already_in_library``. Active items omitted from the batch are rotated
    to history with all feedback/request fields preserved — **except** untouched
    actives, which are auto-retained so Hermes cannot hide titles the user has
    not finished with. Liked/watched/disliked/skipped settle in History.
    The whole commit
    — acceptances, rotations, deny-list appends — is one store transaction,
    and a stale ``base_revision`` aborts with HTTP 409 before any change.
    """
    try:
        body = _read_json_body(handler)
    except _BodyTooLarge:
        send_json(handler, 413, {"ok": False, "error": "Request body too large"})
        return
    except json.JSONDecodeError:
        send_json(handler, 400, {"ok": False, "error": "Invalid JSON body"})
        return
    if not isinstance(body, dict):
        send_json(handler, 400, {"ok": False, "error": "Expected a JSON object body"})
        return

    base_revision = body.get("base_revision")
    if not _is_int(base_revision):
        send_json(handler, 400, {"ok": False, "error": "base_revision must be an integer"})
        return
    raw_candidates = body.get("candidates")
    if not isinstance(raw_candidates, list):
        send_json(handler, 400, {"ok": False, "error": "candidates must be an array"})
        return
    if len(raw_candidates) > 100:
        send_json(
            handler, 400, {"ok": False, "error": "candidates must not exceed 100 items"}
        )
        return

    candidates = []
    rejected = []
    batch_seen = set()
    for index, raw in enumerate(raw_candidates):
        candidate, rejection = _validate_generation_candidate(raw, index)
        if rejection is not None:
            rejected.append(rejection)
            continue
        candidate["identity"] = media_identity(candidate["type"], candidate["tmdb_id"])
        if candidate["identity"] in batch_seen:
            rejected.append(
                {
                    "index": index,
                    "identity": candidate["identity"],
                    "tmdb_id": candidate["tmdb_id"],
                    "reason": "duplicate_in_batch",
                }
            )
            continue
        batch_seen.add(candidate["identity"])
        candidates.append(candidate)

    # Preparation phase: resolve posters for the batch BEFORE the locked
    # commit so the transaction stays short. Successful paths are persisted
    # on newly accepted items; failures leave poster_path unset and become
    # eligible for retry after the negative TTL.
    try:
        candidate_posters = _resolve_poster_paths(
            [(c["type"], c["tmdb_id"]) for c in candidates]
        )
    except Exception as e:
        print(f"[poster-enrich] generation preparation failed: {e}", flush=True)
        candidate_posters = {}

    tracked_set, in_library_set, exclusion_errors = _hermes_exclusion_sets()
    if exclusion_errors:
        print(
            f"[hermes-generations] exclusion context degraded: {exclusion_errors}",
            flush=True,
        )

    result = {}

    def _apply(doc):
        current_revision = doc.get("revision", 0)
        if current_revision != base_revision:
            raise StaleBaseRevision(current_revision)

        presented = doc.setdefault("presented_media_ids", [])
        presented_set = set(presented)
        active_by_identity = {}
        existing_ids = set()
        for item in doc.get("items", []):
            if item.get("source") != "hermes":
                continue
            identity = item.get("identity") or _hermes_identity(item)
            existing_ids.add(identity)
            if item.get("active"):
                active_by_identity[identity] = item

        accepted = []
        retained = []
        touched = set()
        now = utc_now()
        for candidate in candidates:
            tmdb_id = candidate["tmdb_id"]
            identity = candidate["identity"]
            existing = active_by_identity.get(identity)
            if existing is not None:
                if not candidate["retain"]:
                    rejected.append(
                        {
                            "index": candidate["index"],
                            "identity": identity,
                            "tmdb_id": tmdb_id,
                            "reason": "already_active",
                        }
                    )
                    # The item was named in the batch: the rejection means
                    # "no change", not "rotate it out".
                    touched.add(identity)
                    continue
                # Explicit retain: refresh descriptive fields only. Feedback,
                # request state, timestamps and Jellyseerr identifiers are
                # preserved untouched.
                existing["type"] = candidate["type"]
                existing["title"] = candidate["title"]
                if candidate["year"] is not None:
                    existing["year"] = candidate["year"]
                existing["reason"] = candidate["reason"]
                retained.append(identity)
                touched.add(identity)
            elif identity in presented_set or f"legacy:{tmdb_id}" in presented_set or identity in existing_ids:
                # Deny-list check, plus a defensive one: store-produced
                # documents keep both in sync, but a hand-edited file could
                # hold an inactive item row whose ID is missing from
                # presented_media_ids — never accept a duplicate Hermes
                # composite identity. Legacy tombstones conservatively block
                # both movie:<id> and tv:<id>.
                rejected.append(
                    {
                        "index": candidate["index"],
                        "identity": identity,
                        "tmdb_id": tmdb_id,
                        "reason": "already_presented",
                    }
                )
            elif identity in tracked_set:
                rejected.append(
                    {
                        "index": candidate["index"],
                        "identity": identity,
                        "tmdb_id": tmdb_id,
                        "reason": "already_tracked",
                    }
                )
            elif identity in in_library_set:
                rejected.append(
                    {
                        "index": candidate["index"],
                        "identity": identity,
                        "tmdb_id": tmdb_id,
                        "reason": "already_in_library",
                    }
                )
            else:
                item = {
                    "id": f"hermes-{identity.replace(':', '-')}",
                    "identity": identity,
                    "source": "hermes",
                    "type": candidate["type"],
                    "title": candidate["title"],
                    "year": candidate["year"],
                    "tmdb_id": tmdb_id,
                    "reason": candidate["reason"],
                    "active": True,
                    "feedback": None,
                    "feedback_at": None,
                    "request_state": None,
                    "requested_at": None,
                    "jellyseerr_request_id": None,
                    "added_at": now,
                }
                kind = "tv" if candidate["type"] == "tv" else "movie"
                poster_path = candidate_posters.get((kind, tmdb_id))
                if poster_path:
                    # Persisted so warm reads need no Jellyseerr call;
                    # poster_url stays derived, never stored.
                    item["poster_path"] = poster_path
                doc.setdefault("items", []).append(item)
                presented.append(identity)
                presented_set.add(identity)
                accepted.append({"identity": identity, "tmdb_id": tmdb_id, "id": item["id"]})
                touched.add(identity)

        rotated = []
        for item in doc.get("items", []):
            if (
                item.get("source") == "hermes"
                and item.get("active")
                and (item.get("identity") or _hermes_identity(item)) not in touched
            ):
                identity = item.get("identity") or _hermes_identity(item)
                # Hard rule: never rotate untouched actives.
                if _should_auto_retain_hermes_item(item):
                    retained.append(identity)
                    continue
                item["active"] = False
                rotated.append(identity)

        result.update(accepted=accepted, retained=retained, rotated=rotated)

    try:
        committed = settings.RECOMMENDATIONS_STORE.update(_apply)
    except StaleBaseRevision as e:
        send_json(
            handler,
            409,
            {
                "ok": False,
                "error": "stale_base_revision",
                "current_revision": e.current_revision,
            },
        )
        return
    except RecommendationError as e:
        send_json(handler, 500, {"ok": False, "error": f"Store rejected generation: {e}"})
        return

    try:
        _clear_generation_request()
    except RecommendationError as e:
        print(
            f"[discover-hermes] generation committed but failed to clear "
            f"on-demand request: {e}",
            flush=True,
        )

    send_json(
        handler,
        200,
        {
            "ok": True,
            "revision": committed.get("revision"),
            "accepted": result["accepted"],
            "retained": result["retained"],
            "rotated": result["rotated"],
            "rejected": rejected,
        },
    )


def handle_discover_hermes_sync(handler):
    if _reject_mutating(handler):
        return
    try:
        result = sync_hermes_collection()
        send_json(handler, 200, result)
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def handle_discover_hermes_request_more(handler):
    """Queue an on-demand Hermes generation for the next agent run."""
    if _reject_mutating(handler):
        return
    try:
        result = _request_hermes_generation()
    except RecommendationError as e:
        send_json(handler, 500, {"ok": False, "error": str(e)})
        return
    send_json(handler, 200, result)




def _map_jellyseerr_result(raw):
    media_type = (raw.get("mediaType") or raw.get("media_type") or "movie").lower()
    item_type = "tv" if media_type in ("tv", "series") else "movie"
    tmdb_id = _normalize_tmdb_id(
        raw.get("id") or raw.get("tmdbId") or (raw.get("mediaInfo") or {}).get("tmdbId")
    )
    title = raw.get("title") or raw.get("name") or ""
    year = raw.get("releaseDate") or raw.get("firstAirDate") or raw.get("release_date")
    if isinstance(year, str) and len(year) >= 4:
        try:
            year = int(year[:4])
        except ValueError:
            year = None
    overview = raw.get("overview") or ""
    poster_path = raw.get("posterPath") or raw.get("poster_path")
    return {
        "id": f"seerr-{item_type}-{tmdb_id}",
        "source": "jellyseerr",
        "type": item_type,
        "title": title,
        "year": year if isinstance(year, int) else None,
        "tmdb_id": tmdb_id,
        "overview": overview,
        "poster_path": poster_path,
        "poster_url": _tmdb_poster_url(poster_path),
        "rating": raw.get("voteAverage"),
    }


def handle_discover_jellyseerr(handler, query):
    kind = (query.get("kind") or ["trending"])[0]
    paths = {
        "trending": "/api/v1/discover/trending",
        "movies": "/api/v1/discover/movies",
        "tv": "/api/v1/discover/tv",
    }
    path = paths.get(kind, paths["trending"])
    if not settings.JELLYSEERR_ENABLED or not settings.JELLYSEERR_API_KEY:
        send_json(handler, 200, {"ok": True, "enabled": False, "items": []})
        return
    try:
        payload = _jellyseerr_get(path)
        results = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(results, list):
            results = []
        snapshot = _library_exclusion_snapshot()
        items = _filter_library_items(
            [_map_jellyseerr_result(item) for item in results if item], snapshot
        )
        send_json(
            handler,
            200,
            {
                "ok": True,
                "generatedAt": datetime.now().isoformat(timespec="seconds"),
                "library_exclusion": snapshot.public(),
                "items": items,
            },
        )
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})




def _map_trakt_result(raw, item_type):
    if item_type == "shows":
        show = raw if raw.get("title") else raw.get("show") or raw
        ids = show.get("ids") or {}
        year = show.get("year")
        title = show.get("title") or ""
        overview = show.get("overview") or ""
        media_type = "tv"
        images = show.get("images") or raw.get("images") or {}
    else:
        movie = raw if raw.get("title") else raw.get("movie") or raw
        ids = movie.get("ids") or {}
        year = movie.get("year")
        title = movie.get("title") or ""
        overview = movie.get("overview") or ""
        media_type = "movie"
        images = movie.get("images") or raw.get("images") or {}
    tmdb_id = _normalize_tmdb_id(ids.get("tmdb"))
    poster_url = None
    posters = images.get("poster") or []
    if posters:
        # Trakt may return full URLs or paths; normalize to https.
        first = posters[0]
        if isinstance(first, str):
            poster_url = first if first.startswith("http") else f"https://{first.lstrip('/')}"
        elif isinstance(first, dict):
            poster_url = first.get("full") or first.get("thumb") or first.get("url")
    if not poster_url:
        poster_url = _tmdb_poster_url(_jellyseerr_poster_path(media_type, tmdb_id))
    rating = raw.get("rating") or (show.get("rating") if "show" in locals() else movie.get("rating") if "movie" in locals() else None)
    return {
        "id": f"trakt-{media_type}-{tmdb_id}",
        "source": "trakt",
        "type": media_type,
        "title": title,
        "year": year,
        "tmdb_id": tmdb_id,
        "trakt_slug": ids.get("slug"),
        "overview": overview,
        "poster_url": poster_url,
        "rating": rating,
    }


def handle_discover_trakt(handler, query):
    media_type = (query.get("type") or ["movies"])[0]
    if media_type not in ("movies", "shows"):
        media_type = "movies"
    if not settings.TRAKT_CLIENT_ID:
        send_json(handler, 503, {"ok": False, "error": "Trakt OAuth not configured"})
        return
    try:
        results = _trakt_get(
            f"/recommendations/{media_type}?limit=25&ignore_collected=true&ignore_watched=true&extended=full,images"
        )
        watched_snapshot = _trakt_watched_snapshot()
        snapshot = _library_exclusion_snapshot()
        items = _filter_library_items(
            [_map_trakt_result(item, media_type) for item in results if item], snapshot
        )
        items = _filter_watched_items(items, watched_snapshot)
        send_json(
            handler,
            200,
            {
                "ok": True,
                "generatedAt": datetime.now().isoformat(timespec="seconds"),
                "library_exclusion": snapshot.public(),
                "watched_exclusion": watched_snapshot.public(),
                "items": items,
            },
        )
    except TraktAuthError as error:
        send_json(
            handler,
            503,
            {"ok": False, "error": str(error), "code": error.code},
        )
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def handle_discover_request(handler):
    if _reject_mutating(handler):
        return
    try:
        body = _read_json_body(handler)
    except _BodyTooLarge:
        send_json(handler, 413, {"ok": False, "error": "Request body too large"})
        return
    except json.JSONDecodeError:
        send_json(handler, 400, {"ok": False, "error": "Invalid JSON body"})
        return

    if not isinstance(body, dict):
        send_json(handler, 400, {"ok": False, "error": "Expected a JSON object body"})
        return

    media_type = body.get("mediaType")
    media_id = _normalize_tmdb_id(body.get("mediaId"))
    if not media_type or not media_id:
        send_json(handler, 400, {"ok": False, "error": "mediaType and mediaId required"})
        return

    hermes_id = body.get("hermesId")
    if hermes_id:
        try:
            current = settings.RECOMMENDATIONS_STORE.load()
        except RecommendationError as e:
            send_json(handler, 500, {"ok": False, "error": f"Store load failed: {e}"})
            return
        item = _find_hermes_item(current, hermes_id)
        if not item:
            send_json(handler, 404, {"ok": False, "error": "Hermes item not found"})
            return
        expected_type = "tv" if str(media_type).lower() in ("tv", "series") else "movie"
        if item.get("type") != expected_type or item.get("tmdb_id") != media_id:
            send_json(
                handler,
                400,
                {"ok": False, "error": "Hermes item does not match the requested media"},
            )
            return

    try:
        arr_result = _add_to_arr_unmonitored(media_type, media_id)
    except RecommendationError as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})
        return
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})
        return

    arr_id = arr_result.get("arr_id")
    dashboard_state_persisted = True
    reconciliation_queued = False
    if hermes_id:
        def _apply(doc):
            item = _find_hermes_item(doc, hermes_id)
            if not item:
                raise HermesItemNotFound()
            # Request fields only; feedback is preserved. Store the *arr id in
            # jellyseerr_request_id for durable tracing of the add.
            apply_request(item, request_id=arr_id)

        try:
            settings.RECOMMENDATIONS_STORE.update(_apply)
        except Exception as e:
            dashboard_state_persisted = False
            persistence_error = type(e).__name__
            try:
                _enqueue_request_reconciliation(hermes_id, arr_id)
                reconciliation_queued = True
            except Exception as queue_error:
                reconciliation_queued = False
                print(
                    "[discover-request] reconciliation enqueue failed "
                    f"hermes_id={hermes_id!r} "
                    f"arr_id={arr_id!r} "
                    f"error={type(queue_error).__name__}",
                    flush=True,
                )
            print(
                "[discover-request] Arr add succeeded but dashboard state "
                "persistence diverged "
                f"hermes_id={hermes_id!r} "
                f"arr_id={arr_id!r} "
                f"error={persistence_error}",
                flush=True,
            )

    if not dashboard_state_persisted:
        send_json(
            handler,
            200,
            {
                "ok": True,
                "partial_success": True,
                "jellyseerr_request_id": arr_id,
                "arr_id": arr_id,
                "service": arr_result.get("service"),
                "already_added": arr_result.get("already_added"),
                "monitored": arr_result.get("monitored"),
                "dashboard_state_persisted": False,
                "reconciliation_queued": reconciliation_queued,
                "message": (
                    "Added to Sonarr/Radarr; dashboard synchronization failed."
                ),
            },
        )
        return

    service = arr_result.get("service")
    title = arr_result.get("title") or "title"
    already = bool(arr_result.get("already_added"))
    if already:
        message = f"Already in {service}: {title} (left unmonitored / no search)."
    else:
        message = f"Added to {service} unmonitored (no download): {title}."

    send_json(
        handler,
        200,
        {
            "ok": True,
            "jellyseerr_request_id": arr_id,
            "arr_id": arr_id,
            "service": service,
            "already_added": already,
            "monitored": arr_result.get("monitored"),
            "dashboard_state_persisted": True,
            "message": message,
        },
    )


def handle_discover_request_reconcile(handler):
    try:
        send_json(handler, 200, run_reconciliation_cycle())
    except RecommendationError as e:
        send_json(handler, 500, {"ok": False, "error": str(e)})
    except OSError as e:
        send_json(handler, 500, {"ok": False, "error": f"Reconciliation failed: {e}"})
