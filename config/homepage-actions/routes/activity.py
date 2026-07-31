"""Activity feed route handler (merged Sonarr/Radarr history)."""
import time

import config as settings
from clients.arr import _build_activity_feed
from http_support import send_json

ACTIVITY_DEFAULT_LIMIT = 20
ACTIVITY_MAX_LIMIT = 50


def _activity_limit(query):
    raw = (query.get("limit") or [None])[0]
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return ACTIVITY_DEFAULT_LIMIT
    return max(1, min(ACTIVITY_MAX_LIMIT, value))


def _get_activity_cached():
    now = time.monotonic()
    cached = settings._arr_cache.get("activity")
    if cached and now - settings._arr_cache.get("activity_ts", 0) < settings.ACTIVITY_CACHE_TTL:
        return cached
    with settings._arr_cache_lock:
        cached = settings._arr_cache.get("activity")
        if cached and now - settings._arr_cache.get("activity_ts", 0) < settings.ACTIVITY_CACHE_TTL:
            return cached
        feed = _build_activity_feed()
        settings._arr_cache["activity"] = feed
        settings._arr_cache["activity_ts"] = time.monotonic()
        return feed


def handle_activity_feed(handler, query):
    limit = _activity_limit(query)
    try:
        cached = _get_activity_cached()
    except Exception as e:
        print(f"[activity] feed failed: {e}", flush=True)
        send_json(handler, 502, {"ok": False, "error": "Activity feed is temporarily unavailable"})
        return
    if cached["sources"].get("sonarr") == "error" and cached["sources"].get("radarr") == "error":
        send_json(
            handler,
            502,
            {
                "ok": False,
                "error": "Sonarr and Radarr history unavailable",
                "sources": cached["sources"],
            },
        )
        return
    feed = dict(cached)
    feed["items"] = cached["items"][:limit]
    send_json(handler, 200, feed)
