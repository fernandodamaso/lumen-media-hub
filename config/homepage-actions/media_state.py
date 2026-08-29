"""Shared cached Jellyfin, Arr, and typed media-state boundary."""

import os
import re
import threading
import time
import urllib.parse
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


def get_tmdb_library_maps(*, fetch=_fetch_tmdb_map_for_type, now_fn=time.time):
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
        if now < _TMDB_LIBRARY_CACHE["expires"]:
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


def get_library_exclusion_snapshot(*, fetch=_fetch_tmdb_map_for_type, now_fn=time.time):
    maps = get_tmdb_library_maps(fetch=fetch, now_fn=now_fn)
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
):
    """Preserve the last complete typed Arr deny set on partial failures."""
    now = now_fn()
    with _tracked_media_cache_lock:
        if now < _tracked_media_cache["expires"]:
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


def invalidate_media_state_caches():
    """Expire caches while preserving positive last-good state."""
    with _TMDB_LIBRARY_CACHE_LOCK:
        _TMDB_LIBRARY_CACHE["expires"] = 0.0
        if _TMDB_LIBRARY_CACHE["last_successful_refresh_at"] is not None:
            _TMDB_LIBRARY_CACHE["status"] = _SOURCE_STALE
    with _ARR_TRACKING_CACHE_LOCK:
        _ensure_arr_tracking_cache()
        for cached in _ARR_TRACKING_CACHE.values():
            cached["expires"] = 0.0
            if cached["last_successful_refresh_at"] is not None:
                cached["status"] = _SOURCE_STALE
    with _tracked_media_cache_lock:
        _tracked_media_cache["expires"] = 0.0


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
