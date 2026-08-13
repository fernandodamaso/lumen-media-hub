"""Discover Hermes watched feedback -> Trakt history delivery."""

import threading
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from clients.trakt import TraktAuthError, TraktHttpError
from recommendations_store import apply_feedback, media_identity, utc_now
from shared import _find_hermes_item
from trakt_history import _header, _response_parts

TRAKT_HISTORY_SYNC_STATUSES = frozenset(
    {"pending", "synced", "reconnect_required", "failed"}
)
MIN_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 900
RECONNECT_RETRY_SECONDS = 300
LOCAL_SYNC_TTL_SECONDS = 15 * 60
HISTORY_PAGE_LIMIT = 100

_write_lock = threading.Lock()
_local_synced_identities = {}
_local_identities_lock = threading.Lock()


def register_local_synced_identity(identity, *, clock=None):
    clock_fn = clock or time.time
    with _local_identities_lock:
        _local_synced_identities[identity] = clock_fn() + LOCAL_SYNC_TTL_SECONDS


def local_synced_identities(*, clock=None):
    clock_fn = clock or time.time
    now = clock_fn()
    with _local_identities_lock:
        expired = [
            identity
            for identity, expires_at in _local_synced_identities.items()
            if expires_at <= now
        ]
        for identity in expired:
            del _local_synced_identities[identity]
        return frozenset(_local_synced_identities.keys())


def clear_local_synced_identities():
    with _local_identities_lock:
        _local_synced_identities.clear()


def public_trakt_history_sync(event):
    if not isinstance(event, dict):
        return None
    status = event.get("status")
    if status not in TRAKT_HISTORY_SYNC_STATUSES:
        return None
    return {"status": status}


def _sanitize_error(error):
    if isinstance(error, TraktAuthError):
        return "TraktAuthError"
    if isinstance(error, TraktHttpError):
        return f"TraktHttpError:{error.status}"
    return type(error).__name__


def _backoff_seconds(attempts):
    if attempts <= 0:
        return MIN_BACKOFF_SECONDS
    return min(MIN_BACKOFF_SECONDS * (2 ** (attempts - 1)), MAX_BACKOFF_SECONDS)


def _parse_retry_after(headers):
    for key, value in (headers or {}).items():
        if str(key).lower() == "retry-after":
            try:
                return max(1, int(value))
            except (TypeError, ValueError):
                return None
    return None


def _iso_after_seconds(clock, seconds):
    return datetime.fromtimestamp(clock() + seconds, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def create_trakt_history_event(item, now=None):
    watched_at = _truncate_to_minute(now or utc_now())
    identity = media_identity(item["type"], item["tmdb_id"])
    return {
        "event_id": str(uuid.uuid4()),
        "identity": identity,
        "watched_at": watched_at,
        "status": "pending",
        "attempts": 0,
        "next_attempt_at": None,
        "error": None,
        "completed_at": None,
        "trakt_history_ids": [],
        "last_post_status": None,
    }


def apply_watched_feedback(item, now=None):
    """Set watched feedback and queue a Trakt event unless one already exists."""
    watched_at = _truncate_to_minute(now or utc_now())
    existing = item.get("trakt_history_event")
    apply_feedback(item, "watched", now=watched_at)
    if isinstance(existing, dict) and existing.get("event_id"):
        return False
    item["trakt_history_event"] = create_trakt_history_event(item, now=watched_at)
    return True


def cancel_pending_trakt_history_event(item):
    """Drop an undelivered watched event when feedback changes away from watched."""
    event = item.get("trakt_history_event")
    if not isinstance(event, dict):
        return False
    if event.get("status") in ("synced", "failed"):
        return False
    del item["trakt_history_event"]
    return True


def _history_kind(item_type):
    """Trakt history GET kind: movies for films, episodes for show-level watches."""
    return "movies" if item_type == "movie" else "episodes"


def _build_post_payload(item, watched_at):
    tmdb_id = item["tmdb_id"]
    if item["type"] == "movie":
        return {"movies": [{"ids": {"tmdb": tmdb_id}, "watched_at": watched_at}]}
    return {"shows": [{"ids": {"tmdb": tmdb_id}, "watched_at": watched_at}]}


def _normalize_watched_at(value):
    if not isinstance(value, str):
        return None
    text = value.replace("+00:00", "Z")
    if "." in text and text.endswith("Z"):
        text = text.split(".", 1)[0] + "Z"
    if text.endswith("Z"):
        return text
    if "T" in text:
        return text + "Z"
    return text


def _truncate_to_minute(value):
    normalized = _normalize_watched_at(value) if isinstance(value, str) else None
    if not normalized:
        normalized = utc_now()
    dt = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(second=0, microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _minute_range_end(minute_start):
    dt = datetime.fromisoformat(minute_start.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.replace(second=59).strftime("%Y-%m-%dT%H:%M:%SZ")


def _watched_at_minute_key(value):
    normalized = _normalize_watched_at(value)
    if not normalized:
        return None
    dt = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(second=0, microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _watched_at_matches(left, right):
    left_key = _watched_at_minute_key(left)
    right_key = _watched_at_minute_key(right)
    return bool(left_key and right_key and left_key == right_key)


def _extract_history_ids(entries, item_type, tmdb_id, watched_at):
    ids = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        if not _watched_at_matches(entry.get("watched_at"), watched_at):
            continue
        history_id = entry.get("id")
        if not isinstance(history_id, int):
            continue
        if item_type == "movie":
            movie = entry.get("movie") or {}
            if (movie.get("ids") or {}).get("tmdb") == tmdb_id:
                ids.append(history_id)
            continue
        show = entry.get("show") or {}
        if (show.get("ids") or {}).get("tmdb") == tmdb_id:
            ids.append(history_id)
    return sorted(set(ids))


def _match_existing_history(client, item, watched_at):
    kind = _history_kind(item["type"])
    minute_start = _truncate_to_minute(watched_at)
    minute_end = _minute_range_end(minute_start)
    base = (
        f"/sync/history/{kind}?start_at={quote(minute_start, safe='')}"
        f"&end_at={quote(minute_end, safe='')}"
    )
    matched = []
    page = 1
    expected_page_count = None
    while True:
        path = f"{base}&page={page}&limit={HISTORY_PAGE_LIMIT}"
        response = client.get_page(path)
        payload, headers = _response_parts(response)
        if not isinstance(headers, dict):
            headers = {}
        if not isinstance(payload, list):
            raise ValueError("invalid Trakt history response")
        matched.extend(
            _extract_history_ids(payload, item["type"], item["tmdb_id"], watched_at)
        )
        raw_page = _header(headers, "X-Pagination-Page")
        raw_page_count = _header(headers, "X-Pagination-Page-Count")
        if page == 1 and raw_page is None and raw_page_count is None:
            break
        try:
            page_header = int(raw_page) if raw_page is not None else None
            page_count = int(raw_page_count) if raw_page_count is not None else None
        except (TypeError, ValueError):
            raise ValueError("invalid Trakt history pagination headers") from None
        if page_header is not None and page_header != page:
            raise ValueError("inconsistent Trakt history pagination page")
        if page_count is None or page_count < 1:
            raise ValueError("invalid Trakt history pagination page count")
        if page == 1:
            expected_page_count = page_count
        elif page_count != expected_page_count or page_header is None:
            raise ValueError("inconsistent Trakt history pagination headers")
        if page >= page_count:
            break
        page += 1
    return sorted(set(matched))


def _payload_permanent_failure(payload):
    if not isinstance(payload, dict):
        return False
    not_found = payload.get("not_found") or {}
    if not isinstance(not_found, dict):
        return False
    for key in ("movies", "shows", "episodes", "seasons"):
        bucket = not_found.get(key)
        if isinstance(bucket, list) and bucket:
            return True
    return False


def _event_due(event, now):
    status = event.get("status")
    if status not in ("pending", "reconnect_required"):
        return False
    next_at = event.get("next_attempt_at")
    return next_at is None or (isinstance(next_at, str) and next_at <= now)


class TraktHistorySyncService:
    """Serialize Trakt history writes and reconcile pending Discover events."""

    def __init__(
        self,
        client_factory,
        store,
        *,
        clock=None,
        refresh_watched_snapshot=None,
    ):
        self.client_factory = client_factory
        self.store = store
        self.clock = clock or time.time
        self.refresh_watched_snapshot = refresh_watched_snapshot
        self._rate_limit_until = None

    def deliver_item(self, item_id):
        with _write_lock:
            return self._deliver_item_locked(item_id)

    def _deliver_item_locked(self, item_id):
        doc = self.store.load()
        item = _find_hermes_item(doc, item_id)
        if not item:
            return None
        event = item.get("trakt_history_event")
        if not isinstance(event, dict):
            return None
        if event.get("status") not in ("pending", "reconnect_required"):
            return public_trakt_history_sync(event)
        if not _event_due(event, utc_now()):
            return public_trakt_history_sync(event)

        client = self.client_factory()
        try:
            return self._attempt_delivery(client, item_id, item, event)
        except TraktAuthError as error:
            self._persist_event(
                item_id,
                lambda ev: _mark_reconnect(ev, _sanitize_error(error), self.clock),
            )
            return {"status": "reconnect_required"}

    def _attempt_delivery(self, client, item_id, item, event):
        watched_at = event["watched_at"]
        identity = event["identity"]

        try:
            history_ids = _match_existing_history(client, item, watched_at)
        except TraktAuthError:
            raise
        except TraktHttpError as error:
            return self._handle_retryable_http(item_id, event, error)
        except RuntimeError as error:
            return self._handle_retryable_runtime(item_id, event, error)
        except ValueError as error:
            return self._handle_retryable_runtime(item_id, event, error)

        if history_ids:
            self._persist_synced(item_id, history_ids, identity)
            return {"status": "synced"}

        if event.get("last_post_status") == 200:
            return self._persist_pending_retry(item_id, event, ambiguous=True)

        payload = _build_post_payload(item, watched_at)
        try:
            post_result = client.post("/sync/history", payload)
        except TraktAuthError:
            raise
        except TraktHttpError as error:
            if error.status == 429:
                return self._handle_retryable_http(item_id, event, error)
            if error.status >= 500:
                return self._handle_retryable_http(item_id, event, error)
            if _payload_permanent_failure(error.payload):
                def _fail(ev):
                    ev["last_post_status"] = error.status
                    _mark_failed(ev, _sanitize_error(error))

                self._persist_event(item_id, _fail)
                return {"status": "failed"}
            def _remember_status(ev):
                ev["last_post_status"] = error.status

            self._persist_event(item_id, _remember_status)
            return self._handle_retryable_http(item_id, event, error)
        except RuntimeError as error:
            return self._handle_retryable_runtime(item_id, event, error)

        if _payload_permanent_failure(post_result):
            def _fail_success_body(ev):
                ev["last_post_status"] = 200
                _mark_failed(ev, "TraktHttpError:not_found")

            self._persist_event(item_id, _fail_success_body)
            return {"status": "failed"}

        def _remember_success(ev):
            ev["last_post_status"] = 200

        self._persist_event(item_id, _remember_success)

        try:
            history_ids = _match_existing_history(client, item, watched_at)
        except TraktAuthError:
            raise
        except TraktHttpError as error:
            return self._handle_retryable_http(item_id, event, error)
        except RuntimeError as error:
            return self._handle_retryable_runtime(item_id, event, error)
        except ValueError as error:
            return self._handle_retryable_runtime(item_id, event, error)

        if history_ids:
            self._persist_synced(item_id, history_ids, identity)
            return {"status": "synced"}
        return self._persist_pending_retry(item_id, event, ambiguous=True)

    def _handle_retryable_http(self, item_id, event, error):
        retry_after = _parse_retry_after(error.headers) if error.status == 429 else None
        if error.status == 429:
            attempts = int(event.get("attempts") or 0) + 1
            delay = retry_after if retry_after is not None else _backoff_seconds(attempts)
            self._rate_limit_until = self.clock() + delay
        self._persist_event(
            item_id,
            lambda ev: _mark_pending_retry(
                ev,
                self.clock,
                _sanitize_error(error),
                retry_after=retry_after,
            ),
        )
        return public_trakt_history_sync(self._load_event(item_id))

    def _handle_retryable_runtime(self, item_id, event, error):
        self._persist_event(
            item_id,
            lambda ev: _mark_pending_retry(ev, self.clock, _sanitize_error(error)),
        )
        return public_trakt_history_sync(self._load_event(item_id))

    def _persist_pending_retry(self, item_id, event, *, ambiguous=False):
        self._persist_event(
            item_id,
            lambda ev: _mark_pending_retry(
                ev,
                self.clock,
                ev.get("error") or "pending_confirmation",
            ),
        )
        return public_trakt_history_sync(self._load_event(item_id))

    def _persist_synced(self, item_id, history_ids, identity):
        self._persist_event(
            item_id,
            lambda ev: _mark_synced(ev, history_ids),
        )
        register_local_synced_identity(identity, clock=self.clock)
        if self.refresh_watched_snapshot:
            self.refresh_watched_snapshot(identity)

    def _persist_event(self, item_id, mutator):
        def _apply(doc):
            item = _find_hermes_item(doc, item_id)
            if not item:
                raise HermesSyncItemNotFound()
            event = item.get("trakt_history_event")
            if not isinstance(event, dict):
                raise HermesSyncItemNotFound()
            mutator(event)

        self.store.update(_apply)

    def _load_event(self, item_id):
        doc = self.store.load()
        item = _find_hermes_item(doc, item_id)
        if not item:
            return None
        return item.get("trakt_history_event")

    def reconcile_due_events(self):
        doc = self.store.load()
        now = utc_now()
        due = [
            item["id"]
            for item in doc.get("items", [])
            if isinstance(item.get("trakt_history_event"), dict)
            and _event_due(item["trakt_history_event"], now)
        ]
        summary = {"attempted": 0, "synced": 0, "pending": 0, "failed": 0, "reconnect_required": 0}
        self._rate_limit_until = None
        for item_id in due:
            if self._rate_limit_until is not None and self.clock() < self._rate_limit_until:
                break
            result = self.deliver_item(item_id)
            if not result:
                continue
            summary["attempted"] += 1
            status = result.get("status")
            if status in summary:
                summary[status] += 1
            elif status == "pending":
                summary["pending"] += 1
            if self._rate_limit_until is not None and self.clock() < self._rate_limit_until:
                break
        return summary


class HermesSyncItemNotFound(Exception):
    """Raised when a Trakt sync mutation targets a missing item."""


def _mark_synced(event, history_ids):
    event["status"] = "synced"
    event["completed_at"] = utc_now()
    event["trakt_history_ids"] = sorted(set(history_ids))
    event["error"] = None
    event["next_attempt_at"] = None


def _mark_failed(event, error_name):
    event["status"] = "failed"
    event["completed_at"] = utc_now()
    event["error"] = error_name
    event["next_attempt_at"] = None


def _mark_reconnect(event, error_name, clock=None):
    event["status"] = "reconnect_required"
    event["completed_at"] = utc_now()
    event["error"] = error_name
    clock_fn = clock or time.time
    event["next_attempt_at"] = _iso_after_seconds(clock_fn, RECONNECT_RETRY_SECONDS)


def _mark_pending_retry(event, clock, error_name, *, retry_after=None):
    attempts = int(event.get("attempts") or 0) + 1
    event["attempts"] = attempts
    event["error"] = error_name
    delay = retry_after if retry_after is not None else _backoff_seconds(attempts)
    event["next_attempt_at"] = _iso_after_seconds(clock, delay)


_SERVICE = None
_SERVICE_LOCK = threading.Lock()


def _default_client_factory():
    from clients.jellyseerr import _trakt_client

    return _trakt_client()


def _default_refresh_watched_snapshot(identity):
    from routes import discover as discover_routes

    discover_routes._trakt_watched_snapshot(force=True)


def get_trakt_history_sync_service(*, store=None, client_factory=None, clock=None):
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None or store is not None:
            import config as settings

            _SERVICE = TraktHistorySyncService(
                client_factory or _default_client_factory,
                store or settings.RECOMMENDATIONS_STORE,
                clock=clock,
                refresh_watched_snapshot=_default_refresh_watched_snapshot,
            )
        return _SERVICE


def deliver_trakt_history_for_item(item_id, *, service=None):
    service = service or get_trakt_history_sync_service()
    return service.deliver_item(item_id)


def reconcile_trakt_history_sync(*, service=None):
    service = service or get_trakt_history_sync_service()
    return service.reconcile_due_events()
