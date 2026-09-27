"""Default-off Trakt 48-hour episode retention.

The retention rule is intentionally small and conservative.  Trakt is read
through the existing OAuth client, Sonarr owns episode-file deletion, and
Jellyfin is only refreshed after a successful Sonarr delete.  There is no
Trakt write path and no whole-series or torrent deletion helper in this
module.
"""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone

import config as settings
from clients.arr import _arr_get, _arr_json
from clients.jellyfin import jellyfin_get, jellyfin_post
from clients.trakt import TraktAuthError, TraktClient
from trakt_history import _header, _response_parts


RETENTION_SECONDS = 48 * 60 * 60
HISTORY_PAGE_LIMIT = 100
_POSITIVE_INT = lambda value: (
    isinstance(value, int) and not isinstance(value, bool) and value > 0
)


class RetentionBlocked(RuntimeError):
    """A fail-closed preview/commit blocker safe to expose as a reason."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _utc(value):
    """Parse an explicit timezone timestamp and normalize it to UTC."""
    if not isinstance(value, str) or not value.strip():
        raise RetentionBlocked("missing_timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise RetentionBlocked("invalid_timestamp") from None
    if parsed.tzinfo is None:
        raise RetentionBlocked("timestamp_without_timezone")
    return parsed.astimezone(timezone.utc)


def _now(clock):
    value = clock()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("clock must return an aware UTC datetime")
        return value.astimezone(timezone.utc)
    return datetime.fromtimestamp(float(value), timezone.utc)


def _positive_identifier(value):
    if _POSITIVE_INT(value):
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return None


def _season_identifier(value):
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _history_pagination(headers, page):
    raw_page = _header(headers, "X-Pagination-Page")
    raw_count = _header(headers, "X-Pagination-Page-Count")
    raw_items = _header(headers, "X-Pagination-Item-Count")
    if raw_page is None or raw_count is None or raw_items is None:
        raise RetentionBlocked("incomplete_history_pagination")
    try:
        page_header = int(raw_page)
        page_count = int(raw_count)
        item_count = int(raw_items)
    except (TypeError, ValueError):
        raise RetentionBlocked("invalid_history_pagination") from None
    if (
        page_header != page
        or page_count < 1
        or page > page_count
        or item_count < 0
    ):
        raise RetentionBlocked("invalid_history_pagination")
    return page_count, item_count


def fetch_complete_trakt_history(client, *, limit=HISTORY_PAGE_LIMIT):
    """Read the complete current Trakt episode history.

    Pagination headers are required.  A response that cannot prove it is the
    complete history is unsafe for deletion and blocks the whole cycle.
    """
    if not _POSITIVE_INT(limit):
        raise ValueError("history limit must be positive")
    page = 1
    page_count = None
    item_count = None
    entries = []
    history_ids = set()
    while page_count is None or page <= page_count:
        response = client.get_page(f"/sync/history/episodes?page={page}&limit={limit}")
        payload, headers = _response_parts(response)
        if not isinstance(payload, list):
            raise RetentionBlocked("invalid_history_response")
        current_count, current_items = _history_pagination(headers, page)
        if page_count is None:
            page_count = current_count
            item_count = current_items
        elif current_count != page_count or current_items != item_count:
            raise RetentionBlocked("history_changed_during_snapshot")
        if len(payload) > limit:
            raise RetentionBlocked("invalid_history_page")
        if not payload and page < page_count:
            raise RetentionBlocked("incomplete_history_page")
        for entry in payload:
            if not isinstance(entry, dict):
                raise RetentionBlocked("invalid_history_entry")
            history_id = _positive_identifier(entry.get("id"))
            if history_id is None or history_id in history_ids:
                raise RetentionBlocked("history_changed_during_snapshot")
            history_ids.add(history_id)
            entries.append(entry)
        page += 1
    if len(entries) != item_count:
        raise RetentionBlocked("history_changed_during_snapshot")
    return entries


def _history_identity_keys(show):
    ids = show.get("ids") if isinstance(show, dict) else None
    if not isinstance(ids, dict):
        raise RetentionBlocked("ambiguous_series_mapping")
    keys = []
    for name in ("tvdb", "tmdb"):
        identity = _positive_identifier(ids.get(name))
        if identity is not None:
            keys.append((name, identity))
    if not keys:
        raise RetentionBlocked("unknown_series_identity")
    return tuple(keys)


def latest_watches(entries):
    """Return latest UTC watch per stable series id and episode number."""
    latest = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise RetentionBlocked("invalid_history_entry")
        episode = entry.get("episode")
        show = entry.get("show")
        if not isinstance(episode, dict) or not isinstance(show, dict):
            raise RetentionBlocked("ambiguous_episode_mapping")
        season = _season_identifier(episode.get("season"))
        number = _positive_identifier(episode.get("number"))
        if season is None or number is None:
            raise RetentionBlocked("ambiguous_episode_mapping")
        watched = _utc(entry.get("watched_at"))
        for identity in _history_identity_keys(show):
            key = (identity, season, number)
            previous = latest.get(key)
            if previous is None or watched > previous:
                latest[key] = watched
    if not latest and entries:
        raise RetentionBlocked("empty_history_identity")
    return latest


def _sonarr_ids(row):
    values = []
    for name in ("tvdbId", "tmdbId"):
        identity = _positive_identifier(row.get(name))
        if identity is not None:
            values.append(("tvdb" if name == "tvdbId" else "tmdb", identity))
    return tuple(values)


def _episode_number(row):
    season = _season_identifier(row.get("seasonNumber"))
    number = _positive_identifier(row.get("episodeNumber"))
    if season is None or number is None:
        return None
    return season, number


def _file_state(episode, file_lookup=None):
    file_id = _positive_identifier(episode.get("episodeFileId"))
    nested = episode.get("episodeFile") if isinstance(episode.get("episodeFile"), dict) else {}
    path = episode.get("path") or nested.get("path") or nested.get("relativePath")
    if file_id is not None and not path and file_lookup is not None:
        details = file_lookup(file_id)
        if isinstance(details, dict):
            path = details.get("path") or details.get("relativePath")
            nested = {**nested, **details}
    if file_id is None or not isinstance(path, str) or not path or not os.path.isabs(path):
        return None
    return {
        "id": file_id,
        "path": path,
        "size": nested.get("size", episode.get("size")),
        "relative_path": nested.get("relativePath"),
    }


def _episode_snapshot(episode, watch):
    number = _episode_number(episode)
    if number is None or not _POSITIVE_INT(episode.get("id")):
        raise RetentionBlocked("ambiguous_episode_mapping")
    return {
        "id": episode["id"],
        "season": number[0],
        "number": number[1],
        "monitored": bool(episode.get("monitored")),
        "has_file": episode.get("hasFile") is not False,
        "file_id": _positive_identifier(episode.get("episodeFileId")),
        "watch_at": watch.isoformat(timespec="seconds").replace("+00:00", "Z") if watch else None,
    }


class SonarrRetentionClient:
    """Thin adapter over the existing standard-library Arr helpers."""

    def __init__(self, base=None, api_key=None):
        self.base = settings.SONARR_URL if base is None else base
        self.api_key = settings.SONARR_API_KEY if api_key is None else api_key

    def series(self):
        rows = _arr_get(self.base, self.api_key, "/api/v3/series")
        if not isinstance(rows, list):
            raise RetentionBlocked("sonarr_series_query_failed")
        return rows

    def episodes(self, series_id):
        rows = _arr_get(
            self.base,
            self.api_key,
            f"/api/v3/episode?seriesId={int(series_id)}&includeImages=false",
        )
        if not isinstance(rows, list):
            raise RetentionBlocked("sonarr_episode_query_failed")
        return rows

    def episode_file(self, file_id):
        details = _arr_get(self.base, self.api_key, f"/api/v3/episodefile/{int(file_id)}")
        if not isinstance(details, dict):
            raise RetentionBlocked("sonarr_episode_file_query_failed")
        return details

    def set_episode(self, episode):
        return _arr_json(
            self.base,
            self.api_key,
            f"/api/v3/episode/{int(episode['id'])}",
            method="PUT",
            payload=episode,
        )

    def delete_episode_file(self, file_id):
        # This is deliberately the narrow Sonarr episode-file endpoint.
        return _arr_json(
            self.base,
            self.api_key,
            f"/api/v3/episodefile/{int(file_id)}",
            method="DELETE",
        )


class JellyfinRetentionClient:
    """Playback probe used before and immediately before a file delete."""

    def playback_for_file(self, path):
        sessions = jellyfin_get("/Sessions")
        if not isinstance(sessions, list):
            raise RetentionBlocked("playback_query_failed")
        for session in sessions:
            if not isinstance(session, dict):
                raise RetentionBlocked("playback_query_failed")
            item = session.get("NowPlayingItem")
            if not isinstance(item, dict):
                continue
            item_path = item.get("Path")
            if not isinstance(item_path, str) or not item_path:
                raise RetentionBlocked("playback_identity_unknown")
            if item_path == path:
                return True
        return False

    def refresh(self):
        return jellyfin_post("/Library/Refresh")


class RetentionStateStore:
    """Atomic, private intent/outcome state for restart-safe commits."""

    def __init__(self, path=None):
        self.path = os.fspath(path or settings.TRAKT_RETENTION_STATE_PATH)

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, ValueError, TypeError):
            return {"schema_version": 1, "items": {}}
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            return {"schema_version": 1, "items": {}}
        items = value.get("items")
        return {"schema_version": 1, "items": items if isinstance(items, dict) else {}}

    def put(self, key, record):
        state = self.load()
        state.setdefault("items", {})[key] = dict(record)
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".trakt-retention-", suffix=".tmp", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(state, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _candidate_key(series_id, file_id):
    return f"sonarr:{int(series_id)}:episode-file:{int(file_id)}"


def _group_episodes(episodes, file_lookup=None):
    groups = {}
    for episode in episodes:
        file_state = _file_state(episode, file_lookup=file_lookup)
        file_id = _positive_identifier(episode.get("episodeFileId"))
        if file_id is None:
            continue
        group = groups.setdefault(
            file_id,
            {"file": file_state or {"id": file_id, "path": None}, "episodes": []},
        )
        if group["file"].get("path") is None and file_state is not None:
            group["file"] = file_state
        elif (
            file_state is not None
            and group["file"].get("path")
            and group["file"].get("path") != file_state.get("path")
        ):
            group["file_conflict"] = True
        group["episodes"].append(episode)
    return groups


def _watch_for_episode(latest, series, episode):
    number = _episode_number(episode)
    if number is None:
        raise RetentionBlocked("ambiguous_episode_mapping")
    keys = _sonarr_ids(series)
    watches = [latest.get((identity, number[0], number[1])) for identity in keys]
    watches = [watch for watch in watches if watch is not None]
    return max(watches) if watches else None


def build_retention_preview(*, trakt, sonarr, jellyfin, now=None, clock=None):
    """Build an exact, private preview from one complete current snapshot."""
    clock = clock or time.time
    current = now.astimezone(timezone.utc) if isinstance(now, datetime) else _now(clock)
    cutoff = current - timedelta(seconds=RETENTION_SECONDS)
    history = fetch_complete_trakt_history(trakt)
    latest = latest_watches(history)
    series_rows = sonarr.series()
    if not isinstance(series_rows, list):
        raise RetentionBlocked("sonarr_series_query_failed")

    identity_map = {}
    for series in series_rows:
        if not isinstance(series, dict):
            raise RetentionBlocked("ambiguous_series_mapping")
        series_id = _positive_identifier(series.get("id"))
        if series_id is None:
            continue
        for identity in _sonarr_ids(series):
            identity_map.setdefault(identity, []).append(series)

    preview = {
        "status": "preview",
        "generated_at": current.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "cutoff_at": cutoff.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "history_entries": len(history),
        "eligible": [],
        "preserved": [],
    }
    processed_series = set()
    for identity, season, number in sorted(latest, key=str):
        matching = identity_map.get(identity, [])
        if len(matching) != 1:
            preview["preserved"].append({"identity": identity, "season": season, "number": number, "reason": "ambiguous_series_mapping" if len(matching) > 1 else "unknown_series_identity"})
            continue
        series = matching[0]
        series_id = _positive_identifier(series.get("id"))
        if series_id in processed_series:
            continue
        processed_series.add(series_id)
        if any(
            len(identity_map.get(series_identity, [])) != 1
            for series_identity in _sonarr_ids(series)
        ):
            preview["preserved"].append(
                {
                    "identity": identity,
                    "season": season,
                    "number": number,
                    "reason": "ambiguous_series_mapping",
                }
            )
            continue
        try:
            episodes = sonarr.episodes(series_id)
        except RetentionBlocked:
            raise
        except Exception as error:
            raise RetentionBlocked("sonarr_episode_query_failed") from error
        groups = _group_episodes(
            episodes, file_lookup=getattr(sonarr, "episode_file", None)
        )
        for file_id, group in sorted(groups.items()):
            reasons = []
            snapshots = []
            watches = []
            if not group["file"].get("path"):
                reasons.append("episode_file_state_unavailable")
            if group.get("file_conflict"):
                reasons.append("ambiguous_episode_file_mapping")
            for episode in group["episodes"]:
                try:
                    watch = _watch_for_episode(latest, series, episode)
                except RetentionBlocked as error:
                    reasons.append(error.reason)
                    watch = None
                watches.append(watch)
                snapshots.append(_episode_snapshot(episode, watch))
                if watch is None:
                    reasons.append("unwatched_episode")
                elif watch > cutoff:
                    reasons.append("watch_within_48h")
                if episode.get("airDateUtc"):
                    try:
                        if _utc(episode["airDateUtc"]) > current:
                            reasons.append("future_episode")
                    except RetentionBlocked as error:
                        reasons.append(error.reason)
                if episode.get("hasFile") is False:
                    reasons.append("missing_episode_file")
            if reasons:
                preview["preserved"].append({
                    "key": _candidate_key(series_id, file_id),
                    "series_id": series_id,
                    "file": group["file"],
                    "episodes": snapshots,
                    "reason": sorted(set(reasons))[0],
                })
                continue
            try:
                if jellyfin.playback_for_file(group["file"]["path"]):
                    preview["preserved"].append({
                        "key": _candidate_key(series_id, file_id),
                        "series_id": series_id,
                        "file": group["file"],
                        "episodes": snapshots,
                        "reason": "playback_active",
                    })
                    continue
            except RetentionBlocked:
                raise
            except Exception as error:
                raise RetentionBlocked("playback_query_failed") from error
            preview["eligible"].append({
                "key": _candidate_key(series_id, file_id),
                "series_id": series_id,
                "series": {"id": series_id, "monitored": bool(series.get("monitored"))},
                "file": group["file"],
                "episodes": snapshots,
                "watches": [watch.isoformat(timespec="seconds").replace("+00:00", "Z") for watch in watches],
            })
    return preview


def _same_file(current, expected):
    return current.get("file") == expected.get("file") and [
        row.get("id") for row in current.get("episodes", [])
    ] == [row.get("id") for row in expected.get("episodes", [])]


class TraktRetentionRunner:
    """Preview and commit runner with a narrow, restart-safe mutation sequence."""

    def __init__(self, *, trakt=None, sonarr=None, jellyfin=None, state=None, clock=None, enabled=None):
        self.enabled = settings.TRAKT_RETENTION_ENABLED if enabled is None else bool(enabled)
        self.clock = clock or time.time
        self.trakt = trakt
        self.sonarr = sonarr
        self.jellyfin = jellyfin
        self.state = state or RetentionStateStore()
        self._commit_now = None

    def _clients(self):
        if self.trakt is None:
            if not settings.TRAKT_CLIENT_ID or not settings.TRAKT_CLIENT_SECRET:
                raise TraktAuthError()
            self.trakt = TraktClient(
                settings.TRAKT_CLIENT_ID,
                settings.TRAKT_CLIENT_SECRET,
                token_path=settings.TRAKT_TOKEN_PATH,
                clock=self.clock,
            )
        if self.sonarr is None:
            self.sonarr = SonarrRetentionClient()
        if self.jellyfin is None:
            self.jellyfin = JellyfinRetentionClient()
        return self.trakt, self.sonarr, self.jellyfin

    def preview(self, *, now=None):
        if not self.enabled:
            return {"status": "disabled", "reason": "disabled", "eligible": [], "preserved": []}
        try:
            trakt, sonarr, jellyfin = self._clients()
            return build_retention_preview(
                trakt=trakt, sonarr=sonarr, jellyfin=jellyfin, now=now, clock=self.clock
            )
        except TraktAuthError:
            return {"status": "blocked", "reason": "auth_required", "eligible": [], "preserved": []}
        except RetentionBlocked as error:
            return {"status": "blocked", "reason": error.reason, "eligible": [], "preserved": []}
        except Exception:
            return {"status": "blocked", "reason": "retention_query_failed", "eligible": [], "preserved": []}

    def _current_group(self, item):
        episodes = self.sonarr.episodes(item["series_id"])
        groups = _group_episodes(
            episodes, file_lookup=getattr(self.sonarr, "episode_file", None)
        )
        group = groups.get(item["file"]["id"])
        if not group:
            return None
        current = {
            "file": group["file"],
            "episodes": [_episode_snapshot(ep, None) for ep in group["episodes"]],
            "raw_episodes": list(group["episodes"]),
        }
        return current

    def _revalidate_before_delete(self, item):
        """Take a complete Trakt/current Arr/playback snapshot at the delete edge."""
        fresh = build_retention_preview(
            trakt=self.trakt,
            sonarr=self.sonarr,
            jellyfin=self.jellyfin,
            now=self._commit_now,
            clock=self.clock,
        )
        if fresh.get("status") != "preview":
            raise RetentionBlocked("revalidation_failed")
        matches = [candidate for candidate in fresh.get("eligible", []) if candidate.get("key") == item["key"]]
        if len(matches) != 1:
            preserved = [candidate for candidate in fresh.get("preserved", []) if candidate.get("key") == item["key"]]
            if preserved:
                raise RetentionBlocked(preserved[0].get("reason") or "revalidation_failed")
            raise RetentionBlocked("revalidation_failed")
        current = matches[0]
        if current.get("file") != item.get("file") or [
            row.get("id") for row in current.get("episodes", [])
        ] != [row.get("id") for row in item.get("episodes", [])]:
            raise RetentionBlocked("sonarr_state_changed")
        return current

    def _revalidate_candidate(self, item):
        """Require the candidate to still qualify before any unmonitor PUT."""
        fresh = build_retention_preview(
            trakt=self.trakt,
            sonarr=self.sonarr,
            jellyfin=self.jellyfin,
            now=self._commit_now,
            clock=self.clock,
        )
        if fresh.get("status") != "preview":
            raise RetentionBlocked("revalidation_failed")
        matches = [candidate for candidate in fresh.get("eligible", []) if candidate.get("key") == item["key"]]
        if len(matches) != 1:
            preserved = [candidate for candidate in fresh.get("preserved", []) if candidate.get("key") == item["key"]]
            if preserved:
                raise RetentionBlocked(preserved[0].get("reason") or "revalidation_failed")
            raise RetentionBlocked("revalidation_failed")
        current = matches[0]
        if current.get("file") != item.get("file") or [
            row.get("id") for row in current.get("episodes", [])
        ] != [row.get("id") for row in item.get("episodes", [])]:
            raise RetentionBlocked("sonarr_state_changed")
        return current

    def _preserve_after_unmonitor(self, item, prior, reason):
        """Restore monitoring when a post-unmonitor delete gate blocks."""
        expected = {row["id"]: row["monitored"] for row in prior["episodes"]}
        current = self._current_group(item)
        rollback_failed = current is None or not _same_file(current, item)
        if not rollback_failed:
            for episode in current["raw_episodes"]:
                monitored = expected.get(episode.get("id"))
                if monitored is None or episode.get("monitored") is monitored:
                    continue
                payload = dict(episode)
                payload["monitored"] = monitored
                try:
                    self.sonarr.set_episode(payload)
                except Exception:
                    rollback_failed = True
        final_reason = "unmonitor_rollback_failed" if rollback_failed else reason
        record = {**prior, "status": "preserved", "reason": final_reason}
        self.state.put(item["key"], record)
        return {"key": item["key"], "status": "preserved", "reason": final_reason}

    def _commit_item(self, item, prior):
        key = item["key"]
        current = self._current_group(item)
        if current is None or not _same_file(current, item):
            self.state.put(key, {**prior, "status": "preserved", "reason": "sonarr_state_changed"})
            return {"key": key, "status": "preserved", "reason": "sonarr_state_changed"}
        expected_monitoring = {row["id"]: row["monitored"] for row in prior["episodes"]}
        current_monitoring = {row["id"]: row["monitored"] for row in current["episodes"]}
        if prior.get("status") == "unmonitored":
            if any(current_monitoring.get(ep_id) is not False for ep_id in expected_monitoring):
                self.state.put(key, {**prior, "status": "preserved", "reason": "newer_user_edit"})
                return {"key": key, "status": "preserved", "reason": "newer_user_edit"}
        elif any(current_monitoring.get(ep_id) != monitored for ep_id, monitored in expected_monitoring.items()):
            self.state.put(key, {**prior, "status": "preserved", "reason": "newer_user_edit"})
            return {"key": key, "status": "preserved", "reason": "newer_user_edit"}
        if prior.get("status") != "unmonitored":
            try:
                # No mutation is allowed until the just-in-time watch/history
                # and playback snapshot still proves eligibility.
                self._revalidate_candidate(item)
            except RetentionBlocked as error:
                self.state.put(key, {**prior, "status": "preserved", "reason": error.reason})
                return {"key": key, "status": "preserved", "reason": error.reason}
            except Exception:
                self.state.put(key, {**prior, "status": "preserved", "reason": "revalidation_failed"})
                return {"key": key, "status": "preserved", "reason": "revalidation_failed"}
            record = {**prior, "status": "planned"}
            self.state.put(key, record)
            changed = []
            try:
                for episode in current["raw_episodes"]:
                    if expected_monitoring.get(episode.get("id")) is True:
                        payload = dict(episode)
                        payload["monitored"] = False
                        self.sonarr.set_episode(payload)
                        changed.append(dict(episode))
            except Exception:
                rollback_failed = False
                for episode in reversed(changed):
                    try:
                        self.sonarr.set_episode(episode)
                    except Exception:
                        rollback_failed = True
                reason = (
                    "unmonitor_rollback_failed" if rollback_failed else "unmonitor_failed"
                )
                failed = {
                    **record,
                    "status": "preserved",
                    "reason": reason,
                    "changed_episode_ids": sorted(
                        row.get("id") for row in changed if _positive_identifier(row.get("id"))
                    ),
                }
                self.state.put(key, failed)
                return {"key": key, "status": "preserved", "reason": reason}
            record["status"] = "unmonitored"
            record["unmonitored_episode_ids"] = sorted(expected_monitoring)
            self.state.put(key, record)
            prior = record
        try:
            # Re-query complete Trakt history, current Sonarr state, and
            # playback after unmonitoring and immediately before deletion.
            self._revalidate_before_delete(item)
            if self.jellyfin.playback_for_file(item["file"]["path"]):
                return self._preserve_after_unmonitor(item, prior, "playback_active")
        except RetentionBlocked as error:
            return self._preserve_after_unmonitor(item, prior, error.reason)
        except Exception:
            return self._preserve_after_unmonitor(
                item, prior, "playback_query_failed"
            )
        try:
            self.sonarr.delete_episode_file(item["file"]["id"])
        except Exception:
            self.state.put(key, {**prior, "status": "unmonitored", "reason": "delete_failed"})
            return {"key": key, "status": "unmonitored", "reason": "delete_failed"}
        record = {**prior, "status": "deleted", "deleted_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")}
        try:
            self.jellyfin.refresh()
            record["jellyfin_refresh"] = "ok"
        except Exception:
            record["jellyfin_refresh"] = "pending"
        self.state.put(key, record)
        return {"key": key, "status": "deleted", "jellyfin_refresh": record["jellyfin_refresh"]}

    def run(self, *, now=None):
        preview = self.preview(now=now)
        if preview.get("status") != "preview":
            return preview
        # The first snapshot is useful as the exact preview; this second,
        # independent snapshot is the commit gate.  A rewatch, playback
        # start, mapping change, or pagination failure between them leaves the
        # item preserved and prevents a stale delete.
        preview = self.preview(now=now)
        if preview.get("status") != "preview":
            return preview
        self._commit_now = now
        records = self.state.load().get("items", {})
        candidates = {item["key"]: item for item in preview["eligible"]}
        # A restart can leave an unmonitor intent while the next fresh
        # snapshot moves the item to preserved (for example, a rewatch). Keep
        # that intent in the commit queue so it is explicitly revalidated and
        # marked preserved rather than silently abandoned.
        for key, record in records.items():
            if key in candidates or not isinstance(record, dict):
                continue
            if record.get("status") not in {"planned", "unmonitored"}:
                continue
            if not all(record.get(field) is not None for field in ("series_id", "file", "episodes")):
                continue
            candidates[key] = record
        outcomes = []
        for item in candidates.values():
            if not isinstance(item, dict):
                continue
            previous = records.get(item["key"])
            if previous and previous.get("status") == "deleted":
                continue
            if (
                previous
                and previous.get("status") == "preserved"
                and previous.get("reason") == "unmonitor_rollback_failed"
            ):
                outcomes.append(
                    {
                        "key": item["key"],
                        "status": "preserved",
                        "reason": "unmonitor_rollback_failed",
                    }
                )
                continue
            prior = previous if previous and previous.get("status") in {"planned", "unmonitored"} else {
                "key": item["key"],
                "status": "planned",
                "series_id": item["series_id"],
                "file": item["file"],
                "episodes": item["episodes"],
                "watches": item["watches"],
                "prior_monitoring": {str(row["id"]): row["monitored"] for row in item["episodes"]},
            }
            outcomes.append(self._commit_item(item, prior))
        return {**preview, "status": "completed", "outcomes": outcomes}


def preview_trakt_retention(*, now=None, **kwargs):
    """Convenience preview seam; remains inert unless explicitly enabled."""
    return TraktRetentionRunner(**kwargs).preview(now=now)


def run_trakt_retention_cycle(*, now=None, **kwargs):
    return TraktRetentionRunner(**kwargs).run(now=now)


_scheduler_stop = threading.Event()
_scheduler_thread = None
_scheduler_thread_lock = threading.Lock()
_scheduler_status_lock = threading.Lock()
_scheduler_status = {"lastCycleAt": None, "lastStatus": None, "lastError": None}
_SAFE_CYCLE_STATUSES = {"blocked", "completed", "disabled", "retention_cycle_failed"}
_scheduler_logger = logging.getLogger(__name__)


def get_trakt_retention_scheduler_status():
    with _scheduler_thread_lock:
        with _scheduler_status_lock:
            return {
                "running": bool(
                    _scheduler_thread is not None and _scheduler_thread.is_alive()
                ),
                "lastCycleAt": _scheduler_status["lastCycleAt"],
                "lastStatus": _scheduler_status["lastStatus"],
                "lastError": _scheduler_status["lastError"],
            }


def _record_scheduler_cycle(status, error=None):
    with _scheduler_status_lock:
        _scheduler_status["lastCycleAt"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        )
        _scheduler_status["lastStatus"] = status
        _scheduler_status["lastError"] = error


def _retention_scheduler_loop(interval_seconds, stop_event, run_cycle, wait):
    while True:
        try:
            cycle = run_cycle()
        except Exception:
            _record_scheduler_cycle(
                "retention_cycle_failed", "retention_cycle_failed"
            )
            _scheduler_logger.warning("retention_cycle_failed")
        else:
            status = cycle.get("status") if isinstance(cycle, dict) else None
            if status not in _SAFE_CYCLE_STATUSES:
                status = "retention_cycle_failed"
            _record_scheduler_cycle(
                status,
                "retention_cycle_failed"
                if status == "retention_cycle_failed"
                else None,
            )
        if wait(stop_event, interval_seconds):
            return


def _validated_interval(interval_seconds):
    if isinstance(interval_seconds, bool) or not isinstance(
        interval_seconds, (int, float)
    ):
        raise ValueError("Trakt retention interval must be a positive finite number")
    if not math.isfinite(interval_seconds) or interval_seconds <= 0:
        raise ValueError("Trakt retention interval must be a positive finite number")
    return float(interval_seconds)


def start_trakt_retention_scheduler(interval_seconds=None, *, run_cycle=None):
    """Start only when the explicit feature flag is enabled."""
    if not settings.TRAKT_RETENTION_ENABLED or not settings.TRAKT_CLIENT_ID or not settings.TRAKT_CLIENT_SECRET:
        return False
    interval = _validated_interval(
        settings.TRAKT_RETENTION_INTERVAL_SECONDS
        if interval_seconds is None
        else interval_seconds
    )
    global _scheduler_thread, _scheduler_stop
    with _scheduler_thread_lock:
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            return False
        stop_event = threading.Event()
        _scheduler_stop = stop_event
        cycle = run_cycle or run_trakt_retention_cycle
        thread = threading.Thread(
            target=lambda: _retention_scheduler_loop(
                interval,
                stop_event,
                cycle,
                lambda event, timeout: event.wait(timeout),
            ),
            name="trakt-48h-retention",
            daemon=True,
        )
        _scheduler_thread = thread
        thread.start()
        return True


def stop_trakt_retention_scheduler(timeout=2.0):
    global _scheduler_thread
    with _scheduler_thread_lock:
        thread = _scheduler_thread
        _scheduler_stop.set()
    if thread is None:
        return True
    if thread.is_alive():
        thread.join(timeout=timeout)
        if thread.is_alive():
            return False
    with _scheduler_thread_lock:
        if _scheduler_thread is thread:
            _scheduler_thread = None
    return True


__all__ = [
    "HISTORY_PAGE_LIMIT",
    "RETENTION_SECONDS",
    "JellyfinRetentionClient",
    "RetentionBlocked",
    "RetentionStateStore",
    "SonarrRetentionClient",
    "TraktRetentionRunner",
    "build_retention_preview",
    "fetch_complete_trakt_history",
    "get_trakt_retention_scheduler_status",
    "latest_watches",
    "preview_trakt_retention",
    "run_trakt_retention_cycle",
    "start_trakt_retention_scheduler",
    "stop_trakt_retention_scheduler",
]
