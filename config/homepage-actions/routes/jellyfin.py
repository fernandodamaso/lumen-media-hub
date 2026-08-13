"""Jellyfin route handlers."""
import sys

import config as settings
from clients.jellyfin import (
    RECENTLY_AVAILABLE_DEFAULT_LIMIT,
    RECENTLY_AVAILABLE_MAX_LIMIT,
    RECENTLY_AVAILABLE_UPSTREAM_ERROR,
    _get_jellyfin_payload,
    _get_recently_available_payload,
    _get_watch_next_payload,
)
from http_support import send_json


def _recently_available_limit(query):
    raw = query.get("limit", [None])[0]
    if raw is None:
        return RECENTLY_AVAILABLE_DEFAULT_LIMIT
    try:
        if isinstance(raw, str) and "." in raw:
            value = float(raw)
            if value != int(value):
                return RECENTLY_AVAILABLE_DEFAULT_LIMIT
            value = int(value)
        else:
            value = int(raw)
    except (TypeError, ValueError):
        return RECENTLY_AVAILABLE_DEFAULT_LIMIT
    if value <= 0:
        return 1
    if value > RECENTLY_AVAILABLE_MAX_LIMIT:
        return RECENTLY_AVAILABLE_MAX_LIMIT
    return value


def handle_jellyfin_items(handler, item_type):
    if not settings.JELLYFIN_API_KEY:
        send_json(handler, 503, {"ok": False, "error": "JELLYFIN_API_KEY not configured"})
        return
    try:
        send_json(handler, 200, _get_jellyfin_payload(item_type))
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def handle_jellyfin_watch_next(handler):
    if not settings.JELLYFIN_API_KEY:
        send_json(handler, 503, {"ok": False, "error": "JELLYFIN_API_KEY not configured"})
        return
    try:
        send_json(handler, 200, _get_watch_next_payload())
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def handle_jellyfin_recently_available(handler, query):
    if not settings.JELLYFIN_API_KEY:
        send_json(handler, 503, {"ok": False, "error": "JELLYFIN_API_KEY not configured"})
        return
    try:
        send_json(handler, 200, _get_recently_available_payload(_recently_available_limit(query)))
    except Exception as exc:
        print(f"recently-available upstream failure: {exc.__class__.__name__}", file=sys.stderr)
        send_json(handler, 502, {"ok": False, "error": RECENTLY_AVAILABLE_UPSTREAM_ERROR})
