"""Automation summary route handlers."""
import threading
import time

import config as settings
from clients.arr import _arr_get, _bazarr_wanted_details
from http_support import send_json
from queue_hygiene import _read_state, normalized_state


def _safe_arr_count(fn, default=0):
    try:
        return fn()
    except Exception:
        return default


def _queue_count(base, api_key):
    data = _arr_get(base, api_key, "/api/v3/queue?page=1&pageSize=1")
    return int(data.get("totalRecords", 0))


def _episode_code(season, number):
    if season is None or number is None:
        return ""
    return f"S{int(season)}E{int(number)}"


def _sonarr_missing_preview():
    data = _arr_get(
        settings.SONARR_URL,
        settings.SONARR_API_KEY,
        f"/api/v3/wanted/missing?page=1&pageSize={settings.AUTOMATION_MISSING_LIMIT}"
        "&includeSeries=true&sortKey=airDateUtc&sortDirection=descending",
    )
    items = []
    for ep in data.get("records", [])[:settings.AUTOMATION_MISSING_LIMIT]:
        series = ep.get("series") or {}
        title = series.get("title") or ep.get("title") or "Unknown"
        code = _episode_code(ep.get("seasonNumber"), ep.get("episodeNumber"))
        label = f"{title} {code}".strip()
        slug = series.get("titleSlug")
        href = f"{settings.SONARR_EXTERNAL_URL}/series/{slug}" if slug else None
        _sid = series.get("id") or ep.get("seriesId")
        poster_url = f"{settings.SONARR_EXTERNAL_URL}/MediaCover/{_sid}/poster-250.jpg" if _sid else None
        items.append(
            {
                "label": label,
                "airDate": ep.get("airDateUtc") or ep.get("airDate"),
                "seriesId": _sid,
                "titleSlug": slug,
                "href": href,
                "posterUrl": poster_url,
            }
        )
    return int(data.get("totalRecords", 0)), items


def _radarr_missing_preview():
    try:
        data = _arr_get(
            settings.RADARR_URL,
            settings.RADARR_API_KEY,
            f"/api/v3/wanted/missing?page=1&pageSize={settings.AUTOMATION_MISSING_LIMIT}"
            "&monitored=true&sortKey=title&includeMovie=true",
        )
        items = []
        for movie in data.get("records", [])[:settings.AUTOMATION_MISSING_LIMIT]:
            title = movie.get("title") or "Unknown"
            year = movie.get("year")
            label = f"{title} ({year})" if year else title
            slug = movie.get("titleSlug")
            href = f"{settings.RADARR_EXTERNAL_URL}/movie/{slug}" if slug else None
            mid = movie.get("id")
            poster_url = f"{settings.RADARR_EXTERNAL_URL}/MediaCover/{mid}/poster-250.jpg" if mid else None
            items.append(
                {
                    "label": label,
                    "titleSlug": slug,
                    "href": href,
                    "posterUrl": poster_url,
                }
            )
        return int(data.get("totalRecords", 0)), items
    except Exception:
        # Fallback for older Radarr: scan movie list for monitored without file.
        movies = _arr_get(settings.RADARR_URL, settings.RADARR_API_KEY, "/api/v3/movie")
        missing = [
            m for m in movies
            if m.get("monitored") and not m.get("hasFile")
        ]
        items = []
        for movie in missing[:settings.AUTOMATION_MISSING_LIMIT]:
            title = movie.get("title") or "Unknown"
            year = movie.get("year")
            label = f"{title} ({year})" if year else title
            slug = movie.get("titleSlug")
            href = f"{settings.RADARR_EXTERNAL_URL}/movie/{slug}" if slug else None
            mid = movie.get("id")
            poster_url = f"{settings.RADARR_EXTERNAL_URL}/MediaCover/{mid}/poster-250.jpg" if mid else None
            items.append(
                {
                    "label": label,
                    "titleSlug": slug,
                    "href": href,
                    "posterUrl": poster_url,
                }
            )
        return len(missing), items


def _fetch_queue_snapshot(base, api_key):
    """Fetch the complete queue once so diagnostics and preview share records."""
    if base == settings.SONARR_URL:
        query = "includeUnknownSeriesItems=true&includeSeries=true&includeEpisode=true"
    else:
        query = "includeUnknownMovieItems=true&includeMovie=true"
    return _arr_get(base, api_key, f"/api/v3/queue?page=1&pageSize=1000&{query}")


def _queue_preview(snapshot):
    records = snapshot.get("records", []) if isinstance(snapshot, dict) else []
    items = []
    for row in records[: settings.AUTOMATION_PREVIEW_LIMIT]:
        if not isinstance(row, dict):
            continue
        title = row.get("title") or "Unknown"
        status = row.get("trackedDownloadStatus") or row.get("status") or ""
        timeleft = row.get("timeleft") or ""
        error = row.get("errorMessage") or ""
        if not error:
            messages = []
            for entry in row.get("statusMessages") or []:
                if not isinstance(entry, dict):
                    continue
                values = entry.get("messages")
                if isinstance(values, str):
                    messages.append(values)
                elif isinstance(values, list):
                    messages.extend(value for value in values if isinstance(value, str))
            error = "; ".join(message for message in messages if message.strip())
        label = title
        if timeleft and timeleft not in ("00:00:00", "0"):
            label = f"{title} · {timeleft} left"
        elif status:
            label = f"{title} · {status}"
        items.append(
            {
                "label": label,
                "status": status,
                "timeleft": timeleft,
                "error": error,
                "warning": bool(error)
                or str(status).lower() in ("warning", "error"),
            }
        )
    return int(snapshot.get("totalRecords", 0)), items


def _queue_hygiene_summary():
    try:
        state = normalized_state(_read_state())
    except Exception:
        state = normalized_state({})
    return {
        **state,
        "eligibleItems": state["eligibleItems"][: settings.AUTOMATION_PREVIEW_LIMIT],
        "blockedItems": state["blockedItems"][: settings.AUTOMATION_PREVIEW_LIMIT],
    }


def _prowlarr_indexer_details():
    indexers = _arr_get(settings.PROWLARR_URL, settings.PROWLARR_API_KEY, "/api/v1/indexer")
    enabled = [i for i in indexers if i.get("enable", True)]
    disabled = [
        {"name": i.get("name") or "Unknown"}
        for i in indexers
        if not i.get("enable", True)
    ]

    cooldown = []
    try:
        statuses = _arr_get(settings.PROWLARR_URL, settings.PROWLARR_API_KEY, "/api/v1/indexerstatus")
        by_id = {i.get("id"): i for i in indexers}
        for st in statuses:
            indexer = by_id.get(st.get("indexerId"))
            name = (indexer or {}).get("name") or f"Indexer {st.get('indexerId')}"
            cooldown.append(
                {
                    "name": name,
                    "until": st.get("disabledTill"),
                    "reason": st.get("mostRecentFailure") or "",
                }
            )
    except Exception:
        # Some indexers embed status on the indexer object.
        for i in indexers:
            status = i.get("status") or {}
            until = status.get("disabledTill")
            if until:
                cooldown.append(
                    {
                        "name": i.get("name") or "Unknown",
                        "until": until,
                        "reason": status.get("mostRecentFailure") or "",
                    }
                )

    return {
        "indexers": len(indexers),
        "enabled": len(enabled),
        "disabled": disabled[:settings.AUTOMATION_PREVIEW_LIMIT],
        "cooldown": cooldown[:settings.AUTOMATION_PREVIEW_LIMIT],
    }




def _build_automation_summary():
    sonarr = {"ok": False}
    radarr = {"ok": False}
    prowlarr = {"ok": False}
    bazarr = None

    if settings.SONARR_API_KEY:
        try:
            series = _arr_get(settings.SONARR_URL, settings.SONARR_API_KEY, "/api/v3/series")
            monitored = sum(1 for s in series if s.get("monitored"))
            missing_count, missing_items = _sonarr_missing_preview()
            queue_snapshot = _fetch_queue_snapshot(settings.SONARR_URL, settings.SONARR_API_KEY)
            queued_count, queue_items = _queue_preview(queue_snapshot)
            sonarr = {
                "ok": True,
                "series": len(series),
                "monitored": monitored,
                "queued": queued_count,
                "missing": missing_count,
                "missingItems": missing_items,
                "queueItems": queue_items,
            }
            hygiene = _queue_hygiene_summary()
            sonarr["queueHygiene"] = hygiene
            sonarr["degraded"] = bool(
                hygiene["eligibleCount"] or hygiene["blockedCount"] or hygiene["circuitOpen"]
            )
        except Exception as e:
            sonarr = {"ok": False, "error": str(e)}

    if settings.RADARR_API_KEY:
        try:
            movies = _arr_get(settings.RADARR_URL, settings.RADARR_API_KEY, "/api/v3/movie")
            monitored = sum(1 for m in movies if m.get("monitored"))
            missing_count, missing_items = _radarr_missing_preview()
            queue_snapshot = _fetch_queue_snapshot(settings.RADARR_URL, settings.RADARR_API_KEY)
            queued_count, queue_items = _queue_preview(queue_snapshot)
            radarr = {
                "ok": True,
                "movies": len(movies),
                "monitored": monitored,
                "queued": queued_count,
                "missing": missing_count,
                "missingItems": missing_items,
                "queueItems": queue_items,
            }
        except Exception as e:
            radarr = {"ok": False, "error": str(e)}

    if settings.PROWLARR_API_KEY:
        try:
            details = _prowlarr_indexer_details()
            prowlarr = {"ok": True, **details}
        except Exception as e:
            prowlarr = {"ok": False, "error": str(e)}

    if settings.BAZARR_ENABLED and not settings.BAZARR_API_KEY:
        bazarr = {
            "ok": False,
            "enabled": True,
            "configured": False,
            "error": "BAZARR_API_KEY not configured",
        }
    elif settings.BAZARR_ENABLED:
        ep_wanted, movie_wanted, errors = _bazarr_wanted_details()
        bazarr = {
            "ok": not errors,
            "enabled": True,
            "configured": True,
            "wanted": ep_wanted["total"] + movie_wanted["total"],
            "wantedEpisodes": ep_wanted["total"],
            "wantedMovies": movie_wanted["total"],
            "wantedItems": (ep_wanted["items"] + movie_wanted["items"])[
                :settings.AUTOMATION_PREVIEW_LIMIT
            ],
        }
        if errors:
            bazarr["error"] = "; ".join(errors)

    summary = {
        "ok": True,
        "sonarr": sonarr,
        "radarr": radarr,
        "prowlarr": prowlarr,
    }
    if bazarr is not None:
        summary["bazarr"] = bazarr
    return summary


def _get_automation_summary_cached():
    now = time.monotonic()
    cached = settings._arr_cache.get("automation")
    if cached and now - settings._arr_cache.get("automation_ts", 0) < settings.AUTOMATION_CACHE_TTL:
        return cached
    with settings._arr_cache_lock:
        cached = settings._arr_cache.get("automation")
        if cached and now - settings._arr_cache.get("automation_ts", 0) < settings.AUTOMATION_CACHE_TTL:
            return cached
        data = _build_automation_summary()
        settings._arr_cache["automation"] = data
        settings._arr_cache["automation_ts"] = time.monotonic()
        return data


def handle_automation_summary(handler):
    try:
        send_json(handler, 200, _get_automation_summary_cached())
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})
