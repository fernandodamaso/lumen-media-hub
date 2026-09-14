"""Staged verification and opt-in removal of imported torrent originals.

This module is deliberately separate from queue hygiene and library deletion.
It never runs at startup and only qBittorrent owns source removal.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
from pathlib import Path

import config as settings


IMPORT_EVENTS = {
    "downloadFolderImported",
    "episodeFileImported",
    "seriesFolderImported",
    "movieFolderImported",
    "movieFileImported",
}
STOPPED_STATES = {
    "pausedUP",
    "pausedDL",
    "stoppedUP",
    "stoppedDL",
    "stopped",
    "paused",
}
_PATH_KEYS = ("sourcePath", "droppedPath", "downloadedPath", "source_path")
_DESTINATION_KEYS = (
    "importedPath",
    "destinationPath",
    "targetPath",
    "episodeFilePath",
    "movieFilePath",
    "imported_path",
)


class _Skip(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _valid_hash(value):
    return (
        isinstance(value, str)
        and len(value) in (40, 64)
        and all(char in "0123456789abcdefABCDEF" for char in value)
    )


def _positive_id(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _mapping(value):
    if not isinstance(value, dict):
        raise _Skip("invalid_arr_mapping")
    service = value.get("service")
    arr_id = _positive_id(value.get("id"))
    if service not in ("sonarr", "radarr") or arr_id is None:
        raise _Skip("invalid_arr_mapping")
    return service, arr_id


def _absolute(path, reason):
    if not isinstance(path, str) or not path or "\x00" in path:
        raise _Skip(reason)
    value = Path(path)
    if not value.is_absolute():
        raise _Skip(reason)
    return value


def _resolved(path):
    return Path(os.path.abspath(os.fspath(path))).resolve(strict=False)


def _inside(path, root):
    try:
        _resolved(path).relative_to(_resolved(root))
        return True
    except ValueError:
        return False


def _lexically_inside(path, root):
    try:
        Path(os.path.abspath(os.fspath(path))).relative_to(Path(os.path.abspath(os.fspath(root))))
        return True
    except ValueError:
        return False


def _path_overlap(left, right):
    left, right = _resolved(left), _resolved(right)
    return left == right or _inside(left, right) or _inside(right, left)


def _has_symlink(path, stop):
    current = Path(path)
    stop = _resolved(stop)
    while True:
        try:
            if current.is_symlink():
                return True
        except OSError:
            return False
        if _resolved(current) == stop or current.parent == current:
            return False
        current = current.parent


def _safe_file_path(content_path, name):
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
        raise _Skip("unsafe_file_path")
    parts = Path(name).parts
    if Path(name).is_absolute() or any(part in ("", ".", "..") for part in parts):
        raise _Skip("unsafe_file_path")
    # qBittorrent reports a single-file torrent's content_path as the file
    # itself, while its file inventory still uses the basename.  Accept only
    # that exact basename; never reinterpret an arbitrary child as a sibling
    # or allow a file path to become a directory root.
    if Path(content_path).is_file():
        if len(parts) != 1 or parts[0] != Path(content_path).name:
            raise _Skip("unsafe_file_path")
        return Path(content_path)
    candidate = Path(content_path, *parts)
    if not _lexically_inside(candidate, content_path):
        raise _Skip("unsafe_file_path")
    return candidate


def _fingerprint(path, reason):
    try:
        before = os.lstat(path)
    except OSError:
        raise _Skip(reason)
    if os.path.islink(path):
        raise _Skip("symlink_source" if reason == "source_missing" else "symlink_destination")
    if not os.path.isfile(path):
        raise _Skip(reason)
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        after = os.lstat(path)
    except OSError:
        raise _Skip(reason)
    if (before.st_size, before.st_mtime_ns, before.st_ino, before.st_dev) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ino,
        after.st_dev,
    ):
        raise _Skip("source_changed_during_hash" if reason == "source_missing" else "destination_changed_during_hash")
    return {
        "size": after.st_size,
        "mtime_ns": after.st_mtime_ns,
        "inode": after.st_ino,
        "device": after.st_dev,
        "sha256": digest.hexdigest(),
    }


def _content_files(content_path):
    try:
        stat = os.lstat(content_path)
    except OSError:
        raise _Skip("source_missing")
    if os.path.islink(content_path):
        raise _Skip("symlink_source")
    if os.path.isdir(content_path):
        files = []
        for current, directories, names in os.walk(content_path, topdown=True, followlinks=False):
            for name in directories + names:
                item = Path(current, name)
                if item.is_symlink():
                    raise _Skip("symlink_source")
            for name in names:
                item = Path(current, name)
                if not item.is_file():
                    raise _Skip("source_missing")
                files.append(item)
        return sorted(files, key=lambda item: item.as_posix())
    if stat and os.path.isfile(content_path):
        return [Path(content_path)]
    raise _Skip("source_missing")


def _qbit_files(files, content_path):
    if not isinstance(files, list) or not files:
        raise _Skip("qbit_file_inventory_unavailable")
    result = []
    names = set()
    indexes = set()
    single_file = content_path.is_file()
    if single_file and len(files) != 1:
        raise _Skip("qbit_file_inventory_incomplete")
    for item in files:
        if not isinstance(item, dict):
            raise _Skip("qbit_file_inventory_incomplete")
        name = item.get("name")
        if single_file:
            if not isinstance(name, str) or Path(name).name != name:
                raise _Skip("unsafe_file_path")
            source = content_path
        else:
            source = _safe_file_path(content_path, name)
        if name in names:
            raise _Skip("qbit_file_inventory_incomplete")
        names.add(name)
        index = item.get("index")
        if index is not None:
            if isinstance(index, bool) or not isinstance(index, int) or index in indexes:
                raise _Skip("qbit_file_inventory_incomplete")
            indexes.add(index)
        size = item.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise _Skip("qbit_file_inventory_incomplete")
        priority = item.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise _Skip("qbit_file_inventory_incomplete")
        if priority <= 0:
            raise _Skip("qbit_file_not_selected")
        progress = item.get("progress")
        if progress is not None:
            if isinstance(progress, bool) or not isinstance(progress, (int, float)) or not math.isfinite(progress):
                raise _Skip("qbit_file_incomplete")
        if not ((isinstance(progress, (int, float)) and progress >= 1.0) or item.get("is_seed") is True):
            raise _Skip("qbit_file_incomplete")
        result.append(
            {"name": name, "index": index, "size": size, "priority": priority, "source": source}
        )
    return result


def _history_paths(record):
    data = record.get("data") if isinstance(record.get("data"), dict) else {}
    source = next((data.get(key) or record.get(key) for key in _PATH_KEYS if data.get(key) or record.get(key)), None)
    destination = next(
        (data.get(key) or record.get(key) for key in _DESTINATION_KEYS if data.get(key) or record.get(key)),
        None,
    )
    return source, destination


def _arr_records(arr, service, arr_id, torrent_hash):
    try:
        entity = arr.library(service, arr_id)
    except Exception:
        raise _Skip("arr_unavailable")
    if not isinstance(entity, dict) or entity.get("id") not in (None, arr_id):
        raise _Skip("library_missing")
    try:
        history = arr.history(service, arr_id)
    except Exception:
        raise _Skip("arr_unavailable")
    if not isinstance(history, dict) or history.get("complete") is not True:
        raise _Skip("incomplete_import_history")
    records = history.get("records")
    total = history.get("totalRecords")
    if not isinstance(records, list) or isinstance(total, bool) or not isinstance(total, int) or total != len(records):
        raise _Skip("incomplete_import_history")
    matching = []
    for record in records:
        if not isinstance(record, dict) or str(record.get("downloadId") or "").lower() != torrent_hash:
            continue
        if record.get("eventType") not in IMPORT_EVENTS:
            continue
        entity_key = "seriesId" if service == "sonarr" else "movieId"
        if record.get(entity_key) not in (None, arr_id):
            continue
        source, destination = _history_paths(record)
        if source is None or destination is None:
            raise _Skip("incomplete_import_history")
        matching.append((record, source, destination))
    return entity, matching


def _fresh_snapshot(torrent_hash, mapping, qbit, arr, downloads_root, library_root, require_stopped=False):
    torrent_hash = torrent_hash.lower() if _valid_hash(torrent_hash) else None
    if torrent_hash is None:
        raise _Skip("invalid_torrent_hash")
    downloads_root = _resolved(_absolute(os.fspath(downloads_root), "invalid_downloads_root"))
    library_root = _resolved(_absolute(os.fspath(library_root), "invalid_library_root"))
    if downloads_root == library_root or _path_overlap(downloads_root, library_root):
        raise _Skip("source_destination_alias")
    service, arr_id = _mapping(mapping)
    try:
        torrent = qbit.torrent(torrent_hash)
    except Exception:
        raise _Skip("qbit_unavailable")
    if not isinstance(torrent, dict):
        raise _Skip("torrent_missing")
    if str(torrent.get("hash") or "").lower() != torrent_hash:
        raise _Skip("torrent_identity_changed")
    content_path = _absolute(torrent.get("content_path"), "content_path_missing")
    if not _inside(content_path, downloads_root):
        raise _Skip("source_outside_downloads")
    if _has_symlink(content_path, downloads_root):
        raise _Skip("symlink_source")
    state = torrent.get("state")
    if require_stopped and state not in STOPPED_STATES:
        raise _Skip("stop_not_confirmed")
    progress = torrent.get("progress")
    amount_left = torrent.get("amount_left")
    if (
        isinstance(progress, bool)
        or not isinstance(progress, (int, float))
        or not math.isfinite(progress)
        or progress < 1.0
        or isinstance(amount_left, bool)
        or not isinstance(amount_left, int)
        or amount_left != 0
    ):
        raise _Skip("torrent_incomplete")
    try:
        files = qbit.files(torrent_hash)
        all_torrents = qbit.torrents()
    except Exception:
        raise _Skip("qbit_unavailable")
    if not isinstance(all_torrents, list):
        raise _Skip("qbit_torrent_inventory_unavailable")
    for other in all_torrents:
        if not isinstance(other, dict) or not _valid_hash(other.get("hash")):
            raise _Skip("qbit_torrent_inventory_incomplete")
        other_path = _absolute(other.get("content_path"), "qbit_torrent_inventory_incomplete")
        if _has_symlink(other_path, downloads_root):
            raise _Skip("symlink_source")
        other_hash = other["hash"].lower()
        if other_hash == torrent_hash:
            if _resolved(other_path) != _resolved(content_path):
                raise _Skip("torrent_identity_changed")
        elif _path_overlap(other_path, content_path):
            raise _Skip("shared_source_path")
    qbit_files = _qbit_files(files, content_path)
    actual_files = _content_files(content_path)
    actual_by_path = {_resolved(item): item for item in actual_files}
    expected_by_path = {_resolved(item["source"]): item for item in qbit_files}
    if (
        len(actual_by_path) != len(actual_files)
        or len(expected_by_path) != len(qbit_files)
        or set(actual_by_path) != set(expected_by_path)
    ):
        raise _Skip("unknown_extra")
    _entity, history = _arr_records(arr, service, arr_id, torrent_hash)
    matches = {}
    destinations = set()
    for qbit_file in qbit_files:
        source = _resolved(qbit_file["source"])
        candidates = []
        for record, source_text, destination_text in history:
            source_path = _absolute(source_text, "incomplete_import_history")
            destination_path = _absolute(destination_text, "incomplete_import_history")
            if not _lexically_inside(source_path, downloads_root) or not _inside(source_path, downloads_root):
                raise _Skip("source_outside_downloads")
            if _has_symlink(source_path, downloads_root):
                raise _Skip("symlink_source")
            if _resolved(source_path) == source:
                candidates.append((record, destination_path))
        if len(candidates) != 1:
            raise _Skip("ambiguous_import_history" if len(candidates) > 1 else "missing_import_evidence")
        record, destination = candidates[0]
        if not _lexically_inside(destination, library_root) or not _inside(destination, library_root):
            raise _Skip("destination_outside_library")
        if _has_symlink(destination, library_root):
            raise _Skip("symlink_destination")
        destination = _resolved(destination)
        if destination in destinations:
            raise _Skip("ambiguous_import_history")
        if _path_overlap(source, destination):
            raise _Skip("source_destination_alias")
        destinations.add(destination)
        source_fingerprint = _fingerprint(source, "source_missing")
        destination_fingerprint = _fingerprint(destination, "destination_missing")
        if source_fingerprint["sha256"] != destination_fingerprint["sha256"]:
            raise _Skip("hash_mismatch")
        if source_fingerprint["size"] != qbit_file["size"] or source_fingerprint["size"] != destination_fingerprint["size"]:
            raise _Skip("size_mismatch")
        matches[qbit_file["name"]] = {
            "history_id": record.get("id"),
            "source": str(source),
            "destination": str(destination),
            "source_fingerprint": source_fingerprint,
            "destination_fingerprint": destination_fingerprint,
        }
    fingerprint = {
        "hash": torrent_hash,
        "content_path": str(_resolved(content_path)),
        "files": [
            {
                "name": item["name"],
                "size": item["size"],
                "index": item["index"],
                "priority": item["priority"],
            }
            for item in qbit_files
        ],
        "matches": matches,
    }
    return {
        "status": "verified",
        "reason": "verified",
        "torrent_hash": torrent_hash,
        "state": state,
        "fingerprint": fingerprint,
        "files": list(matches.values()),
    }


class _State:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    def put(self, torrent_hash, record):
        value = self.load()
        value[torrent_hash] = record
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def verify_torrent(
    torrent_hash,
    mapping,
    *,
    qbit,
    arr,
    downloads_root,
    library_root,
):
    """Derive a fresh read-only verification result for one torrent."""
    try:
        return _fresh_snapshot(torrent_hash, mapping, qbit, arr, downloads_root, library_root)
    except _Skip as error:
        return {"status": "skipped", "reason": error.reason, "torrent_hash": torrent_hash}


def _terminal_record(record, torrent_hash):
    if not isinstance(record, dict) or record.get("torrent_hash", torrent_hash) != torrent_hash:
        return None
    if record.get("status") in {
        "ambiguous_delete",
        "delete_outcome_unknown",
        "source_remains",
        "library_missing_after_delete",
        "library_changed_after_delete",
        "deleted",
    }:
        return record
    return None


def apply_verified_cleanup(
    torrent_hash,
    mapping,
    *,
    qbit=None,
    arr=None,
    downloads_root="/downloads",
    library_root="/data/media",
    enabled=None,
    state_path=None,
):
    """Stop, revalidate, and request qBittorrent source removal when enabled.

    ``enabled`` is an explicit rollout gate.  The default reads the false
    configuration flag and performs no API calls while disabled.
    """
    if enabled is None:
        enabled = settings.VERIFIED_CLEANUP_ENABLED
    if not enabled:
        return {"status": "disabled", "reason": "disabled", "torrent_hash": torrent_hash}
    if not _valid_hash(torrent_hash):
        return {"status": "skipped", "reason": "invalid_torrent_hash", "torrent_hash": torrent_hash}
    torrent_hash = torrent_hash.lower()
    state = _State(state_path or settings.VERIFIED_CLEANUP_STATE_PATH)
    previous = state.load().get(torrent_hash)
    terminal = _terminal_record(previous, torrent_hash)
    if terminal is not None:
        return dict(terminal, status=terminal["status"], reason=terminal["status"])
    if qbit is None:
        qbit = QbittorrentVerificationClient()
    if arr is None:
        arr = ArrVerificationClient()
    try:
        before = _fresh_snapshot(torrent_hash, mapping, qbit, arr, downloads_root, library_root)
        state.put(torrent_hash, {"status": "verified", "torrent_hash": torrent_hash, "fingerprint": before["fingerprint"], "files": before["files"]})
        if before["state"] not in STOPPED_STATES:
            try:
                qbit.stop(torrent_hash)
            except Exception:
                record = {
                    "status": "preserved",
                    "torrent_hash": torrent_hash,
                    "reason": "stop_failed",
                    "fingerprint": before["fingerprint"],
                }
                state.put(torrent_hash, record)
                return {"status": "skipped", "reason": record["reason"], "torrent_hash": torrent_hash}
        stop_deadline = time.monotonic() + 10
        while True:
            try:
                after = _fresh_snapshot(
                    torrent_hash,
                    mapping,
                    qbit,
                    arr,
                    downloads_root,
                    library_root,
                    require_stopped=True,
                )
                break
            except _Skip as error:
                if error.reason != "stop_not_confirmed" or time.monotonic() >= stop_deadline:
                    raise
                time.sleep(0.25)
        if after["fingerprint"] != before["fingerprint"]:
            state.put(torrent_hash, {"status": "preserved", "torrent_hash": torrent_hash, "reason": "snapshot_changed", "fingerprint": after["fingerprint"]})
            return {"status": "skipped", "reason": "snapshot_changed", "torrent_hash": torrent_hash}
        state.put(torrent_hash, {"status": "verified", "torrent_hash": torrent_hash, "fingerprint": after["fingerprint"], "files": after["files"]})
        try:
            qbit.delete(torrent_hash)
        except Exception:
            pass
        try:
            remaining = qbit.torrent(torrent_hash)
        except Exception:
            record = {"status": "delete_outcome_unknown", "torrent_hash": torrent_hash}
            state.put(torrent_hash, record)
            return dict(record, reason=record["status"])
        if remaining is not None:
            record = {"status": "ambiguous_delete", "torrent_hash": torrent_hash, "fingerprint": after["fingerprint"]}
            state.put(torrent_hash, record)
            return dict(record, reason=record["status"])
        service, arr_id = _mapping(mapping)
        try:
            library_entity = arr.library(service, arr_id)
        except Exception:
            library_entity = None
        if not isinstance(library_entity, dict) or library_entity.get("id") not in (None, arr_id):
            record = {"status": "library_missing_after_delete", "torrent_hash": torrent_hash}
            state.put(torrent_hash, record)
            return dict(record, reason=record["status"])
        post_library_fingerprints = []
        for item in after["files"]:
            try:
                destination_fingerprint = _fingerprint(item["destination"], "destination_missing")
            except _Skip:
                record = {
                    "status": "library_missing_after_delete",
                    "torrent_hash": torrent_hash,
                    "fingerprint": after["fingerprint"],
                }
                state.put(torrent_hash, record)
                return dict(record, reason=record["status"])
            if destination_fingerprint != item["destination_fingerprint"]:
                record = {
                    "status": "library_changed_after_delete",
                    "torrent_hash": torrent_hash,
                    "fingerprint": after["fingerprint"],
                }
                state.put(torrent_hash, record)
                return dict(record, reason=record["status"])
            post_library_fingerprints.append(
                {"path": item["destination"], "fingerprint": destination_fingerprint}
            )
        if any(os.path.lexists(item["source"]) for item in after["files"]):
            record = {"status": "source_remains", "torrent_hash": torrent_hash, "fingerprint": after["fingerprint"]}
            state.put(torrent_hash, record)
            return dict(record, reason=record["status"])
        record = {
            "status": "deleted",
            "torrent_hash": torrent_hash,
            "fingerprint": after["fingerprint"],
            "files": after["files"],
            "post_library_fingerprints": post_library_fingerprints,
        }
        state.put(torrent_hash, record)
        return dict(record, reason="deleted")
    except _Skip as error:
        state.put(
            torrent_hash,
            {"status": "preserved", "torrent_hash": torrent_hash, "reason": error.reason},
        )
        return {"status": "skipped", "reason": error.reason, "torrent_hash": torrent_hash}


class QbittorrentVerificationClient:
    """Small adapter over the existing stdlib qBittorrent client."""

    def __init__(self, opener=None):
        if opener is None:
            import http.cookiejar
            import urllib.request

            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            from clients.qbittorrent import qbt_login

            qbt_login(opener)
        self.opener = opener

    def torrent(self, torrent_hash):
        from clients.qbittorrent import qbt_get_json

        rows = qbt_get_json("/api/v2/torrents/info", self.opener, {"hashes": torrent_hash})
        return rows[0] if isinstance(rows, list) and len(rows) == 1 else None

    def torrents(self):
        from clients.qbittorrent import qbt_get_json

        return qbt_get_json("/api/v2/torrents/info", self.opener)

    def files(self, torrent_hash):
        from clients.qbittorrent import qbt_get_json

        return qbt_get_json("/api/v2/torrents/files", self.opener, {"hash": torrent_hash})

    def stop(self, torrent_hash):
        from clients.qbittorrent import qbt_post

        return qbt_post("/api/v2/torrents/stop", {"hashes": torrent_hash}, self.opener)

    def delete(self, torrent_hash):
        from clients.qbittorrent import qbt_post

        return qbt_post(
            "/api/v2/torrents/delete",
            {"hashes": torrent_hash, "deleteFiles": "true"},
            self.opener,
        )


class ArrVerificationClient:
    """Small adapter over existing Arr GET/history clients."""

    def _target(self, service):
        if service == "sonarr":
            return settings.SONARR_URL, settings.SONARR_API_KEY, "seriesIds", "/api/v3/series/"
        if service == "radarr":
            return settings.RADARR_URL, settings.RADARR_API_KEY, "movieIds", "/api/v3/movie/"
        raise ValueError("unsupported Arr service")

    def library(self, service, arr_id):
        from clients.arr import _arr_get

        base, key, _entity_param, path = self._target(service)
        return _arr_get(base, key, f"{path}{arr_id}")

    def history(self, service, arr_id):
        from clients.arr import fetch_arr_history_all

        base, key, entity_param, _path = self._target(service)
        return fetch_arr_history_all(base, key, entity_param, arr_id)


__all__ = [
    "ArrVerificationClient",
    "QbittorrentVerificationClient",
    "apply_verified_cleanup",
    "verify_torrent",
]
