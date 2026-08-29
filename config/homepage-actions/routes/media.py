"""Read-only catalog search and TV season route handlers."""

import re
import urllib.parse
from datetime import date

import config as settings
from clients.jellyseerr import _jellyseerr_get
from http_support import send_json
from media_state import (
    ArrTrackingSnapshot,
    LibraryExclusionSnapshot,
    get_arr_tracking_snapshot,
    get_library_exclusion_snapshot,
    jellyseerr_request_state,
    resolve_media_state,
)
_TMDB_ID_RE = re.compile(r"^[1-9][0-9]*$")


def _search_error(handler):
    send_json(
        handler,
        200,
        {
            "ok": False,
            "availability": "unavailable",
            "sources": {"jellyseerr": "unavailable"},
            "items": [],
            "error": "Media search is temporarily unavailable",
        },
    )


def _validated_query(query):
    values = query.get("q") if isinstance(query, dict) else None
    if not isinstance(values, list) or len(values) != 1:
        return None
    value = values[0]
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if 2 <= len(value) <= 100 else None


def _safe_text(value, default=""):
    return value if isinstance(value, str) else default


def _year_from_result(raw):
    value = (
        raw.get("releaseDate")
        or raw.get("firstAirDate")
        or raw.get("release_date")
        or raw.get("first_air_date")
    )
    if isinstance(value, int) and not isinstance(value, bool):
        return value if 0 < value <= 9999 else None
    if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
        year = int(value[:4])
        return year if year > 0 else None
    return None


def _poster_url(value):
    if not isinstance(value, str) or not value.startswith("/") or value.startswith("//"):
        return None
    if (
        ".." in value
        or "\\" in value
        or "?" in value
        or "#" in value
        or any(ord(char) < 32 for char in value)
    ):
        return None
    return f"https://image.tmdb.org/t/p/w342{value}"


def _media_type(raw):
    value = raw.get("mediaType") or raw.get("media_type")
    if not isinstance(value, str):
        return None
    value = value.lower()
    if value == "movie":
        return "movie"
    if value in ("tv", "series"):
        return "tv"
    return None


def _catalog_item(raw, *, library, arr):
    if not isinstance(raw, dict):
        return None
    item_type = _media_type(raw)
    if not item_type:
        return None
    media_info = raw.get("mediaInfo") or raw.get("media_info") or {}
    if not isinstance(media_info, dict):
        media_info = {}
    tmdb_id = _strict_positive_int(
        raw.get("id") or raw.get("tmdbId") or media_info.get("tmdbId")
    )
    if not tmdb_id:
        return None
    item = {
        "identity": f"{item_type}:{tmdb_id}",
        "type": item_type,
        "tmdbId": tmdb_id,
        "title": _safe_text(raw.get("title") or raw.get("name")),
        "year": _year_from_result(raw),
        "overview": _safe_text(raw.get("overview")),
        "posterUrl": _poster_url(raw.get("posterPath") or raw.get("poster_path")),
    }
    item.update(
        resolve_media_state(
            item_type,
            tmdb_id,
            library=library,
            arr=arr,
            jellyseerr=jellyseerr_request_state(raw),
            jellyseerr_status="fresh",
        )
    )
    return item


def _unavailable_library_snapshot():
    return LibraryExclusionSnapshot.from_maps(
        {}, {}, status="unavailable", last_successful_refresh_at=None
    )


def _unavailable_arr_snapshot():
    return ArrTrackingSnapshot.from_maps(
        movie={},
        tv={},
        sources={"radarr": "unavailable", "sonarr": "unavailable"},
    )


def handle_media_search(handler, query):
    search_query = _validated_query(query)
    if search_query is None:
        send_json(
            handler,
            400,
            {
                "ok": False,
                "error": "Search query must contain 2 to 100 characters",
            },
        )
        return
    if not settings.JELLYSEERR_ENABLED or not settings.JELLYSEERR_API_KEY:
        send_json(
            handler,
            200,
            {
                "ok": True,
                "availability": "disabled",
                "sources": {"jellyseerr": "disabled"},
                "items": [],
            },
        )
        return

    path = "/api/v1/search?" + urllib.parse.urlencode(
        {"query": search_query, "page": 1},
        quote_via=urllib.parse.quote,
    )
    try:
        payload = _jellyseerr_get(path)
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ValueError("invalid search response")
    except Exception:
        _search_error(handler)
        return

    try:
        library = get_library_exclusion_snapshot()
    except Exception:
        library = _unavailable_library_snapshot()
    try:
        arr = get_arr_tracking_snapshot()
    except Exception:
        arr = _unavailable_arr_snapshot()

    items = [
        item
        for raw in payload["results"]
        for item in [_catalog_item(raw, library=library, arr=arr)]
        if item is not None
    ]
    send_json(
        handler,
        200,
        {
            "ok": True,
            "availability": "available",
            "sources": {
                "jellyseerr": "fresh",
                "jellyfin": library.status,
                "radarr": arr.sources.get("radarr", "unavailable"),
                "sonarr": arr.sources.get("sonarr", "unavailable"),
            },
            "items": items,
        },
    )


def _validated_tmdb_id(value):
    if not isinstance(value, str) or not _TMDB_ID_RE.fullmatch(value):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _strict_positive_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _map_seasons(raw):
    seasons = {}
    values = raw.get("seasons") if isinstance(raw, dict) else None
    for value in values if isinstance(values, list) else []:
        if not isinstance(value, dict):
            continue
        number = value.get("seasonNumber")
        if isinstance(number, bool) or not isinstance(number, int) or number < 0:
            continue
        episode_count = value.get("episodeCount")
        if (
            isinstance(episode_count, bool)
            or not isinstance(episode_count, int)
            or episode_count < 0
        ):
            episode_count = 0
        air_date = value.get("airDate")
        if isinstance(air_date, str):
            try:
                date.fromisoformat(air_date)
            except ValueError:
                air_date = None
        else:
            air_date = None
        seasons.setdefault(
            number,
            {
                "seasonNumber": number,
                "name": _safe_text(value.get("name"), f"Season {number}"),
                "episodeCount": episode_count,
                "airDate": air_date,
            },
        )
    return [seasons[number] for number in sorted(seasons)]


def handle_media_tv_seasons(handler, tmdb_id_value):
    tmdb_id = _validated_tmdb_id(tmdb_id_value)
    if tmdb_id is None:
        send_json(
            handler,
            400,
            {"ok": False, "error": "TMDB id must be a positive integer"},
        )
        return
    if not settings.JELLYSEERR_ENABLED or not settings.JELLYSEERR_API_KEY:
        send_json(
            handler,
            503,
            {"ok": False, "error": "TV seasons are unavailable"},
        )
        return
    try:
        payload = _jellyseerr_get(f"/api/v1/tv/{tmdb_id}")
        if not isinstance(payload, dict):
            raise ValueError("invalid TV response")
    except Exception:
        send_json(
            handler,
            502,
            {"ok": False, "error": "TV seasons are temporarily unavailable"},
        )
        return
    send_json(
        handler,
        200,
        {
            "ok": True,
            "tmdbId": tmdb_id,
            "title": _safe_text(payload.get("name") or payload.get("title")),
            "seasons": _map_seasons(payload),
        },
    )
