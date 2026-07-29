"""Jellyseerr and Trakt HTTP clients."""
import json
import urllib.parse
import urllib.request

import config as settings

def _jellyseerr_get(path):
    if not settings.JELLYSEERR_ENABLED:
        raise RuntimeError("Jellyseerr is disabled (set JELLYSEERR_ENABLED=true)")
    if not settings.JELLYSEERR_API_KEY:
        raise RuntimeError("JELLYSEERR_API_KEY not configured")
    req = urllib.request.Request(f"{settings.JELLYSEERR_URL}{path}")
    req.add_header("X-Api-Key", settings.JELLYSEERR_API_KEY)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=settings.TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))
def _trakt_get(path):
    if not settings.TRAKT_CLIENT_ID or not settings.TRAKT_ACCESS_TOKEN:
        raise RuntimeError("Trakt OAuth not configured")
    req = urllib.request.Request(f"https://api.trakt.tv{path}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "media-stack-dashboard/1.0")
    req.add_header("trakt-api-version", "2")
    req.add_header("trakt-api-key", settings.TRAKT_CLIENT_ID)
    req.add_header("Authorization", f"Bearer {settings.TRAKT_ACCESS_TOKEN}")
    with urllib.request.urlopen(req, timeout=settings.TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))
