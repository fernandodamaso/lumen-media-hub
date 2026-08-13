"""Safe library deletion: Jellyfin resolve, Arr match, qBit intersect, preview store."""
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timezone

import config as settings
from clients.arr import (
    delete_radarr_movie,
    delete_sonarr_series,
    fetch_arr_history,
    find_radarr_movies_by_tmdb,
    find_sonarr_series_by_tmdb,
    find_sonarr_series_by_tvdb,
)
from clients.jellyfin import (
    _jellyfin_user_id_for_queries,
    _series_episode_count,
    invalidate_jellyfin_caches,
    jellyfin_get,
    jellyfin_post,
)
from clients.qbittorrent import qbt_get_json, qbt_login, qbt_post
from http_support import _valid_torrent_hash
from recommendations_store import RecommendationError

PREVIEW_TTL_SECONDS = 120
PREVIEW_STORE_LIMIT = 100
HISTORY_PAGE_SIZE = 1000


class MatchError(Exception):
    pass


class UpstreamError(Exception):
    def __init__(self, source):
        super().__init__(source)
        self.source = source


class ConflictError(Exception):
    pass


def _parse_provider_id(provider_ids, *keys):
    if not isinstance(provider_ids, dict):
        return None
    for key in keys:
        for candidate in (key, key.lower(), key.upper()):
            if candidate not in provider_ids:
                continue
            value = provider_ids[candidate]
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _match_movie(provider_ids):
    tmdb = _parse_provider_id(provider_ids, "Tmdb", "tmdb")
    if tmdb is None:
        raise MatchError()
    matches = find_radarr_movies_by_tmdb(tmdb)
    if len(matches) != 1:
        raise MatchError()
    movie = matches[0]
    return "Radarr", movie["id"]


def _match_series(provider_ids):
    tmdb = _parse_provider_id(provider_ids, "Tmdb", "tmdb")
    tvdb = _parse_provider_id(provider_ids, "Tvdb", "tvdb")
    if tmdb is None and tvdb is None:
        raise MatchError()
    tvdb_matches = find_sonarr_series_by_tvdb(tvdb) if tvdb is not None else []
    tmdb_matches = find_sonarr_series_by_tmdb(tmdb) if tmdb is not None else []
    if tmdb is not None and tvdb is not None:
        if len(tvdb_matches) != 1 or len(tmdb_matches) != 1:
            raise MatchError()
        if tvdb_matches[0]["id"] != tmdb_matches[0]["id"]:
            raise MatchError()
        return "Sonarr", tvdb_matches[0]["id"]
    if tvdb is not None:
        if len(tvdb_matches) != 1:
            raise MatchError()
        return "Sonarr", tvdb_matches[0]["id"]
    if len(tmdb_matches) != 1:
        raise MatchError()
    return "Sonarr", tmdb_matches[0]["id"]


def _history_download_ids(history):
    total = history.get("totalRecords", 0)
    if total > HISTORY_PAGE_SIZE:
        raise MatchError()
    ids = []
    for record in history.get("records") or []:
        download_id = record.get("downloadId")
        if _valid_torrent_hash(download_id):
            ids.append(download_id.lower())
    return ids


def _current_qbit_hashes():
    try:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        qbt_login(opener)
        torrents = qbt_get_json("/api/v2/torrents/info", opener)
    except Exception as exc:
        raise UpstreamError("qbit") from exc
    hashes = set()
    for torrent in torrents or []:
        torrent_hash = torrent.get("hash")
        if _valid_torrent_hash(torrent_hash):
            hashes.add(torrent_hash.lower())
    return hashes


def _intersect_hashes(download_ids, qbit_hashes):
    download_set = set(download_ids)
    return tuple(sorted(download_set & qbit_hashes))


def _fetch_target_hashes(manager, arr_id):
    if manager == "Radarr":
        history = fetch_arr_history(
            settings.RADARR_URL, settings.RADARR_API_KEY, "movieId", arr_id
        )
    else:
        history = fetch_arr_history(
            settings.SONARR_URL, settings.SONARR_API_KEY, "seriesId", arr_id
        )
    download_ids = _history_download_ids(history)
    qbit_hashes = _current_qbit_hashes()
    return _intersect_hashes(download_ids, qbit_hashes)


def resolve_library_target(jellyfin_item_id):
    user_id = _jellyfin_user_id_for_queries()
    path = (
        f"/Users/{user_id}/Items/{jellyfin_item_id}"
        if user_id
        else f"/Items/{jellyfin_item_id}"
    )
    raw = jellyfin_get(path, {"Fields": "ProviderIds,UserData,Type,Name"})
    item_type = raw.get("Type")
    if item_type not in ("Movie", "Series"):
        raise MatchError()
    provider_ids = raw.get("ProviderIds") or {}
    title = raw.get("Name") or ""
    if item_type == "Movie":
        manager, arr_id = _match_movie(provider_ids)
        kind = "movie"
        episode_count = None
    else:
        manager, arr_id = _match_series(provider_ids)
        kind = "series"
        episode_count = _series_episode_count(jellyfin_item_id)
    hashes = _fetch_target_hashes(manager, arr_id)
    return {
        "jellyfin_id": jellyfin_item_id,
        "kind": kind,
        "title": title,
        "episode_count": episode_count,
        "manager": manager,
        "arr_id": arr_id,
        "hashes": hashes,
    }


class PreviewStore:
    def __init__(self, monotonic=None, ttl=PREVIEW_TTL_SECONDS, limit=PREVIEW_STORE_LIMIT):
        self._monotonic = monotonic or time.monotonic
        self._ttl = ttl
        self._limit = limit
        self._lock = threading.Lock()
        self._entries = {}
        self._order = []

    def _purge_expired(self, now):
        expired = [
            preview_id
            for preview_id, entry in self._entries.items()
            if now - entry["created"] >= self._ttl
        ]
        for preview_id in expired:
            self._entries.pop(preview_id, None)
            if preview_id in self._order:
                self._order.remove(preview_id)

    def put(self, target):
        now = self._monotonic()
        preview_id = str(uuid.uuid4())
        expires_at = datetime.fromtimestamp(
            time.time() + self._ttl, tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._lock:
            self._purge_expired(now)
            while len(self._entries) >= self._limit and self._order:
                oldest = self._order.pop(0)
                self._entries.pop(oldest, None)
            self._entries[preview_id] = {"created": now, "target": dict(target)}
            self._order.append(preview_id)
        return {
            "previewId": preview_id,
            "title": target["title"],
            "kind": target["kind"],
            "manager": target["manager"],
            "episodeCount": target["episode_count"],
            "torrentCount": len(target["hashes"]),
            "expiresAt": expires_at,
        }

    def get(self, preview_id):
        now = self._monotonic()
        with self._lock:
            entry = self._entries.get(preview_id)
            if not entry:
                return None
            if now - entry["created"] >= self._ttl:
                self._entries.pop(preview_id, None)
                if preview_id in self._order:
                    self._order.remove(preview_id)
                return None
            return dict(entry["target"])

    def pop(self, preview_id):
        now = self._monotonic()
        with self._lock:
            entry = self._entries.pop(preview_id, None)
            if preview_id in self._order:
                self._order.remove(preview_id)
            if not entry:
                return None
            if now - entry["created"] >= self._ttl:
                return None
            return dict(entry["target"])


PREVIEW_STORE = PreviewStore()


def _delete_qbit_hashes(hashes):
    if not hashes:
        return
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    qbt_login(opener)
    status, _body = qbt_post(
        "/api/v2/torrents/delete",
        {"hashes": "|".join(hashes), "deleteFiles": "true"},
        opener,
    )
    if status < 200 or status >= 300:
        raise UpstreamError("qbit")


def execute_library_delete(item_id, preview_id, store=None):
    store = store or PREVIEW_STORE
    preview = store.pop(preview_id)
    if not preview:
        raise ConflictError()
    if preview["jellyfin_id"] != item_id:
        raise ConflictError()
    fresh = resolve_library_target(item_id)
    if (
        fresh["arr_id"] != preview["arr_id"]
        or fresh["kind"] != preview["kind"]
        or fresh["manager"] != preview["manager"]
        or tuple(fresh["hashes"]) != tuple(preview["hashes"])
    ):
        raise ConflictError()
    hashes = list(preview["hashes"])
    torrent_step = "skipped"
    if hashes:
        _delete_qbit_hashes(hashes)
        torrent_step = "ok"
    try:
        if preview["manager"] == "Radarr":
            delete_radarr_movie(preview["arr_id"])
        else:
            delete_sonarr_series(preview["arr_id"])
    except (RecommendationError, Exception):
        return {
            "ok": False,
            "removed": False,
            "partial": True,
            "torrentCount": len(hashes),
            "error": "Unable to finish deletion",
            "steps": {
                "torrents": torrent_step,
                "library": "failed",
                "jellyfin": "skipped",
            },
        }
    invalidate_jellyfin_caches()
    with settings._arr_cache_lock:
        settings._arr_cache.clear()
    from routes.discover import invalidate_discover_library_caches

    invalidate_discover_library_caches()
    jellyfin_refresh = "ok"
    warning = None
    try:
        jellyfin_post("/Library/Refresh")
    except Exception:
        jellyfin_refresh = "pending"
        warning = "Removed; Jellyfin refresh pending"
    return {
        "ok": True,
        "removed": True,
        "torrentCount": len(hashes),
        "jellyfinRefresh": jellyfin_refresh,
        "warning": warning,
        "steps": {
            "torrents": torrent_step,
            "library": "ok",
            "jellyfin": jellyfin_refresh,
        },
    }
