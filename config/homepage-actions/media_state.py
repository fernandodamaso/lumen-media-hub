"""Shared cached Jellyfin, Arr, and typed media-state boundary."""

import os
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

import config as settings
from clients.arr import _arr_get
from clients.jellyfin import (
    JELLYFIN_PAGE_SIZE,
    _jellyfin_item_is_playable,
    _jellyfin_items_path,
    jellyfin_get,
)
from clients.jellyseerr import _jellyseerr_get
from shared import _normalize_tmdb_id


_SOURCE_FRESH = "fresh"
_SOURCE_STALE = "stale"
_SOURCE_UNAVAILABLE = "unavailable"
_SAFE_SLUG_LIMIT = 256


@dataclass(frozen=True)
class LibraryExclusionSnapshot:
    """Last known playable Jellyfin identities and refresh health."""

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
        return self.jellyfin_id(item_type, tmdb_id) is not None

    def jellyfin_id(self, item_type, tmdb_id):
        normalized = _normalize_tmdb_id(tmdb_id)
        if not normalized:
            return None
        return (self.tv if item_type == "tv" else self.movie).get(normalized)

    def public(self):
        return {
            "status": self.status,
            "last_successful_refresh_at": self.last_successful_refresh_at,
        }


@dataclass(frozen=True)
class ArrMediaState:
    service: str
    monitored: bool
    title_slug: str | None
    service_href: str | None


@dataclass(frozen=True)
class JellyseerrRequestSnapshot:
    states: dict
    sources: dict

    def get(self, item_type, tmdb_id):
        identity = _typed_identity(item_type, tmdb_id)
        state = self.states.get(identity) if identity else None
        return dict(state) if isinstance(state, dict) else None

    def status(self, item_type, tmdb_id):
        identity = _typed_identity(item_type, tmdb_id)
        return self.sources.get(identity, _SOURCE_UNAVAILABLE)


def _typed_identity(item_type, tmdb_id):
    if isinstance(tmdb_id, bool):
        return None
    normalized = _normalize_tmdb_id(tmdb_id)
    if item_type not in ("movie", "tv") or not normalized:
        return None
    return f"{item_type}:{normalized}"


def _request_identity_parts(identity):
    item_type, _, value = str(identity).partition(":")
    normalized = _normalize_tmdb_id(value)
    if item_type not in ("movie", "tv") or not normalized:
        return None
    return item_type, normalized


@dataclass(frozen=True)
class ArrTrackingSnapshot:
    """Typed Radarr/Sonarr tracking state with per-provider freshness."""

    movie: dict
    tv: dict
    sources: dict

    @classmethod
    def from_maps(cls, *, movie, tv, sources):
        def normalize(values):
            result = {}
            for tmdb_id, row in (values or {}).items():
                normalized = _normalize_tmdb_id(tmdb_id)
                if not normalized:
                    continue
                if isinstance(row, ArrMediaState):
                    result[normalized] = row
                    continue
                if not isinstance(row, dict):
                    continue
                result[normalized] = ArrMediaState(
                    service=row.get("service"),
                    monitored=bool(row.get("monitored")),
                    title_slug=row.get("titleSlug") or row.get("title_slug"),
                    service_href=row.get("serviceHref") or row.get("service_href"),
                )
            return result

        return cls(normalize(movie), normalize(tv), dict(sources or {}))

    def get(self, item_type, tmdb_id):
        normalized = _normalize_tmdb_id(tmdb_id)
        if not normalized:
            return None
        return (self.tv if item_type == "tv" else self.movie).get(normalized)


_TMDB_LIBRARY_CACHE = {
    "expires": 0.0,
    "movie": {},
    "tv": {},
    "status": _SOURCE_UNAVAILABLE,
    "last_successful_refresh_at": None,
}
TMDB_LIBRARY_CACHE_TTL = 90.0
_TMDB_LIBRARY_CACHE_LOCK = threading.Lock()

ARR_TRACKING_CACHE_TTL = 60.0
_ARR_RETRY_TTL = 15.0
_ARR_TRACKING_CACHE = {}
_ARR_TRACKING_CACHE_LOCK = threading.Lock()

JELLYSEERR_REQUEST_CACHE_TTL = 45.0
_JELLYSEERR_REQUEST_RETRY_TTL = 10.0
_JELLYSEERR_REQUEST_CACHE_LIMIT = 512
_JELLYSEERR_REQUEST_CACHE = {}
_JELLYSEERR_REQUEST_CACHE_LOCK = threading.Lock()


def _empty_jellyseerr_request_cache():
    return {
        "expires": 0.0,
        "state": None,
        "status": _SOURCE_UNAVAILABLE,
        "has_success": False,
    }


def _detail_media_type(raw):
    value = raw.get("mediaType") or raw.get("media_type")
    if value is None:
        return None
    value = str(value).lower()
    if value in ("tv", "series"):
        return "tv"
    return "movie" if value == "movie" else None


def _fetch_jellyseerr_request_detail(item_type, tmdb_id):
    raw = _jellyseerr_get(f"/api/v1/{item_type}/{tmdb_id}")
    if not isinstance(raw, dict):
        raise ValueError("invalid Jellyseerr detail")
    media_info = raw.get("mediaInfo") or raw.get("media_info") or {}
    if not isinstance(media_info, dict):
        media_info = {}
    returned_id = _normalize_tmdb_id(
        raw.get("id") or raw.get("tmdbId") or media_info.get("tmdbId")
    )
    if isinstance(
        raw.get("id") or raw.get("tmdbId") or media_info.get("tmdbId"), bool
    ):
        returned_id = None
    returned_type = _detail_media_type(raw)
    if returned_id != tmdb_id or (returned_type is not None and returned_type != item_type):
        raise ValueError("mismatched Jellyseerr detail")
    return raw


def _bounded_request_cache_locked(protected):
    overflow = len(_JELLYSEERR_REQUEST_CACHE) - _JELLYSEERR_REQUEST_CACHE_LIMIT
    if overflow <= 0:
        return
    candidates = sorted(
        (
            (entry.get("expires", 0.0), identity)
            for identity, entry in _JELLYSEERR_REQUEST_CACHE.items()
            if identity not in protected
        )
    )
    for _expires, identity in candidates[:overflow]:
        _JELLYSEERR_REQUEST_CACHE.pop(identity, None)


def get_jellyseerr_request_snapshot(
    identities,
    *,
    force=False,
    fetch=_fetch_jellyseerr_request_detail,
    now_fn=time.monotonic,
):
    """Return typed active-request state with bounded last-good caching."""
    requested = {}
    for value in identities or ():
        if isinstance(value, str):
            parts = _request_identity_parts(value)
        elif isinstance(value, (tuple, list)) and len(value) == 2:
            identity = _typed_identity(value[0], value[1])
            parts = _request_identity_parts(identity) if identity else None
        else:
            parts = None
        if parts:
            requested[f"{parts[0]}:{parts[1]}"] = parts

    now = now_fn()
    pending = []
    with _JELLYSEERR_REQUEST_CACHE_LOCK:
        for identity in requested:
            entry = _JELLYSEERR_REQUEST_CACHE.setdefault(
                identity, _empty_jellyseerr_request_cache()
            )
            if force or now >= entry["expires"]:
                pending.append(identity)

    def refresh(identity):
        item_type, tmdb_id = requested[identity]
        try:
            raw = fetch(item_type, tmdb_id)
            state = jellyseerr_request_state(raw)
            return identity, state, None
        except Exception as error:
            return identity, None, error

    if pending:
        worker_count = min(4, len(pending))
        with ThreadPoolExecutor(
            max_workers=worker_count, thread_name_prefix="jellyseerr-state"
        ) as pool:
            refreshed = list(pool.map(refresh, pending))
        refreshed_at = now_fn()
        with _JELLYSEERR_REQUEST_CACHE_LOCK:
            for identity, state, error in refreshed:
                entry = _JELLYSEERR_REQUEST_CACHE.setdefault(
                    identity, _empty_jellyseerr_request_cache()
                )
                if error is None:
                    entry.update(
                        state=dict(state) if isinstance(state, dict) else None,
                        status=_SOURCE_FRESH,
                        has_success=True,
                        expires=refreshed_at + JELLYSEERR_REQUEST_CACHE_TTL,
                    )
                else:
                    entry["status"] = (
                        _SOURCE_STALE if entry["has_success"] else _SOURCE_UNAVAILABLE
                    )
                    if not entry["has_success"]:
                        entry["state"] = None
                    entry["expires"] = refreshed_at + _JELLYSEERR_REQUEST_RETRY_TTL
            _bounded_request_cache_locked(set(requested))

    with _JELLYSEERR_REQUEST_CACHE_LOCK:
        return JellyseerrRequestSnapshot(
            states={
                identity: dict(entry["state"])
                for identity in requested
                for entry in [_JELLYSEERR_REQUEST_CACHE[identity]]
                if isinstance(entry.get("state"), dict)
            },
            sources={
                identity: _JELLYSEERR_REQUEST_CACHE[identity]["status"]
                for identity in requested
            },
        )

# Compatibility cache used by the Hermes generation context. Its storage and
# fallback policy live here even though Discover retains small wrapper names.
TRACKED_MEDIA_CACHE_TTL = float(os.environ.get("TRACKED_MEDIA_CACHE_TTL", "60"))
_tracked_media_cache = {
    "expires": 0.0,
    "ids": [],
    "errors": [],
    "has_success": False,
}
_tracked_media_cache_lock = threading.Lock()


def _empty_arr_source_cache():
    return {
        "expires": 0.0,
        "items": {},
        "status": _SOURCE_UNAVAILABLE,
        "last_successful_refresh_at": None,
    }


def _ensure_arr_tracking_cache():
    for source in ("radarr", "sonarr"):
        _ARR_TRACKING_CACHE.setdefault(source, _empty_arr_source_cache())


def _safe_http_base(base):
    if not isinstance(base, str) or not base or any(ord(char) < 32 for char in base):
        return None
    try:
        parsed = urllib.parse.urlsplit(base)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            return None
        # Accessing port validates malformed values before the base is returned.
        parsed.port
    except (TypeError, ValueError):
        return None
    path = parsed.path.rstrip("/")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def build_service_href(service, title_slug, base):
    """Build a browser-safe Arr deep link without trusting upstream URLs."""
    if service not in ("radarr", "sonarr"):
        return None
    safe_base = _safe_http_base(base)
    if (
        not safe_base
        or not isinstance(title_slug, str)
        or not title_slug.strip()
        or len(title_slug) > _SAFE_SLUG_LIMIT
        or any(ord(char) < 32 for char in title_slug)
    ):
        return None
    section = "movie" if service == "radarr" else "series"
    encoded_slug = urllib.parse.quote(title_slug.strip(), safe="")
    return f"{safe_base}/{section}/{encoded_slug}"


def _build_jellyfin_href(jellyfin_id):
    safe_base = _safe_http_base(settings.JELLYFIN_EXTERNAL_URL)
    if not safe_base or not isinstance(jellyfin_id, str) or not jellyfin_id:
        return None
    encoded_id = urllib.parse.quote(jellyfin_id, safe="")
    return f"{safe_base}/web/index.html#!/details?id={encoded_id}"


def _provider_tmdb_id(raw):
    providers = raw.get("ProviderIds") or {}
    return _normalize_tmdb_id(providers.get("Tmdb") or providers.get("tmdb"))


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
            jellyfin_id = raw.get("Id")
            if tmdb_id and jellyfin_id and tmdb_id not in mapping:
                mapping[tmdb_id] = jellyfin_id
        total = data.get("TotalRecordCount", start + len(batch))
        start += len(batch)
        if not batch or start >= total:
            break
    return mapping


def get_tmdb_library_maps(*, fetch=_fetch_tmdb_map_for_type, now_fn=time.time, force=False):
    with _TMDB_LIBRARY_CACHE_LOCK:
        if not settings.JELLYFIN_API_KEY:
            _TMDB_LIBRARY_CACHE["status"] = (
                _SOURCE_STALE
                if _TMDB_LIBRARY_CACHE["last_successful_refresh_at"] is not None
                else _SOURCE_UNAVAILABLE
            )
            return {
                "movie": _TMDB_LIBRARY_CACHE["movie"],
                "tv": _TMDB_LIBRARY_CACHE["tv"],
            }

        now = now_fn()
        if not force and now < _TMDB_LIBRARY_CACHE["expires"]:
            return {
                "movie": _TMDB_LIBRARY_CACHE["movie"],
                "tv": _TMDB_LIBRARY_CACHE["tv"],
            }

        previous_movie = _TMDB_LIBRARY_CACHE["movie"]
        previous_tv = _TMDB_LIBRARY_CACHE["tv"]
        try:
            refreshed_movie = fetch("Movie")
            refreshed_tv = fetch("Series")
        except Exception:
            _TMDB_LIBRARY_CACHE["status"] = (
                _SOURCE_STALE
                if _TMDB_LIBRARY_CACHE["last_successful_refresh_at"] is not None
                else _SOURCE_UNAVAILABLE
            )
            return {"movie": previous_movie, "tv": previous_tv}

        _TMDB_LIBRARY_CACHE.update(
            {
                "movie": refreshed_movie,
                "tv": refreshed_tv,
                "expires": now + TMDB_LIBRARY_CACHE_TTL,
                "status": _SOURCE_FRESH,
                "last_successful_refresh_at": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
            }
        )
        return {"movie": refreshed_movie, "tv": refreshed_tv}


def get_library_exclusion_snapshot(*, fetch=_fetch_tmdb_map_for_type, now_fn=time.time, force=False):
    maps = get_tmdb_library_maps(fetch=fetch, now_fn=now_fn, force=force)
    with _TMDB_LIBRARY_CACHE_LOCK:
        return LibraryExclusionSnapshot.from_maps(
            maps.get("movie"),
            maps.get("tv"),
            status=_TMDB_LIBRARY_CACHE["status"],
            last_successful_refresh_at=_TMDB_LIBRARY_CACHE[
                "last_successful_refresh_at"
            ],
        )


def _arr_source_settings(source):
    if source == "radarr":
        return (
            settings.RADARR_URL,
            settings.RADARR_API_KEY,
            settings.RADARR_EXTERNAL_URL,
            "/api/v3/movie",
            "movie",
        )
    return (
        settings.SONARR_URL,
        settings.SONARR_API_KEY,
        settings.SONARR_EXTERNAL_URL,
        "/api/v3/series",
        "tv",
    )


def _normalize_arr_items(source, values, external_base):
    if not isinstance(values, list):
        raise ValueError("invalid Arr catalog")
    result = {}
    for raw in values:
        if not isinstance(raw, dict):
            continue
        tmdb_id = _normalize_tmdb_id(raw.get("tmdbId"))
        if not tmdb_id or tmdb_id in result:
            continue
        slug = raw.get("titleSlug") if isinstance(raw.get("titleSlug"), str) else None
        result[tmdb_id] = ArrMediaState(
            service=source,
            monitored=bool(raw.get("monitored")),
            title_slug=slug,
            service_href=build_service_href(source, slug, external_base),
        )
    return result


def _refresh_arr_source(source, *, force, now):
    base, api_key, external_base, path, _kind = _arr_source_settings(source)
    cached = _ARR_TRACKING_CACHE[source]
    if not force and now < cached["expires"]:
        return
    if not api_key:
        cached["status"] = (
            _SOURCE_STALE
            if cached["last_successful_refresh_at"] is not None
            else _SOURCE_UNAVAILABLE
        )
        cached["expires"] = now + _ARR_RETRY_TTL
        return
    try:
        items = _normalize_arr_items(
            source, _arr_get(base, api_key, path), external_base
        )
    except Exception:
        cached["status"] = (
            _SOURCE_STALE
            if cached["last_successful_refresh_at"] is not None
            else _SOURCE_UNAVAILABLE
        )
        cached["expires"] = now + _ARR_RETRY_TTL
        return
    cached.update(
        {
            "items": items,
            "status": _SOURCE_FRESH,
            "expires": now + ARR_TRACKING_CACHE_TTL,
            "last_successful_refresh_at": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        }
    )


def get_arr_tracking_snapshot(*, force=False):
    now = time.monotonic()
    with _ARR_TRACKING_CACHE_LOCK:
        _ensure_arr_tracking_cache()
        for source in ("radarr", "sonarr"):
            _refresh_arr_source(source, force=force, now=now)
        return ArrTrackingSnapshot(
            movie=dict(_ARR_TRACKING_CACHE["radarr"]["items"]),
            tv=dict(_ARR_TRACKING_CACHE["sonarr"]["items"]),
            sources={
                source: _ARR_TRACKING_CACHE[source]["status"]
                for source in ("radarr", "sonarr")
            },
        )


def build_tracked_media_ids():
    """Return typed identities and sanitized source errors for Discover."""
    ids = set()
    errors = []
    providers = (
        (
            "radarr",
            "movie",
            settings.RADARR_URL,
            settings.RADARR_API_KEY,
            "/api/v3/movie",
        ),
        (
            "sonarr",
            "tv",
            settings.SONARR_URL,
            settings.SONARR_API_KEY,
            "/api/v3/series",
        ),
    )
    for source, item_type, base, api_key, path in providers:
        if not api_key:
            continue
        try:
            rows = _arr_get(base, api_key, path)
            if not isinstance(rows, list):
                raise ValueError("invalid Arr catalog")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                tmdb_id = _normalize_tmdb_id(row.get("tmdbId"))
                if tmdb_id:
                    ids.add(f"{item_type}:{tmdb_id}")
        except Exception:
            errors.append(f"{source}: unavailable")
    return sorted(ids), errors


def safe_arr_error(error):
    value = str(error)
    for provider in ("radarr", "sonarr"):
        if value.startswith(f"{provider}:"):
            return f"{provider}: unavailable"
    return "arr: unavailable"


def get_tracked_media_ids(
    *,
    build=build_tracked_media_ids,
    ttl=TRACKED_MEDIA_CACHE_TTL,
    now_fn=time.monotonic,
    force=False,
):
    """Preserve the last complete typed Arr deny set on partial failures."""
    now = now_fn()
    with _tracked_media_cache_lock:
        if not force and now < _tracked_media_cache["expires"]:
            return (
                list(_tracked_media_cache["ids"]),
                list(_tracked_media_cache["errors"]),
            )
    ids, errors = build()
    errors = [safe_arr_error(error) for error in errors]
    with _tracked_media_cache_lock:
        if errors:
            result = (
                list(_tracked_media_cache["ids"])
                if _tracked_media_cache["has_success"]
                else list(ids)
            )
            if not _tracked_media_cache["has_success"]:
                _tracked_media_cache["ids"] = list(ids)
        else:
            result = list(ids)
            _tracked_media_cache["ids"] = list(ids)
            _tracked_media_cache["has_success"] = True
        _tracked_media_cache["errors"] = list(errors)
        cache_ttl = ttl if not errors else min(ttl, 15.0)
        _tracked_media_cache["expires"] = now_fn() + cache_ttl
        return result, errors


def invalidate_request_state_caches(item_type=None, tmdb_id=None):
    """Expire typed Jellyseerr and relevant Arr request-state caches."""
    identity = _typed_identity(item_type, tmdb_id) if item_type is not None else None
    with _JELLYSEERR_REQUEST_CACHE_LOCK:
        targets = (
            [identity]
            if identity and identity in _JELLYSEERR_REQUEST_CACHE
            else list(_JELLYSEERR_REQUEST_CACHE)
            if item_type is None
            else []
        )
        for key in targets:
            cached = _JELLYSEERR_REQUEST_CACHE[key]
            cached["expires"] = 0.0
            cached["status"] = (
                _SOURCE_STALE if cached["has_success"] else _SOURCE_UNAVAILABLE
            )
    with _ARR_TRACKING_CACHE_LOCK:
        _ensure_arr_tracking_cache()
        sources = (
            ("radarr", "sonarr")
            if item_type is None
            else (("sonarr",) if item_type == "tv" else ("radarr",))
        )
        for source in sources:
            cached = _ARR_TRACKING_CACHE[source]
            cached["expires"] = 0.0
            if cached["last_successful_refresh_at"] is not None:
                cached["status"] = _SOURCE_STALE
    with _tracked_media_cache_lock:
        _tracked_media_cache["expires"] = 0.0


def invalidate_media_state_caches():
    """Expire caches while preserving positive last-good state."""
    with _TMDB_LIBRARY_CACHE_LOCK:
        _TMDB_LIBRARY_CACHE["expires"] = 0.0
        if _TMDB_LIBRARY_CACHE["last_successful_refresh_at"] is not None:
            _TMDB_LIBRARY_CACHE["status"] = _SOURCE_STALE
    invalidate_request_state_caches()


def _normalized_request_status(value):
    if isinstance(value, bool):
        return None
    if value == 1 or (isinstance(value, str) and value.strip().lower() == "pending"):
        return "requested"
    if value == 2 or (
        isinstance(value, str)
        and value.strip().lower() in ("approved", "processing", "partial")
    ):
        return "processing"
    return None


def _positive_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        try:
            normalized = int(value)
        except ValueError:
            return None
        return normalized if normalized > 0 else None
    return None


def jellyseerr_request_state(raw):
    """Normalize only active Jellyseerr request/media states."""
    if not isinstance(raw, dict):
        return None
    media_info = raw.get("mediaInfo") or raw.get("media_info") or {}
    if not isinstance(media_info, dict):
        media_info = {}
    requests = media_info.get("requests") or raw.get("requests") or []
    if not isinstance(requests, list):
        requests = []
    normalized = []
    for request in requests:
        if not isinstance(request, dict):
            continue
        status = _normalized_request_status(request.get("status"))
        if status:
            normalized.append(
                {
                    "status": status,
                    "request_id": _positive_int(request.get("id")),
                }
            )
    # A still-pending request is more useful to the UI than an older approval.
    for wanted in ("requested", "processing"):
        for state in normalized:
            if state["status"] == wanted:
                return state

    media_status = media_info.get("status")
    if media_status in (2, 3, 4) or (
        isinstance(media_status, str)
        and re.sub(r"[^a-z]", "", media_status.lower())
        in ("pending", "processing", "partiallyavailable", "partial")
    ):
        return {"status": "processing", "request_id": None}
    return None


def resolve_media_state(
    item_type,
    tmdb_id,
    *,
    library,
    arr,
    jellyseerr=None,
    jellyseerr_status="fresh",
):
    """Apply positive-first precedence and fail closed for negative state."""
    normalized = _normalize_tmdb_id(tmdb_id)
    base = {"status": "unknown", "service": None, "serviceHref": None}
    if not normalized or item_type not in ("movie", "tv"):
        return base

    jellyfin_id = library.jellyfin_id(item_type, normalized)
    if jellyfin_id:
        return {
            "status": "available",
            "service": "jellyfin",
            "serviceHref": _build_jellyfin_href(jellyfin_id),
            "jellyfinId": jellyfin_id,
        }

    if isinstance(jellyseerr, dict) and jellyseerr.get("status") in (
        "requested",
        "processing",
    ):
        state = {
            "status": jellyseerr["status"],
            "service": None,
            "serviceHref": None,
        }
        request_id = _positive_int(
            jellyseerr.get("request_id") or jellyseerr.get("requestId")
        )
        if request_id:
            state["requestId"] = request_id
        return state

    arr_state = arr.get(item_type, normalized)
    if arr_state:
        return {
            "status": "tracked",
            "service": arr_state.service,
            "serviceHref": arr_state.service_href,
            "monitored": arr_state.monitored,
        }

    relevant_arr = "sonarr" if item_type == "tv" else "radarr"
    if (
        library.status == _SOURCE_FRESH
        and jellyseerr_status == _SOURCE_FRESH
        and arr.sources.get(relevant_arr) == _SOURCE_FRESH
    ):
        base["status"] = "missing"
    return base
