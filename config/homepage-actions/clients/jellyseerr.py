"""Jellyseerr and Trakt HTTP clients."""
import json
import socket
import urllib.error
import urllib.request

import config as settings
from clients.trakt import TraktClient


class JellyseerrUpstreamError(Exception):
    """Internal Jellyseerr failure with sanitized transport metadata."""

    def __init__(self, *, status=None, ambiguous=False, safe_detail=None):
        del safe_detail
        super().__init__("Jellyseerr upstream request failed")
        self.status = status if isinstance(status, int) and not isinstance(status, bool) else None
        self.ambiguous = bool(ambiguous)


def _jellyseerr_json(path, *, method="GET", payload=None):
    if not settings.JELLYSEERR_ENABLED:
        raise RuntimeError("Jellyseerr is disabled (set JELLYSEERR_ENABLED=true)")
    if not settings.JELLYSEERR_API_KEY:
        raise RuntimeError("JELLYSEERR_API_KEY not configured")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{settings.JELLYSEERR_URL}{path}", data=data, method=method
    )
    req.add_header("X-Api-Key", settings.JELLYSEERR_API_KEY)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=settings.TIMEOUT) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as error:
        # The status is useful for duplicate recovery. The upstream body is
        # deliberately neither read nor retained.
        try:
            error.close()
        except Exception:
            pass
        raise JellyseerrUpstreamError(status=error.code) from None
    except (TimeoutError, socket.timeout):
        raise JellyseerrUpstreamError(ambiguous=method == "POST") from None
    except urllib.error.URLError as error:
        ambiguous = method == "POST" and isinstance(
            getattr(error, "reason", None), (TimeoutError, socket.timeout)
        )
        raise JellyseerrUpstreamError(ambiguous=ambiguous) from None
    except (UnicodeDecodeError, ValueError):
        raise JellyseerrUpstreamError() from None


def _jellyseerr_post(path, payload):
    return _jellyseerr_json(path, method="POST", payload=payload)

def _jellyseerr_get(path):
    return _jellyseerr_json(path)
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
