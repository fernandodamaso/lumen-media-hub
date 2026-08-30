"""Discover / AI Picks route handlers."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import config as settings
from clients.jellyfin import (
    _jellyfin_image_url,
    _jellyfin_item_is_playable,
    _jellyfin_items_path,
    jellyfin_get,
    jellyfin_post,
    jellyfin_post_json,
)
from clients.jellyseerr import _jellyseerr_get, _trakt_get, _trakt_get_page
from clients.trakt import TraktAuthError
import media_state
from media_state import LibraryExclusionSnapshot
from media_requests import (
    HermesIdentityMismatch,
    HermesItemNotFound as RequestAiPickItemNotFound,
    MediaRequestConflict,
    MediaRequestUnavailable,
    MediaRequestUpstreamFailure,
    MediaRequestValidationError,
    request_media,
)
from trakt_history import TraktWatchedService, WatchedSnapshotStore
from http_support import (
    _BodyTooLarge,
    _read_json_body,
    _reject_mutating,
    send_json,
)
from recommendations_store import (
    RecommendationError,
    apply_feedback,
    media_identity,
)
from ai_candidates import build_candidate_snapshot
from ai_generation import AiGenerationCoordinator, public_generation
from trakt_history_sync import (
    apply_watched_feedback,
    cancel_pending_trakt_history_event,
    deliver_trakt_history_for_item,
    public_trakt_history_sync,
)
from reconciliation import (
    AiPickItemNotFound,
    _pending_request_sync_public,
    run_reconciliation_cycle,
)
from shared import (
    _find_ai_picks_item,
    _ai_picks_identity,
    _ai_picks_items,
    _normalize_tmdb_id,
)


VALID_FEEDBACK_STATUSES = frozenset({"liked", "disliked", "watched", "skipped"})


_JELLYSEERR_ACTIVE_REQUEST_PAGE_SIZE = 100
_JELLYSEERR_ACTIVE_REQUEST_MAX_PAGES = 3


def _jellyseerr_active_request_snapshot(identities, *, fetch=_jellyseerr_get):
    """Read active request state with a bounded number of list requests."""
    requested = {
        identity
        for item_type, tmdb_id in identities or ()
        for identity in [media_state._typed_identity(item_type, tmdb_id)]
        if identity
    }
    if not requested:
        return media_state.JellyseerrRequestSnapshot({}, {})

    states = {}
    complete = False
    for page_index in range(_JELLYSEERR_ACTIVE_REQUEST_MAX_PAGES):
        skip = page_index * _JELLYSEERR_ACTIVE_REQUEST_PAGE_SIZE
        payload = fetch(
            "/api/v1/request"
            f"?take={_JELLYSEERR_ACTIVE_REQUEST_PAGE_SIZE}"
            f"&skip={skip}&filter=unavailable&sort=modified&sortDirection=desc"
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ValueError("invalid Jellyseerr request list")
        rows = payload["results"]
        for row in rows:
            if not isinstance(row, dict) or row.get("is4k") is True:
                continue
            media = row.get("media") or {}
            if not isinstance(media, dict):
                media = {}
            identity = media_state._typed_identity(
                row.get("type") or media.get("mediaType"),
                media.get("tmdbId") or row.get("tmdbId"),
            )
            status = media_state._normalized_request_status(row.get("status"))
            if identity not in requested or not status:
                continue
            candidate = {
                "status": status,
                "request_id": media_state._positive_int(row.get("id")),
            }
            current = states.get(identity)
            if current is None or (
                current.get("status") == "processing" and status == "requested"
            ):
                states[identity] = candidate

        if requested.issubset(states):
            complete = True
            break
        page_info = payload.get("pageInfo") or {}
        if not isinstance(page_info, dict):
            page_info = {}
        page_count = media_state._positive_int(page_info.get("pages"))
        if page_count is not None:
            if page_index + 1 >= page_count:
                complete = True
                break
        elif len(rows) < _JELLYSEERR_ACTIVE_REQUEST_PAGE_SIZE:
            complete = True
            break

    return media_state.JellyseerrRequestSnapshot(
        states=states,
        sources={
            identity: "fresh" if complete or identity in states else "unavailable"
            for identity in requested
        },
    )

def _decorate_discover_lifecycle(items, *, library=None):
    identities = [
        (item.get("type"), item.get("tmdb_id"))
        for item in items
        if isinstance(item, dict)
    ]
    if library is None:
        try:
            library = media_state.get_library_exclusion_snapshot()
        except Exception:
            library = media_state.LibraryExclusionSnapshot.from_maps(
                {}, {}, status="unavailable", last_successful_refresh_at=None
            )
    try:
        arr = media_state.get_arr_tracking_snapshot()
    except Exception:
        arr = media_state.ArrTrackingSnapshot.from_maps(
            movie={},
            tv={},
            sources={"radarr": "unavailable", "sonarr": "unavailable"},
        )
    try:
        requests = _jellyseerr_active_request_snapshot(identities)
    except Exception:
        requests = media_state.JellyseerrRequestSnapshot(
            {},
            {
                f"{item_type}:{tmdb_id}": "unavailable"
                for item_type, tmdb_id in identities
                if item_type in ("movie", "tv") and _normalize_tmdb_id(tmdb_id)
            },
        )
    for item in items:
        item_type = item.get("type")
        tmdb_id = item.get("tmdb_id")
        state = media_state.resolve_media_state(
            item_type,
            tmdb_id,
            library=library,
            arr=arr,
            jellyseerr=requests.get(item_type, tmdb_id),
            jellyseerr_status=requests.status(item_type, tmdb_id),
        )
        item.update(
            media_status=state.get("status", "unknown"),
            service=state.get("service"),
            service_href=state.get("serviceHref"),
            request_id=state.get("requestId"),
            monitored=state.get("monitored"),
        )
    return items

# Keep the dashboard response independent from the recommendation-store schema.
# In particular, identity sets and generation context are server-only data.
_AI_PICKS_PUBLIC_ITEM_FIELDS = frozenset(
    {
        "id", "source", "type", "title", "year", "tmdb_id", "reason", "active",
        "feedback", "feedback_at", "request_state", "request_provider", "requested_at",
        "jellyseerr_request_id", "in_library", "excluded_reason", "watched_on_trakt",
        "jellyfin_id", "poster_path", "poster_url", "added_at", "notes", "rating",
        "trakt_history_sync", "media_status", "service", "service_href", "request_id",
        "monitored",
    }
)


_TMDB_LIBRARY_CACHE = media_state._TMDB_LIBRARY_CACHE
_TMDB_LIBRARY_CACHE_TTL = media_state.TMDB_LIBRARY_CACHE_TTL
_TMDB_LIBRARY_CACHE_LOCK = media_state._TMDB_LIBRARY_CACHE_LOCK
_TRAKT_WATCHED_SERVICE = None
_TRAKT_WATCHED_SERVICE_LOCK = threading.Lock()


def invalidate_discover_library_caches():
    """Expire library exclusion caches without discarding the last-good snapshot."""
    media_state.invalidate_media_state_caches()


def _trakt_watched_snapshot(*, force=False):
    global _TRAKT_WATCHED_SERVICE
    with _TRAKT_WATCHED_SERVICE_LOCK:
        if _TRAKT_WATCHED_SERVICE is None:
            _TRAKT_WATCHED_SERVICE = TraktWatchedService(
                _trakt_get_page,
                store=WatchedSnapshotStore(settings.TRAKT_WATCHED_PATH),
            )
        return _TRAKT_WATCHED_SERVICE.snapshot(force=force)


def _parse_refresh_watched_flag(query):
    value = (query.get("refresh_watched") or ["false"])[0]
    return str(value).lower() in ("1", "true", "yes")


def _filter_watched_items(items, snapshot):
    if snapshot.status == "unavailable":
        return items
    return [item for item in items if not snapshot.contains(item.get("type"), item.get("tmdb_id"))]


_provider_tmdb_id = media_state._provider_tmdb_id
_fetch_tmdb_map_for_type = media_state._fetch_tmdb_map_for_type


def _tmdb_library_maps(*, force=False):
    return media_state.get_tmdb_library_maps(
        fetch=_fetch_tmdb_map_for_type,
        now_fn=time.time,
        force=force,
    )


def _library_exclusion_snapshot(*, force=False):
    """Return the cached library exclusion set and its refresh health."""
    return media_state.get_library_exclusion_snapshot(
        fetch=_fetch_tmdb_map_for_type,
        now_fn=time.time,
        force=force,
    )


# Explicit name for callers that prefer the getter convention.
_get_library_exclusion_snapshot = _library_exclusion_snapshot


def _enrich_ai_picks_library_flags(items, snapshot=None):
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
    except Exception as error:
        # Degrade, never fail the caller: unresolved keys get no poster.
        print(
            f"[poster-enrich] batch aborted exception={type(error).__name__}",
            flush=True,
        )
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


def _enrich_ai_picks_posters(items):
    """Fill poster_url on AI Picks items.

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


def _find_collection_id_named(name):
    try:
        data = jellyfin_get(
            _jellyfin_items_path(),
            {
                "Recursive": "true",
                "IncludeItemTypes": "BoxSet",
                "SearchTerm": name,
                "Limit": "20",
            },
        )
        for item in data.get("Items", []):
            if item.get("Name") == name:
                return item.get("Id")
    except Exception:
        return None
    return None


def _ensure_ai_picks_collection_name():
    current_id = _find_collection_id_named(settings.AI_PICKS_COLLECTION_NAME)
    legacy_id = _find_collection_id_named(settings.LEGACY_HERMES_COLLECTION_NAME)
    if current_id and legacy_id:
        print(
            "[ai-picks-collection] both AI Picks and legacy collections exist; using AI Picks",
            flush=True,
        )
        return current_id
    if current_id:
        return current_id
    if not legacy_id:
        return None
    dto = jellyfin_get(f"/Items/{legacy_id}")
    updated = dict(dto)
    updated["Name"] = settings.AI_PICKS_COLLECTION_NAME
    jellyfin_post_json(f"/Items/{legacy_id}", updated)
    return legacy_id


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


def sync_ai_picks_collection():
    if not settings.JELLYFIN_API_KEY:
        raise RuntimeError("JELLYFIN_API_KEY not configured")

    data = settings.RECOMMENDATIONS_STORE.load()
    snapshot = _library_exclusion_snapshot()
    if snapshot.status == "unavailable":
        raise RuntimeError("Jellyfin library snapshot unavailable")

    target_ids = []
    for item in _ai_picks_items(data):
        if item.get("feedback") in ("disliked", "skipped"):
            continue
        jf_id = item.get("jellyfin_id") if item.get("in_library") else None
        if not jf_id:
            jf_id = snapshot.jellyfin_id(item.get("type"), item.get("tmdb_id"))
        if jf_id:
            target_ids.append(jf_id)

    target_ids = list(dict.fromkeys(target_ids))
    collection_id = _ensure_ai_picks_collection_name()

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
            {"name": settings.AI_PICKS_COLLECTION_NAME, "ids": ",".join(target_ids)},
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


def _sync_ai_picks_collection_best_effort():
    if not settings.JELLYFIN_API_KEY:
        return None
    try:
        return sync_ai_picks_collection()
    except Exception:
        return {"ok": False, "error": "AI Picks collection is temporarily unavailable"}


_AI_PICKS_COLLECTION_SYNC_LOCK = threading.Lock()
_AI_PICKS_COLLECTION_SYNC_PENDING = threading.Event()
_AI_PICKS_COLLECTION_SYNC_THREAD = None


def _request_ai_picks_collection_sync():
    """Coalesce best-effort collection syncs without blocking API readiness."""
    global _AI_PICKS_COLLECTION_SYNC_THREAD
    _AI_PICKS_COLLECTION_SYNC_PENDING.set()
    with _AI_PICKS_COLLECTION_SYNC_LOCK:
        thread = _AI_PICKS_COLLECTION_SYNC_THREAD
        if thread is not None and thread.is_alive():
            return False

        def run():
            global _AI_PICKS_COLLECTION_SYNC_THREAD
            try:
                while _AI_PICKS_COLLECTION_SYNC_PENDING.is_set():
                    _AI_PICKS_COLLECTION_SYNC_PENDING.clear()
                    _sync_ai_picks_collection_best_effort()
            finally:
                with _AI_PICKS_COLLECTION_SYNC_LOCK:
                    _AI_PICKS_COLLECTION_SYNC_THREAD = None
                if _AI_PICKS_COLLECTION_SYNC_PENDING.is_set():
                    _request_ai_picks_collection_sync()

        _AI_PICKS_COLLECTION_SYNC_THREAD = threading.Thread(
            target=run,
            name="ai-picks-collection-sync",
            daemon=True,
        )
        _AI_PICKS_COLLECTION_SYNC_THREAD.start()
        return True


def _ai_picks_item_for_client(item, snapshot=None, watched_snapshot=None):
    """Project exclusions for a read without writing the recommendation store."""
    projected = dict(item)
    watched_on_trakt = bool(
        watched_snapshot
        and watched_snapshot.status != "unavailable"
        and watched_snapshot.contains(projected.get("type"), projected.get("tmdb_id"))
    )
    projected["watched_on_trakt"] = watched_on_trakt
    if projected.get("feedback") is not None:
        projected["active"] = False
    if snapshot and snapshot.contains(projected.get("type"), projected.get("tmdb_id")):
        projected["active"] = False
        projected["in_library"] = True
        projected["jellyfin_id"] = snapshot.jellyfin_id(
            projected.get("type"), projected.get("tmdb_id")
        )
        projected["excluded_reason"] = "in_library"
    elif watched_on_trakt:
        projected["active"] = False
        projected["excluded_reason"] = "watched_on_trakt"
    sync = public_trakt_history_sync(item.get("trakt_history_event"))
    if sync:
        projected["trakt_history_sync"] = sync
    return projected


def _ai_picks_public_item(item):
    """Return only fields declared by the dashboard AI Picks item contract."""
    return {key: item[key] for key in _AI_PICKS_PUBLIC_ITEM_FIELDS if key in item}


def _filter_library_items(items, snapshot):
    """Filter external cards by typed TMDB identity only."""
    return [
        item for item in items
        if not snapshot.contains(item.get("type"), item.get("tmdb_id"))
    ]


def handle_discover_ai_picks_get(handler):
    try:
        data = settings.RECOMMENDATIONS_STORE.load()
        snapshot = _library_exclusion_snapshot()
        watched_snapshot = _trakt_watched_snapshot()
        items = [
            _ai_picks_item_for_client(item, snapshot, watched_snapshot)
            for item in _ai_picks_items(data)
        ]
        items = _enrich_ai_picks_posters(_enrich_ai_picks_library_flags(items, snapshot))
        items = _decorate_discover_lifecycle(items, library=snapshot)
        items = [_ai_picks_public_item(item) for item in items]
    except Exception:
        send_json(handler, 500, {"ok": False, "error": "Discover recommendations are temporarily unavailable"})
        return
    send_json(
        handler,
        200,
        {
            "ok": True,
            "pending_request_sync": _pending_request_sync_public(),
            "library_exclusion": snapshot.public(),
            "watched_exclusion": watched_snapshot.public(),
            "generation_enabled": settings.AI_ENABLED,
            "generation": public_generation(data.get("generation")),
            "items": items,
        },
    )


def handle_discover_ai_picks_patch(handler, item_id):
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

    status = (body.get("status") or "").strip()
    # PATCH writes feedback only. Request lifecycle is owned by
    # POST /discover/request so a feedback call can never fabricate a
    # request_state=requested annotation without a real Jellyseerr request.
    if status not in VALID_FEEDBACK_STATUSES - {"suggested", "requested"}:
        send_json(handler, 400, {"ok": False, "error": "Invalid feedback status"})
        return

    confirm_all_aired = body.get("confirm_all_aired") is True

    def _apply(doc):
        item = _find_ai_picks_item(doc, item_id)
        if not item:
            raise AiPickItemNotFound()
        if status == "watched":
            if item.get("type") == "tv" and not confirm_all_aired:
                raise ShowWatchConfirmationRequired()
            apply_watched_feedback(item)
        else:
            cancel_pending_trakt_history_event(item)
            apply_feedback(item, status)
        if "notes" in body:
            item["notes"] = body.get("notes") or ""

    try:
        settings.RECOMMENDATIONS_STORE.update(_apply)
    except ShowWatchConfirmationRequired:
        send_json(
            handler,
            400,
            {"ok": False, "code": "confirmation_required", "error": "Confirmation required"},
        )
        return
    except AiPickItemNotFound:
        send_json(handler, 404, {"ok": False, "error": "Item not found"})
        return
    except Exception:
        send_json(handler, 500, {"ok": False, "error": "Feedback could not be saved"})
        return

    if status in ("disliked", "skipped"):
        _request_ai_picks_collection_sync()

    if status == "watched":
        try:
            deliver_trakt_history_for_item(item_id)
        except Exception:
            pass

    sync_status = None
    try:
        item = _find_ai_picks_item(settings.RECOMMENDATIONS_STORE.load(), item_id)
        sync_status = public_trakt_history_sync(
            item.get("trakt_history_event") if item else None
        )
    except Exception:
        sync_status = {"status": "pending"}

    payload = {"ok": True, "id": item_id, "status": status}
    if sync_status:
        payload["trakt_history_sync"] = sync_status
    send_json(handler, 200, payload)


class ShowWatchConfirmationRequired(Exception):
    """Raised when a show watched action lacks confirm_all_aired."""


def _is_untouched_ai_picks_item(item):
    """True when the user has not given feedback or requested the title."""
    return item.get("feedback") is None and item.get("request_state") is None


def _should_auto_retain_ai_picks_item(item):
    """True when omission must not rotate the active item to history.

    Only untouched picks (no feedback, no request) are protected. Liked,
    disliked, watched, skipped, and requested actives may rotate when omitted
    so feedbacked titles settle in History.
    """
    return _is_untouched_ai_picks_item(item)


AI_PICKS_TASTE_CAP = 50
TRACKED_MEDIA_CACHE_TTL = media_state.TRACKED_MEDIA_CACHE_TTL
_tracked_media_cache = media_state._tracked_media_cache
_tracked_media_cache_lock = media_state._tracked_media_cache_lock


def _build_tracked_media_ids():
    return media_state.build_tracked_media_ids()


def _get_tracked_media_ids(*, force=False):
    return media_state.get_tracked_media_ids(
        build=_build_tracked_media_ids,
        ttl=TRACKED_MEDIA_CACHE_TTL,
        now_fn=time.monotonic,
        force=force,
    )


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
    except Exception:
        return [], ["jellyfin: unavailable"]


def _safe_arr_error(error):
    return media_state.safe_arr_error(error)


def _ai_picks_required_retain(
    items, *, excluded_tracked=None, excluded_library=None, excluded_watched=None
):
    """Complete generation candidates AI Picks must keep."""
    excluded = (
        set(excluded_tracked or ())
        | set(excluded_library or ())
        | set(excluded_watched or ())
    )
    retain = {}
    for item in items:
        if not item.get("active"):
            continue
        if not _should_auto_retain_ai_picks_item(item):
            continue
        identity = item.get("identity") or _ai_picks_identity(item)
        if identity and identity not in excluded:
            retain[identity] = {
                "type": item["type"],
                "title": item["title"],
                "year": item.get("year"),
                "tmdb_id": item["tmdb_id"],
                "reason": item.get("reason", ""),
                "retain": True,
            }
    return [retain[identity] for identity in sorted(retain)]


def _ai_picks_taste_entry(item):
    return {
        "identity": item.get("identity") or _ai_picks_identity(item),
        "title": item.get("title"),
        "type": item.get("type"),
        "year": item.get("year"),
    }


def _ai_picks_taste_summary(items, cap=AI_PICKS_TASTE_CAP):
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
        entry = _ai_picks_taste_entry(item)
        if len(buckets[feedback]) < cap:
            buckets[feedback].append(entry)
        # Liked also counts as watched for History / taste consumers.
        if feedback == "liked" and len(buckets["watched"]) < cap:
            identity = entry["identity"]
            if not any(existing["identity"] == identity for existing in buckets["watched"]):
                buckets["watched"].append(entry)
    return buckets


def _ai_picks_generation_context(data, snapshot=None, watched_snapshot=None, *, force=False):
    """Server-built helpers so AI Picks need not curl Arr/Jellyfin itself."""
    items = list(_ai_picks_items(data))
    tracked, tracked_errors = _get_tracked_media_ids(force=force)
    snapshot = snapshot or _library_exclusion_snapshot(force=force)
    in_library = _in_library_media_ids_from_maps(
        {"movie": snapshot.movie, "tv": snapshot.tv}
    )
    watched_snapshot = watched_snapshot or _trakt_watched_snapshot(force=force)
    watched = (
        sorted(set(watched_snapshot.identities))
        if watched_snapshot.status != "unavailable"
        else []
    )
    errors = [_safe_arr_error(error) for error in tracked_errors]
    if snapshot.status == "unavailable":
        errors.append("jellyfin: unavailable")
    if watched_snapshot.status == "unavailable":
        errors.append("trakt_watched: unavailable")
    context = {
        "tracked_media_ids": sorted(set(tracked)),
        "in_library_media_ids": sorted(set(in_library)),
        "watched_media_ids": watched,
        "library_exclusion": snapshot.public(),
        "required_retain": _ai_picks_required_retain(
            items,
            excluded_tracked=tracked,
            excluded_library=in_library,
            excluded_watched=watched,
        ),
        "taste": _ai_picks_taste_summary(items),
    }
    if errors:
        context["context_errors"] = errors
    return context


def handle_discover_ai_picks_request_more(handler):
    """Queue an on-demand AI Picks generation for the internal worker."""
    if _reject_mutating(handler):
        return
    if not settings.AI_ENABLED:
        send_json(handler, 409, {"ok": False, "error": "AI generation is disabled"})
        return
    try:
        result = _generation_coordinator().queue(
            "on_demand", settings.AI_PICKS_ON_DEMAND_COUNT
        )
    except Exception:
        send_json(handler, 500, {"ok": False, "error": "Generation request could not be queued"})
        return
    send_json(handler, 200, dict(result, ok=True))




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
        watched_snapshot = _trakt_watched_snapshot()
        items = _filter_watched_items(items, watched_snapshot)
        items = _decorate_discover_lifecycle(items, library=snapshot)
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
    except Exception:
        send_json(handler, 502, {"ok": False, "error": "Jellyseerr is temporarily unavailable"})




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
        watched_snapshot = _trakt_watched_snapshot(force=_parse_refresh_watched_flag(query))
        snapshot = _library_exclusion_snapshot()
        items = _filter_library_items(
            [_map_trakt_result(item, media_type) for item in results if item], snapshot
        )
        items = _filter_watched_items(items, watched_snapshot)
        items = _decorate_discover_lifecycle(items, library=snapshot)
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
            {"ok": False, "error": "Trakt reconnect required", "code": "reconnect_required"},
        )
    except Exception:
        send_json(handler, 502, {"ok": False, "error": "Trakt temporarily unavailable"})


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
    try:
        result = request_media(body)
    except MediaRequestValidationError as error:
        send_json(handler, 400, {"ok": False, "error": str(error)})
        return
    except RequestAiPickItemNotFound:
        send_json(handler, 404, {"ok": False, "error": "AI Picks item not found"})
        return
    except HermesIdentityMismatch:
        send_json(
            handler,
            400,
            {"ok": False, "error": "AI Picks item does not match the requested media"},
        )
        return
    except MediaRequestConflict:
        send_json(handler, 409, {"ok": False, "error": "This title is already managed"})
        return
    except MediaRequestUnavailable:
        send_json(
            handler,
            503,
            {"ok": False, "error": "Media status is temporarily unavailable"},
        )
        return
    except MediaRequestUpstreamFailure:
        send_json(
            handler,
            502,
            {"ok": False, "error": "Jellyseerr could not accept this request"},
        )
        return
    except Exception:
        send_json(
            handler,
            502,
            {"ok": False, "error": "Jellyseerr could not accept this request"},
        )
        return
    send_json(handler, 200, result)



def handle_discover_request_reconcile(handler):
    try:
        send_json(handler, 200, run_reconciliation_cycle())
    except Exception:
        send_json(handler, 500, {"ok": False, "error": "Request reconciliation is temporarily unavailable"})


_AI_GENERATION_COORDINATOR = None
_AI_GENERATION_COORDINATOR_LOCK = threading.Lock()


def _candidate_signal(items, signal):
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        candidate = dict(item)
        candidate["signals"] = [signal]
        result.append(candidate)
    return result


def _trakt_candidate_source(media_type):
    raw = _trakt_get(
        f"/recommendations/{media_type}?limit=25&ignore_collected=true&ignore_watched=true&extended=full,images"
    )
    return _candidate_signal(
        [_map_trakt_result(item, media_type) for item in raw if item], "trakt"
    )


def _jellyseerr_candidate_source(kind):
    if not settings.JELLYSEERR_ENABLED or not settings.JELLYSEERR_API_KEY:
        raise RuntimeError("jellyseerr unavailable")
    payload = _jellyseerr_get(f"/api/v1/discover/{kind}")
    raw = payload.get("results") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        raise RuntimeError("jellyseerr invalid response")
    return _candidate_signal(
        [_map_jellyseerr_result(item) for item in raw if item], "jellyseerr"
    )


def _candidate_exclusions(doc, *, force=False):
    context = _ai_picks_generation_context(doc, force=force)
    return {
        "tracked": context["tracked_media_ids"],
        "in_library": context["in_library_media_ids"],
        "watched": context["watched_media_ids"],
        "errors": context.get("context_errors", []),
        "required_retain": [
            media_identity(item["type"], item["tmdb_id"])
            for item in context["required_retain"]
        ],
        "taste": context["taste"],
    }


def effective_ai_picks_active_count(doc):
    """Count active picks after authoritative tracked/library/watched exclusions."""
    context = _ai_picks_generation_context(doc)
    if context.get("context_errors"):
        raise RuntimeError("authoritative exclusion snapshot unavailable")
    denied = set(context["tracked_media_ids"])
    denied.update(context["in_library_media_ids"])
    denied.update(context["watched_media_ids"])
    return sum(
        1
        for item in _ai_picks_items(doc)
        if item.get("active") and _ai_picks_identity(item) not in denied
    )


def _build_ai_candidate_snapshot(doc):
    return build_candidate_snapshot(
        doc,
        sources=(
            lambda: _trakt_candidate_source("movies"),
            lambda: _trakt_candidate_source("shows"),
            lambda: _jellyseerr_candidate_source("movies"),
            lambda: _jellyseerr_candidate_source("tv"),
        ),
        exclusions=_candidate_exclusions,
        cap=100,
    )


def _generation_coordinator():
    global _AI_GENERATION_COORDINATOR
    with _AI_GENERATION_COORDINATOR_LOCK:
        if _AI_GENERATION_COORDINATOR is None:
            _AI_GENERATION_COORDINATOR = AiGenerationCoordinator(
                settings.RECOMMENDATIONS_STORE,
                _build_ai_candidate_snapshot,
                commit_exclusions=lambda doc: _candidate_exclusions(doc, force=True),
                lease_seconds=settings.AI_PICKS_LEASE_SECONDS,
            )
        return _AI_GENERATION_COORDINATOR


def _read_worker_body(handler):
    try:
        body = _read_json_body(handler)
    except _BodyTooLarge:
        send_json(handler, 413, {"ok": False, "error": "Request body too large"})
        return None
    except json.JSONDecodeError:
        send_json(handler, 400, {"ok": False, "error": "Invalid JSON body"})
        return None
    if not isinstance(body, dict):
        send_json(handler, 400, {"ok": False, "error": "Expected a JSON object body"})
        return None
    return body


def handle_ai_picks_job_claim(handler):
    if not settings.AI_ENABLED:
        send_json(handler, 200, {"ok": True, "job": None})
        return
    coordinator = _generation_coordinator()
    coordinator.expire_stale()
    send_json(handler, 200, {"ok": True, "job": coordinator.claim()})


def handle_ai_picks_job_complete(handler, job_id):
    body = _read_worker_body(handler)
    if body is None:
        return
    lease = handler.headers.get("X-AI-Lease-Token") or body.get("lease_token")
    result = _generation_coordinator().complete(job_id, lease, body.get("picks"))
    if result.get("ok"):
        result["collection"] = _sync_ai_picks_collection_best_effort()
    send_json(handler, 200 if result.get("ok") else 409, result)


def handle_ai_picks_job_fail(handler, job_id):
    body = _read_worker_body(handler)
    if body is None:
        return
    lease = handler.headers.get("X-AI-Lease-Token") or body.get("lease_token")
    result = _generation_coordinator().fail(job_id, lease, body.get("code"))
    send_json(handler, 200 if result.get("ok") else 409, result)
