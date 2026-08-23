"""Pure diagnostics for stale Sonarr queue imports.

This module deliberately contains no network calls or mutation.  It classifies a
complete Sonarr queue snapshot against a qBittorrent snapshot so callers can
choose whether an independently verified cleanup is appropriate.
"""
from datetime import datetime, timezone
import math
import json
import os
import re
import threading

import config as settings


NOT_AN_UPGRADE_PREFIX = "Not an upgrade for existing episode file(s)."
_HASH_PATTERN = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
_COMPLETED_STATES = {"completed", "importpending", "importblocked"}
MAX_STATE_ITEMS = 100
_cycle_lock = threading.Lock()
_scheduler_stop = threading.Event()
_scheduler_thread = None
_scheduler_thread_lock = threading.Lock()


def _fetch_sonarr_queue_snapshot():
    from routes.automation import _fetch_queue_snapshot

    return _fetch_queue_snapshot(settings.SONARR_URL, settings.SONARR_API_KEY)


def _fetch_qbt_torrents():
    import http.cookiejar
    from clients.qbittorrent import qbt_get_json, qbt_login

    opener = __import__("urllib.request", fromlist=["build_opener"]).build_opener(
        http.cookiejar.CookieJar()
    )
    qbt_login(opener)
    return qbt_get_json("/api/v2/torrents/info", opener)


def _ignore_sonarr_queue_items(queue_ids):
    from clients.arr import ignore_sonarr_queue_items

    return ignore_sonarr_queue_items(queue_ids)


def _read_state():
    try:
        with open(settings.QUEUE_HYGIENE_STATE_PATH, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_state(state):
    path = settings.QUEUE_HYGIENE_STATE_PATH
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temporary = f"{path}.tmp-{os.getpid()}-{threading.get_ident()}"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _bounded(values):
    return list(values or [])[:MAX_STATE_ITEMS]


def _invalidate_automation_cache():
    settings._arr_cache.pop("automation", None)
    settings._arr_cache.pop("automation_ts", None)


def _nonnegative_int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def normalized_state(state=None):
    """Return the bounded, secret-free state contract used by HTTP/UI readers."""
    raw = _read_state() if state is None else state
    if not isinstance(raw, dict):
        raw = {}
    counts = raw.get("counts") if isinstance(raw.get("counts"), dict) else {}
    verification = raw.get("verification") if isinstance(raw.get("verification"), dict) else None
    normalized_verification = None
    if verification is not None:
        normalized_verification = {
            "queueIdsGone": verification.get("queueIdsGone") is True,
            "hashesPreserved": verification.get("hashesPreserved") is True,
            "missingHashes": _bounded(
                value for value in verification.get("missingHashes", []) if isinstance(value, str)
            ),
        }
    last_cleanup = raw.get("lastCleanup") if isinstance(raw.get("lastCleanup"), dict) else None
    result = {
        "mode": raw.get("mode") if raw.get("mode") in {"off", "observe", "auto"} else settings.QUEUE_HYGIENE_MODE,
        "circuitOpen": raw.get("circuitOpen") is True,
        "eligibleCount": _nonnegative_int(counts.get("eligible")),
        "blockedCount": _nonnegative_int(counts.get("blocked")),
        "eligibleItems": _bounded(raw.get("eligibleItems")),
        "blockedItems": _bounded(raw.get("blockedItems")),
        "lastCycleAt": raw.get("lastCycleAt") if isinstance(raw.get("lastCycleAt"), str) else None,
        "lastCleanup": last_cleanup,
        "verification": normalized_verification,
    }
    if isinstance(raw.get("error"), str) and raw["error"].strip():
        result["error"] = raw["error"].strip()
    return result


def _queue_hygiene_scheduler_loop(interval_seconds, stop_event, run_cycle, wait):
    run_cycle()
    while not wait(stop_event, interval_seconds):
        run_cycle()


def start_queue_hygiene_scheduler(interval_seconds=None):
    interval = settings.QUEUE_HYGIENE_INTERVAL_SECONDS if interval_seconds is None else float(interval_seconds)
    global _scheduler_thread
    with _scheduler_thread_lock:
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            return False
        _scheduler_stop.clear()

        def wait(event, timeout):
            return event.wait(timeout)

        def target():
            _queue_hygiene_scheduler_loop(interval, _scheduler_stop, run_queue_hygiene_cycle, wait)

        _scheduler_thread = threading.Thread(target=target, name="sonarr-queue-hygiene", daemon=True)
        _scheduler_thread.start()
        return True


def stop_queue_hygiene_scheduler(timeout=2.0):
    global _scheduler_thread
    with _scheduler_thread_lock:
        thread = _scheduler_thread
        _scheduler_stop.set()
        _scheduler_thread = None
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)
        return not thread.is_alive()
    return True


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
    duplicates = set()
    for torrent in qbt_torrents or []:
        if not isinstance(torrent, dict):
            continue
        raw_hash = torrent.get("hash")
        if _valid_hash(raw_hash):
            key = raw_hash.strip().lower()
            if key in index:
                duplicates.add(key)
            else:
                index[key] = torrent
    return index, duplicates


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
    clock_valid = isinstance(now, datetime) and now.tzinfo is not None and now.utcoffset() is not None
    if not clock_valid:
        now = datetime.now(timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    try:
        if isinstance(grace_seconds, bool):
            raise ValueError("boolean grace period")
        grace_seconds = float(grace_seconds)
    except (TypeError, ValueError):
        grace_seconds = float("inf")
    if not math.isfinite(grace_seconds) or grace_seconds < 0 or not clock_valid:
        grace_seconds = float("inf")

    records = list(queue_records or [])
    qbt_index, duplicate_hashes = _build_qbt_index(qbt_torrents)
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

        row_checks.sort(
            key=lambda item: (
                item["queue_id"] is None,
                item["queue_id"] if isinstance(item["queue_id"], int) else 0,
                _title(item["row"]),
            )
        )
        first_reason = next((item["reason"] for item in row_checks if item["reason"]), "")
        group_blocker = next((item["blocker"] for item in row_checks if item["blocker"]), None)
        if group_blocker is not None:
            for item in row_checks:
                blocked.append(
                    _blocked(item["queue_id"], _title(item["row"]), item["reason"] or first_reason, item["blocker"] or "mixed_group")
                )
            continue

        torrent = qbt_index.get(group_key)
        if group_key in duplicate_hashes:
            for item in row_checks:
                blocked.append(_blocked(item["queue_id"], _title(item["row"]), item["reason"], "ambiguous_qbt"))
            continue
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
        canonical_download_id = min(
            (item["row"].get("downloadId").strip() for item in row_checks),
            key=lambda value: (value.lower(), value),
        )
        eligible.append(
            {
                "downloadId": canonical_download_id,
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


def run_queue_hygiene_cycle(mode=None, now=None):
    """Run one guarded queue-hygiene cycle."""
    selected_mode = str(mode if mode is not None else settings.QUEUE_HYGIENE_MODE).strip().lower()
    if selected_mode not in {"off", "observe", "auto"}:
        selected_mode = "observe"
    if not _cycle_lock.acquire(blocking=False):
        return {"status": "skipped", "skipped": True, "circuitOpen": bool(_read_state().get("circuitOpen"))}
    try:
        state = _read_state()
        circuit_open = bool(state.get("circuitOpen"))
        if selected_mode == "off":
            return {"status": "off", "mode": selected_mode, "circuitOpen": circuit_open}
        if selected_mode == "auto" and circuit_open:
            return {
                "status": "circuit_open",
                "mode": selected_mode,
                "circuitOpen": True,
                "error": state.get("error", "Automatic cleanup paused; manual reset required."),
            }

        observed_at = now if isinstance(now, datetime) else datetime.now(timezone.utc)
        try:
            queue_snapshot = _fetch_sonarr_queue_snapshot()
            qbt_torrents = _fetch_qbt_torrents()
            records = queue_snapshot.get("records", []) if isinstance(queue_snapshot, dict) else []
            diagnostics = classify_queue(
                records,
                qbt_torrents,
                observed_at,
                settings.QUEUE_HYGIENE_GRACE_SECONDS,
            )
        except Exception as error:
            result = {
                "status": "error",
                "mode": selected_mode,
                "circuitOpen": circuit_open,
                "error": str(error),
            }
            _write_state({**state, "mode": selected_mode, "circuitOpen": circuit_open, "lastCycleAt": _format_timestamp(observed_at), "error": str(error)})
            return result

        eligible_groups = diagnostics["eligibleGroups"]
        queue_ids = sorted({queue_id for group in eligible_groups for queue_id in group["queueIds"]})
        hashes = sorted({group["downloadId"].lower() for group in eligible_groups})
        counts = {
            "eligible": len(eligible_groups),
            "blocked": len(diagnostics["blockedItems"]),
            "queued": diagnostics["totalQueued"],
        }
        result = {
            "status": "observed",
            "mode": selected_mode,
            "circuitOpen": circuit_open,
            "observedAt": diagnostics["observedAt"],
            "counts": counts,
            "queueIds": _bounded(queue_ids),
            "hashes": _bounded(hashes),
            "eligibleGroups": eligible_groups,
            "blockedItems": diagnostics["blockedItems"],
        }
        state_update = {
            **state,
            "mode": selected_mode,
            "circuitOpen": circuit_open,
            "lastCycleAt": diagnostics["observedAt"],
            "counts": counts,
            "queueIds": _bounded(queue_ids),
            "hashes": _bounded(hashes),
            "eligibleItems": _bounded(eligible_groups),
            "blockedItems": _bounded(diagnostics["blockedItems"]),
        }

        if selected_mode != "auto" or not queue_ids:
            _write_state(state_update)
            _invalidate_automation_cache()
            return result

        _ignore_sonarr_queue_items(queue_ids)
        post_queue_snapshot = _fetch_sonarr_queue_snapshot()
        post_qbt_torrents = _fetch_qbt_torrents()
        post_records = post_queue_snapshot.get("records", []) if isinstance(post_queue_snapshot, dict) else []
        remaining_ids = {
            row.get("id") for row in post_records if isinstance(row, dict) and isinstance(row.get("id"), int)
        }
        post_hashes = {
            item.get("hash", "").strip().lower()
            for item in post_qbt_torrents or []
            if isinstance(item, dict) and isinstance(item.get("hash"), str)
        }
        missing_hashes = sorted(set(hashes) - post_hashes)
        verification = {
            "queueIdsGone": not (set(queue_ids) & remaining_ids),
            "hashesPreserved": not missing_hashes,
            "missingHashes": _bounded(missing_hashes),
        }
        result["verification"] = verification
        if missing_hashes:
            error = "Expected qBittorrent hash disappeared after Sonarr cleanup."
            result.update({"status": "circuit_open", "circuitOpen": True, "error": error})
            _write_state({
                **state_update,
                "circuitOpen": True,
                "error": error,
                "verification": verification,
            })
            return result
        if not verification["queueIdsGone"]:
            result.update({"status": "verification_failed", "error": "Sonarr queue IDs remained after cleanup."})
            _write_state({**state_update, "verification": verification, "error": result["error"]})
            return result

        result.update({"status": "cleaned", "lastCleanup": {"at": diagnostics["observedAt"], "queueIds": _bounded(queue_ids), "hashes": _bounded(hashes)}})
        state_update.update({"lastCleanup": result["lastCleanup"], "verification": verification})
        _write_state(state_update)
        _invalidate_automation_cache()
        return result
    finally:
        _cycle_lock.release()
