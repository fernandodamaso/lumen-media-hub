"""Private, typed Trakt watched-history snapshot support."""

import json
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
import time

from shared import _normalize_tmdb_id


PAGE_LIMIT = 100
FRESHNESS_SECONDS = 15 * 60


def _identity_for_entry(entry, media_type):
    member = _validate_watched_entry(entry, media_type)
    ids = member["ids"]
    tmdb_id = _normalize_tmdb_id(ids.get("tmdb"))
    if not tmdb_id:
        return None
    return f"{'movie' if media_type == 'movies' else 'tv'}:{tmdb_id}"


def _validate_watched_entry(entry, media_type):
    if media_type not in ("movies", "shows") or not isinstance(entry, dict):
        raise ValueError("invalid Trakt watched item")
    key = "movie" if media_type == "movies" else "show"
    member = entry.get(key)
    if not isinstance(member, dict) or not isinstance(member.get("ids"), dict):
        raise ValueError("invalid Trakt watched item")
    return member


def parse_watched_identities(payload, media_type):
    """Return only typed TMDB identities from one Trakt watched page."""
    if media_type not in ("movies", "shows") or not isinstance(payload, list):
        raise ValueError("invalid Trakt watched response")
    return {
        identity
        for entry in payload
        for identity in [_identity_for_entry(entry, media_type)]
        if identity
    }


def _response_parts(response):
    if isinstance(response, tuple):
        if len(response) == 2:
            return response[0], response[1] or {}
        if len(response) == 3:
            return response[0], response[2] or {}
    payload = getattr(response, "payload", response)
    return payload, getattr(response, "headers", {}) or {}


def _header(headers, name):
    for key, value in headers.items():
        if str(key).lower() == name.lower():
            return value
    return None


@dataclass(frozen=True)
class WatchedSnapshot:
    identities: frozenset
    refreshed_at: str | None
    status: str

    def public(self):
        return {
            "status": self.status,
            "last_successful_refresh_at": self.refreshed_at,
        }

    def contains(self, item_type, tmdb_id):
        kind = "tv" if item_type == "tv" else "movie"
        normalized = _normalize_tmdb_id(tmdb_id)
        return bool(normalized and f"{kind}:{normalized}" in self.identities)


class WatchedSnapshotStore:
    """Atomic store for the privacy-safe watched identity snapshot."""

    def __init__(self, path):
        self.path = os.fspath(path)

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as handle:
                value = json.load(handle)
        except FileNotFoundError:
            return None
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            return None
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            return None
        refreshed_at = value.get("refreshed_at")
        identities = value.get("identities")
        if not isinstance(refreshed_at, str) or not isinstance(identities, list):
            return None
        clean = {identity for identity in identities if isinstance(identity, str) and _valid_identity(identity)}
        return WatchedSnapshot(frozenset(clean), refreshed_at, "stale")

    def replace(self, identities, *, refreshed_at):
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".trakt-watched-", suffix=".tmp", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(
                    {
                        "schema_version": 1,
                        "refreshed_at": refreshed_at,
                        "identities": sorted(set(identities)),
                    },
                    handle,
                    separators=(",", ":"),
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass


def _valid_identity(value):
    kind, separator, number = value.partition(":")
    return kind in ("movie", "tv") and bool(separator) and bool(_normalize_tmdb_id(number))


class TraktWatchedService:
    def __init__(self, get_page, *, store=None, clock=None, freshness_seconds=FRESHNESS_SECONDS):
        self.get_page = get_page
        self.store = store
        self.clock = clock or time.time
        self.freshness_seconds = freshness_seconds
        self._lock = threading.Lock()
        self._snapshot = None
        self._loaded_at = None

    def fetch_identities(self):
        identities = set()
        for media_type in ("movies", "shows"):
            page = 1
            while True:
                path = f"/sync/watched/{media_type}?page={page}&limit={PAGE_LIMIT}"
                payload, headers = _response_parts(self.get_page(path))
                if not isinstance(payload, list):
                    raise ValueError("invalid Trakt watched response")
                identities.update(parse_watched_identities(payload, media_type))
                raw_page = _header(headers, "X-Pagination-Page")
                raw_page_count = _header(headers, "X-Pagination-Page-Count")
                if page == 1 and raw_page is None and raw_page_count is None:
                    break
                try:
                    page_header = int(raw_page) if raw_page is not None else None
                    page_count = int(raw_page_count) if raw_page_count is not None else None
                except (TypeError, ValueError):
                    raise ValueError("invalid Trakt watched pagination headers") from None
                if page_header is not None and page_header != page:
                    raise ValueError("inconsistent Trakt watched pagination page")
                if page_count is None or page_count < 1:
                    raise ValueError("invalid Trakt watched pagination page count")
                if page == 1:
                    expected_page_count = page_count
                elif page_count != expected_page_count or page_header is None:
                    raise ValueError("inconsistent Trakt watched pagination headers")
                if page >= page_count:
                    break
                page += 1
        return identities

    def _now_iso(self):
        return datetime.fromtimestamp(self.clock(), timezone.utc).isoformat(timespec="seconds")

    def snapshot(self):
        with self._lock:
            now = self.clock()
            if self._snapshot is not None and self._loaded_at is not None and now - self._loaded_at < self.freshness_seconds:
                return self._snapshot
            previous = self._snapshot or (self.store.load() if self.store else None)
            try:
                identities = self.fetch_identities()
                refreshed_at = self._now_iso()
                if self.store:
                    self.store.replace(identities, refreshed_at=refreshed_at)
                self._snapshot = WatchedSnapshot(frozenset(identities), refreshed_at, "fresh")
                self._loaded_at = now
                return self._snapshot
            except Exception:
                if previous is not None:
                    self._snapshot = WatchedSnapshot(previous.identities, previous.refreshed_at, "stale")
                    self._loaded_at = now
                    return self._snapshot
                self._snapshot = WatchedSnapshot(frozenset(), None, "unavailable")
                self._loaded_at = now
                return self._snapshot
