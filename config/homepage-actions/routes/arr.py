"""Sonarr/Radarr library and calendar route handlers."""
import threading
import time
from datetime import date, datetime, timedelta

import config as settings
from clients.arr import _arr_get
from http_support import send_json


def _arr_slug_map(items):
    entries = []
    title_counts = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        slug = item.get("titleSlug")
        title = item.get("title")
        if not isinstance(slug, str) or not slug.strip() or not isinstance(title, str) or not title.strip():
            continue
        key = title.strip().lower()
        year = item.get("year")
        normalized_year = year if isinstance(year, int) and not isinstance(year, bool) and year > 0 else None
        entries.append((key, slug.strip(), normalized_year))
        title_counts[key] = title_counts.get(key, 0) + 1

    result = {}
    for key, slug, year in entries:
        if title_counts[key] == 1:
            result[key] = slug
        if year is not None:
            result[f"{key}::{year}"] = slug
    return result


def _build_arr_library():
    series = {}
    movies = {}
    if settings.SONARR_API_KEY:
        try:
            series = _arr_slug_map(
                _arr_get(settings.SONARR_URL, settings.SONARR_API_KEY, "/api/v3/series")
            )
        except Exception:
            pass
    if settings.RADARR_API_KEY:
        try:
            movies = _arr_slug_map(
                _arr_get(settings.RADARR_URL, settings.RADARR_API_KEY, "/api/v3/movie")
            )
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


def handle_arr_library(handler):
    try:
        send_json(handler, 200, _get_arr_library())
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def _get_sonarr_missing_count():
    if not settings.SONARR_API_KEY:
        return {"ok": False, "error": "SONARR_API_KEY not configured"}
    data = _arr_get(
        settings.SONARR_URL,
        settings.SONARR_API_KEY,
        "/api/v3/wanted/missing?page=1&pageSize=1",
    )
    return {"ok": True, "count": int(data.get("totalRecords", 0))}


def _get_sonarr_missing_cached():
    now = time.monotonic()
    cached = settings._arr_cache.get("missing")
    if cached and now - settings._arr_cache.get("missing_ts", 0) < settings.ARR_CACHE_TTL:
        return cached
    with settings._arr_cache_lock:
        cached = settings._arr_cache.get("missing")
        if cached and now - settings._arr_cache.get("missing_ts", 0) < settings.ARR_CACHE_TTL:
            return cached
        data = _get_sonarr_missing_count()
        settings._arr_cache["missing"] = data
        settings._arr_cache["missing_ts"] = time.monotonic()
        return data


def handle_sonarr_missing_count(handler):
    try:
        send_json(handler, 200, _get_sonarr_missing_cached())
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def _get_sonarr_series_count():
    if not settings.SONARR_API_KEY:
        return {"ok": False, "error": "SONARR_API_KEY not configured"}
    series = _arr_get(settings.SONARR_URL, settings.SONARR_API_KEY, "/api/v3/series")
    monitored = sum(1 for s in series if s.get("monitored"))
    return {"ok": True, "count": int(monitored)}


def _get_sonarr_series_cached():
    now = time.monotonic()
    cached = settings._arr_cache.get("series_count")
    if cached and now - settings._arr_cache.get("series_count_ts", 0) < settings.ARR_CACHE_TTL:
        return cached
    with settings._arr_cache_lock:
        cached = settings._arr_cache.get("series_count")
        if cached and now - settings._arr_cache.get("series_count_ts", 0) < settings.ARR_CACHE_TTL:
            return cached
        data = _get_sonarr_series_count()
        settings._arr_cache["series_count"] = data
        settings._arr_cache["series_count_ts"] = time.monotonic()
        return data


def handle_sonarr_series_count(handler):
    try:
        send_json(handler, 200, _get_sonarr_series_cached())
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def _episode_label(ep):
    season = ep.get("seasonNumber")
    number = ep.get("episodeNumber")
    if season is None or number is None:
        return ""
    return f"S{int(season)} E{int(number)}"


def _format_calendar_date(air_date):
    if not air_date:
        return ""
    try:
        if "T" in air_date:
            dt = datetime.fromisoformat(air_date.replace("Z", "+00:00"))
            return dt.strftime("%b %d")
        d = date.fromisoformat(air_date[:10])
        return d.strftime("%b %d")
    except Exception:
        return air_date[:10]


def _build_sonarr_calendar():
    if not settings.SONARR_API_KEY:
        return {"ok": False, "error": "SONARR_API_KEY not configured", "events": []}

    start = date.today()
    end = start + timedelta(days=settings.CALENDAR_DAYS)
    path = (
        f"/api/v3/calendar?start={start.isoformat()}&end={end.isoformat()}"
        "&includeSeries=true&unmonitored=false"
    )
    episodes = _arr_get(settings.SONARR_URL, settings.SONARR_API_KEY, path)
    events = []
    for ep in episodes:
        series = ep.get("series") or {}
        title = series.get("title") or ep.get("title") or "Unknown"
        air = ep.get("airDateUtc") or ep.get("airDate") or ""
        events.append(
            {
                "title": title,
                "additional": _episode_label(ep),
                "date": _format_calendar_date(air),
                "airDate": air,
                "seriesId": series.get("id") or ep.get("seriesId"),
                "hasFile": bool(ep.get("hasFile")),
            }
        )

    events.sort(key=lambda e: e.get("airDate") or "")
    events = events[:settings.CALENDAR_MAX_EVENTS]
    return {"ok": True, "events": events}


def _get_sonarr_calendar_cached():
    now = time.monotonic()
    cached = settings._arr_cache.get("calendar")
    if cached and now - settings._arr_cache.get("calendar_ts", 0) < settings.CALENDAR_CACHE_TTL:
        return cached
    with settings._arr_cache_lock:
        cached = settings._arr_cache.get("calendar")
        if cached and now - settings._arr_cache.get("calendar_ts", 0) < settings.CALENDAR_CACHE_TTL:
            return cached
        data = _build_sonarr_calendar()
        settings._arr_cache["calendar"] = data
        settings._arr_cache["calendar_ts"] = time.monotonic()
        return data


def handle_sonarr_calendar(handler):
    try:
        send_json(handler, 200, _get_sonarr_calendar_cached())
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e), "events": []})
