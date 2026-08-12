"""Jellyseerr and Trakt HTTP clients."""
import json
import urllib.request

import config as settings
from clients.trakt import TraktClient

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
    return _trakt_client().get(path)

def _trakt_client():
    client = TraktClient(
        client_id=settings.TRAKT_CLIENT_ID,
        client_secret=settings.TRAKT_CLIENT_SECRET,
        token_path=settings.TRAKT_TOKEN_PATH,
        timeout=settings.TIMEOUT,
    )
    return client

def _trakt_get_page(path):
    return _trakt_client().get_page(path)
