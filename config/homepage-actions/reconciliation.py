"""Hermes request reconciliation queue and scheduler."""
import json
import os
import threading

import config
import config as settings
from recommendations_store import (
    REQUEST_PROVIDER_VALUES,
    RecommendationError,
    RecommendationValidationError,
    apply_request,
    utc_now,
)

from shared import _find_hermes_item



class HermesItemNotFound(Exception):
    """Raised inside a store transaction to abort when the item is missing."""


class StaleBaseRevision(Exception):
    """Raised inside a generation commit when the base revision is stale."""

    def __init__(self, current_revision):
        super().__init__(f"stale base_revision; current revision is {current_revision}")
        self.current_revision = current_revision


class AlreadyReconciled(Exception):
    """Queue entry already matches the persisted Jellyseerr request id."""


class RequestSyncConflict(Exception):
    """Stale queue entry would overwrite a newer persisted request id."""


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
    provider = entry.get("request_provider", "arr_legacy")
    if provider not in REQUEST_PROVIDER_VALUES:
        return None
    normalized = {
        "hermes_id": hermes_id.strip(),
        "jellyseerr_request_id": request_id,
        "request_provider": provider,
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
    with settings._reconciliation_lock:
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
                "request_provider": normalized["request_provider"],
            }
        )
    return pending


def _read_reconciliation_queue():
    if not os.path.isfile(settings.RECONCILIATION_PATH):
        return []
    try:
        with open(settings.RECONCILIATION_PATH, encoding="utf-8-sig") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as e:
        raise RecommendationError(f"cannot read reconciliation queue: {e}") from e
    if not isinstance(raw, list):
        raise RecommendationError("reconciliation queue must be an array")
    return raw


def _write_reconciliation_queue(queue):
    directory = os.path.dirname(settings.RECONCILIATION_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{settings.RECONCILIATION_PATH}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(queue, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, settings.RECONCILIATION_PATH)
    except BaseException:
        try:
            if os.path.isfile(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _enqueue_request_reconciliation(hermes_id, jellyseerr_request_id, provider):
    entry = {
        "hermes_id": hermes_id,
        "jellyseerr_request_id": jellyseerr_request_id,
        "request_provider": provider,
        "queued_at": utc_now(),
    }
    if _normalize_reconciliation_entry(entry) is None:
        raise RecommendationValidationError("invalid request reconciliation entry")
    with settings._reconciliation_lock:
        queue = _read_reconciliation_queue()
        for existing in queue:
            normalized = _normalize_reconciliation_entry(existing)
            if (
                normalized
                and normalized["hermes_id"] == hermes_id.strip()
                and normalized["jellyseerr_request_id"] == jellyseerr_request_id
                and normalized["request_provider"] == provider
            ):
                return False
        queue.append(entry)
        _write_reconciliation_queue(queue)
    return True


def _read_generation_request():
    """Return the on-demand Hermes generation request dict, or None."""
    if not os.path.isfile(settings.GENERATION_REQUEST_PATH):
        return None
    try:
        with open(settings.GENERATION_REQUEST_PATH, encoding="utf-8-sig") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as e:
        raise RecommendationError(f"cannot read generation request: {e}") from e
    if not isinstance(raw, dict):
        raise RecommendationError("generation request must be an object")
    return raw


def _write_generation_request(payload):
    """Atomically write or clear the on-demand generation request file."""
    directory = os.path.dirname(settings.GENERATION_REQUEST_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    if payload is None:
        try:
            if os.path.isfile(settings.GENERATION_REQUEST_PATH):
                os.unlink(settings.GENERATION_REQUEST_PATH)
        except OSError as e:
            raise RecommendationError(f"cannot clear generation request: {e}") from e
        return
    tmp_path = f"{settings.GENERATION_REQUEST_PATH}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, settings.GENERATION_REQUEST_PATH)
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
    with settings._generation_request_lock:
        _write_generation_request(None)


def _request_hermes_generation():
    """Queue an on-demand Hermes generation. Idempotent while pending."""
    with settings._generation_request_lock:
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
    with settings._reconciliation_lock:
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
            provider = normalized["request_provider"]

            def _apply(
                doc,
                _hermes_id=hermes_id,
                _request_id=request_id,
                _provider=provider,
            ):
                item = _find_hermes_item(doc, _hermes_id)
                if not item:
                    raise HermesItemNotFound()
                if item.get("request_state") == "requested":
                    existing_id = item.get("jellyseerr_request_id")
                    existing_provider = item.get("request_provider")
                    if existing_id == _request_id and existing_provider == _provider:
                        raise AlreadyReconciled()
                    if existing_provider != _provider or (
                        existing_id is not None and existing_id != _request_id
                    ):
                        raise RequestSyncConflict(
                            f"hermes_id={_hermes_id!r} "
                            f"queued_jellyseerr_request_id={_request_id!r} "
                            f"persisted_jellyseerr_request_id={existing_id!r} "
                            f"queued_provider={_provider!r} "
                            f"persisted_provider={existing_provider!r}"
                        )
                apply_request(item, provider=_provider, request_id=_request_id)

            try:
                settings.RECOMMENDATIONS_STORE.update(_apply)
            except AlreadyReconciled:
                reconciled += 1
                continue
            except RequestSyncConflict as e:
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
    if not settings._reconcile_cycle_lock.acquire(blocking=False):
        return {"ok": True, "skipped": True, "reason": "already_running"}
    try:
        request_result = _reconcile_pending_requests()
        try:
            from trakt_history_sync import reconcile_trakt_history_sync

            trakt_result = reconcile_trakt_history_sync()
        except Exception as error:
            trakt_result = {"error": type(error).__name__}
        request_result["trakt_history_sync"] = trakt_result
        return request_result
    except Exception as e:
        print(
            "[discover-request-reconcile] cycle failed "
            f"error={type(e).__name__}",
            flush=True,
        )
        return {"ok": False, "error": type(e).__name__}
    finally:
        settings._reconcile_cycle_lock.release()


def _reconciliation_scheduler_loop(interval_seconds, stop_event, run_cycle, wait):
    """Deterministic scheduler body (injectable wait for tests)."""
    run_cycle()
    while not wait(stop_event, interval_seconds):
        run_cycle()


def start_reconciliation_scheduler(interval_seconds=None):
    """Start the single background reconciliation thread if not already running."""
    interval = (
        settings.RECONCILE_INTERVAL_SECONDS if interval_seconds is None else float(interval_seconds)
    )
    with config._reconcile_thread_lock:
        if config._reconcile_thread is not None and config._reconcile_thread.is_alive():
            return False
        config._reconcile_stop.clear()

        def _wait(event, timeout):
            return event.wait(timeout)

        def _target():
            _reconciliation_scheduler_loop(
                interval,
                config._reconcile_stop,
                run_reconciliation_cycle,
                _wait,
            )

        thread = threading.Thread(
            target=_target,
            name="hermes-request-reconcile",
            daemon=True,
        )
        config._reconcile_thread = thread
        thread.start()
        return True


def stop_reconciliation_scheduler(timeout=2.0):
    """Signal the scheduler to stop and join it (tests / shutdown)."""
    with config._reconcile_thread_lock:
        thread = config._reconcile_thread
        config._reconcile_stop.set()
        config._reconcile_thread = None
    if thread is not None and thread.is_alive():
        thread.join(timeout=timeout)
        return not thread.is_alive()
    return True
