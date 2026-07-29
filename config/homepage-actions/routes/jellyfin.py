"""Jellyfin route handlers."""
import config as settings
from clients.jellyfin import _get_jellyfin_payload, _get_watch_next_payload
from http_support import send_json


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

