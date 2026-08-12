"""HTTP helpers: CORS, auth, JSON bodies, responses."""
import hmac
import json
import re
import urllib.parse

import config


def _cors_header_for(handler):
    cors_origins = config.CORS_ORIGINS
    if "*" in cors_origins or not cors_origins:
        return "*"
    origin = _request_origin(handler)
    if origin in cors_origins:
        return origin
    return cors_origins[0]


def send_json(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", _cors_header_for(handler))
    handler.send_header("Access-Control-Allow-Methods", config.CORS_ALLOW_METHODS)
    handler.send_header("Access-Control-Allow-Headers", config.CORS_ALLOW_HEADERS)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_options(handler):
    handler.send_response(204)
    handler.send_header("Access-Control-Allow-Origin", _cors_header_for(handler))
    handler.send_header("Access-Control-Allow-Methods", config.CORS_ALLOW_METHODS)
    handler.send_header("Access-Control-Allow-Headers", config.CORS_ALLOW_HEADERS)
    handler.end_headers()


def _request_origin(handler):
    origin = handler.headers.get("Origin", "").strip()
    if origin:
        return origin
    referer = handler.headers.get("Referer", "").strip()
    if referer:
        parsed = urllib.parse.urlparse(referer)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return ""


def _origin_allowed(handler):
    cors_origins = config.CORS_ORIGINS
    if "*" in cors_origins or not cors_origins:
        return True
    origin = _request_origin(handler)
    # Same-origin proxy (nginx) may omit Origin; allow empty when token is valid.
    if not origin:
        return True
    return origin in cors_origins


def _token_valid(handler):
    token = config.ACTIONS_TOKEN
    if not token:
        return False
    provided = handler.headers.get("X-Actions-Token") or ""
    return hmac.compare_digest(provided, token)


_TORRENT_HASH_RE = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")


def _valid_torrent_hash(torrent_id):
    if not isinstance(torrent_id, str):
        return False
    value = torrent_id.strip()
    if not value or value.lower() == "all":
        return False
    if any(ch in value for ch in ",/\\"):
        return False
    if ".." in value:
        return False
    return _TORRENT_HASH_RE.fullmatch(value) is not None


MAX_JSON_BODY_BYTES = 1_048_576  # 1 MiB


class _BodyTooLarge(ValueError):
    pass


def _read_json_body(handler):
    try:
        length = int(handler.headers.get("Content-Length", "0") or "0")
    except ValueError:
        raise json.JSONDecodeError("invalid Content-Length", "", 0)
    if length > MAX_JSON_BODY_BYTES:
        raise _BodyTooLarge(f"body exceeds {MAX_JSON_BODY_BYTES} bytes")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _reject_mutating(handler):
    if not _origin_allowed(handler):
        send_json(handler, 403, {"ok": False, "error": "Origin not allowed"})
        return True
    if not _token_valid(handler):
        send_json(handler, 401, {"ok": False, "error": "Unauthorized"})
        return True
    return False


def _reject_internal_get(handler):
    """Require both the actions token and an explicit approved Origin."""
    if not _token_valid(handler):
        send_json(handler, 401, {"ok": False, "error": "Unauthorized"})
        return True
    if not _request_origin(handler) or not _origin_allowed(handler):
        send_json(handler, 403, {"ok": False, "error": "Origin not allowed"})
        return True
    return False


def _reject_post(handler):
    return _reject_mutating(handler)


# ---------------------------------------------------------------------------
