"""Sonarr/Radarr library and calendar route handlers."""
import threading
import time
from datetime import date, datetime, timedelta, timezone

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


def _positive_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _calendar_window():
    start = date.today()
    end = start + timedelta(days=settings.CALENDAR_DAYS)
    return start, end


def _fetch_sonarr_calendar_events():
    start, end = _calendar_window()
    path = (
        f"/api/v3/calendar?start={start.isoformat()}&end={end.isoformat()}"
        "&includeSeries=true&unmonitored=false"
    )
    episodes = _arr_get(settings.SONARR_URL, settings.SONARR_API_KEY, path)
    if not isinstance(episodes, list):
        raise ValueError("invalid Sonarr calendar payload")

    events = []
    for ep in episodes:
        if not isinstance(ep, dict) or ep.get("monitored") is False:
            continue
        episode_id = _positive_int(ep.get("id"))
        if episode_id is None:
            continue
        series = ep.get("series") if isinstance(ep.get("series"), dict) else {}
        series_id = _positive_int(series.get("id") or ep.get("seriesId"))
        title = series.get("title") or ep.get("title") or "Unknown"
        air = ep.get("airDateUtc") or ep.get("airDate") or ""
        if not air:
            continue
        events.append(
            {
                "id": f"sonarr:episode:{episode_id}",
                "kind": "episode",
                "title": str(title),
                "additional": _episode_label(ep),
                "date": _format_calendar_date(air),
                "airDate": str(air),
                "episodeId": episode_id,
                "seriesId": series_id,
                "hasFile": bool(ep.get("hasFile")),
                "monitored": bool(ep.get("monitored", series.get("monitored", True))),
            }
        )
    return events


def _radarr_release(movie, start, end):
    candidates = (
        ("inCinemas", "In cinemas"),
        ("digitalRelease", "Digital release"),
        ("physicalRelease", "Physical release"),
    )
    releases = []
    for field, label in candidates:
        value = movie.get(field)
        if not isinstance(value, str) or len(value) < 10:
            continue
        try:
            release_day = date.fromisoformat(value[:10])
        except ValueError:
            continue
        if start <= release_day <= end:
            releases.append((value, label))
    if not releases:
        return None
    releases.sort(key=lambda item: (item[0], item[1]))
    return releases[0]


def _fetch_radarr_calendar_events():
    start, end = _calendar_window()
    path = (
        f"/api/v3/calendar?start={start.isoformat()}&end={end.isoformat()}"
        "&unmonitored=false"
    )
    movies = _arr_get(settings.RADARR_URL, settings.RADARR_API_KEY, path)
    if not isinstance(movies, list):
        raise ValueError("invalid Radarr calendar payload")

    events = []
    for movie in movies:
        if not isinstance(movie, dict) or movie.get("monitored") is False:
            continue
        movie_id = _positive_int(movie.get("id"))
        if movie_id is None:
            continue
        release = _radarr_release(movie, start, end)
        if release is None:
            continue
        air, label = release
        title = movie.get("title") or "Unknown"
        event = {
            "id": f"radarr:movie:{movie_id}",
            "kind": "movie",
            "title": str(title),
            "additional": label,
            "date": _format_calendar_date(air),
            "airDate": air,
            "movieId": movie_id,
            "hasFile": bool(movie.get("hasFile")),
            "monitored": bool(movie.get("monitored", True)),
            "premiere": label == "In cinemas",
        }
        title_slug = movie.get("titleSlug")
        if isinstance(title_slug, str) and title_slug.strip():
            event["titleSlug"] = title_slug.strip()
        events.append(event)
    return events


def _calendar_sort_key(event):
    air = str(event.get("airDate") or "")
    day = air[:10] or "9999-12-31"
    clock = air[11:19] if len(air) >= 19 and "T" in air else ""
    return (
        day,
        clock,
        str(event.get("kind") or ""),
        str(event.get("title") or "").casefold(),
        str(event.get("id") or ""),
    )


def _build_calendar():
    provider_specs = {
        "sonarr": (settings.SONARR_API_KEY, _fetch_sonarr_calendar_events),
        "radarr": (settings.RADARR_API_KEY, _fetch_radarr_calendar_events),
    }
    results = {}
    results_lock = threading.Lock()
    threads = {}
    sources = {}

    def worker(source, fetcher):
        try:
            result = ("ok", fetcher())
        except Exception:
            result = ("error", [])
        with results_lock:
            results[source] = result

    for source, (api_key, fetcher) in provider_specs.items():
        if not api_key:
            sources[source] = "unconfigured"
            continue
        thread = threading.Thread(target=worker, args=(source, fetcher), daemon=True)
        threads[source] = thread
        thread.start()

    deadline = time.monotonic() + max(0.0, float(settings.CALENDAR_PROVIDER_TIMEOUT))
    for thread in threads.values():
        remaining = deadline - time.monotonic()
        if remaining > 0:
            thread.join(remaining)

    events = []
    with results_lock:
        completed = dict(results)
    for source, thread in threads.items():
        if thread.is_alive():
            sources[source] = "error"
            continue
        status, provider_events = completed.get(source, ("error", []))
        sources[source] = status
        if status == "ok":
            events.extend(provider_events)

    events.sort(key=_calendar_sort_key)
    events = events[:settings.CALENDAR_MAX_EVENTS]
    return {
        "ok": any(status == "ok" for status in sources.values()),
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": sources,
        "events": events,
    }


def _get_calendar_cached():
    now = time.monotonic()
    cached = settings._arr_cache.get("calendar")
    if cached and now - settings._arr_cache.get("calendar_ts", 0) < settings.CALENDAR_CACHE_TTL:
        return cached
    with settings._arr_cache_lock:
        cached = settings._arr_cache.get("calendar")
        if cached and now - settings._arr_cache.get("calendar_ts", 0) < settings.CALENDAR_CACHE_TTL:
            return cached
        data = _build_calendar()
        settings._arr_cache["calendar"] = data
        settings._arr_cache["calendar_ts"] = time.monotonic()
        return data


def handle_sonarr_calendar(handler):
    """Serve the neutral combined calendar; retained name backs the legacy route alias."""
    try:
        feed = _get_calendar_cached()
    except Exception as error:
        print(f"[calendar] feed failed: {type(error).__name__}", flush=True)
        send_json(
            handler,
            502,
            {
                "ok": False,
                "error": "Calendar is temporarily unavailable",
                "sources": {"sonarr": "error", "radarr": "error"},
                "events": [],
            },
        )
        return
    if not feed.get("ok"):
        send_json(
            handler,
            502,
            {
                "ok": False,
                "error": "Calendar is temporarily unavailable",
                "sources": feed.get("sources", {}),
                "events": [],
            },
        )
        return
    send_json(handler, 200, feed)
