"""Pure diagnostics for stale Sonarr queue imports.

This module deliberately contains no network calls or mutation.  It classifies a
complete Sonarr queue snapshot against a qBittorrent snapshot so callers can
choose whether an independently verified cleanup is appropriate.
"""
from datetime import datetime, timezone
import math
import re


NOT_AN_UPGRADE_PREFIX = "Not an upgrade for existing episode file(s)."
_HASH_PATTERN = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
_COMPLETED_STATES = {"completed", "importpending", "importblocked"}


def _flatten(value):
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        result = []
        for item in value:
            result.extend(_flatten(item))
        return result
    if isinstance(value, dict):
        if "messages" in value:
            return _flatten(value.get("messages"))
        if "message" in value:
            return _flatten(value.get("message"))
    return []


def flatten_status_messages(row):
    """Return Sonarr status-message text in source order."""
    if not isinstance(row, dict):
        return []
    return _flatten(row.get("statusMessages", []))


def group_queue_by_download_id(records):
    """Group well-formed rows by case-insensitive download id."""
    groups = {}
    for row in records or []:
        if not isinstance(row, dict):
            continue
        raw_id = row.get("downloadId")
        if not isinstance(raw_id, str) or not raw_id.strip():
            continue
        key = raw_id.strip().lower()
        groups.setdefault(key, []).append(row)
    return {key: groups[key] for key in sorted(groups)}


def _positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_hash(value):
    return isinstance(value, str) and _HASH_PATTERN.fullmatch(value.strip()) is not None


def _parse_timestamp(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normal_status(value):
    if not isinstance(value, str):
        return ""
    return value.strip().lower().replace("_", "")


def _row_has_completed_state(row):
    return any(
        _normal_status(row.get(field)) in _COMPLETED_STATES
        for field in ("status", "trackedDownloadStatus", "trackedDownloadState")
    )


def _title(row):
    value = row.get("title")
    return value.strip() if isinstance(value, str) and value.strip() else "Unknown"


def _blocked(queue_id, title, reason, blocker):
    return {
        "queueId": queue_id,
        "title": title,
        "reason": reason,
        "blocker": blocker,
    }


def _row_reason_and_blocker(row):
    messages = flatten_status_messages(row)
    if not messages:
        return "", "unknown_reason"
    valid = [message for message in messages if message.startswith(NOT_AN_UPGRADE_PREFIX)]
    invalid = [message for message in messages if not message.startswith(NOT_AN_UPGRADE_PREFIX)]
    if invalid:
        return messages[0], "mixed_reason" if valid else "unknown_reason"
    return valid[0], None


def _build_qbt_index(qbt_torrents):
    index = {}
    for torrent in qbt_torrents or []:
        if not isinstance(torrent, dict):
            continue
        raw_hash = torrent.get("hash")
        if _valid_hash(raw_hash):
            index.setdefault(raw_hash.strip().lower(), torrent)
    return index


def _qbt_completion(torrent, now, grace_seconds):
    if not isinstance(torrent, dict):
        return None, "malformed"
    progress = torrent.get("progress")
    amount_left = torrent.get("amount_left")
    completion_on = torrent.get("completion_on")
    numeric = lambda value: isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if not numeric(progress) or not numeric(amount_left) or not numeric(completion_on):
        return None, "malformed"
    if progress != 1 or amount_left != 0 or completion_on <= 0:
        return None, "active_download"
    try:
        completed_at = datetime.fromtimestamp(completion_on, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None, "malformed"
    age_seconds = (now - completed_at).total_seconds()
    if age_seconds < grace_seconds:
        return None, "grace_period"
    return (completed_at, age_seconds), None


def classify_queue(queue_records, qbt_torrents, now, grace_seconds):
    """Classify queue rows without performing any external side effect."""
    if not isinstance(now, datetime):
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None or now.utcoffset() is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    try:
        grace_seconds = float(grace_seconds)
    except (TypeError, ValueError):
        grace_seconds = float("inf")
    if not math.isfinite(grace_seconds) or grace_seconds < 0:
        grace_seconds = float("inf")

    records = list(queue_records or [])
    qbt_index = _build_qbt_index(qbt_torrents)
    groups = group_queue_by_download_id(records)
    grouped_ids = {id(row) for rows in groups.values() for row in rows}
    blocked = []
    eligible = []

    for row in records:
        if not isinstance(row, dict) or id(row) not in grouped_ids:
            queue_id = row.get("id") if isinstance(row, dict) else None
            blocked.append(_blocked(queue_id, _title(row) if isinstance(row, dict) else "Unknown", "", "malformed"))

    for group_key, rows in groups.items():
        row_checks = []
        for row in rows:
            queue_id = row.get("id")
            reason, reason_blocker = _row_reason_and_blocker(row)
            blocker = None
            if not _positive_int(queue_id):
                blocker = "malformed"
            elif not _valid_hash(row.get("downloadId")):
                blocker = "malformed"
            elif not row.get("episodeHasFile") is True:
                blocker = "no_episode_file"
            elif not _row_has_completed_state(row):
                blocker = "malformed"
            elif reason_blocker:
                blocker = reason_blocker
            row_checks.append({"row": row, "queue_id": queue_id, "reason": reason, "blocker": blocker})

        first_reason = next((item["reason"] for item in row_checks if item["reason"]), "")
        group_blocker = next((item["blocker"] for item in row_checks if item["blocker"]), None)
        if group_blocker is not None:
            for item in row_checks:
                blocked.append(
                    _blocked(item["queue_id"], _title(item["row"]), item["reason"] or first_reason, item["blocker"] or "mixed_group")
                )
            continue

        torrent = qbt_index.get(group_key)
        if torrent is None:
            for item in row_checks:
                blocked.append(_blocked(item["queue_id"], _title(item["row"]), item["reason"], "missing_qbt"))
            continue
        completion, qbt_blocker = _qbt_completion(torrent, now, grace_seconds)
        if qbt_blocker:
            for item in row_checks:
                blocked.append(_blocked(item["queue_id"], _title(item["row"]), item["reason"], qbt_blocker))
            continue

        completed_at, age_seconds = completion
        eligible.append(
            {
                "downloadId": rows[0].get("downloadId").strip(),
                "queueIds": sorted(item["queue_id"] for item in row_checks),
                "titles": [_title(item["row"]) for item in row_checks],
                "reason": first_reason,
                "completedAt": _format_timestamp(completed_at),
                "ageHours": round(age_seconds / 3600, 2),
            }
        )

    blocked.sort(key=lambda item: (item["queueId"] is None, item["queueId"] if isinstance(item["queueId"], int) else 0, item["title"]))
    eligible.sort(key=lambda item: item["downloadId"].lower())
    return {
        "observedAt": _format_timestamp(now),
        "totalQueued": len(records),
        "eligibleGroups": eligible,
        "blockedItems": blocked,
    }
