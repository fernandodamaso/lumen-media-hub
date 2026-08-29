"""Jellyseerr-only media request service."""

import threading
from contextlib import contextmanager
from dataclasses import dataclass

import config as settings
import media_state
from clients.jellyseerr import JellyseerrUpstreamError, _jellyseerr_post
from recommendations_store import apply_request
from reconciliation import _enqueue_request_reconciliation
from shared import _find_ai_picks_item


class MediaRequestValidationError(Exception):
    """The browser request does not match the safe request contract."""


class MediaRequestConflict(Exception):
    """The title is already available or tracked."""


class MediaRequestUnavailable(Exception):
    """Authoritative state is insufficient for a safe write."""


class MediaRequestUpstreamFailure(Exception):
    """Jellyseerr did not produce a confirmed request."""


class HermesItemNotFound(Exception):
    """The optional Hermes item no longer exists."""


class HermesIdentityMismatch(Exception):
    """The Hermes item does not match the typed request identity."""


@dataclass(frozen=True)
class MediaRequestCommand:
    media_type: str
    media_id: int
    seasons: tuple | str | None
    hermes_id: str | None

    @property
    def identity(self):
        return f"{self.media_type}:{self.media_id}"

    def jellyseerr_payload(self):
        payload = {
            "mediaType": self.media_type,
            "mediaId": self.media_id,
        }
        if self.media_type == "tv":
            payload["seasons"] = (
                self.seasons if self.seasons == "all" else list(self.seasons)
            )
        payload["is4k"] = False
        return payload


_REQUEST_FIELDS = frozenset({"mediaType", "mediaId", "aiPickId", "hermesId", "seasons", "is4k"})


def validate_request_payload(payload):
    if not isinstance(payload, dict):
        raise MediaRequestValidationError("Expected a JSON object body")
    if set(payload) - _REQUEST_FIELDS:
        raise MediaRequestValidationError("Unsupported request field")

    media_type = payload.get("mediaType")
    if media_type not in ("movie", "tv"):
        raise MediaRequestValidationError("mediaType must be movie or tv")
    media_id = payload.get("mediaId")
    if isinstance(media_id, bool) or not isinstance(media_id, int) or media_id <= 0:
        raise MediaRequestValidationError("mediaId must be a positive integer")

    if "is4k" in payload and payload["is4k"] is not False:
        raise MediaRequestValidationError("4K requests are not supported")

    seasons = None
    if media_type == "movie":
        if "seasons" in payload:
            raise MediaRequestValidationError("Movie requests do not accept seasons")
    else:
        seasons = payload.get("seasons")
        if seasons != "all":
            if not isinstance(seasons, list) or not seasons:
                raise MediaRequestValidationError("TV requests require seasons")
            if any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
                for value in seasons
            ):
                raise MediaRequestValidationError(
                    "TV seasons must be nonnegative integers"
                )
            if len(set(seasons)) != len(seasons):
                raise MediaRequestValidationError("TV seasons must be unique")
            seasons = tuple(sorted(seasons))

    if "aiPickId" in payload and "hermesId" in payload:
        raise MediaRequestValidationError("provide only one recommendation item id")
    item_id_field = "aiPickId" if "aiPickId" in payload else "hermesId"
    hermes_id = payload.get(item_id_field)
    if item_id_field in payload:
        if (
            not isinstance(hermes_id, str)
            or not hermes_id.strip()
            or len(hermes_id) > 256
            or any(ord(char) < 32 for char in hermes_id)
        ):
            raise MediaRequestValidationError(f"{item_id_field} must be a non-empty string")
        hermes_id = hermes_id.strip()

    return MediaRequestCommand(media_type, media_id, seasons, hermes_id)


class _KeyedLockPool:
    def __init__(self):
        self._guard = threading.Lock()
        self._entries = {}

    @contextmanager
    def hold(self, key):
        with self._guard:
            entry = self._entries.get(key)
            if entry is None:
                entry = {"lock": threading.Lock(), "references": 0}
                self._entries[key] = entry
            entry["references"] += 1
        lock = entry["lock"]
        acquired = False
        try:
            lock.acquire()
            acquired = True
            yield
        finally:
            if acquired:
                lock.release()
            with self._guard:
                entry["references"] -= 1
                if entry["references"] == 0 and self._entries.get(key) is entry:
                    del self._entries[key]


def _unavailable_library_snapshot():
    return media_state.LibraryExclusionSnapshot.from_maps(
        {}, {}, status="unavailable", last_successful_refresh_at=None
    )


def _unavailable_arr_snapshot():
    return media_state.ArrTrackingSnapshot.from_maps(
        movie={},
        tv={},
        sources={"radarr": "unavailable", "sonarr": "unavailable"},
    )


def _read_authoritative_state(media_type, media_id, *, force=False):
    try:
        library = media_state.get_library_exclusion_snapshot()
    except Exception:
        library = _unavailable_library_snapshot()
    try:
        arr = media_state.get_arr_tracking_snapshot()
    except Exception:
        arr = _unavailable_arr_snapshot()
    try:
        jellyseerr = media_state.get_jellyseerr_request_snapshot(
            [(media_type, media_id)], force=force
        )
    except Exception:
        jellyseerr = media_state.JellyseerrRequestSnapshot(
            {}, {f"{media_type}:{media_id}": "unavailable"}
        )
    return media_state.resolve_media_state(
        media_type,
        media_id,
        library=library,
        arr=arr,
        jellyseerr=jellyseerr.get(media_type, media_id),
        jellyseerr_status=jellyseerr.status(media_type, media_id),
    )


def _positive_int(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _normalized_status(value):
    if isinstance(value, bool):
        return None
    if value == 1 or (
        isinstance(value, str) and value.strip().lower() in ("pending", "requested")
    ):
        return "requested"
    if value == 2 or (
        isinstance(value, str)
        and value.strip().lower() in ("approved", "processing", "partial")
    ):
        return "processing"
    return None


class MediaRequestService:
    def __init__(
        self,
        *,
        state_reader=None,
        post_request=None,
        invalidate_state=None,
        store=None,
        enqueue_reconciliation=None,
        locks=None,
    ):
        self._state_reader = state_reader
        self._post_request = post_request
        self._invalidate_state = invalidate_state
        self._store = store
        self._enqueue_reconciliation = enqueue_reconciliation
        self._locks = locks or _KeyedLockPool()

    def _state(self, command, *, force=False):
        reader = self._state_reader or _read_authoritative_state
        return reader(command.media_type, command.media_id, force=force)

    def _invalidate(self, command):
        invalidate = self._invalidate_state or media_state.invalidate_request_state_caches
        invalidate(command.media_type, command.media_id)

    def _store_for_request(self):
        return self._store or settings.RECOMMENDATIONS_STORE

    def _validate_hermes(self, command):
        if not command.hermes_id:
            return
        try:
            document = self._store_for_request().load()
        except Exception:
            raise MediaRequestUnavailable(
                "Discover recommendations are temporarily unavailable"
            ) from None
        item = _find_ai_picks_item(document, command.hermes_id)
        if not item:
            raise HermesItemNotFound("Hermes item not found")
        if (
            item.get("type") != command.media_type
            or item.get("tmdb_id") != command.media_id
        ):
            raise HermesIdentityMismatch(
                "Hermes item does not match the requested media"
            )

    def _persist(self, command, request_id):
        if not command.hermes_id:
            return True, False

        def apply(document):
            item = _find_ai_picks_item(document, command.hermes_id)
            if not item:
                raise HermesItemNotFound()
            if (
                item.get("type") != command.media_type
                or item.get("tmdb_id") != command.media_id
            ):
                raise HermesIdentityMismatch()
            apply_request(item, provider="jellyseerr", request_id=request_id)

        try:
            self._store_for_request().update(apply)
            return True, False
        except Exception as error:
            queued = False
            try:
                enqueue = (
                    self._enqueue_reconciliation
                    or _enqueue_request_reconciliation
                )
                enqueue(command.hermes_id, request_id, "jellyseerr")
                queued = True
            except Exception as queue_error:
                print(
                    "[discover-request] reconciliation enqueue failed "
                    f"exception={type(queue_error).__name__}",
                    flush=True,
                )
            print(
                "[discover-request] Jellyseerr succeeded but dashboard state "
                f"persistence diverged exception={type(error).__name__}",
                flush=True,
            )
            return False, queued

    def _result(
        self,
        command,
        *,
        request_id,
        request_status,
        already_requested,
    ):
        persisted, queued = self._persist(command, request_id)
        partial = not persisted
        if partial:
            message = (
                "Jellyseerr accepted the request; dashboard synchronization failed."
            )
        elif already_requested:
            message = "This title is already requested in Jellyseerr."
        else:
            message = "Request submitted to Jellyseerr."
        return {
            "ok": True,
            "partial_success": partial,
            "jellyseerr_request_id": request_id,
            "request_status": request_status,
            "already_requested": already_requested,
            "dashboard_state_persisted": persisted,
            "reconciliation_queued": queued,
            "message": message,
        }

    def _confirmed_active(self, state):
        if not isinstance(state, dict):
            return None
        status = state.get("status")
        if status not in ("requested", "processing"):
            return None
        request_id = _positive_int(state.get("requestId") or state.get("request_id"))
        if not request_id:
            return None
        return status, request_id

    def request(self, payload):
        command = validate_request_payload(payload)
        self._validate_hermes(command)

        with self._locks.hold(command.identity):
            state = self._state(command)
            status = state.get("status") if isinstance(state, dict) else "unknown"
            active = self._confirmed_active(state)
            if active:
                return self._result(
                    command,
                    request_id=active[1],
                    request_status=active[0],
                    already_requested=True,
                )
            if status in ("requested", "processing", "unknown"):
                raise MediaRequestUnavailable(
                    "Media status is temporarily unavailable"
                )
            if status in ("available", "tracked"):
                raise MediaRequestConflict("This title is already managed")
            if status != "missing":
                raise MediaRequestUnavailable(
                    "Media status is temporarily unavailable"
                )

            post = self._post_request or _jellyseerr_post
            recovered = False
            try:
                response = post("/api/v1/request", command.jellyseerr_payload())
                if not isinstance(response, dict):
                    raise MediaRequestUpstreamFailure(
                        "Jellyseerr could not confirm the request"
                    )
                request_id = _positive_int(response.get("id"))
                request_status = _normalized_status(response.get("status"))
                if not request_id or not request_status:
                    raise MediaRequestUpstreamFailure(
                        "Jellyseerr could not confirm the request"
                    )
            except JellyseerrUpstreamError as error:
                if error.status != 409 and not error.ambiguous:
                    raise MediaRequestUpstreamFailure(
                        "Jellyseerr could not accept the request"
                    ) from None
                self._invalidate(command)
                active = self._confirmed_active(self._state(command, force=True))
                if not active:
                    raise MediaRequestUpstreamFailure(
                        "Jellyseerr could not confirm the request"
                    ) from None
                request_status, request_id = active
                recovered = True

            self._invalidate(command)
            return self._result(
                command,
                request_id=request_id,
                request_status=request_status,
                already_requested=recovered,
            )


_REQUEST_SERVICE = MediaRequestService()


def request_media(payload):
    return _REQUEST_SERVICE.request(payload)
