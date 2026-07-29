#!/usr/bin/env python3
"""CORS-enabled API for the media dashboard (qBittorrent, Jellyfin, *arr)."""

import hmac
import http.cookiejar
import json
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from recommendations_store import (
    ITEM_TYPES,
    RecommendationError,
    RecommendationStore,
    apply_feedback,
    apply_request,
    media_identity,
    utc_now,
)

QBT_URL = os.environ.get("QBT_URL", "http://qbittorrent:8081").rstrip("/")
QBT_USERNAME = os.environ.get("QBT_USERNAME", "admin")
QBT_PASSWORD = os.environ.get("QBT_PASSWORD", "changeme")

JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://jellyfin:8096").rstrip("/")
JELLYFIN_EXTERNAL_URL = os.environ.get("JELLYFIN_EXTERNAL_URL", "http://localhost:8096").rstrip("/")
JELLYFIN_API_KEY = os.environ.get("JELLYFIN_API_KEY", "")
JELLYFIN_USER_ID = os.environ.get("JELLYFIN_USER_ID", "")

SONARR_URL = os.environ.get("SONARR_URL", "http://sonarr:8989").rstrip("/")
SONARR_API_KEY = os.environ.get("SONARR_API_KEY", "")
RADARR_URL = os.environ.get("RADARR_URL", "http://radarr:7878").rstrip("/")
RADARR_API_KEY = os.environ.get("RADARR_API_KEY", "")
PROWLARR_URL = os.environ.get("PROWLARR_URL", "http://prowlarr:9696").rstrip("/")
PROWLARR_API_KEY = os.environ.get("PROWLARR_API_KEY", "")
BAZARR_URL = os.environ.get("BAZARR_URL", "http://bazarr:6767").rstrip("/")
BAZARR_ENABLED = os.environ.get("BAZARR_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
BAZARR_API_KEY = os.environ.get("BAZARR_API_KEY", "")

JELLYSEERR_URL = os.environ.get("JELLYSEERR_URL", "http://jellyseerr:5055").rstrip("/")
JELLYSEERR_ENABLED = os.environ.get("JELLYSEERR_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
JELLYSEERR_API_KEY = os.environ.get("JELLYSEERR_API_KEY", "")

TRAKT_CLIENT_ID = os.environ.get("TRAKT_CLIENT_ID", "")
TRAKT_ACCESS_TOKEN = os.environ.get("TRAKT_ACCESS_TOKEN", "")

HERMES_COLLECTION_NAME = os.environ.get("HERMES_COLLECTION_NAME", "Hermes Picks")

_cors_raw = os.environ.get("CORS_ORIGINS") or os.environ.get(
    "CORS_ORIGIN", "http://localhost:3000,http://localhost:4200"
)
CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]
ACTIONS_TOKEN = os.environ.get("ACTIONS_TOKEN", "")
PORT = int(os.environ.get("PORT", "8085"))
DATA_PATH = os.environ.get("DATA_PATH", "/data")
RECOMMENDATIONS_PATH = os.environ.get(
    "RECOMMENDATIONS_PATH",
    os.path.join(DATA_PATH, "config", "recommendations", "recommendations.json"),
)
RECOMMENDATIONS_STORE = RecommendationStore(RECOMMENDATIONS_PATH)
RECONCILIATION_PATH = os.environ.get(
    "HERMES_REQUEST_RECONCILIATION_PATH",
    os.path.join(os.path.dirname(RECOMMENDATIONS_PATH), "request-reconciliation.json"),
)
GENERATION_REQUEST_PATH = os.environ.get(
    "HERMES_GENERATION_REQUEST_PATH",
    os.path.join(os.path.dirname(RECOMMENDATIONS_PATH), "generation-request.json"),
)
# Automatic retries: one startup attempt, then a bounded periodic cycle.
# Override with HERMES_RECONCILE_INTERVAL_SECONDS (seconds). Manual recovery
# remains available at POST /discover/request/reconcile.
RECONCILE_INTERVAL_SECONDS = float(
    os.environ.get("HERMES_RECONCILE_INTERVAL_SECONDS", "30")
)
_reconciliation_lock = threading.RLock()
_generation_request_lock = threading.RLock()
_reconcile_cycle_lock = threading.Lock()
_reconcile_stop = threading.Event()
_reconcile_thread = None
_reconcile_thread_lock = threading.Lock()
TMP_DIR = os.path.abspath(os.environ.get("TMP_DIR", os.path.join(DATA_PATH, "tmp")))
TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "10"))
CRON_LOG_FILES = (
    {
        "id": "watchdog",
        "title": "Media Download Watchdog",
        "file": "watch-downloads.log",
        "format": "ndjson",
        "schedule": "every 15m",
        "description": (
            "Finds completed torrents that Sonarr/Radarr should have imported but left stuck "
            "in qBittorrent. Covers the gaps native Completed Download Handling does not age out."
        ),
        "actions": [
            "Import stuck downloads via Sonarr/Radarr when safe",
            "Verify hardlinks into the library",
            "Trigger Bazarr for new imports",
            "Remove the finished qBittorrent row after import",
            "Blocklist hard-rejected releases and re-search a replacement",
        ],
    },
    {
        "id": "stale-metadata",
        "title": "Stale Metadata Cleanup",
        "file": "stale-metadata-cleanup.log",
        "format": "text",
        "schedule": "every 30m",
        "description": (
            "Clears Sonarr/Radarr queue items that are stuck fetching torrent metadata "
            "or sitting in long stalled/error states so a better release can be grabbed."
        ),
        "actions": [
            "Remove metaDL items older than 60 minutes",
            "Remove stalled/error/missing-files items older than 6 hours",
            "Remove the matching qBittorrent torrent",
            "Blocklist the bad release",
            "Queue a replacement episode/movie search",
        ],
    },
    {
        "id": "hardlink-cleanup",
        "title": "Hardlink Staging Cleanup",
        "file": "hardlink-staging-cleanup.log",
        "format": "text",
        "schedule": "Saturday 03:00",
        "description": (
            "Frees leftover staging copies under downloads/torrents if a post-import remove was missed. "
            "Only deletes files that already have a hardlink in the library."
        ),
        "actions": [
            "Scan downloads/torrents for multi-hardlink files",
            "Skip anything still under an active qBittorrent content path",
            "Delete leftover staging copies (library copy stays)",
            "Remove empty directories afterward",
        ],
    },
    {
        "id": "weekly-validate",
        "title": "Weekly Validate Final",
        "file": "weekly-validate-final.log",
        "format": "text",
        "schedule": "Sunday 05:00",
        "description": (
            "Runs the full stack health check: compose, containers, ports, qBit categories, "
            "*arr clients, hardlinks, Prowlarr/Bazarr, Jellyfin libraries, and disk space."
        ),
        "actions": [
            "Validate Docker Compose and running containers",
            "Confirm localhost-only UI ports (Jellyfin LAN allowed)",
            "Check qBittorrent categories and *arr download clients",
            "Verify hardlink config, Prowlarr/Bazarr, and Jellyfin libraries",
            "Flag non-green findings as alerts",
        ],
    },
)
JELLYFIN_CACHE_TTL = float(os.environ.get("JELLYFIN_CACHE_TTL", "45"))
ARR_CACHE_TTL = float(os.environ.get("ARR_CACHE_TTL", "300"))
CALENDAR_CACHE_TTL = float(os.environ.get("CALENDAR_CACHE_TTL", "60"))
AUTOMATION_CACHE_TTL = float(os.environ.get("AUTOMATION_CACHE_TTL", "30"))
RESOURCES_CACHE_TTL = float(os.environ.get("RESOURCES_CACHE_TTL", "5"))
CALENDAR_MAX_EVENTS = int(os.environ.get("CALENDAR_MAX_EVENTS", "10"))
CALENDAR_DAYS = int(os.environ.get("CALENDAR_DAYS", "30"))

CORS_ALLOW_HEADERS = "Content-Type, X-Actions-Token"
CORS_ALLOW_METHODS = "GET, POST, PATCH, OPTIONS"

_jellyfin_cache = {}
_jellyfin_locks = {}
_jellyfin_cache_lock = threading.Lock()
_jellyfin_user_id = None
_jellyfin_user_id_lock = threading.Lock()

_arr_cache = {}
_arr_cache_lock = threading.Lock()

_cpu_prev = None
_cpu_prev_lock = threading.Lock()


def _cors_header_for(handler):
    if "*" in CORS_ORIGINS or not CORS_ORIGINS:
        return "*"
    origin = _request_origin(handler)
    if origin in CORS_ORIGINS:
        return origin
    return CORS_ORIGINS[0]


def send_json(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", _cors_header_for(handler))
    handler.send_header("Access-Control-Allow-Methods", CORS_ALLOW_METHODS)
    handler.send_header("Access-Control-Allow-Headers", CORS_ALLOW_HEADERS)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_options(handler):
    handler.send_response(204)
    handler.send_header("Access-Control-Allow-Origin", _cors_header_for(handler))
    handler.send_header("Access-Control-Allow-Methods", CORS_ALLOW_METHODS)
    handler.send_header("Access-Control-Allow-Headers", CORS_ALLOW_HEADERS)
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
    if "*" in CORS_ORIGINS or not CORS_ORIGINS:
        return True
    origin = _request_origin(handler)
    # Same-origin proxy (nginx) may omit Origin; allow empty when token is valid.
    if not origin:
        return True
    return origin in CORS_ORIGINS


def _token_valid(handler):
    if not ACTIONS_TOKEN:
        return False
    provided = handler.headers.get("X-Actions-Token") or ""
    return hmac.compare_digest(provided, ACTIONS_TOKEN)


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


def _reject_post(handler):
    return _reject_mutating(handler)


# ---------------------------------------------------------------------------
# qBittorrent helpers
# ---------------------------------------------------------------------------

def _qbt_request(url, data=None, method="GET", opener=None):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Referer", f"{QBT_URL}/")
    if data is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    if opener:
        return opener.open(req, timeout=TIMEOUT)
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def qbt_login(opener):
    """Authenticate with the qBittorrent WebAPI and store the session cookie."""
    data = urllib.parse.urlencode(
        {"username": QBT_USERNAME, "password": QBT_PASSWORD}
    ).encode("utf-8")
    with _qbt_request(
        f"{QBT_URL}/api/v2/auth/login", data=data, method="POST", opener=opener
    ) as resp:
        body = resp.read().decode("utf-8", errors="ignore").strip()
        if resp.status < 200 or resp.status >= 300:
            raise RuntimeError(f"qBittorrent login failed: HTTP {resp.status} {body}")
        if body == "Fails.":
            raise RuntimeError("qBittorrent login failed: invalid credentials")
        if body not in ("Ok.", ""):
            raise RuntimeError(
                f"qBittorrent login failed: unexpected login response ({body})"
            )
        if body == "":
            try:
                with _qbt_request(
                    f"{QBT_URL}/api/v2/app/version", method="GET", opener=opener
                ) as ver_resp:
                    ver_resp.read()
            except Exception as exc:
                raise RuntimeError(
                    "qBittorrent login failed: invalid credentials (empty response)"
                ) from exc


def qbt_post(path, params, opener):
    """POST to the qBittorrent WebAPI, logging in first if the session expired."""
    data = urllib.parse.urlencode(params).encode("utf-8")
    url = f"{QBT_URL}{path}"
    try:
        with _qbt_request(url, data=data, method="POST", opener=opener) as resp:
            return resp.status, resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            qbt_login(opener)
            with _qbt_request(url, data=data, method="POST", opener=opener) as resp:
                return resp.status, resp.read().decode("utf-8", errors="ignore")
        raise


def qbt_get_json(path, opener, query=None):
    """GET JSON from the qBittorrent WebAPI, logging in first if needed."""
    url = f"{QBT_URL}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)

    try:
        with _qbt_request(url, method="GET", opener=opener) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            qbt_login(opener)
            with _qbt_request(url, method="GET", opener=opener) as resp:
                return json.loads(resp.read().decode("utf-8"))
        raise


def handle_qbt_action(handler, action_path):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        qbt_login(opener)
        status, _ = qbt_post(action_path, {"hashes": "all"}, opener)
        send_json(handler, 200, {"ok": status >= 200 and status < 300})
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def handle_qbt_torrent_hash_action(handler, action_path):
    try:
        body = _read_json_body(handler)
    except _BodyTooLarge:
        send_json(handler, 413, {"ok": False, "error": "Request body too large"})
        return
    except json.JSONDecodeError:
        send_json(handler, 400, {"ok": False, "error": "Invalid JSON"})
        return
    if not isinstance(body, dict):
        send_json(handler, 400, {"ok": False, "error": "Invalid torrent id"})
        return
    torrent_id = body.get("id")
    if not _valid_torrent_hash(torrent_id):
        send_json(handler, 400, {"ok": False, "error": "Invalid torrent id"})
        return

    torrent_hash = torrent_id.strip().lower()
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        qbt_login(opener)
        status, _ = qbt_post(action_path, {"hashes": torrent_hash}, opener)
        send_json(handler, 200, {"ok": status >= 200 and status < 300})
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def handle_qbt_torrents(handler):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        qbt_login(opener)
        torrents = qbt_get_json("/api/v2/torrents/info", opener)
        send_json(handler, 200, torrents)
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


# ---------------------------------------------------------------------------
# Jellyfin helpers
# ---------------------------------------------------------------------------

def jellyfin_get(path, query=None):
    url = f"{JELLYFIN_URL}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url)
    req.add_header("X-Emby-Token", JELLYFIN_API_KEY)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _jellyfin_lock_for(item_type):
    with _jellyfin_cache_lock:
        lock = _jellyfin_locks.get(item_type)
        if lock is None:
            lock = threading.Lock()
            _jellyfin_locks[item_type] = lock
        return lock


def _jellyfin_image_url(item_id, image_tag=None):
    """Build a browser-facing Primary image URL.

    Do not append api_key: authenticated image requests fail when Jellyfin's
    auth/DB path is unhealthy, while anonymous Primary GETs still succeed.
    Optional tag= is only a cache-buster when ImageTags.Primary is known.
    """
    if not item_id:
        return None
    url = f"{JELLYFIN_EXTERNAL_URL}/Items/{item_id}/Images/Primary"
    if image_tag:
        url += "?" + urllib.parse.urlencode({"tag": image_tag})
    return url


def _jellyfin_user_id_for_queries():
    global _jellyfin_user_id
    if JELLYFIN_USER_ID:
        return JELLYFIN_USER_ID
    with _jellyfin_user_id_lock:
        if _jellyfin_user_id:
            return _jellyfin_user_id
        users = jellyfin_get("/Users")
        for user in users:
            if user.get("Policy", {}).get("IsAdministrator"):
                _jellyfin_user_id = user["Id"]
                return _jellyfin_user_id
        if users:
            _jellyfin_user_id = users[0]["Id"]
        return _jellyfin_user_id


def _jellyfin_items_path():
    user_id = _jellyfin_user_id_for_queries()
    if user_id:
        return f"/Users/{user_id}/Items"
    return "/Items"


JELLYFIN_PAGE_SIZE = 100


def _jellyfin_item_is_playable(raw, item_type):
    if raw.get("IsPlaceHolder"):
        return False
    path = raw.get("Path")
    # Exclude JellyNext virtual-library stubs. Those are .strm recommendation /
    # "next season" entries that live under the plugin's jellynext-virtual tree
    # (Trakt recommendations), not media Fernando actually has. They carry a
    # real-looking Path and LocationType=FileSystem, so the only reliable signal
    # is the path itself. Keep genuine items whose Path is outside that tree.
    if path and "jellynext-virtual" in path:
        return False
    if item_type == "Movie":
        return bool(path)
    return True


def _fetch_all_jellyfin_raw(item_type):
    items = []
    start = 0
    while True:
        data = jellyfin_get(
            _jellyfin_items_path(),
            {
                "Recursive": "true",
                "IncludeItemTypes": item_type,
                "StartIndex": str(start),
                "Limit": str(JELLYFIN_PAGE_SIZE),
                "SortBy": "SortName",
                "SortOrder": "Ascending",
                "Fields": "ProductionYear,CommunityRating,PrimaryImageAspectRatio,Path,IsPlaceHolder,ImageTags",
            },
        )
        batch = [
            item for item in data.get("Items", [])
            if _jellyfin_item_is_playable(item, item_type)
        ]
        items.extend(batch)
        total = data.get("TotalRecordCount", len(items))
        start += len(data.get("Items", []))
        if not data.get("Items") or start >= total:
            break
    return items


def _series_episode_count(item_id):
    user_id = _jellyfin_user_id_for_queries()
    path = f"/Users/{user_id}/Items" if user_id else "/Items"
    try:
        episodes_data = jellyfin_get(
            path,
            {
                "ParentId": item_id,
                "Recursive": "true",
                "IncludeItemTypes": "Episode",
                "Limit": "0",
            },
        )
        return episodes_data.get("TotalRecordCount", 0)
    except Exception:
        return 0


def _map_jellyfin_item(raw, item_type):
    item_id = raw.get("Id")
    aspect = raw.get("PrimaryImageAspectRatio")
    rating = raw.get("CommunityRating")
    if isinstance(rating, bool) or not isinstance(rating, (int, float)) or not 0 <= rating <= 10:
        rating = None
    image_tags = raw.get("ImageTags") or {}
    primary_tag = image_tags.get("Primary")
    item_data = {
        "name": raw.get("Name", ""),
        "year": raw.get("ProductionYear"),
        "rating": rating,
        "id": item_id,
        "image": _jellyfin_image_url(item_id, primary_tag),
        "aspectRatio": aspect if aspect else (2 / 3),
    }
    if item_type == "Series":
        item_data["episodeCount"] = _series_episode_count(item_id)
    return item_data


def _dedupe_jellyfin_items(items, item_type):
    # Jellyfin can return the same title from multiple library paths (different IDs).
    seen = {}
    for item in items:
        key = (item["name"].strip().lower(), item.get("year"))
        existing = seen.get(key)
        if item_type == "Series":
            if existing is None or item.get("episodeCount", 0) > existing.get("episodeCount", 0):
                seen[key] = item
        elif existing is None:
            seen[key] = item
    return list(seen.values())


def _fetch_jellyfin_items(item_type):
    ret_items = [_map_jellyfin_item(raw, item_type) for raw in _fetch_all_jellyfin_raw(item_type)]
    ret_items = _dedupe_jellyfin_items(ret_items, item_type)

    if item_type == "Series":
        ret_items = [item for item in ret_items if item.get("episodeCount", 0) > 0]

    ret_items.sort(key=lambda item: item.get("name", "").lower())

    return {
        "ok": True,
        "total": len(ret_items),
        "items": ret_items,
    }


def _get_jellyfin_payload(item_type):
    now = time.monotonic()
    cached = _jellyfin_cache.get(item_type)
    if cached and now - cached["ts"] < JELLYFIN_CACHE_TTL:
        return cached["payload"]

    lock = _jellyfin_lock_for(item_type)
    with lock:
        cached = _jellyfin_cache.get(item_type)
        if cached and now - cached["ts"] < JELLYFIN_CACHE_TTL:
            return cached["payload"]

        payload = _fetch_jellyfin_items(item_type)
        _jellyfin_cache[item_type] = {"ts": time.monotonic(), "payload": payload}
        return payload


def handle_jellyfin_items(handler, item_type):
    if not JELLYFIN_API_KEY:
        send_json(handler, 503, {"ok": False, "error": "JELLYFIN_API_KEY not configured"})
        return
    try:
        send_json(handler, 200, _get_jellyfin_payload(item_type))
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


WATCH_NEXT_ITEM_LIMIT = 40
WATCH_NEXT_UNSTARTED_SERIES_LOOKUP_LIMIT = 60
WATCH_NEXT_FIELDS = (
    "UserData,RunTimeTicks,SeriesName,ParentId,SeasonId,IndexNumber,"
    "ParentIndexNumber,ImageTags,Path,SeriesId,MediaType,Type,Name,"
    "DateCreated,DateLastContentAdded"
)


def _clamp_progress_percent(value):
    if not isinstance(value, (int, float)):
        return 0
    if value != value:
        return 0
    return max(0, min(100, int(round(value))))


def _progress_percent(user_data, runtime_ticks):
    user_data = user_data or {}
    if user_data.get("Played"):
        return None
    position = user_data.get("PlaybackPositionTicks") or 0
    if not isinstance(position, (int, float)):
        position = 0
    runtime = runtime_ticks or 0
    if not isinstance(runtime, (int, float)):
        runtime = 0
    if position <= 0:
        return 0
    if runtime <= 0:
        return 1
    return _clamp_progress_percent(position / runtime * 100)


def _format_episode_subtitle(raw):
    season = raw.get("ParentIndexNumber")
    episode = raw.get("IndexNumber")
    name = (raw.get("Name") or "").strip()
    if isinstance(season, int) and isinstance(episode, int):
        prefix = f"S{season:02d}E{episode:02d}"
        return f"{prefix} · {name}" if name else prefix
    return name


def _watch_next_image(raw):
    item_type = raw.get("Type") or ""
    series_id = raw.get("SeriesId")
    if item_type == "Episode" and series_id:
        return _jellyfin_image_url(series_id)
    item_id = raw.get("Id")
    image_tags = raw.get("ImageTags") or {}
    primary_tag = image_tags.get("Primary")
    if primary_tag and item_id:
        return _jellyfin_image_url(item_id, primary_tag)
    if series_id:
        return _jellyfin_image_url(series_id)
    return None


def _jellyfin_media_kind(raw):
    item_type = raw.get("Type") or ""
    if item_type == "Movie":
        return "movie"
    if item_type == "Episode":
        return "episode"
    return None


def _map_watch_next_item(raw, force_progress=None):
    kind = _jellyfin_media_kind(raw)
    if kind == "movie":
        if not _jellyfin_item_is_playable(raw, "Movie"):
            return None
    elif kind == "episode":
        if not _jellyfin_item_is_playable(raw, "Episode"):
            return None
    else:
        return None

    if force_progress is not None:
        progress = _clamp_progress_percent(force_progress)
    else:
        progress = _progress_percent(raw.get("UserData"), raw.get("RunTimeTicks"))
    if progress is None:
        return None

    item_id = raw.get("Id")
    if not item_id:
        return None

    last_played = (raw.get("UserData") or {}).get("LastPlayedDate") or ""
    sort_date = raw.get("DateLastContentAdded") or raw.get("DateCreated") or ""

    if kind == "movie":
        title = (raw.get("Name") or "").strip()
        if not title:
            return None
        return {
            "id": item_id,
            "parentId": None,
            "title": title,
            "subtitle": "",
            "kind": "movie",
            "image": _watch_next_image(raw),
            "playable": True,
            "progressPercent": progress,
            "_sort_last_played": last_played,
            "_sort_date": sort_date,
        }

    series_id = raw.get("SeriesId")
    title = (raw.get("SeriesName") or "").strip()
    if not series_id or not title:
        return None
    return {
        "id": item_id,
        "parentId": series_id,
        "title": title,
        "subtitle": _format_episode_subtitle(raw),
        "kind": "episode",
        "image": _watch_next_image(raw),
        "playable": True,
        "progressPercent": progress,
        "_sort_last_played": last_played,
        "_sort_date": sort_date,
        "_series_id": series_id,
    }


def _watch_next_sort_date(raw):
    return raw.get("DateLastContentAdded") or raw.get("DateCreated") or ""


def _apply_watch_next_sort_date(item, sort_date):
    if sort_date:
        item["_sort_date"] = sort_date
    elif "_sort_date" not in item:
        item["_sort_date"] = ""


def _sort_watch_next_items(items):
    items.sort(key=lambda item: item["title"].lower())
    items.sort(key=lambda item: item.get("_sort_date") or "", reverse=True)
    items.sort(key=lambda item: 0 if item["progressPercent"] > 0 else 1)


def _strip_watch_next_sort_keys(item):
    return {key: value for key, value in item.items() if not key.startswith("_")}


def _fetch_jellyfin_resume_raw():
    user_id = _jellyfin_user_id_for_queries()
    if not user_id:
        return []
    data = jellyfin_get(
        f"/Users/{user_id}/Items/Resume",
        {
            "Recursive": "true",
            "MediaTypes": "Video",
            "Fields": WATCH_NEXT_FIELDS,
            "Limit": str(JELLYFIN_PAGE_SIZE),
        },
    )
    return data.get("Items", [])


def _fetch_jellyfin_next_up_raw():
    user_id = _jellyfin_user_id_for_queries()
    if not user_id:
        return []
    data = jellyfin_get(
        "/Shows/NextUp",
        {
            "UserId": user_id,
            "Fields": WATCH_NEXT_FIELDS,
            "Limit": str(JELLYFIN_PAGE_SIZE),
        },
    )
    return data.get("Items", [])


def _fetch_jellyfin_unwatched_movies_raw():
    user_id = _jellyfin_user_id_for_queries()
    if not user_id:
        return []
    items = []
    start = 0
    while True:
        data = jellyfin_get(
            _jellyfin_items_path(),
            {
                "Recursive": "true",
                "IncludeItemTypes": "Movie",
                "Filters": "IsUnplayed",
                "StartIndex": str(start),
                "Limit": str(JELLYFIN_PAGE_SIZE),
                "SortBy": "DateCreated",
                "SortOrder": "Descending",
                "Fields": WATCH_NEXT_FIELDS,
            },
        )
        batch = [
            item for item in data.get("Items", [])
            if _jellyfin_item_is_playable(item, "Movie")
        ]
        items.extend(batch)
        total = data.get("TotalRecordCount", len(items))
        start += len(data.get("Items", []))
        if not data.get("Items") or start >= total:
            break
    return items


def _fetch_jellyfin_unplayed_series_raw():
    user_id = _jellyfin_user_id_for_queries()
    if not user_id:
        return []
    items = []
    start = 0
    while True:
        data = jellyfin_get(
            _jellyfin_items_path(),
            {
                "Recursive": "true",
                "IncludeItemTypes": "Series",
                "Filters": "IsUnplayed",
                "StartIndex": str(start),
                "Limit": str(JELLYFIN_PAGE_SIZE),
                "SortBy": "DateCreated",
                "SortOrder": "Descending",
                "Fields": WATCH_NEXT_FIELDS,
            },
        )
        items.extend(data.get("Items", []))
        total = data.get("TotalRecordCount", len(items))
        start += len(data.get("Items", []))
        if not data.get("Items") or start >= total:
            break
    return items


def _fetch_first_playable_episode_for_series(series_id):
    data = jellyfin_get(
        _jellyfin_items_path(),
        {
            "ParentId": series_id,
            "Recursive": "true",
            "IncludeItemTypes": "Episode",
            "SortBy": "ParentIndexNumber,IndexNumber",
            "SortOrder": "Ascending",
            "Fields": WATCH_NEXT_FIELDS,
            "Limit": "25",
        },
    )
    for raw in data.get("Items", []):
        if _jellyfin_item_is_playable(raw, "Episode"):
            return raw
    return None


def _merge_watch_next_episode(existing, candidate):
    if existing is None:
        return candidate
    if candidate["progressPercent"] > existing["progressPercent"]:
        return candidate
    if candidate["progressPercent"] < existing["progressPercent"]:
        return existing
    if candidate.get("_sort_last_played", "") > existing.get("_sort_last_played", ""):
        return candidate
    return existing


def _fetch_watch_next_items():
    episodes_by_series = {}
    movies = []

    for raw in _fetch_jellyfin_resume_raw():
        mapped = _map_watch_next_item(raw)
        if not mapped:
            continue
        if mapped["kind"] == "movie":
            if mapped["progressPercent"] > 0:
                movies.append(mapped)
            continue
        series_id = mapped.get("_series_id")
        if series_id:
            episodes_by_series[series_id] = _merge_watch_next_episode(
                episodes_by_series.get(series_id),
                mapped,
            )

    for raw in _fetch_jellyfin_next_up_raw():
        series_id = raw.get("SeriesId")
        if not series_id or series_id in episodes_by_series:
            continue
        mapped = _map_watch_next_item(raw, force_progress=0)
        if not mapped or mapped["kind"] != "episode":
            continue
        episodes_by_series[series_id] = mapped

    movie_ids = {movie["id"] for movie in movies}
    for raw in _fetch_jellyfin_unwatched_movies_raw():
        item_id = raw.get("Id")
        if not item_id or item_id in movie_ids:
            continue
        mapped = _map_watch_next_item(raw, force_progress=0)
        if not mapped or mapped["kind"] != "movie":
            continue
        movies.append(mapped)
        movie_ids.add(item_id)

    series_lookups = 0
    for series_raw in _fetch_jellyfin_unplayed_series_raw():
        if series_lookups >= WATCH_NEXT_UNSTARTED_SERIES_LOOKUP_LIMIT:
            break
        series_id = series_raw.get("Id")
        if not series_id or series_id in episodes_by_series:
            continue
        series_lookups += 1
        episode_raw = _fetch_first_playable_episode_for_series(series_id)
        if not episode_raw:
            continue
        mapped = _map_watch_next_item(episode_raw, force_progress=0)
        if not mapped or mapped["kind"] != "episode":
            continue
        _apply_watch_next_sort_date(mapped, _watch_next_sort_date(series_raw))
        episodes_by_series[series_id] = mapped
        if len(movies) + len(episodes_by_series) >= WATCH_NEXT_ITEM_LIMIT:
            break

    items = movies + list(episodes_by_series.values())
    _sort_watch_next_items(items)
    items = items[:WATCH_NEXT_ITEM_LIMIT]
    return {"ok": True, "items": [_strip_watch_next_sort_keys(item) for item in items]}


def _get_watch_next_payload():
    cache_key = "watch-next"
    now = time.monotonic()
    cached = _jellyfin_cache.get(cache_key)
    if cached and now - cached["ts"] < JELLYFIN_CACHE_TTL:
        return cached["payload"]

    lock = _jellyfin_lock_for(cache_key)
    with lock:
        cached = _jellyfin_cache.get(cache_key)
        if cached and now - cached["ts"] < JELLYFIN_CACHE_TTL:
            return cached["payload"]

        payload = _fetch_watch_next_items()
        _jellyfin_cache[cache_key] = {"ts": time.monotonic(), "payload": payload}
        return payload


def handle_jellyfin_watch_next(handler):
    if not JELLYFIN_API_KEY:
        send_json(handler, 503, {"ok": False, "error": "JELLYFIN_API_KEY not configured"})
        return
    try:
        send_json(handler, 200, _get_watch_next_payload())
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


# ---------------------------------------------------------------------------
# Sonarr / Radarr / Prowlarr / Bazarr
# ---------------------------------------------------------------------------

def _arr_get(base, api_key, path):
    req = urllib.request.Request(f"{base}{path}")
    req.add_header("X-Api-Key", api_key)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _arr_json(base, api_key, path, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{base}{path}", data=data, method=method)
    req.add_header("X-Api-Key", api_key)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        raise RecommendationError(detail or str(e)) from e


RADARR_ROOT_FOLDER = os.environ.get("RADARR_ROOT_FOLDER", "/data/media/movies")
SONARR_ROOT_FOLDER = os.environ.get("SONARR_ROOT_FOLDER", "/data/media/tv")
RADARR_QUALITY_PROFILE_ID = int(os.environ.get("RADARR_QUALITY_PROFILE_ID", "7"))
SONARR_QUALITY_PROFILE_ID = int(os.environ.get("SONARR_QUALITY_PROFILE_ID", "7"))


def _radarr_find_movie(tmdb_id):
    for movie in _arr_get(RADARR_URL, RADARR_API_KEY, "/api/v3/movie"):
        if movie.get("tmdbId") == tmdb_id:
            return movie
    return None


def _sonarr_find_series(tmdb_id):
    for series in _arr_get(SONARR_URL, SONARR_API_KEY, "/api/v3/series"):
        if series.get("tmdbId") == tmdb_id:
            return series
    return None


def _add_radarr_movie_unmonitored(tmdb_id):
    """Add a movie to Radarr without monitoring or searching."""
    if not RADARR_API_KEY:
        raise RecommendationError("RADARR_API_KEY not configured")
    existing = _radarr_find_movie(tmdb_id)
    if existing:
        return {
            "service": "radarr",
            "already_added": True,
            "arr_id": existing.get("id"),
            "title": existing.get("title"),
            "monitored": bool(existing.get("monitored")),
        }
    lookup = _arr_json(
        RADARR_URL,
        RADARR_API_KEY,
        f"/api/v3/movie/lookup/tmdb?tmdbId={int(tmdb_id)}",
    )
    if not isinstance(lookup, dict) or not lookup.get("tmdbId"):
        raise RecommendationError(f"Radarr lookup failed for tmdbId={tmdb_id}")
    payload = dict(lookup)
    payload["qualityProfileId"] = RADARR_QUALITY_PROFILE_ID
    payload["rootFolderPath"] = RADARR_ROOT_FOLDER
    payload["monitored"] = False
    payload["addOptions"] = {"searchForMovie": False}
    added = _arr_json(
        RADARR_URL, RADARR_API_KEY, "/api/v3/movie", method="POST", payload=payload
    )
    if not isinstance(added, dict) or not added.get("id"):
        raise RecommendationError("Radarr add returned no movie id")
    return {
        "service": "radarr",
        "already_added": False,
        "arr_id": added.get("id"),
        "title": added.get("title"),
        "monitored": bool(added.get("monitored")),
    }


def _add_sonarr_series_unmonitored(tmdb_id):
    """Add a series to Sonarr without monitoring or searching."""
    if not SONARR_API_KEY:
        raise RecommendationError("SONARR_API_KEY not configured")
    existing = _sonarr_find_series(tmdb_id)
    if existing:
        return {
            "service": "sonarr",
            "already_added": True,
            "arr_id": existing.get("id"),
            "title": existing.get("title"),
            "monitored": bool(existing.get("monitored")),
        }
    results = _arr_json(
        SONARR_URL,
        SONARR_API_KEY,
        f"/api/v3/series/lookup?term={urllib.parse.quote(f'tmdb:{int(tmdb_id)}')}",
    )
    if not isinstance(results, list) or not results:
        raise RecommendationError(f"Sonarr lookup failed for tmdbId={tmdb_id}")
    lookup = results[0]
    payload = dict(lookup)
    payload["qualityProfileId"] = SONARR_QUALITY_PROFILE_ID
    payload["rootFolderPath"] = SONARR_ROOT_FOLDER
    payload["monitored"] = False
    payload["seasonFolder"] = True
    seasons = []
    for season in payload.get("seasons") or []:
        if not isinstance(season, dict):
            continue
        row = dict(season)
        row["monitored"] = False
        seasons.append(row)
    payload["seasons"] = seasons
    payload["addOptions"] = {
        "monitor": "none",
        "searchForMissingEpisodes": False,
        "searchForCutoffUnmetEpisodes": False,
    }
    added = _arr_json(
        SONARR_URL, SONARR_API_KEY, "/api/v3/series", method="POST", payload=payload
    )
    if not isinstance(added, dict) or not added.get("id"):
        raise RecommendationError("Sonarr add returned no series id")
    return {
        "service": "sonarr",
        "already_added": False,
        "arr_id": added.get("id"),
        "title": added.get("title"),
        "monitored": bool(added.get("monitored")),
    }


def _add_to_arr_unmonitored(media_type, tmdb_id):
    kind = str(media_type or "").lower()
    if kind in ("tv", "series"):
        return _add_sonarr_series_unmonitored(tmdb_id)
    if kind == "movie":
        return _add_radarr_movie_unmonitored(tmdb_id)
    raise RecommendationError("mediaType must be movie or tv")


def _build_arr_library():
    series = {}
    movies = {}
    if SONARR_API_KEY:
        try:
            for s in _arr_get(SONARR_URL, SONARR_API_KEY, "/api/v3/series"):
                slug = s.get("titleSlug")
                title = s.get("title")
                if slug and title:
                    series[title.strip().lower()] = slug
        except Exception:
            pass
    if RADARR_API_KEY:
        try:
            for m in _arr_get(RADARR_URL, RADARR_API_KEY, "/api/v3/movie"):
                slug = m.get("titleSlug")
                title = m.get("title")
                if slug and title:
                    movies[title.strip().lower()] = slug
        except Exception:
            pass
    return {"ok": True, "series": series, "movies": movies}


def _get_arr_library():
    now = time.monotonic()
    cached = _arr_cache.get("data")
    if cached and now - _arr_cache.get("ts", 0) < ARR_CACHE_TTL:
        return cached
    with _arr_cache_lock:
        cached = _arr_cache.get("data")
        if cached and now - _arr_cache.get("ts", 0) < ARR_CACHE_TTL:
            return cached
        data = _build_arr_library()
        _arr_cache["data"] = data
        _arr_cache["ts"] = time.monotonic()
        return data


def handle_arr_library(handler):
    try:
        send_json(handler, 200, _get_arr_library())
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def _get_sonarr_missing_count():
    if not SONARR_API_KEY:
        return {"ok": False, "error": "SONARR_API_KEY not configured"}
    data = _arr_get(
        SONARR_URL,
        SONARR_API_KEY,
        "/api/v3/wanted/missing?page=1&pageSize=1",
    )
    return {"ok": True, "count": int(data.get("totalRecords", 0))}


def _get_sonarr_missing_cached():
    now = time.monotonic()
    cached = _arr_cache.get("missing")
    if cached and now - _arr_cache.get("missing_ts", 0) < ARR_CACHE_TTL:
        return cached
    with _arr_cache_lock:
        cached = _arr_cache.get("missing")
        if cached and now - _arr_cache.get("missing_ts", 0) < ARR_CACHE_TTL:
            return cached
        data = _get_sonarr_missing_count()
        _arr_cache["missing"] = data
        _arr_cache["missing_ts"] = time.monotonic()
        return data


def handle_sonarr_missing_count(handler):
    try:
        send_json(handler, 200, _get_sonarr_missing_cached())
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def _get_sonarr_series_count():
    if not SONARR_API_KEY:
        return {"ok": False, "error": "SONARR_API_KEY not configured"}
    series = _arr_get(SONARR_URL, SONARR_API_KEY, "/api/v3/series")
    monitored = sum(1 for s in series if s.get("monitored"))
    return {"ok": True, "count": int(monitored)}


def _get_sonarr_series_cached():
    now = time.monotonic()
    cached = _arr_cache.get("series_count")
    if cached and now - _arr_cache.get("series_count_ts", 0) < ARR_CACHE_TTL:
        return cached
    with _arr_cache_lock:
        cached = _arr_cache.get("series_count")
        if cached and now - _arr_cache.get("series_count_ts", 0) < ARR_CACHE_TTL:
            return cached
        data = _get_sonarr_series_count()
        _arr_cache["series_count"] = data
        _arr_cache["series_count_ts"] = time.monotonic()
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
        # Sonarr returns YYYY-MM-DD or ISO datetime.
        if "T" in air_date:
            dt = datetime.fromisoformat(air_date.replace("Z", "+00:00"))
            return dt.strftime("%b %d")
        d = date.fromisoformat(air_date[:10])
        return d.strftime("%b %d")
    except Exception:
        return air_date[:10]


def _build_sonarr_calendar():
    if not SONARR_API_KEY:
        return {"ok": False, "error": "SONARR_API_KEY not configured", "events": []}

    start = date.today()
    end = start + timedelta(days=CALENDAR_DAYS)
    path = (
        f"/api/v3/calendar?start={start.isoformat()}&end={end.isoformat()}"
        "&includeSeries=true&unmonitored=false"
    )
    episodes = _arr_get(SONARR_URL, SONARR_API_KEY, path)
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
    events = events[:CALENDAR_MAX_EVENTS]
    return {"ok": True, "events": events}


def _get_sonarr_calendar_cached():
    now = time.monotonic()
    cached = _arr_cache.get("calendar")
    if cached and now - _arr_cache.get("calendar_ts", 0) < CALENDAR_CACHE_TTL:
        return cached
    with _arr_cache_lock:
        cached = _arr_cache.get("calendar")
        if cached and now - _arr_cache.get("calendar_ts", 0) < CALENDAR_CACHE_TTL:
            return cached
        data = _build_sonarr_calendar()
        _arr_cache["calendar"] = data
        _arr_cache["calendar_ts"] = time.monotonic()
        return data


def handle_sonarr_calendar(handler):
    try:
        send_json(handler, 200, _get_sonarr_calendar_cached())
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e), "events": []})


AUTOMATION_PREVIEW_LIMIT = int(os.environ.get("AUTOMATION_PREVIEW_LIMIT", "3"))
AUTOMATION_MISSING_LIMIT = int(os.environ.get("AUTOMATION_MISSING_LIMIT", "50"))
SONARR_EXTERNAL_URL = os.environ.get("SONARR_EXTERNAL_URL", "http://localhost:8989").rstrip("/")
RADARR_EXTERNAL_URL = os.environ.get("RADARR_EXTERNAL_URL", "http://localhost:7878").rstrip("/")


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
        SONARR_URL,
        SONARR_API_KEY,
        f"/api/v3/wanted/missing?page=1&pageSize={AUTOMATION_MISSING_LIMIT}"
        "&includeSeries=true&sortKey=airDateUtc&sortDirection=descending",
    )
    items = []
    for ep in data.get("records", [])[:AUTOMATION_MISSING_LIMIT]:
        series = ep.get("series") or {}
        title = series.get("title") or ep.get("title") or "Unknown"
        code = _episode_code(ep.get("seasonNumber"), ep.get("episodeNumber"))
        label = f"{title} {code}".strip()
        slug = series.get("titleSlug")
        href = f"{SONARR_EXTERNAL_URL}/series/{slug}" if slug else None
        _sid = series.get("id") or ep.get("seriesId")
        poster_url = f"{SONARR_EXTERNAL_URL}/MediaCover/{_sid}/poster-250.jpg" if _sid else None
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
            RADARR_URL,
            RADARR_API_KEY,
            f"/api/v3/wanted/missing?page=1&pageSize={AUTOMATION_MISSING_LIMIT}"
            "&monitored=true&sortKey=title&includeMovie=true",
        )
        items = []
        for movie in data.get("records", [])[:AUTOMATION_MISSING_LIMIT]:
            title = movie.get("title") or "Unknown"
            year = movie.get("year")
            label = f"{title} ({year})" if year else title
            slug = movie.get("titleSlug")
            href = f"{RADARR_EXTERNAL_URL}/movie/{slug}" if slug else None
            mid = movie.get("id")
            poster_url = f"{RADARR_EXTERNAL_URL}/MediaCover/{mid}/poster-250.jpg" if mid else None
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
        movies = _arr_get(RADARR_URL, RADARR_API_KEY, "/api/v3/movie")
        missing = [
            m for m in movies
            if m.get("monitored") and not m.get("hasFile")
        ]
        items = []
        for movie in missing[:AUTOMATION_MISSING_LIMIT]:
            title = movie.get("title") or "Unknown"
            year = movie.get("year")
            label = f"{title} ({year})" if year else title
            slug = movie.get("titleSlug")
            href = f"{RADARR_EXTERNAL_URL}/movie/{slug}" if slug else None
            mid = movie.get("id")
            poster_url = f"{RADARR_EXTERNAL_URL}/MediaCover/{mid}/poster-250.jpg" if mid else None
            items.append(
                {
                    "label": label,
                    "titleSlug": slug,
                    "href": href,
                    "posterUrl": poster_url,
                }
            )
        return len(missing), items


def _queue_preview(base, api_key):
    data = _arr_get(
        base,
        api_key,
        f"/api/v3/queue?page=1&pageSize={AUTOMATION_PREVIEW_LIMIT}&includeUnknownSeriesItems=true"
        "&includeUnknownMovieItems=true",
    )
    items = []
    for row in data.get("records", [])[:AUTOMATION_PREVIEW_LIMIT]:
        title = row.get("title") or "Unknown"
        status = row.get("trackedDownloadStatus") or row.get("status") or ""
        timeleft = row.get("timeleft") or ""
        error = row.get("errorMessage") or ""
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
    return int(data.get("totalRecords", 0)), items


def _prowlarr_indexer_details():
    indexers = _arr_get(PROWLARR_URL, PROWLARR_API_KEY, "/api/v1/indexer")
    enabled = [i for i in indexers if i.get("enable", True)]
    disabled = [
        {"name": i.get("name") or "Unknown"}
        for i in indexers
        if not i.get("enable", True)
    ]

    cooldown = []
    try:
        statuses = _arr_get(PROWLARR_URL, PROWLARR_API_KEY, "/api/v1/indexerstatus")
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
        "disabled": disabled[:AUTOMATION_PREVIEW_LIMIT],
        "cooldown": cooldown[:AUTOMATION_PREVIEW_LIMIT],
    }


def _bazarr_wanted_langs(missing):
    langs = []
    for item in missing or []:
        code = item.get("code2") or item.get("name") or ""
        if code and code not in langs:
            langs.append(code)
    return langs


def _bazarr_wanted_details():
    ep_wanted = {"total": 0, "items": []}
    movie_wanted = {"total": 0, "items": []}

    ep = _arr_get(
        BAZARR_URL,
        BAZARR_API_KEY,
        f"/api/episodes/wanted?start=0&length={AUTOMATION_PREVIEW_LIMIT}",
    )
    total = ep.get("total")
    if total is None:
        total = ep.get("recordsTotal", 0)
    ep_wanted["total"] = int(total or 0)
    for row in (ep.get("data") or ep.get("records") or [])[:AUTOMATION_PREVIEW_LIMIT]:
        series = row.get("seriesTitle") or row.get("series") or "Unknown"
        ep_num = row.get("episode_number") or ""
        langs = _bazarr_wanted_langs(row.get("missing_subtitles"))
        label = f"{series} {ep_num}".strip()
        if langs:
            label = f"{label} · {', '.join(langs)}"
        ep_wanted["items"].append({"label": label})

    movies = _arr_get(
        BAZARR_URL,
        BAZARR_API_KEY,
        f"/api/movies/wanted?start=0&length={AUTOMATION_PREVIEW_LIMIT}",
    )
    total = movies.get("total")
    if total is None:
        total = movies.get("recordsTotal", 0)
    movie_wanted["total"] = int(total or 0)
    for row in (movies.get("data") or movies.get("records") or [])[:AUTOMATION_PREVIEW_LIMIT]:
        title = row.get("title") or "Unknown"
        langs = _bazarr_wanted_langs(row.get("missing_subtitles"))
        label = title
        if langs:
            label = f"{title} · {', '.join(langs)}"
        movie_wanted["items"].append({"label": label})

    return ep_wanted, movie_wanted


def _build_automation_summary():
    sonarr = {"ok": False}
    radarr = {"ok": False}
    prowlarr = {"ok": False}
    bazarr = None

    if SONARR_API_KEY:
        try:
            series = _arr_get(SONARR_URL, SONARR_API_KEY, "/api/v3/series")
            monitored = sum(1 for s in series if s.get("monitored"))
            missing_count, missing_items = _sonarr_missing_preview()
            queued_count, queue_items = _queue_preview(SONARR_URL, SONARR_API_KEY)
            sonarr = {
                "ok": True,
                "series": len(series),
                "monitored": monitored,
                "queued": queued_count,
                "missing": missing_count,
                "missingItems": missing_items,
                "queueItems": queue_items,
            }
        except Exception as e:
            sonarr = {"ok": False, "error": str(e)}

    if RADARR_API_KEY:
        try:
            movies = _arr_get(RADARR_URL, RADARR_API_KEY, "/api/v3/movie")
            monitored = sum(1 for m in movies if m.get("monitored"))
            missing_count, missing_items = _radarr_missing_preview()
            queued_count, queue_items = _queue_preview(RADARR_URL, RADARR_API_KEY)
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

    if PROWLARR_API_KEY:
        try:
            details = _prowlarr_indexer_details()
            prowlarr = {"ok": True, **details}
        except Exception as e:
            prowlarr = {"ok": False, "error": str(e)}

    if BAZARR_ENABLED and not BAZARR_API_KEY:
        bazarr = {
            "ok": False,
            "enabled": True,
            "configured": False,
            "error": "BAZARR_API_KEY not configured",
        }
    elif BAZARR_ENABLED:
        try:
            ep_wanted, movie_wanted = _bazarr_wanted_details()
            bazarr = {
                "ok": True,
                "enabled": True,
                "configured": True,
                "wanted": ep_wanted["total"] + movie_wanted["total"],
                "wantedEpisodes": ep_wanted["total"],
                "wantedMovies": movie_wanted["total"],
                "wantedItems": (ep_wanted["items"] + movie_wanted["items"])[
                    :AUTOMATION_PREVIEW_LIMIT
                ],
            }
        except Exception:
            try:
                _arr_get(BAZARR_URL, BAZARR_API_KEY, "/api/system/status")
                bazarr = {
                    "ok": True,
                    "enabled": True,
                    "configured": True,
                    "wanted": 0,
                    "wantedEpisodes": 0,
                    "wantedMovies": 0,
                    "wantedItems": [],
                }
            except Exception as e:
                bazarr = {"ok": False, "enabled": True, "configured": True, "error": str(e)}

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
    cached = _arr_cache.get("automation")
    if cached and now - _arr_cache.get("automation_ts", 0) < AUTOMATION_CACHE_TTL:
        return cached
    with _arr_cache_lock:
        cached = _arr_cache.get("automation")
        if cached and now - _arr_cache.get("automation_ts", 0) < AUTOMATION_CACHE_TTL:
            return cached
        data = _build_automation_summary()
        _arr_cache["automation"] = data
        _arr_cache["automation_ts"] = time.monotonic()
        return data


def handle_automation_summary(handler):
    try:
        send_json(handler, 200, _get_automation_summary_cached())
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


# ---------------------------------------------------------------------------
# System resources (container / Docker VM view — same caveat as Homepage)
# ---------------------------------------------------------------------------

def _read_cpu_times():
    try:
        with open("/proc/stat", "r", encoding="utf-8") as f:
            line = f.readline()
        parts = line.split()
        if parts[0] != "cpu":
            return None
        values = [int(x) for x in parts[1:]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
        return idle, total
    except Exception:
        return None


def _cpu_percent():
    global _cpu_prev
    cur = _read_cpu_times()
    if not cur:
        return None
    with _cpu_prev_lock:
        prev = _cpu_prev
        _cpu_prev = cur
    if not prev:
        return 0.0
    idle_d = cur[0] - prev[0]
    total_d = cur[1] - prev[1]
    if total_d <= 0:
        return 0.0
    used = 1.0 - (idle_d / total_d)
    return round(max(0.0, min(1.0, used)) * 100.0, 1)


def _mem_stats():
    try:
        info = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                key, _, rest = line.partition(":")
                info[key] = int(rest.strip().split()[0]) * 1024
        total = info.get("MemTotal", 0)
        available = info.get("MemAvailable", info.get("MemFree", 0))
        used = max(0, total - available)
        pct = round((used / total) * 100.0, 1) if total else 0.0
        return {"total": total, "used": used, "available": available, "percent": pct}
    except Exception:
        return None


def _disk_stats():
    path = DATA_PATH if os.path.exists(DATA_PATH) else "/"
    try:
        usage = shutil.disk_usage(path)
        pct = round((usage.used / usage.total) * 100.0, 1) if usage.total else 0.0
        return {
            "path": path,
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": pct,
        }
    except Exception:
        return None


def _build_system_resources():
    return {
        "ok": True,
        "cpu": {"percent": _cpu_percent()},
        "memory": _mem_stats(),
        "disk": _disk_stats(),
        "note": "CPU/RAM reflect the container/Docker VM view, same as Homepage widgets.",
    }


def _get_system_resources_cached():
    now = time.monotonic()
    cached = _arr_cache.get("resources")
    if cached and now - _arr_cache.get("resources_ts", 0) < RESOURCES_CACHE_TTL:
        return cached
    with _arr_cache_lock:
        data = _build_system_resources()
        _arr_cache["resources"] = data
        _arr_cache["resources_ts"] = time.monotonic()
        return data


def handle_system_resources(handler):
    try:
        send_json(handler, 200, _get_system_resources_cached())
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def _safe_tmp_log_path(filename):
    name = os.path.basename(str(filename or ""))
    if not name or name != filename:
        return None
    candidate = os.path.abspath(os.path.join(TMP_DIR, name))
    if candidate != TMP_DIR and not candidate.startswith(TMP_DIR + os.sep):
        return None
    return candidate


def _tail_text_file(path, max_bytes=120_000, max_lines=200):
    if not os.path.isfile(path):
        return {"exists": False, "lines": [], "size": 0, "mtime": None}
    size = os.path.getsize(path)
    mtime = datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds")
    with open(path, "rb") as f:
        if size > max_bytes:
            f.seek(-max_bytes, os.SEEK_END)
            data = f.read()
            # Drop possibly partial first line after mid-file seek.
            data = data.split(b"\n", 1)[-1] if b"\n" in data else data
        else:
            data = f.read()
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return {"exists": True, "lines": lines, "size": size, "mtime": mtime}


def _short_title(value, limit=72):
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _watchdog_detail(row):
    summary = row.get("summary") or {}
    applied = int(summary.get("applied") or 0)
    skipped = int(summary.get("skipped") or 0)
    evaluated = int(summary.get("evaluated") or 0)
    fatal = row.get("fatal")
    if fatal:
        return str(fatal)
    if applied == 0 and skipped == 0 and evaluated == 0:
        return "Nothing to check"
    if applied == 0:
        return f"Checked {evaluated}, no repairs needed"
    entries = row.get("entries") or []
    highlights = []
    for item in entries:
        if item.get("status") not in ("applied", "repaired", "deleted", "blocklisted"):
            if not item.get("action") or item.get("action") == "none":
                continue
        title = _short_title(item.get("title") or item.get("hash") or "item")
        reason = item.get("reason") or item.get("action") or "repaired"
        highlights.append(f"{title} ({reason})")
        if len(highlights) >= 3:
            break
    if highlights:
        return f"Repaired {applied}: " + "; ".join(highlights)
    return f"Repaired {applied} of {evaluated}"


def _summarize_watchdog_lines(lines):
    """Parse NDJSON watchdog lines into compact run summaries."""
    runs = []
    for line in lines:
        line = line.strip().lstrip("\ufeff")
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            runs.append(
                {
                    "status": "unparsed",
                    "detail": "Could not parse log line",
                }
            )
            continue
        summary = row.get("summary") or {}
        applied = int(summary.get("applied") or 0)
        fatal = row.get("fatal")
        status = "fatal" if fatal else ("applied" if applied > 0 else "ok")
        runs.append(
            {
                "timestamp": row.get("timestamp"),
                "exitCode": row.get("exitCode"),
                "status": status,
                "applied": applied,
                "evaluated": summary.get("evaluated"),
                "skipped": summary.get("skipped"),
                "fatal": fatal,
                "detail": _watchdog_detail(row),
            }
        )
    return runs[-50:]


def _has_real_blockers(stdout):
    """Return True only if the Blockers: section has actual items (not '(none)')."""
    in_blockers = False
    for ln in stdout:
        stripped = ln.strip()
        if stripped.lower() == "blockers:":
            in_blockers = True
            continue
        if in_blockers:
            if not stripped or stripped.lower().startswith("manual steps"):
                break
            if stripped not in ("(none)", "- (none)"):
                return True
    return False


def _summarize_text_job_lines(lines):
    """Parse Hermes text job blocks into compact run summaries."""
    runs = []
    current = None

    def finish():
        nonlocal current
        if not current:
            return
        stdout = [ln.strip() for ln in current.pop("_stdout", []) if ln.strip()]
        rc = current.get("exitCode")
        dry = current.get("dryRun")
        detail = None
        status = "ok"
        if rc not in (None, 0):
            status = "fatal"
            detail = f"Failed (exit {rc})"
        elif _has_real_blockers(stdout):
            status = "warn"
        for ln in reversed(stdout):
            low = ln.lower()
            if low.startswith("summary:"):
                detail = ln
                break
            if "no stale" in low or "nothing to" in low:
                detail = ln
                break
            if low.startswith("homepage descriptions updated"):
                detail = "Homepage storage descriptions updated"
                break
            if "phase completed" in low:
                detail = ln
                break
            if ln.startswith("[DELETE]") or ln.startswith("[KEEP]"):
                detail = ln
                break
        if not detail and stdout:
            detail = stdout[-1]
        if not detail:
            detail = "Completed"
        if dry and status == "ok":
            detail = f"Dry-run - {detail}"
        current["status"] = status
        current["detail"] = detail
        current["highlights"] = stdout[-6:]
        runs.append(current)
        current = None

    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("===="):
            finish()
            current = {"_stdout": [], "dryRun": False}
            continue
        if current is None:
            continue
        if line.startswith("timestamp="):
            # timestamp=... job=... returncode=...
            parts = {}
            for token in line.split():
                if "=" in token:
                    key, value = token.split("=", 1)
                    parts[key] = value
            current["timestamp"] = parts.get("timestamp")
            if "returncode" in parts:
                try:
                    current["exitCode"] = int(parts["returncode"])
                except ValueError:
                    current["exitCode"] = None
            continue
        if line.startswith("extra="):
            try:
                extra = json.loads(line[len("extra=") :])
                current["dryRun"] = bool(extra.get("dry_run"))
            except json.JSONDecodeError:
                pass
            continue
        if line.startswith("--- stdout ---") or line.startswith("command="):
            continue
        if line.startswith("--- stderr ---"):
            continue
        current.setdefault("_stdout", []).append(line)

    finish()
    return runs[-50:]


def handle_cron_logs(handler):
    """Return tails of Hermes repair-job logs under DATA_PATH/tmp."""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
    wanted = (query.get("id") or [None])[0]
    logs = []
    for spec in CRON_LOG_FILES:
        if wanted and wanted != spec["id"]:
            continue
        path = _safe_tmp_log_path(spec["file"])
        if not path:
            continue
        tail = _tail_text_file(path)
        entry = {
            "id": spec["id"],
            "title": spec["title"],
            "file": spec["file"],
            "format": spec["format"],
            "schedule": spec["schedule"],
            "description": spec.get("description") or "",
            "actions": list(spec.get("actions") or []),
            "exists": tail["exists"],
            "size": tail["size"],
            "mtime": tail["mtime"],
            "runs": [],
        }
        if not tail["exists"]:
            entry["summary"] = "No log file yet"
        elif not tail["lines"]:
            entry["summary"] = "Log is empty"
        elif spec["format"] == "ndjson":
            entry["runs"] = _summarize_watchdog_lines(tail["lines"])
        else:
            entry["runs"] = _summarize_text_job_lines(tail["lines"])

        if entry["runs"]:
            last = entry["runs"][-1]
            entry["summary"] = last.get("detail") or status_label_for_run(last)
            entry["lastStatus"] = last.get("status") or "ok"
        elif entry.get("summary") is None:
            entry["summary"] = "No recent runs"
            entry["lastStatus"] = "missing"
        logs.append(entry)

    send_json(
        handler,
        200,
        {
            "ok": True,
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
            "logs": logs,
            "note": "Healthy ticks stay silent in Hermes chat. This page shows readable run history.",
        },
    )


def status_label_for_run(run):
    status = (run or {}).get("status") or "ok"
    if status == "fatal":
        return "Failed"
    if status == "applied":
        return "Repaired something"
    if status == "warn":
        return "Completed with warnings"
    if status == "missing":
        return "No log yet"
    return "All clear"


# ---------------------------------------------------------------------------
# Discover / Hermes recommendations
# ---------------------------------------------------------------------------

VALID_FEEDBACK_STATUSES = frozenset({"liked", "disliked", "watched", "skipped"})


class _HermesItemNotFound(Exception):
    """Raised inside a store transaction to abort when the item is missing."""


class _StaleBaseRevision(Exception):
    """Raised inside a generation commit when the base revision is stale."""

    def __init__(self, current_revision):
        super().__init__(f"stale base_revision; current revision is {current_revision}")
        self.current_revision = current_revision


class _AlreadyReconciled(Exception):
    """Queue entry already matches the persisted Jellyseerr request id."""


class _RequestSyncConflict(Exception):
    """Stale queue entry would overwrite a newer persisted request id."""


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _hermes_items(data):
    return [item for item in data.get("items", []) if item.get("source") == "hermes"]


def _normalize_tmdb_id(value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _find_hermes_item(data, item_id):
    for item in data.get("items", []):
        if item.get("id") == item_id and item.get("source") == "hermes":
            return item
    return None


def _hermes_identity(item):
    return f"{item.get('type')}:{item.get('tmdb_id')}"


def _normalize_reconciliation_entry(entry):
    """Return a validated queue entry dict, or None if malformed."""
    if not isinstance(entry, dict):
        return None
    hermes_id = entry.get("hermes_id")
    request_id = entry.get("jellyseerr_request_id")
    if not isinstance(hermes_id, str) or not hermes_id.strip():
        return None
    if isinstance(request_id, bool) or not isinstance(request_id, int) or request_id <= 0:
        return None
    normalized = {
        "hermes_id": hermes_id.strip(),
        "jellyseerr_request_id": request_id,
    }
    queued_at = entry.get("queued_at")
    if isinstance(queued_at, str) and queued_at:
        normalized["queued_at"] = queued_at
    last_error = entry.get("last_error")
    if isinstance(last_error, str) and last_error:
        normalized["last_error"] = last_error
    return normalized


def _pending_request_sync_public():
    """Public pending-sync view: Hermes ids + Jellyseerr ids only."""
    with _reconciliation_lock:
        queue = _read_reconciliation_queue()
    pending = []
    for entry in queue:
        normalized = _normalize_reconciliation_entry(entry)
        if not normalized:
            continue
        pending.append(
            {
                "id": normalized["hermes_id"],
                "jellyseerr_request_id": normalized["jellyseerr_request_id"],
            }
        )
    return pending


def _read_reconciliation_queue():
    if not os.path.isfile(RECONCILIATION_PATH):
        return []
    try:
        with open(RECONCILIATION_PATH, encoding="utf-8-sig") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as e:
        raise RecommendationError(f"cannot read reconciliation queue: {e}") from e
    if not isinstance(raw, list):
        raise RecommendationError("reconciliation queue must be an array")
    return raw


def _write_reconciliation_queue(queue):
    directory = os.path.dirname(RECONCILIATION_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{RECONCILIATION_PATH}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(queue, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, RECONCILIATION_PATH)
    except BaseException:
        try:
            if os.path.isfile(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _enqueue_request_reconciliation(hermes_id, jellyseerr_request_id):
    entry = {
        "hermes_id": hermes_id,
        "jellyseerr_request_id": jellyseerr_request_id,
        "queued_at": utc_now(),
    }
    with _reconciliation_lock:
        queue = _read_reconciliation_queue()
        for existing in queue:
            if (
                existing.get("hermes_id") == hermes_id
                and existing.get("jellyseerr_request_id") == jellyseerr_request_id
            ):
                return False
        queue.append(entry)
        _write_reconciliation_queue(queue)
    return True


def _read_generation_request():
    """Return the on-demand Hermes generation request dict, or None."""
    if not os.path.isfile(GENERATION_REQUEST_PATH):
        return None
    try:
        with open(GENERATION_REQUEST_PATH, encoding="utf-8-sig") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as e:
        raise RecommendationError(f"cannot read generation request: {e}") from e
    if not isinstance(raw, dict):
        raise RecommendationError("generation request must be an object")
    return raw


def _write_generation_request(payload):
    """Atomically write or clear the on-demand generation request file."""
    directory = os.path.dirname(GENERATION_REQUEST_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    if payload is None:
        try:
            if os.path.isfile(GENERATION_REQUEST_PATH):
                os.unlink(GENERATION_REQUEST_PATH)
        except OSError as e:
            raise RecommendationError(f"cannot clear generation request: {e}") from e
        return
    tmp_path = f"{GENERATION_REQUEST_PATH}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, GENERATION_REQUEST_PATH)
    except BaseException:
        try:
            if os.path.isfile(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _generation_request_public():
    """Public view of a pending Hermes generation request, or None."""
    try:
        raw = _read_generation_request()
    except RecommendationError:
        return None
    if not isinstance(raw, dict) or raw.get("status") != "pending":
        return None
    requested_at = raw.get("requested_at")
    if not isinstance(requested_at, str) or not requested_at:
        return None
    return {"requested_at": requested_at, "status": "pending"}


def _clear_generation_request():
    with _generation_request_lock:
        _write_generation_request(None)


def _request_hermes_generation():
    """Queue an on-demand Hermes generation. Idempotent while pending."""
    with _generation_request_lock:
        existing = _read_generation_request()
        if isinstance(existing, dict) and existing.get("status") == "pending":
            requested_at = existing.get("requested_at")
            if isinstance(requested_at, str) and requested_at:
                return {
                    "ok": True,
                    "queued": True,
                    "already_pending": True,
                    "requested_at": requested_at,
                }
        requested_at = utc_now()
        _write_generation_request(
            {"status": "pending", "requested_at": requested_at}
        )
        return {
            "ok": True,
            "queued": True,
            "already_pending": False,
            "requested_at": requested_at,
        }


def _reconcile_pending_requests():
    with _reconciliation_lock:
        queue = _read_reconciliation_queue()
        remaining = []
        reconciled = 0
        conflicts = 0
        dropped_malformed = 0
        for entry in queue:
            normalized = _normalize_reconciliation_entry(entry)
            if not normalized:
                dropped_malformed += 1
                print(
                    "[discover-request-reconcile] dropped malformed queue entry",
                    flush=True,
                )
                continue

            hermes_id = normalized["hermes_id"]
            request_id = normalized["jellyseerr_request_id"]

            def _apply(doc, _hermes_id=hermes_id, _request_id=request_id):
                item = _find_hermes_item(doc, _hermes_id)
                if not item:
                    raise _HermesItemNotFound()
                if item.get("request_state") == "requested":
                    existing_id = item.get("jellyseerr_request_id")
                    if existing_id == _request_id:
                        raise _AlreadyReconciled()
                    if existing_id is not None and existing_id != _request_id:
                        raise _RequestSyncConflict(
                            f"hermes_id={_hermes_id!r} "
                            f"queued_jellyseerr_request_id={_request_id!r} "
                            f"persisted_jellyseerr_request_id={existing_id!r}"
                        )
                apply_request(item, request_id=_request_id)

            try:
                RECOMMENDATIONS_STORE.update(_apply)
            except _AlreadyReconciled:
                reconciled += 1
                continue
            except _RequestSyncConflict as e:
                conflicts += 1
                print(
                    "[discover-request-reconcile] stale queue entry superseded "
                    f"without overwrite ({e})",
                    flush=True,
                )
                continue
            except Exception as e:
                failed = dict(normalized)
                failed["last_error"] = type(e).__name__
                remaining.append(failed)
                continue
            reconciled += 1
        if remaining != queue:
            _write_reconciliation_queue(remaining)
        return {
            "ok": True,
            "reconciled": reconciled,
            "conflicts": conflicts,
            "dropped_malformed": dropped_malformed,
            "pending": len(remaining),
        }


def run_reconciliation_cycle():
    """Run one non-overlapping reconciliation cycle.

    Safe for startup, the periodic scheduler, the manual endpoint, and tests.
    Failed entries remain queued; overlapping calls are skipped rather than
    stacked.
    """
    if not _reconcile_cycle_lock.acquire(blocking=False):
        return {"ok": True, "skipped": True, "reason": "already_running"}
    try:
        return _reconcile_pending_requests()
    except Exception as e:
        print(
            "[discover-request-reconcile] cycle failed "
            f"error={type(e).__name__}",
            flush=True,
        )
        return {"ok": False, "error": type(e).__name__}
    finally:
        _reconcile_cycle_lock.release()


def _reconciliation_scheduler_loop(interval_seconds, stop_event, run_cycle, wait):
    """Deterministic scheduler body (injectable wait for tests)."""
    run_cycle()
    while not wait(stop_event, interval_seconds):
        run_cycle()


def start_reconciliation_scheduler(interval_seconds=None):
    """Start the single background reconciliation thread if not already running."""
    global _reconcile_thread
    interval = (
        RECONCILE_INTERVAL_SECONDS if interval_seconds is None else float(interval_seconds)
    )
    with _reconcile_thread_lock:
        if _reconcile_thread is not None and _reconcile_thread.is_alive():
            return False
        _reconcile_stop.clear()

        def _wait(event, timeout):
            return event.wait(timeout)

        def _target():
            _reconciliation_scheduler_loop(
                interval,
                _reconcile_stop,
                run_reconciliation_cycle,
                _wait,
            )

        thread = threading.Thread(
            target=_target,
            name="hermes-request-reconcile",
            daemon=True,
        )
        _reconcile_thread = thread
        thread.start()
        return True


def stop_reconciliation_scheduler(timeout=2.0):
    """Signal the scheduler to stop and join it (tests / shutdown)."""
    global _reconcile_thread
    with _reconcile_thread_lock:
        thread = _reconcile_thread
        _reconcile_stop.set()
        _reconcile_thread = None
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)
        return not thread.is_alive()
    return True


_TMDB_LIBRARY_CACHE = {"expires": 0.0, "movie": {}, "tv": {}}
_TMDB_LIBRARY_CACHE_TTL = 90.0
_TMDB_LIBRARY_CACHE_LOCK = threading.Lock()


def _provider_tmdb_id(raw):
    providers = raw.get("ProviderIds") or {}
    value = providers.get("Tmdb") or providers.get("tmdb")
    return _normalize_tmdb_id(value)


def _fetch_tmdb_map_for_type(item_type):
    mapping = {}
    start = 0
    while True:
        data = jellyfin_get(
            _jellyfin_items_path(),
            {
                "Recursive": "true",
                "IncludeItemTypes": item_type,
                "StartIndex": str(start),
                "Limit": str(JELLYFIN_PAGE_SIZE),
                "Fields": "Path,IsPlaceHolder,ProviderIds",
            },
        )
        batch = data.get("Items", [])
        for raw in batch:
            if not _jellyfin_item_is_playable(raw, item_type):
                continue
            tmdb_id = _provider_tmdb_id(raw)
            jf_id = raw.get("Id")
            if tmdb_id and jf_id and tmdb_id not in mapping:
                mapping[tmdb_id] = jf_id
        total = data.get("TotalRecordCount", start + len(batch))
        start += len(batch)
        if not batch or start >= total:
            break
    return mapping


def _tmdb_library_maps():
    if not JELLYFIN_API_KEY:
        return {"movie": {}, "tv": {}}
    now = time.time()
    with _TMDB_LIBRARY_CACHE_LOCK:
        if now < _TMDB_LIBRARY_CACHE["expires"]:
            return {
                "movie": _TMDB_LIBRARY_CACHE["movie"],
                "tv": _TMDB_LIBRARY_CACHE["tv"],
            }
        movie_map = _TMDB_LIBRARY_CACHE["movie"]
        tv_map = _TMDB_LIBRARY_CACHE["tv"]
        try:
            movie_map = _fetch_tmdb_map_for_type("Movie")
            tv_map = _fetch_tmdb_map_for_type("Series")
            _TMDB_LIBRARY_CACHE["movie"] = movie_map
            _TMDB_LIBRARY_CACHE["tv"] = tv_map
            _TMDB_LIBRARY_CACHE["expires"] = now + _TMDB_LIBRARY_CACHE_TTL
        except Exception:
            pass
        return {"movie": movie_map, "tv": tv_map}


def _enrich_hermes_library_flags(items):
    if not JELLYFIN_API_KEY or not items:
        for item in items:
            item.setdefault("in_library", False)
            item.setdefault("jellyfin_id", None)
        return items
    maps = _tmdb_library_maps()
    for item in items:
        tmdb_id = _normalize_tmdb_id(item.get("tmdb_id"))
        bucket = "tv" if (item.get("type") or "movie") == "tv" else "movie"
        jf_id = maps.get(bucket, {}).get(tmdb_id) if tmdb_id else None
        item["in_library"] = bool(jf_id)
        item["jellyfin_id"] = jf_id
    return items


def _tmdb_poster_url(poster_path):
    if not poster_path or not isinstance(poster_path, str):
        return None
    path = poster_path if poster_path.startswith("/") else f"/{poster_path}"
    return f"https://image.tmdb.org/t/p/w342{path}"


# Poster enrichment (PR 4): bounded Jellyseerr detail lookups behind a TTL
# cache. Successful paths are cached for 24h; misses and transient failures
# for 5 minutes so a brief Jellyseerr outage recovers without a restart.
POSTER_ENRICH_CONCURRENCY = 4
POSTER_CACHE_TTL_SECONDS = 24 * 60 * 60
POSTER_NEGATIVE_TTL_SECONDS = 5 * 60

# (kind, tmdb_id) -> (poster_path_or_None, monotonic expiry)
_poster_path_cache = {}
_poster_path_cache_lock = threading.Lock()


def _now():
    """Clock used for cache expiry; tests monkeypatch this with a fake clock."""
    return time.monotonic()


def _poster_cache_get(key):
    """Return (hit, value); expired entries are evicted lazily."""
    with _poster_path_cache_lock:
        entry = _poster_path_cache.get(key)
        if entry is None:
            return False, None
        value, expiry = entry
        if _now() >= expiry:
            del _poster_path_cache[key]
            return False, None
        return True, value


def _poster_cache_put(key, value, ttl):
    with _poster_path_cache_lock:
        _poster_path_cache[key] = (value, _now() + ttl)


def _fetch_poster_path(kind, tmdb_id):
    """One Jellyseerr detail call; returns the poster path or None. Raises on error."""
    payload = _jellyseerr_get(f"/api/v1/{kind}/{tmdb_id}")
    return payload.get("posterPath") or payload.get("poster_path")


def _lookup_and_cache_poster(kind, tmdb_id):
    """Fetch one poster path and cache it under the matching TTL.

    Returns (path_or_None, found). Never raises: not-found and transient
    failures are cached under the negative TTL, after which the lookup becomes
    eligible for retry.
    """
    try:
        path = _fetch_poster_path(kind, tmdb_id)
    except Exception:
        path = None
    found = isinstance(path, str) and bool(path)
    if not found:
        # Covers not-found, failures, and malformed (non-string) payloads:
        # never cache or persist anything but a real path.
        path = None
    _poster_cache_put(
        (kind, tmdb_id),
        path,
        POSTER_CACHE_TTL_SECONDS if found else POSTER_NEGATIVE_TTL_SECONDS,
    )
    return path, found


def _log_poster_batch(items, hits, fetched, failed, duration, skipped=0, reason=None):
    line = (
        f"[poster-enrich] items={items} hits={hits} fetched={fetched} "
        f"failed={failed} duration={duration:.3f}s"
    )
    if skipped:
        line += f" skipped={skipped}"
    if reason:
        line += f" reason={reason}"
    print(line, flush=True)


def _resolve_poster_paths(requests):
    """Resolve poster paths for a batch of (media_type, tmdb_id) pairs.

    Cache hits need no network call; misses are fetched through a worker pool
    bounded by POSTER_ENRICH_CONCURRENCY. Returns
    {(kind, tmdb_id): path_or_None} for every resolvable request. Never raises:
    on any failure the unresolved keys map to None (no poster).
    """
    resolved = {}
    pending = {}
    hits = 0
    for media_type, tmdb_id in requests:
        tmdb_id = _normalize_tmdb_id(tmdb_id)
        if not tmdb_id:
            continue
        kind = "tv" if media_type == "tv" else "movie"
        key = (kind, tmdb_id)
        if key in resolved or key in pending:
            continue
        hit, value = _poster_cache_get(key)
        if hit:
            resolved[key] = value
            hits += 1
        else:
            pending[key] = kind
    if not pending:
        if resolved:
            _log_poster_batch(len(resolved), hits, 0, 0, 0.0)
        return resolved

    fetched = len(pending)
    failed = 0
    if not JELLYSEERR_ENABLED or not JELLYSEERR_API_KEY:
        for key in pending:
            resolved[key] = None
        _log_poster_batch(
            hits + fetched, hits, 0, 0, 0.0, skipped=fetched, reason="no-api-key"
        )
        return resolved

    started = time.monotonic()

    def _worker(item):
        key, kind = item
        path, found = _lookup_and_cache_poster(kind, key[1])
        return key, path, found

    try:
        with ThreadPoolExecutor(
            max_workers=POSTER_ENRICH_CONCURRENCY,
            thread_name_prefix="poster-enrich",
        ) as pool:
            for key, path, found in pool.map(_worker, pending.items()):
                resolved[key] = path
                if not found:
                    failed += 1
    except Exception as e:
        # Degrade, never fail the caller: unresolved keys get no poster.
        print(f"[poster-enrich] batch aborted: {e}", flush=True)
        for key in pending:
            resolved.setdefault(key, None)
        return resolved
    _log_poster_batch(hits + fetched, hits, fetched, failed, time.monotonic() - started)
    return resolved


def _jellyseerr_poster_path(media_type, tmdb_id):
    """Single cached lookup kept for non-batched callers (Trakt mapping)."""
    tmdb_id = _normalize_tmdb_id(tmdb_id)
    if not tmdb_id or not JELLYSEERR_ENABLED or not JELLYSEERR_API_KEY:
        return None
    kind = "tv" if media_type == "tv" else "movie"
    hit, value = _poster_cache_get((kind, tmdb_id))
    if hit:
        return value
    path, _found = _lookup_and_cache_poster(kind, tmdb_id)
    return path


def _poster_url_for_item(item):
    """Derive a poster URL from data already on the item; no network calls."""
    existing = item.get("poster_url")
    if existing:
        return existing
    jf_id = item.get("jellyfin_id")
    if jf_id:
        return _jellyfin_image_url(jf_id)
    return _tmdb_poster_url(item.get("poster_path"))


def _enrich_hermes_posters(items):
    """Fill poster_url on Hermes items.

    Items that already carry poster_url/poster_path (or a Jellyfin ID) need no
    network call; the remaining misses are resolved in one bounded batch.
    Failures degrade to no-poster items — the frontend recovers on its own.
    """
    pending = []
    for item in items:
        url = _poster_url_for_item(item)
        if url:
            item["poster_url"] = url
        else:
            pending.append(item)
    if not pending:
        return items
    resolved = _resolve_poster_paths(
        [(item.get("type"), item.get("tmdb_id")) for item in pending]
    )
    for item in pending:
        kind = "tv" if item.get("type") == "tv" else "movie"
        key = (kind, _normalize_tmdb_id(item.get("tmdb_id")))
        item["poster_url"] = _tmdb_poster_url(resolved.get(key))
    return items



def jellyfin_post(path, query=None, method="POST"):
    url = f"{JELLYFIN_URL}{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, method=method)
    req.add_header("X-Emby-Token", JELLYFIN_API_KEY)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        if resp.status == 204:
            return {}
        body = resp.read()
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))


def _jellyfin_id_for_tmdb(media_type, tmdb_id):
    tmdb_id = _normalize_tmdb_id(tmdb_id)
    if not tmdb_id or not JELLYFIN_API_KEY:
        return None
    bucket = "tv" if media_type == "tv" else "movie"
    maps = _tmdb_library_maps()
    cached = maps.get(bucket, {}).get(tmdb_id)
    if cached:
        return cached
    item_type = "Series" if media_type == "tv" else "Movie"
    provider_key = f"tmdb.{tmdb_id}"
    try:
        data = jellyfin_get(
            _jellyfin_items_path(),
            {
                "Recursive": "true",
                "IncludeItemTypes": item_type,
                "AnyProviderIdEquals": provider_key,
                "Limit": "10",
                "Fields": "Path,IsPlaceHolder",
            },
        )
        for raw in data.get("Items", []):
            if _jellyfin_item_is_playable(raw, item_type):
                return raw.get("Id")
    except Exception:
        return None
    return None


def _find_hermes_collection_id():
    try:
        data = jellyfin_get(
            _jellyfin_items_path(),
            {
                "Recursive": "true",
                "IncludeItemTypes": "BoxSet",
                "SearchTerm": HERMES_COLLECTION_NAME,
                "Limit": "20",
            },
        )
        for item in data.get("Items", []):
            if item.get("Name") == HERMES_COLLECTION_NAME:
                return item.get("Id")
    except Exception:
        return None
    return None


def _collection_item_ids(collection_id):
    try:
        data = jellyfin_get(
            f"/Items/{collection_id}/Children",
            {"Fields": "Path"},
        )
        ids = []
        for item in data.get("Items", []):
            path = item.get("Path") or ""
            if "jellynext-virtual" in path:
                continue
            if item.get("Id"):
                ids.append(item["Id"])
        return ids
    except Exception:
        return []


def sync_hermes_collection():
    if not JELLYFIN_API_KEY:
        raise RuntimeError("JELLYFIN_API_KEY not configured")

    data = RECOMMENDATIONS_STORE.load()

    target_ids = []
    for item in _hermes_items(data):
        if item.get("feedback") in ("disliked", "skipped"):
            continue
        jf_id = item.get("jellyfin_id") if item.get("in_library") else None
        if not jf_id:
            jf_id = _jellyfin_id_for_tmdb(item.get("type"), item.get("tmdb_id"))
        if jf_id:
            target_ids.append(jf_id)

    target_ids = list(dict.fromkeys(target_ids))
    collection_id = _find_hermes_collection_id()

    if not target_ids:
        if collection_id:
            current = _collection_item_ids(collection_id)
            if current:
                jellyfin_post(
                    f"/Collections/{collection_id}/Items",
                    {"ids": ",".join(current)},
                    method="DELETE",
                )
        return {"ok": True, "collectionId": collection_id, "added": 0, "removed": 0, "total": 0}

    if not collection_id:
        created = jellyfin_post(
            "/Collections",
            {"name": HERMES_COLLECTION_NAME, "ids": ",".join(target_ids)},
        )
        collection_id = created.get("Id")
        return {
            "ok": True,
            "collectionId": collection_id,
            "added": len(target_ids),
            "removed": 0,
            "total": len(target_ids),
        }

    current = _collection_item_ids(collection_id)
    to_add = [item_id for item_id in target_ids if item_id not in current]
    to_remove = [item_id for item_id in current if item_id not in target_ids]

    if to_add:
        jellyfin_post(
            f"/Collections/{collection_id}/Items",
            {"ids": ",".join(to_add)},
        )
    if to_remove:
        jellyfin_post(
            f"/Collections/{collection_id}/Items",
            {"ids": ",".join(to_remove)},
            method="DELETE",
        )

    return {
        "ok": True,
        "collectionId": collection_id,
        "added": len(to_add),
        "removed": len(to_remove),
        "total": len(target_ids),
    }


def _sync_hermes_collection_best_effort():
    if not JELLYFIN_API_KEY:
        return None
    try:
        return sync_hermes_collection()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def handle_discover_hermes_get(handler):
    try:
        data = RECOMMENDATIONS_STORE.load()
    except RecommendationError as e:
        send_json(handler, 500, {"ok": False, "error": f"Store load failed: {e}"})
        return
    items = _enrich_hermes_posters(
        _enrich_hermes_library_flags(
            [_hermes_item_for_client(item) for item in _hermes_items(data)]
        )
    )
    send_json(
        handler,
        200,
        {
            "ok": True,
            "version": data.get("version", 3),
            "revision": data.get("revision", 0),
            "updated_at": data.get("updated_at", ""),
            "presented_media_ids": data.get("presented_media_ids", []),
            "pending_request_sync": _pending_request_sync_public(),
            "generation_request": _generation_request_public(),
            "context": _hermes_generation_context(data),
            "items": items,
        },
    )


def handle_discover_hermes_patch(handler, item_id):
    try:
        body = _read_json_body(handler)
    except _BodyTooLarge:
        send_json(handler, 413, {"ok": False, "error": "Request body too large"})
        return
    except json.JSONDecodeError:
        send_json(handler, 400, {"ok": False, "error": "Invalid JSON body"})
        return

    status = (body.get("status") or "").strip()
    # PATCH writes feedback only. Request lifecycle is owned by
    # POST /discover/request so a feedback call can never fabricate a
    # request_state=requested annotation without a real Jellyseerr request.
    if status not in VALID_FEEDBACK_STATUSES - {"suggested", "requested"}:
        send_json(handler, 400, {"ok": False, "error": "Invalid feedback status"})
        return

    def _apply(doc):
        item = _find_hermes_item(doc, item_id)
        if not item:
            raise _HermesItemNotFound()
        # Feedback and request state are independent dimensions: a feedback
        # write never clears request fields, a request write keeps feedback.
        apply_feedback(item, status)
        if "notes" in body:
            item["notes"] = body.get("notes") or ""

    try:
        RECOMMENDATIONS_STORE.update(_apply)
    except _HermesItemNotFound:
        send_json(handler, 404, {"ok": False, "error": "Item not found"})
        return
    except RecommendationError as e:
        send_json(handler, 500, {"ok": False, "error": f"Store rejected update: {e}"})
        return

    payload = {"ok": True, "id": item_id, "status": status}
    send_json(handler, 200, payload)


def handle_discover_hermes_post(handler):
    # Retired in PR 2: this unrestricted upsert could create or reactivate
    # items without checking the deny list or holding a base revision, so it
    # bypassed the never-twice invariant. Item creation/activation now happens
    # exclusively through POST /discover/hermes/generations. Feedback and
    # requests still use PATCH /discover/hermes/{id} and POST /discover/request.
    send_json(
        handler,
        410,
        {
            "ok": False,
            "error": "Endpoint retired: direct item upserts are no longer accepted",
            "use": "POST /discover/hermes/generations",
        },
    )


def _validate_generation_candidate(raw, index):
    """Normalize one generation candidate. Returns (candidate, rejection).

    ``candidate`` is a dict with type/title/year/tmdb_id/identity/reason/retain on
    success; ``rejection`` is a machine-readable entry for the response on
    failure. Exactly one of the two is non-None.
    """
    if not isinstance(raw, dict):
        return None, {"index": index, "reason": "invalid_candidate", "detail": "expected object"}
    tmdb_id = raw.get("tmdb_id")
    label = {"index": index}
    if raw.get("type") in ITEM_TYPES and _is_int(tmdb_id) and tmdb_id > 0:
        label["identity"] = media_identity(raw["type"], tmdb_id)
    if _is_int(tmdb_id):
        label["tmdb_id"] = tmdb_id
    errors = []
    if raw.get("type") not in ITEM_TYPES:
        errors.append(f"type must be one of {list(ITEM_TYPES)}")
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("title must be a non-empty string")
    if not _is_int(tmdb_id) or tmdb_id <= 0:
        errors.append("tmdb_id must be a positive integer")
    year = raw.get("year")
    if year is not None and not _is_int(year):
        errors.append("year must be an integer or null")
    reason = raw.get("reason", "")
    if not isinstance(reason, str):
        errors.append("reason must be a string")
    retain = raw.get("retain", False)
    if not isinstance(retain, bool):
        errors.append("retain must be a boolean")
    if errors:
        label.update({"reason": "invalid_candidate", "detail": "; ".join(errors)})
        return None, label
    return (
        {
            "index": index,
            "type": raw["type"],
            "title": title.strip(),
            "year": year,
            "tmdb_id": tmdb_id,
            "reason": reason,
            "retain": retain,
        },
        None,
    )


def _is_untouched_hermes_item(item):
    """True when the user has not given feedback or requested the title."""
    return item.get("feedback") is None and item.get("request_state") is None


def _should_auto_retain_hermes_item(item):
    """True when omission must not rotate the active item to history.

    Only untouched picks (no feedback, no request) are protected. Liked,
    disliked, watched, skipped, and requested actives may rotate when omitted
    so feedbacked titles settle in History.
    """
    return _is_untouched_hermes_item(item)


HERMES_TASTE_CAP = 50
TRACKED_MEDIA_CACHE_TTL = float(os.environ.get("TRACKED_MEDIA_CACHE_TTL", "60"))
_tracked_media_cache = {"expires": 0.0, "ids": []}
_tracked_media_cache_lock = threading.Lock()


def _build_tracked_media_ids():
    """Return sorted movie:/tv: identities currently in Radarr/Sonarr."""
    ids = set()
    errors = []
    if RADARR_API_KEY:
        try:
            for movie in _arr_get(RADARR_URL, RADARR_API_KEY, "/api/v3/movie"):
                tmdb_id = _normalize_tmdb_id(movie.get("tmdbId"))
                if tmdb_id:
                    ids.add(f"movie:{tmdb_id}")
        except Exception as e:
            errors.append(f"radarr: {e}")
    if SONARR_API_KEY:
        try:
            for series in _arr_get(SONARR_URL, SONARR_API_KEY, "/api/v3/series"):
                tmdb_id = _normalize_tmdb_id(series.get("tmdbId"))
                if tmdb_id:
                    ids.add(f"tv:{tmdb_id}")
        except Exception as e:
            errors.append(f"sonarr: {e}")
    return sorted(ids), errors


def _get_tracked_media_ids():
    """Cached Arr tracked identities; soft-fail to empty on errors."""
    now = time.monotonic()
    with _tracked_media_cache_lock:
        if now < _tracked_media_cache["expires"]:
            return list(_tracked_media_cache["ids"]), []
    ids, errors = _build_tracked_media_ids()
    with _tracked_media_cache_lock:
        _tracked_media_cache["ids"] = list(ids)
        # Cache successes longer; on errors keep a short empty cache so polls
        # do not hammer a down Arr, but recover within the TTL window.
        ttl = TRACKED_MEDIA_CACHE_TTL if not errors else min(TRACKED_MEDIA_CACHE_TTL, 15.0)
        _tracked_media_cache["expires"] = time.monotonic() + ttl
        return list(_tracked_media_cache["ids"]), errors


def _in_library_media_ids_from_maps(maps):
    ids = []
    for kind in ("movie", "tv"):
        for tmdb_id in (maps or {}).get(kind, {}):
            normalized = _normalize_tmdb_id(tmdb_id)
            if normalized:
                ids.append(f"{kind}:{normalized}")
    return sorted(set(ids))


def _get_in_library_media_ids():
    """Jellyfin-backed playable identities; soft-fail to empty."""
    if not JELLYFIN_API_KEY:
        return [], []
    try:
        maps = _tmdb_library_maps()
        return _in_library_media_ids_from_maps(maps), []
    except Exception as e:
        return [], [f"jellyfin: {e}"]


def _hermes_required_retain(items):
    """Active identities Hermes must keep (untouched only)."""
    retain = []
    for item in items:
        if not item.get("active"):
            continue
        if not _should_auto_retain_hermes_item(item):
            continue
        identity = item.get("identity") or _hermes_identity(item)
        if identity:
            retain.append(identity)
    return retain


def _hermes_item_for_client(item):
    """Project store rows for Discover clients.

    Feedbacked titles always read as inactive so they appear in History even
    when a legacy row still has active=true in the store.
    """
    projected = dict(item)
    if projected.get("feedback") is not None:
        projected["active"] = False
    return projected


def _hermes_taste_entry(item):
    return {
        "identity": item.get("identity") or _hermes_identity(item),
        "title": item.get("title"),
        "type": item.get("type"),
        "year": item.get("year"),
    }


def _hermes_taste_summary(items, cap=HERMES_TASTE_CAP):
    buckets = {
        "liked": [],
        "disliked": [],
        "skipped": [],
        "watched": [],
    }
    for item in items:
        feedback = item.get("feedback")
        if feedback not in buckets:
            continue
        entry = _hermes_taste_entry(item)
        if len(buckets[feedback]) < cap:
            buckets[feedback].append(entry)
        # Liked also counts as watched for History / taste consumers.
        if feedback == "liked" and len(buckets["watched"]) < cap:
            identity = entry["identity"]
            if not any(existing["identity"] == identity for existing in buckets["watched"]):
                buckets["watched"].append(entry)
    return buckets


def _hermes_exclusion_sets():
    """Live exclude sets for generation commits (fresh enough via caches)."""
    tracked, tracked_errors = _get_tracked_media_ids()
    in_library, library_errors = _get_in_library_media_ids()
    return set(tracked), set(in_library), tracked_errors + library_errors


def _hermes_generation_context(data):
    """Server-built helpers so Hermes need not curl Arr/Jellyfin itself."""
    items = list(_hermes_items(data))
    tracked, tracked_errors = _get_tracked_media_ids()
    in_library, library_errors = _get_in_library_media_ids()
    errors = tracked_errors + library_errors
    context = {
        "tracked_media_ids": tracked,
        "in_library_media_ids": in_library,
        "required_retain": _hermes_required_retain(items),
        "taste": _hermes_taste_summary(items),
    }
    if errors:
        context["context_errors"] = errors
    return context


def handle_discover_hermes_generations(handler):
    """Commit one Hermes generation: the only writer of recommendation items.

    Candidates with ``retain: true`` keep an already-active item active; any
    other candidate whose composite identity is already in
    ``presented_media_ids`` is rejected (never-twice). New candidates already in
    Sonarr/Radarr or Jellyfin are rejected as ``already_tracked`` /
    ``already_in_library``. Active items omitted from the batch are rotated
    to history with all feedback/request fields preserved — **except** untouched
    actives, which are auto-retained so Hermes cannot hide titles the user has
    not finished with. Liked/watched/disliked/skipped settle in History.
    The whole commit
    — acceptances, rotations, deny-list appends — is one store transaction,
    and a stale ``base_revision`` aborts with HTTP 409 before any change.
    """
    try:
        body = _read_json_body(handler)
    except _BodyTooLarge:
        send_json(handler, 413, {"ok": False, "error": "Request body too large"})
        return
    except json.JSONDecodeError:
        send_json(handler, 400, {"ok": False, "error": "Invalid JSON body"})
        return
    if not isinstance(body, dict):
        send_json(handler, 400, {"ok": False, "error": "Expected a JSON object body"})
        return

    base_revision = body.get("base_revision")
    if not _is_int(base_revision):
        send_json(handler, 400, {"ok": False, "error": "base_revision must be an integer"})
        return
    raw_candidates = body.get("candidates")
    if not isinstance(raw_candidates, list):
        send_json(handler, 400, {"ok": False, "error": "candidates must be an array"})
        return
    if len(raw_candidates) > 100:
        send_json(
            handler, 400, {"ok": False, "error": "candidates must not exceed 100 items"}
        )
        return

    candidates = []
    rejected = []
    batch_seen = set()
    for index, raw in enumerate(raw_candidates):
        candidate, rejection = _validate_generation_candidate(raw, index)
        if rejection is not None:
            rejected.append(rejection)
            continue
        candidate["identity"] = media_identity(candidate["type"], candidate["tmdb_id"])
        if candidate["identity"] in batch_seen:
            rejected.append(
                {
                    "index": index,
                    "identity": candidate["identity"],
                    "tmdb_id": candidate["tmdb_id"],
                    "reason": "duplicate_in_batch",
                }
            )
            continue
        batch_seen.add(candidate["identity"])
        candidates.append(candidate)

    # Preparation phase: resolve posters for the batch BEFORE the locked
    # commit so the transaction stays short. Successful paths are persisted
    # on newly accepted items; failures leave poster_path unset and become
    # eligible for retry after the negative TTL.
    try:
        candidate_posters = _resolve_poster_paths(
            [(c["type"], c["tmdb_id"]) for c in candidates]
        )
    except Exception as e:
        print(f"[poster-enrich] generation preparation failed: {e}", flush=True)
        candidate_posters = {}

    tracked_set, in_library_set, exclusion_errors = _hermes_exclusion_sets()
    if exclusion_errors:
        print(
            f"[hermes-generations] exclusion context degraded: {exclusion_errors}",
            flush=True,
        )

    result = {}

    def _apply(doc):
        current_revision = doc.get("revision", 0)
        if current_revision != base_revision:
            raise _StaleBaseRevision(current_revision)

        presented = doc.setdefault("presented_media_ids", [])
        presented_set = set(presented)
        active_by_identity = {}
        existing_ids = set()
        for item in doc.get("items", []):
            if item.get("source") != "hermes":
                continue
            identity = item.get("identity") or _hermes_identity(item)
            existing_ids.add(identity)
            if item.get("active"):
                active_by_identity[identity] = item

        accepted = []
        retained = []
        touched = set()
        now = utc_now()
        for candidate in candidates:
            tmdb_id = candidate["tmdb_id"]
            identity = candidate["identity"]
            existing = active_by_identity.get(identity)
            if existing is not None:
                if not candidate["retain"]:
                    rejected.append(
                        {
                            "index": candidate["index"],
                            "identity": identity,
                            "tmdb_id": tmdb_id,
                            "reason": "already_active",
                        }
                    )
                    # The item was named in the batch: the rejection means
                    # "no change", not "rotate it out".
                    touched.add(identity)
                    continue
                # Explicit retain: refresh descriptive fields only. Feedback,
                # request state, timestamps and Jellyseerr identifiers are
                # preserved untouched.
                existing["type"] = candidate["type"]
                existing["title"] = candidate["title"]
                if candidate["year"] is not None:
                    existing["year"] = candidate["year"]
                existing["reason"] = candidate["reason"]
                retained.append(identity)
                touched.add(identity)
            elif identity in presented_set or f"legacy:{tmdb_id}" in presented_set or identity in existing_ids:
                # Deny-list check, plus a defensive one: store-produced
                # documents keep both in sync, but a hand-edited file could
                # hold an inactive item row whose ID is missing from
                # presented_media_ids — never accept a duplicate Hermes
                # composite identity. Legacy tombstones conservatively block
                # both movie:<id> and tv:<id>.
                rejected.append(
                    {
                        "index": candidate["index"],
                        "identity": identity,
                        "tmdb_id": tmdb_id,
                        "reason": "already_presented",
                    }
                )
            elif identity in tracked_set:
                rejected.append(
                    {
                        "index": candidate["index"],
                        "identity": identity,
                        "tmdb_id": tmdb_id,
                        "reason": "already_tracked",
                    }
                )
            elif identity in in_library_set:
                rejected.append(
                    {
                        "index": candidate["index"],
                        "identity": identity,
                        "tmdb_id": tmdb_id,
                        "reason": "already_in_library",
                    }
                )
            else:
                item = {
                    "id": f"hermes-{identity.replace(':', '-')}",
                    "identity": identity,
                    "source": "hermes",
                    "type": candidate["type"],
                    "title": candidate["title"],
                    "year": candidate["year"],
                    "tmdb_id": tmdb_id,
                    "reason": candidate["reason"],
                    "active": True,
                    "feedback": None,
                    "feedback_at": None,
                    "request_state": None,
                    "requested_at": None,
                    "jellyseerr_request_id": None,
                    "added_at": now,
                }
                kind = "tv" if candidate["type"] == "tv" else "movie"
                poster_path = candidate_posters.get((kind, tmdb_id))
                if poster_path:
                    # Persisted so warm reads need no Jellyseerr call;
                    # poster_url stays derived, never stored.
                    item["poster_path"] = poster_path
                doc.setdefault("items", []).append(item)
                presented.append(identity)
                presented_set.add(identity)
                accepted.append({"identity": identity, "tmdb_id": tmdb_id, "id": item["id"]})
                touched.add(identity)

        rotated = []
        for item in doc.get("items", []):
            if (
                item.get("source") == "hermes"
                and item.get("active")
                and (item.get("identity") or _hermes_identity(item)) not in touched
            ):
                identity = item.get("identity") or _hermes_identity(item)
                # Hard rule: never rotate untouched actives.
                if _should_auto_retain_hermes_item(item):
                    retained.append(identity)
                    continue
                item["active"] = False
                rotated.append(identity)

        result.update(accepted=accepted, retained=retained, rotated=rotated)

    try:
        committed = RECOMMENDATIONS_STORE.update(_apply)
    except _StaleBaseRevision as e:
        send_json(
            handler,
            409,
            {
                "ok": False,
                "error": "stale_base_revision",
                "current_revision": e.current_revision,
            },
        )
        return
    except RecommendationError as e:
        send_json(handler, 500, {"ok": False, "error": f"Store rejected generation: {e}"})
        return

    try:
        _clear_generation_request()
    except RecommendationError as e:
        print(
            f"[discover-hermes] generation committed but failed to clear "
            f"on-demand request: {e}",
            flush=True,
        )

    send_json(
        handler,
        200,
        {
            "ok": True,
            "revision": committed.get("revision"),
            "accepted": result["accepted"],
            "retained": result["retained"],
            "rotated": result["rotated"],
            "rejected": rejected,
        },
    )


def handle_discover_hermes_sync(handler):
    if _reject_mutating(handler):
        return
    try:
        result = sync_hermes_collection()
        send_json(handler, 200, result)
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def handle_discover_hermes_request_more(handler):
    """Queue an on-demand Hermes generation for the next agent run."""
    if _reject_mutating(handler):
        return
    try:
        result = _request_hermes_generation()
    except RecommendationError as e:
        send_json(handler, 500, {"ok": False, "error": str(e)})
        return
    send_json(handler, 200, result)


def _jellyseerr_get(path):
    if not JELLYSEERR_ENABLED or not JELLYSEERR_API_KEY:
        raise RuntimeError("JELLYSEERR_API_KEY not configured")
    req = urllib.request.Request(f"{JELLYSEERR_URL}{path}")
    req.add_header("X-Api-Key", JELLYSEERR_API_KEY)
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _map_jellyseerr_result(raw):
    media_type = (raw.get("mediaType") or raw.get("media_type") or "movie").lower()
    item_type = "tv" if media_type in ("tv", "series") else "movie"
    tmdb_id = _normalize_tmdb_id(
        raw.get("id") or raw.get("tmdbId") or (raw.get("mediaInfo") or {}).get("tmdbId")
    )
    title = raw.get("title") or raw.get("name") or ""
    year = raw.get("releaseDate") or raw.get("firstAirDate") or raw.get("release_date")
    if isinstance(year, str) and len(year) >= 4:
        try:
            year = int(year[:4])
        except ValueError:
            year = None
    overview = raw.get("overview") or ""
    poster_path = raw.get("posterPath") or raw.get("poster_path")
    return {
        "id": f"seerr-{item_type}-{tmdb_id}",
        "source": "jellyseerr",
        "type": item_type,
        "title": title,
        "year": year if isinstance(year, int) else None,
        "tmdb_id": tmdb_id,
        "overview": overview,
        "poster_path": poster_path,
        "poster_url": _tmdb_poster_url(poster_path),
        "rating": raw.get("voteAverage"),
    }


def handle_discover_jellyseerr(handler, query):
    kind = (query.get("kind") or ["trending"])[0]
    paths = {
        "trending": "/api/v1/discover/trending",
        "movies": "/api/v1/discover/movies",
        "tv": "/api/v1/discover/tv",
    }
    path = paths.get(kind, paths["trending"])
    if not JELLYSEERR_ENABLED or not JELLYSEERR_API_KEY:
        send_json(handler, 200, {"ok": True, "enabled": False, "items": []})
        return
    try:
        payload = _jellyseerr_get(path)
        results = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(results, list):
            results = []
        items = [_map_jellyseerr_result(item) for item in results if item]
        send_json(
            handler,
            200,
            {
                "ok": True,
                "generatedAt": datetime.now().isoformat(timespec="seconds"),
                "items": items,
            },
        )
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def _trakt_get(path):
    if not TRAKT_CLIENT_ID or not TRAKT_ACCESS_TOKEN:
        raise RuntimeError("Trakt OAuth not configured")
    req = urllib.request.Request(f"https://api.trakt.tv{path}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "media-stack-dashboard/1.0")
    req.add_header("trakt-api-version", "2")
    req.add_header("trakt-api-key", TRAKT_CLIENT_ID)
    req.add_header("Authorization", f"Bearer {TRAKT_ACCESS_TOKEN}")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _map_trakt_result(raw, item_type):
    if item_type == "shows":
        show = raw if raw.get("title") else raw.get("show") or raw
        ids = show.get("ids") or {}
        year = show.get("year")
        title = show.get("title") or ""
        overview = show.get("overview") or ""
        media_type = "tv"
        images = show.get("images") or raw.get("images") or {}
    else:
        movie = raw if raw.get("title") else raw.get("movie") or raw
        ids = movie.get("ids") or {}
        year = movie.get("year")
        title = movie.get("title") or ""
        overview = movie.get("overview") or ""
        media_type = "movie"
        images = movie.get("images") or raw.get("images") or {}
    tmdb_id = _normalize_tmdb_id(ids.get("tmdb"))
    poster_url = None
    posters = images.get("poster") or []
    if posters:
        # Trakt may return full URLs or paths; normalize to https.
        first = posters[0]
        if isinstance(first, str):
            poster_url = first if first.startswith("http") else f"https://{first.lstrip('/')}"
        elif isinstance(first, dict):
            poster_url = first.get("full") or first.get("thumb") or first.get("url")
    if not poster_url:
        poster_url = _tmdb_poster_url(_jellyseerr_poster_path(media_type, tmdb_id))
    rating = raw.get("rating") or (show.get("rating") if "show" in locals() else movie.get("rating") if "movie" in locals() else None)
    return {
        "id": f"trakt-{media_type}-{tmdb_id}",
        "source": "trakt",
        "type": media_type,
        "title": title,
        "year": year,
        "tmdb_id": tmdb_id,
        "overview": overview,
        "poster_url": poster_url,
        "rating": rating,
    }


def handle_discover_trakt(handler, query):
    media_type = (query.get("type") or ["movies"])[0]
    if media_type not in ("movies", "shows"):
        media_type = "movies"
    if not TRAKT_CLIENT_ID or not TRAKT_ACCESS_TOKEN:
        send_json(handler, 503, {"ok": False, "error": "Trakt OAuth not configured"})
        return
    try:
        results = _trakt_get(
            f"/recommendations/{media_type}?limit=25&ignore_collected=true&extended=full,images"
        )
        items = [_map_trakt_result(item, media_type) for item in results if item]
        send_json(
            handler,
            200,
            {
                "ok": True,
                "generatedAt": datetime.now().isoformat(timespec="seconds"),
                "items": items,
            },
        )
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})


def handle_discover_request(handler):
    if _reject_mutating(handler):
        return
    try:
        body = _read_json_body(handler)
    except _BodyTooLarge:
        send_json(handler, 413, {"ok": False, "error": "Request body too large"})
        return
    except json.JSONDecodeError:
        send_json(handler, 400, {"ok": False, "error": "Invalid JSON body"})
        return

    if not isinstance(body, dict):
        send_json(handler, 400, {"ok": False, "error": "Expected a JSON object body"})
        return

    media_type = body.get("mediaType")
    media_id = _normalize_tmdb_id(body.get("mediaId"))
    if not media_type or not media_id:
        send_json(handler, 400, {"ok": False, "error": "mediaType and mediaId required"})
        return

    hermes_id = body.get("hermesId")
    if hermes_id:
        try:
            current = RECOMMENDATIONS_STORE.load()
        except RecommendationError as e:
            send_json(handler, 500, {"ok": False, "error": f"Store load failed: {e}"})
            return
        item = _find_hermes_item(current, hermes_id)
        if not item:
            send_json(handler, 404, {"ok": False, "error": "Hermes item not found"})
            return
        expected_type = "tv" if str(media_type).lower() in ("tv", "series") else "movie"
        if item.get("type") != expected_type or item.get("tmdb_id") != media_id:
            send_json(
                handler,
                400,
                {"ok": False, "error": "Hermes item does not match the requested media"},
            )
            return

    try:
        arr_result = _add_to_arr_unmonitored(media_type, media_id)
    except RecommendationError as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})
        return
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})
        return

    arr_id = arr_result.get("arr_id")
    dashboard_state_persisted = True
    reconciliation_queued = False
    if hermes_id:
        def _apply(doc):
            item = _find_hermes_item(doc, hermes_id)
            if not item:
                raise _HermesItemNotFound()
            # Request fields only; feedback is preserved. Store the *arr id in
            # jellyseerr_request_id for durable tracing of the add.
            apply_request(item, request_id=arr_id)

        try:
            RECOMMENDATIONS_STORE.update(_apply)
        except Exception as e:
            dashboard_state_persisted = False
            persistence_error = type(e).__name__
            try:
                _enqueue_request_reconciliation(hermes_id, arr_id)
                reconciliation_queued = True
            except Exception as queue_error:
                reconciliation_queued = False
                print(
                    "[discover-request] reconciliation enqueue failed "
                    f"hermes_id={hermes_id!r} "
                    f"arr_id={arr_id!r} "
                    f"error={type(queue_error).__name__}",
                    flush=True,
                )
            print(
                "[discover-request] Arr add succeeded but dashboard state "
                "persistence diverged "
                f"hermes_id={hermes_id!r} "
                f"arr_id={arr_id!r} "
                f"error={persistence_error}",
                flush=True,
            )

    if not dashboard_state_persisted:
        send_json(
            handler,
            200,
            {
                "ok": True,
                "partial_success": True,
                "jellyseerr_request_id": arr_id,
                "arr_id": arr_id,
                "service": arr_result.get("service"),
                "already_added": arr_result.get("already_added"),
                "monitored": arr_result.get("monitored"),
                "dashboard_state_persisted": False,
                "reconciliation_queued": reconciliation_queued,
                "message": (
                    "Added to Sonarr/Radarr; dashboard synchronization failed."
                ),
            },
        )
        return

    service = arr_result.get("service")
    title = arr_result.get("title") or "title"
    already = bool(arr_result.get("already_added"))
    if already:
        message = f"Already in {service}: {title} (left unmonitored / no search)."
    else:
        message = f"Added to {service} unmonitored (no download): {title}."

    send_json(
        handler,
        200,
        {
            "ok": True,
            "jellyseerr_request_id": arr_id,
            "arr_id": arr_id,
            "service": service,
            "already_added": already,
            "monitored": arr_result.get("monitored"),
            "dashboard_state_persisted": True,
            "message": message,
        },
    )


def handle_discover_request_reconcile(handler):
    try:
        send_json(handler, 200, run_reconciliation_cycle())
    except RecommendationError as e:
        send_json(handler, 500, {"ok": False, "error": str(e)})
    except OSError as e:
        send_json(handler, 500, {"ok": False, "error": f"Reconciliation failed: {e}"})


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class ActionsHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Reduce noise; errors still printed by the server.
        pass

    def do_OPTIONS(self):
        send_options(self)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        if path == "/qbt/torrents":
            handle_qbt_torrents(self)
        elif path == "/jellyfin/movies":
            handle_jellyfin_items(self, "Movie")
        elif path == "/jellyfin/series":
            handle_jellyfin_items(self, "Series")
        elif path == "/jellyfin/watch-next":
            handle_jellyfin_watch_next(self)
        elif path == "/arr/library":
            handle_arr_library(self)
        elif path == "/sonarr/missing-count":
            handle_sonarr_missing_count(self)
        elif path == "/sonarr/series-count":
            handle_sonarr_series_count(self)
        elif path == "/sonarr/calendar":
            handle_sonarr_calendar(self)
        elif path == "/automation/summary":
            handle_automation_summary(self)
        elif path == "/system/resources":
            handle_system_resources(self)
        elif path == "/health":
            send_json(self, 200, {"ok": True})
        elif path == "/cron/logs":
            handle_cron_logs(self)
        elif path == "/discover/hermes":
            handle_discover_hermes_get(self)
        elif path == "/discover/jellyseerr":
            handle_discover_jellyseerr(self, query)
        elif path == "/discover/trakt":
            handle_discover_trakt(self, query)
        else:
            send_json(self, 404, {"ok": False, "error": "Unknown endpoint"})

    def do_PATCH(self):
        if _reject_mutating(self):
            return
        path = urllib.parse.urlparse(self.path).path
        prefix = "/discover/hermes/"
        if path.startswith(prefix):
            item_id = urllib.parse.unquote(path[len(prefix):])
            handle_discover_hermes_patch(self, item_id)
        else:
            send_json(self, 404, {"ok": False, "error": "Unknown endpoint"})

    def do_POST(self):
        if _reject_post(self):
            return
        path = urllib.parse.urlparse(self.path).path
        if path == "/qbt/torrents/stop":
            handle_qbt_torrent_hash_action(self, "/api/v2/torrents/stop")
        elif path == "/qbt/torrents/start":
            handle_qbt_torrent_hash_action(self, "/api/v2/torrents/start")
        elif path == "/stop-all":
            handle_qbt_action(self, "/api/v2/torrents/stop")
        elif path == "/start-all":
            handle_qbt_action(self, "/api/v2/torrents/start")
        elif path == "/discover/hermes":
            handle_discover_hermes_post(self)
        elif path == "/discover/hermes/generations":
            handle_discover_hermes_generations(self)
        elif path == "/discover/hermes/sync":
            handle_discover_hermes_sync(self)
        elif path == "/discover/hermes/request-more":
            handle_discover_hermes_request_more(self)
        elif path == "/discover/request/reconcile":
            handle_discover_request_reconcile(self)
        elif path == "/discover/request":
            handle_discover_request(self)
        else:
            send_json(self, 404, {"ok": False, "error": "Unknown endpoint"})


if __name__ == "__main__":
    start_reconciliation_scheduler()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), ActionsHandler)
    print(
        f"Dashboard actions API listening on :{PORT} "
        f"(request reconcile every {RECONCILE_INTERVAL_SECONDS:g}s; "
        "manual POST /discover/request/reconcile)",
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        stop_reconciliation_scheduler()
        server.server_close()
