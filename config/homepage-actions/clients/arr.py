"""Sonarr, Radarr, Prowlarr, and Bazarr HTTP clients."""
import json
import urllib.error
import urllib.parse
import urllib.request

import config as settings
import time
from datetime import datetime, timezone
from recommendations_store import RecommendationError

def _arr_get(base, api_key, path):
    req = urllib.request.Request(f"{base}{path}")
    req.add_header("X-Api-Key", api_key)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=settings.TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _arr_json(base, api_key, path, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{base}{path}", data=data, method=method)
    req.add_header("X-Api-Key", api_key)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=settings.TIMEOUT) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RecommendationError(detail or str(e)) from e


def _build_arr_library():
    series = {}
    movies = {}
    if settings.SONARR_API_KEY:
        try:
            for s in _arr_get(settings.SONARR_URL, settings.SONARR_API_KEY, "/api/v3/series"):
                slug = s.get("titleSlug")
                title = s.get("title")
                if slug and title:
                    series[title.strip().lower()] = slug
        except Exception:
            pass
    if settings.RADARR_API_KEY:
        try:
            for m in _arr_get(settings.RADARR_URL, settings.RADARR_API_KEY, "/api/v3/movie"):
                slug = m.get("titleSlug")
                title = m.get("title")
                if slug and title:
                    movies[title.strip().lower()] = slug
        except Exception:
            pass
    return {"ok": True, "series": series, "movies": movies}


def _get_arr_library():
    now = time.monotonic()
    cached = settings._arr_cache.get("data")
    if cached and now - settings._arr_cache.get("ts", 0) < settings.ARR_CACHE_TTL:
        return cached
    with settings._arr_cache_lock:
        cached = settings._arr_cache.get("data")
        if cached and now - settings._arr_cache.get("ts", 0) < settings.ARR_CACHE_TTL:
            return cached
        data = _build_arr_library()
        settings._arr_cache["data"] = data
        settings._arr_cache["ts"] = time.monotonic()
        return data
def _bazarr_wanted_langs(missing):
    langs = []
    for item in missing or []:
        code = item.get("code2") or item.get("name") or ""
        if code and code not in langs:
            langs.append(code)
    return langs


def _bazarr_wanted_details():
    ep_wanted = {"total": 0, "items": []}
    movie_wanted = {"total": 0, "items": []}
    errors = []

    try:
        ep = _arr_get(
            settings.BAZARR_URL,
            settings.BAZARR_API_KEY,
            f"/api/episodes/wanted?start=0&length={settings.AUTOMATION_PREVIEW_LIMIT}",
        )
        total = ep.get("total")
        if total is None:
            total = ep.get("recordsTotal", 0)
        ep_wanted["total"] = int(total or 0)
        for row in (ep.get("data") or ep.get("records") or [])[: settings.AUTOMATION_PREVIEW_LIMIT]:
            series = row.get("seriesTitle") or row.get("series") or "Unknown"
            ep_num = row.get("episode_number") or ""
            langs = _bazarr_wanted_langs(row.get("missing_subtitles"))
            label = f"{series} {ep_num}".strip()
            if langs:
                label = f"{label} · {', '.join(langs)}"
            ep_wanted["items"].append({"label": label})
    except Exception as e:
        errors.append(f"episodes: {e}")

    try:
        movies = _arr_get(
            settings.BAZARR_URL,
            settings.BAZARR_API_KEY,
            f"/api/movies/wanted?start=0&length={settings.AUTOMATION_PREVIEW_LIMIT}",
        )
        total = movies.get("total")
        if total is None:
            total = movies.get("recordsTotal", 0)
        movie_wanted["total"] = int(total or 0)
        for row in (movies.get("data") or movies.get("records") or [])[: settings.AUTOMATION_PREVIEW_LIMIT]:
            title = row.get("title") or "Unknown"
            langs = _bazarr_wanted_langs(row.get("missing_subtitles"))
            label = title
            if langs:
                label = f"{title} · {', '.join(langs)}"
            movie_wanted["items"].append({"label": label})
    except Exception as e:
        errors.append(f"movies: {e}")

    return ep_wanted, movie_wanted, errors


ACTIVITY_HISTORY_BASE = (
    "/api/v3/history?page=1&pageSize=25&sortKey=date&sortDirection=descending"
)


def _activity_history_path(source):
    if source == "sonarr":
        return f"{ACTIVITY_HISTORY_BASE}&includeSeries=true&includeEpisode=true"
    return f"{ACTIVITY_HISTORY_BASE}&includeMovie=true"

ACTIVITY_EVENT_KINDS = {
    "grabbed": "grabbed",
    "downloadFolderImported": "imported",
    "seriesFolderImported": "imported",
    "movieFolderImported": "imported",
    "episodeFileDeleted": "deleted",
    "movieFileDeleted": "deleted",
    "downloadFailed": "failed",
}


def _activity_quality(record):
    quality = record.get("quality")
    if not isinstance(quality, dict):
        return ""
    name = (quality.get("quality") or {}).get("name")
    return name if isinstance(name, str) else ""


def _map_activity_record(source, record):
    kind = ACTIVITY_EVENT_KINDS.get(record.get("eventType"))
    if not kind:
        return None
    timestamp = record.get("date")
    if not isinstance(timestamp, str) or not timestamp.strip():
        return None
    if source == "sonarr":
        series = record.get("series") or {}
        title = series.get("title") or record.get("sourceTitle") or "Unknown"
        episode = record.get("episode") or {}
        season = episode.get("seasonNumber")
        number = episode.get("episodeNumber")
        code = ""
        if isinstance(season, int) and isinstance(number, int):
            code = f"S{season:02d}E{number:02d}"
        subtitle = " · ".join(part for part in (code, _activity_quality(record)) if part)
        slug = series.get("titleSlug")
        href = f"{settings.SONARR_EXTERNAL_URL}/series/{slug}" if slug else None
    else:
        movie = record.get("movie") or {}
        title = movie.get("title") or record.get("sourceTitle") or "Unknown"
        year = movie.get("year")
        subtitle = " · ".join(
            part
            for part in (str(year) if isinstance(year, int) else "", _activity_quality(record))
            if part
        )
        slug = movie.get("titleSlug")
        href = f"{settings.RADARR_EXTERNAL_URL}/movie/{slug}" if slug else None
    return {
        "id": f"{source}:{record.get('id')}",
        "source": source,
        "kind": kind,
        "title": title,
        "subtitle": subtitle,
        "timestamp": timestamp,
        "href": href,
    }


def _fetch_activity_items(source):
    if source == "sonarr":
        base, api_key = settings.SONARR_URL, settings.SONARR_API_KEY
    else:
        base, api_key = settings.RADARR_URL, settings.RADARR_API_KEY
    data = _arr_get(base, api_key, _activity_history_path(source))
    records = data.get("records") if isinstance(data, dict) else None
    items = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        mapped = _map_activity_record(source, record)
        if mapped:
            items.append(mapped)
    return items


def delete_sonarr_series(arr_id):
    _arr_json(
        settings.SONARR_URL,
        settings.SONARR_API_KEY,
        f"/api/v3/series/{int(arr_id)}?deleteFiles=true&addImportListExclusion=false",
        method="DELETE",
    )


def ignore_sonarr_queue_items(queue_ids):
    """Ignore Sonarr queue items without blocklisting or redownloading them."""
    if not isinstance(queue_ids, list) or not queue_ids:
        raise ValueError("queue_ids must be a non-empty list of positive integers")
    if any(
        isinstance(queue_id, bool) or not isinstance(queue_id, int) or queue_id <= 0
        for queue_id in queue_ids
    ):
        raise ValueError("queue_ids must be a non-empty list of positive integers")

    ids = sorted(set(queue_ids))
    query = urllib.parse.urlencode(
        {
            "removeFromClient": "false",
            "blocklist": "false",
            "skipRedownload": "false",
            "changeCategory": "false",
        }
    )
    return _arr_json(
        settings.SONARR_URL,
        settings.SONARR_API_KEY,
        f"/api/v3/queue/bulk?{query}",
        method="DELETE",
        payload={"ids": ids},
    )


def find_radarr_movies_by_tmdb(tmdb_id):
    matches = []
    for movie in _arr_get(settings.RADARR_URL, settings.RADARR_API_KEY, "/api/v3/movie"):
        if movie.get("tmdbId") == tmdb_id:
            matches.append(movie)
    return matches


def find_sonarr_series_by_tvdb(tvdb_id):
    matches = []
    for series in _arr_get(settings.SONARR_URL, settings.SONARR_API_KEY, "/api/v3/series"):
        if series.get("tvdbId") == tvdb_id:
            matches.append(series)
    return matches


def find_sonarr_series_by_tmdb(tmdb_id):
    matches = []
    for series in _arr_get(settings.SONARR_URL, settings.SONARR_API_KEY, "/api/v3/series"):
        if series.get("tmdbId") == tmdb_id:
            matches.append(series)
    return matches


def fetch_arr_history(base, api_key, entity_param, arr_id):
    """Fetch paged Arr history scoped to one entity.

    Sonarr filters on seriesIds (plural); Radarr on movieIds. Singular params are ignored.
    """
    path = (
        f"/api/v3/history?{entity_param}={int(arr_id)}"
        f"&page=1&pageSize=1000&sortKey=date&sortDirection=descending"
    )
    return _arr_get(base, api_key, path)


def delete_radarr_movie(arr_id):
    _arr_json(
        settings.RADARR_URL,
        settings.RADARR_API_KEY,
        f"/api/v3/movie/{int(arr_id)}?deleteFiles=true&addImportExclusion=false",
        method="DELETE",
    )


def _build_activity_feed():
    """Merge Sonarr + Radarr history; per-source degradation, never raises per-source."""
    sources = {}
    items = []
    for source in ("sonarr", "radarr"):
        configured = settings.SONARR_API_KEY if source == "sonarr" else settings.RADARR_API_KEY
        if not configured:
            sources[source] = "unconfigured"
            continue
        try:
            items.extend(_fetch_activity_items(source))
            sources[source] = "ok"
        except Exception:
            sources[source] = "error"
    items.sort(key=lambda item: item["timestamp"], reverse=True)
    return {
        "ok": any(status == "ok" for status in sources.values()),
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": sources,
        "items": items,
    }
