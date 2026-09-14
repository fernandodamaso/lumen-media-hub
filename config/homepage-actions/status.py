"""Bounded, read-only status projections for staged storage protections.

The installer guard and the two cleanup runners are not started by this API.
This module reports their configured state and durable summaries without
calling qBittorrent, Arr, Jellyfin, or Trakt and without exposing private
state-file contents.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timezone

import config as settings
from clients.trakt import TraktTokenStore


MAX_STATE_ITEMS = 20
_KNOWN_RESULT_STATUSES = {
    "ambiguous_delete",
    "delete_outcome_unknown",
    "deleted",
    "library_missing_after_delete",
    "preserved",
    "skipped",
    "source_remains",
    "verified",
}
_KNOWN_RETENTION_STATUSES = {"deleted", "planned", "preserved", "unmonitored"}
_SAFE_REASON = {
    "disabled",
    "auth_required",
    "delete_failed",
    "incomplete_import_history",
    "invalid_history_response",
    "invalid_history_page",
    "history_changed_during_snapshot",
    "invalid_history_pagination",
    "playback_active",
    "playback_query_failed",
    "revalidation_failed",
    "sonarr_state_changed",
    "unmonitor_failed",
    "unknown_series_identity",
    "ambiguous_series_mapping",
    "unwatched_episode",
    "watch_within_48h",
    "future_episode",
    "missing_episode_file",
    "ambiguous_episode_file_mapping",
}


def _read_object(path):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, TypeError, ValueError, UnicodeDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _safe_reason(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value in _SAFE_REASON else ("other" if value else None)


def _iso_epoch(value):
    try:
        stamp = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not stamp > 0:
        return None
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _disk(path, identifier, label):
    try:
        usage = shutil.disk_usage(path)
        stats = os.statvfs(path)
        block = int(stats.f_frsize or stats.f_bsize)
        available = int(stats.f_bavail) * block
        free = int(stats.f_bfree) * block
        total = int(usage.total)
        if min(available, free, total) < 0 or available > total or free > total:
            raise ValueError("invalid capacity")
        os.stat(path)
    except (OSError, TypeError, ValueError, OverflowError):
        return {
            "id": identifier,
            "label": label,
            "status": "unavailable",
            "identityStatus": "unavailable",
            "availableBytes": None,
            "freeBytes": None,
            "usedBytes": None,
            "totalBytes": None,
        }
    return {
        "id": identifier,
        "label": label,
        "status": "healthy",
        "identityStatus": "observed",
        "availableBytes": available,
        "freeBytes": free,
        "usedBytes": max(0, total - free),
        "totalBytes": total,
    }


def build_storage_status():
    """Measure only the two role paths visible to homepage-actions."""
    disks = [
        _disk("/downloads", "staging", "Staging"),
        _disk("/data/media", "library", "Library"),
    ]
    healthy = all(item["status"] == "healthy" and item["identityStatus"] == "observed" for item in disks)
    return {"status": "healthy" if healthy else "unavailable", "disks": disks}


def _state_summary(path, statuses):
    raw = _read_object(path)
    records = raw.get("items") if isinstance(raw.get("items"), dict) else raw
    if not isinstance(records, dict):
        records = {}
    counts = {status: 0 for status in statuses}
    latest = None
    for record in records.values():
        if not isinstance(record, dict):
            continue
        status = record.get("status")
        if status in counts:
            counts[status] += 1
            latest = {"status": status, "reason": _safe_reason(record.get("reason"))}
    return counts, latest


def _verified_cleanup_status():
    enabled = bool(getattr(settings, "VERIFIED_CLEANUP_ENABLED", False))
    counts, latest = _state_summary(settings.VERIFIED_CLEANUP_STATE_PATH, _KNOWN_RESULT_STATUSES)
    pending = counts.get("verified", 0)
    result = {
        "enabled": enabled,
        "status": "disabled" if not enabled else ("queued" if pending else ("ready" if latest else "idle")),
        "lastResult": latest if enabled else None,
        "queueCount": pending if enabled else 0,
    }
    return result


def _verification_status(cleanup):
    if not cleanup["enabled"]:
        return {"status": "disabled", "queuedCount": 0, "previewCount": 0}
    return {
        "status": "queued" if cleanup["queueCount"] else "idle",
        "queuedCount": cleanup["queueCount"],
        "previewCount": cleanup["queueCount"],
    }


def _retention_status():
    enabled = bool(getattr(settings, "TRAKT_RETENTION_ENABLED", False))
    counts, latest = _state_summary(settings.TRAKT_RETENTION_STATE_PATH, _KNOWN_RETENTION_STATUSES)
    skips = []
    raw = _read_object(settings.TRAKT_RETENTION_STATE_PATH)
    records = raw.get("items") if isinstance(raw.get("items"), dict) else raw
    reasons = {}
    if isinstance(records, dict):
        for record in records.values():
            if not isinstance(record, dict) or record.get("status") != "preserved":
                continue
            reason = _safe_reason(record.get("reason")) or "other"
            reasons[reason] = reasons.get(reason, 0) + 1
    for reason, count in sorted(reasons.items())[:MAX_STATE_ITEMS]:
        skips.append({"reason": reason, "count": count})
    preview = {
        "eligibleCount": counts.get("planned", 0) + counts.get("unmonitored", 0),
        "preservedCount": counts.get("preserved", 0),
    }
    results = {
        "deletedCount": counts.get("deleted", 0),
        "preservedCount": counts.get("preserved", 0),
        "pendingCount": counts.get("planned", 0) + counts.get("unmonitored", 0),
    }
    return {
        "enabled": enabled,
        "status": "disabled" if not enabled else ("result" if latest else "idle"),
        "preview": preview if enabled else None,
        "skips": skips if enabled else [],
        "results": results if enabled else {"deletedCount": 0, "preservedCount": 0, "pendingCount": 0},
        "lastResult": latest if enabled else None,
        "scheduler": {"enabled": False, "running": False},
    }


def _trakt_status():
    configured = bool(settings.TRAKT_CLIENT_ID and settings.TRAKT_CLIENT_SECRET)
    if not configured:
        return {"configured": False, "auth": "unconfigured", "health": "unavailable", "expiresAt": None}
    try:
        state = TraktTokenStore(settings.TRAKT_TOKEN_PATH).load()
    except ValueError:
        return {"configured": True, "auth": "invalid", "health": "unavailable", "expiresAt": None}
    except (OSError, RuntimeError):
        return {"configured": True, "auth": "unavailable", "health": "unavailable", "expiresAt": None}
    if state is None:
        return {"configured": True, "auth": "missing_token", "health": "unavailable", "expiresAt": None}
    expires_at = _iso_epoch(state.expires_at)
    if state.expires_at - time.time() < 60:
        return {"configured": True, "auth": "expired", "health": "unavailable", "expiresAt": expires_at}
    return {"configured": True, "auth": "healthy", "health": "healthy", "expiresAt": expires_at}


def _guard_status():
    enabled = bool(getattr(settings, "DISK_GUARD_ENABLED", False))
    if not enabled:
        return {"enabled": False, "status": "disabled", "health": "disabled", "lastCycleAt": None}
    state = _read_object(getattr(settings, "DISK_GUARD_STATE_PATH", "/state/disk-guard-state.json"))
    updated_at = state.get("updated_at") if isinstance(state.get("updated_at"), str) else None
    fresh = False
    if updated_at:
        try:
            stamp = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            fresh = (datetime.now(timezone.utc) - stamp).total_seconds() <= 15
        except (TypeError, ValueError, OverflowError):
            fresh = False
    if fresh and state.get("status") == "healthy":
        return {"enabled": True, "status": "active", "health": "healthy", "lastCycleAt": updated_at}
    if fresh and state.get("status") in {"qbit-unavailable", "guard-failed", "destination-unavailable"}:
        return {"enabled": True, "status": "blocked", "health": "fail_closed", "lastCycleAt": updated_at}
    return {"enabled": True, "status": "staged", "health": "not_running", "lastCycleAt": updated_at}


def build_operational_status():
    cleanup = _verified_cleanup_status()
    storage = build_storage_status()
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "storage": storage,
        "pause": {
            "status": "not_reported",
            "reason": "not_reported",
            "manual": None,
            "guard": None,
            "known": False,
        },
        "guard": _guard_status(),
        "verifiedCleanup": cleanup,
        "verification": _verification_status(cleanup),
        "trakt": _trakt_status(),
        "retention": _retention_status(),
    }


__all__ = ["build_operational_status", "build_storage_status"]
