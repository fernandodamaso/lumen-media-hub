#!/usr/bin/env python3
"""Versioned AI Picks store (v4) with safe v2→v3→v4 migration.

Sole in-process read/write abstraction for ``recommendations.json``:

- process-wide lock around read-modify-write transactions;
- schema validation before commit (hand-rolled, stdlib only);
- write to a sibling temporary file, flush + fsync, atomic replace, then a
  best-effort directory fsync;
- monotonically increment ``revision`` on every successful mutation;
- never mutate the caller's object in place.

Runtime loading accepts valid v2/v3 (migrated in memory to v4) and valid v4.
Missing, unknown, malformed, or legacy-v1 documents are rejected; fields are
never derived from a legacy ``status`` value.

The active contract is ``config/recommendations/schema-v4.json``;
``validate_v4`` here is the enforcing implementation and must stay in sync.
"""

import copy
import json
import os
import re
import threading
from datetime import datetime, timezone

SCHEMA_V2_VERSION = 2
SCHEMA_V3_VERSION = 3
SCHEMA_VERSION = 4

FEEDBACK_VALUES = ("liked", "disliked", "watched", "skipped")
REQUEST_STATE_VALUES = ("requested",)
ITEM_TYPES = ("movie", "tv")
TRAKT_HISTORY_SYNC_STATUSES = ("pending", "synced", "reconnect_required", "failed")
GENERATION_STATUSES = ("queued", "running", "succeeded", "failed")
GENERATION_TRIGGERS = ("on_demand", "scheduled")


class RecommendationError(Exception):
    """Base error for store failures."""


class RecommendationValidationError(RecommendationError):
    """The candidate document violates the active schema contract."""


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _fail(path, message):
    raise RecommendationValidationError(f"{path}: {message}")


def _validate_nullable_str(value, path):
    if value is not None and not isinstance(value, str):
        _fail(path, "expected string or null")


def validate_v2(data):
    """Validate a document against the v2 contract. Raises on violation."""
    if not isinstance(data, dict):
        _fail("$", "expected object")
    if data.get("version") != SCHEMA_V2_VERSION:
        _fail("version", f"expected {SCHEMA_V2_VERSION}")
    revision = data.get("revision")
    if not _is_int(revision) or revision < 0:
        _fail("revision", "expected non-negative integer")
    if not isinstance(data.get("updated_at"), str):
        _fail("updated_at", "expected string")
    presented = data.get("presented_tmdb_ids")
    if not isinstance(presented, list):
        _fail("presented_tmdb_ids", "expected array")
    presented_seen = set()
    for i, tmdb_id in enumerate(presented):
        if not _is_int(tmdb_id) or tmdb_id <= 0:
            _fail(f"presented_tmdb_ids[{i}]", "expected positive integer")
        if tmdb_id in presented_seen:
            _fail(f"presented_tmdb_ids[{i}]", "duplicate TMDB identity")
        presented_seen.add(tmdb_id)
    items = data.get("items")
    if not isinstance(items, list):
        _fail("items", "expected array")
    item_ids = set()
    current_tmdb_ids = set()
    for i, item in enumerate(items):
        path = f"items[{i}]"
        _validate_item(item, path)
        item_id = item["id"]
        if item_id in item_ids:
            _fail(f"{path}.id", "duplicate item id")
        item_ids.add(item_id)
        tmdb_id = item["tmdb_id"]
        if tmdb_id in current_tmdb_ids:
            _fail(f"{path}.tmdb_id", "duplicate current TMDB identity")
        current_tmdb_ids.add(tmdb_id)
        if tmdb_id not in presented_seen:
            _fail(
                f"{path}.tmdb_id",
                "current TMDB identity must be present in presented_tmdb_ids",
            )
    return True


REQUIRED_ITEM_FIELDS = (
    "id",
    "source",
    "type",
    "title",
    "tmdb_id",
    "reason",
    "active",
    "feedback",
    "feedback_at",
    "request_state",
    "requested_at",
    "jellyseerr_request_id",
    "added_at",
)


def _validate_trakt_history_event(value, path):
    if value is None:
        return
    if not isinstance(value, dict):
        _fail(path, "expected object or null")
    required = (
        "event_id",
        "identity",
        "watched_at",
        "status",
        "attempts",
        "next_attempt_at",
        "error",
        "completed_at",
        "trakt_history_ids",
        "last_post_status",
    )
    for field in required:
        if field not in value:
            _fail(f"{path}.{field}", "required field missing")
    if not isinstance(value.get("event_id"), str) or not value["event_id"]:
        _fail(f"{path}.event_id", "expected non-empty string")
    _validate_v3_identity(value.get("identity"), f"{path}.identity")
    if not isinstance(value.get("watched_at"), str):
        _fail(f"{path}.watched_at", "expected string")
    if value.get("status") not in TRAKT_HISTORY_SYNC_STATUSES:
        _fail(f"{path}.status", f"expected one of {TRAKT_HISTORY_SYNC_STATUSES}")
    if not _is_int(value.get("attempts")) or value["attempts"] < 0:
        _fail(f"{path}.attempts", "expected non-negative integer")
    _validate_nullable_str(value.get("next_attempt_at"), f"{path}.next_attempt_at")
    _validate_nullable_str(value.get("error"), f"{path}.error")
    _validate_nullable_str(value.get("completed_at"), f"{path}.completed_at")
    history_ids = value.get("trakt_history_ids")
    if not isinstance(history_ids, list) or any(not _is_int(item_id) for item_id in history_ids):
        _fail(f"{path}.trakt_history_ids", "expected array of integers")
    last_post_status = value.get("last_post_status")
    if last_post_status is not None and not _is_int(last_post_status):
        _fail(f"{path}.last_post_status", "expected integer or null")


def _validate_item(item, path):
    if not isinstance(item, dict):
        _fail(path, "expected object")
    for field in REQUIRED_ITEM_FIELDS:
        if field not in item:
            _fail(f"{path}.{field}", "required field missing")
    for field in ("id", "source", "title", "reason", "added_at"):
        if not isinstance(item.get(field), str):
            _fail(f"{path}.{field}", "expected string")
    if item.get("type") not in ITEM_TYPES:
        _fail(f"{path}.type", f"expected one of {ITEM_TYPES}")
    tmdb_id = item.get("tmdb_id")
    if not _is_int(tmdb_id) or tmdb_id <= 0:
        _fail(f"{path}.tmdb_id", "expected positive integer")
    if not isinstance(item.get("active"), bool):
        _fail(f"{path}.active", "expected boolean")
    feedback = item.get("feedback")
    if feedback is not None and feedback not in FEEDBACK_VALUES:
        _fail(f"{path}.feedback", f"expected null or one of {FEEDBACK_VALUES}")
    request_state = item.get("request_state")
    if request_state is not None and request_state not in REQUEST_STATE_VALUES:
        _fail(f"{path}.request_state", f"expected null or one of {REQUEST_STATE_VALUES}")
    _validate_nullable_str(item.get("feedback_at"), f"{path}.feedback_at")
    _validate_nullable_str(item.get("requested_at"), f"{path}.requested_at")
    _validate_nullable_str(item.get("poster_path"), f"{path}.poster_path")
    _validate_nullable_str(item.get("notes"), f"{path}.notes")
    if "rating" in item and not isinstance(item["rating"], (int, float, type(None))):
        _fail(f"{path}.rating", "expected number or null")
    if "in_library" in item and not isinstance(item["in_library"], bool):
        _fail(f"{path}.in_library", "expected boolean")
    if "jellyfin_id" in item and not isinstance(item["jellyfin_id"], (str, type(None))):
        _fail(f"{path}.jellyfin_id", "expected string or null")
    if "poster_url" in item and not isinstance(item["poster_url"], (str, type(None))):
        _fail(f"{path}.poster_url", "expected string or null")
    _validate_trakt_history_event(item.get("trakt_history_event"), f"{path}.trakt_history_event")
    request_id = item.get("jellyseerr_request_id")
    if request_id is not None and not _is_int(request_id):
        _fail(f"{path}.jellyseerr_request_id", "expected integer or null")
    year = item.get("year")
    if year is not None and not _is_int(year):
        _fail(f"{path}.year", "expected integer or null")


MEDIA_ID_RE = re.compile(r"^(?:movie|tv):[1-9][0-9]*$")
LEGACY_TOMBSTONE_RE = re.compile(r"^legacy:[1-9][0-9]*$")


def media_identity(item_type, tmdb_id):
    """Return the durable never-twice identity for one media item."""
    if item_type not in ITEM_TYPES or not _is_int(tmdb_id) or tmdb_id <= 0:
        raise ValueError("media identity requires a valid movie/tv type and TMDB ID")
    return f"{item_type}:{tmdb_id}"


def _legacy_tombstone(tmdb_id):
    return f"legacy:{tmdb_id}"


def _validate_v3_identity(value, path):
    if not isinstance(value, str) or not (MEDIA_ID_RE.fullmatch(value) or LEGACY_TOMBSTONE_RE.fullmatch(value)):
        _fail(path, "expected movie:<id>, tv:<id>, or legacy:<id>")


def _identity_is_present(presented, identity, tmdb_id):
    return identity in presented or _legacy_tombstone(tmdb_id) in presented


def validate_v3(data):
    """Validate a document against the v3 composite-identity contract."""
    if not isinstance(data, dict):
        _fail("$", "expected object")
    if data.get("version") != SCHEMA_V3_VERSION:
        _fail("version", f"expected {SCHEMA_V3_VERSION}")
    revision = data.get("revision")
    if not _is_int(revision) or revision < 0:
        _fail("revision", "expected non-negative integer")
    if not isinstance(data.get("updated_at"), str):
        _fail("updated_at", "expected string")
    presented = data.get("presented_media_ids")
    if not isinstance(presented, list):
        _fail("presented_media_ids", "expected array")
    presented_seen = set()
    for i, identity in enumerate(presented):
        _validate_v3_identity(identity, f"presented_media_ids[{i}]")
        if identity in presented_seen:
            _fail(f"presented_media_ids[{i}]", "duplicate media identity")
        presented_seen.add(identity)

    items = data.get("items")
    if not isinstance(items, list):
        _fail("items", "expected array")
    item_ids = set()
    current_identities = set()
    for i, item in enumerate(items):
        path = f"items[{i}]"
        _validate_item(item, path)
        identity = item.get("identity")
        expected_identity = media_identity(item["type"], item["tmdb_id"])
        if identity != expected_identity:
            _fail(f"{path}.identity", f"expected {expected_identity}")
        expected_item_id = f"hermes-{item['type']}-{item['tmdb_id']}"
        if item["id"] != expected_item_id:
            _fail(f"{path}.id", f"expected {expected_item_id}")
        if item["id"] in item_ids:
            _fail(f"{path}.id", "duplicate item id")
        item_ids.add(item["id"])
        if identity in current_identities:
            _fail(f"{path}.identity", "duplicate current media identity")
        current_identities.add(identity)
        if identity not in presented_seen:
            _fail(
                f"{path}.identity",
                "current media identity must be present in presented_media_ids",
            )
    return True


def _validate_generation(value, path="generation"):
    if value is None:
        return
    if not isinstance(value, dict):
        _fail(path, "expected object or null")
    required = (
        "id", "status", "trigger", "requested_at", "started_at",
        "finished_at", "desired_count", "attempt", "lease_expires_at",
        "lease_token", "base_revision", "candidates", "taste",
        "required_retain", "error_code", "counts",
    )
    for field in required:
        if field not in value:
            _fail(f"{path}.{field}", "required field missing")
    if not isinstance(value.get("id"), str) or not value["id"]:
        _fail(f"{path}.id", "expected non-empty string")
    if value.get("status") not in GENERATION_STATUSES:
        _fail(f"{path}.status", f"expected one of {GENERATION_STATUSES}")
    if value.get("trigger") not in GENERATION_TRIGGERS:
        _fail(f"{path}.trigger", f"expected one of {GENERATION_TRIGGERS}")
    if not isinstance(value.get("requested_at"), str):
        _fail(f"{path}.requested_at", "expected string")
    for field in ("started_at", "finished_at", "lease_expires_at", "lease_token", "error_code"):
        _validate_nullable_str(value.get(field), f"{path}.{field}")
    desired_count = value.get("desired_count")
    if not _is_int(desired_count) or not 1 <= desired_count <= 100:
        _fail(f"{path}.desired_count", "expected integer between 1 and 100")
    attempt = value.get("attempt")
    if not _is_int(attempt) or attempt < 0:
        _fail(f"{path}.attempt", "expected non-negative integer")
    base_revision = value.get("base_revision")
    if base_revision is not None and (not _is_int(base_revision) or base_revision < 0):
        _fail(f"{path}.base_revision", "expected non-negative integer or null")
    candidates = value.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > 100:
        _fail(f"{path}.candidates", "expected array")
    candidate_identities = set()
    for index, candidate in enumerate(candidates):
        candidate_path = f"{path}.candidates[{index}]"
        if not isinstance(candidate, dict):
            _fail(candidate_path, "expected object")
        item_type = candidate.get("type")
        tmdb_id = candidate.get("tmdb_id")
        if item_type not in ITEM_TYPES:
            _fail(f"{candidate_path}.type", f"expected one of {ITEM_TYPES}")
        if not _is_int(tmdb_id) or tmdb_id <= 0:
            _fail(f"{candidate_path}.tmdb_id", "expected positive integer")
        expected_identity = media_identity(item_type, tmdb_id)
        if candidate.get("identity") != expected_identity:
            _fail(f"{candidate_path}.identity", f"expected {expected_identity}")
        if expected_identity in candidate_identities:
            _fail(f"{candidate_path}.identity", "duplicate media identity")
        candidate_identities.add(expected_identity)
        if not isinstance(candidate.get("title"), str) or not candidate["title"].strip():
            _fail(f"{candidate_path}.title", "expected non-empty string")
    if not isinstance(value.get("taste"), dict):
        _fail(f"{path}.taste", "expected object")
    required_retain = value.get("required_retain")
    if not isinstance(required_retain, list):
        _fail(f"{path}.required_retain", "expected array")
    retain_seen = set()
    for index, identity in enumerate(required_retain):
        _validate_v3_identity(identity, f"{path}.required_retain[{index}]")
        if identity.startswith("legacy:"):
            _fail(f"{path}.required_retain[{index}]", "legacy identity not allowed")
        if identity in retain_seen:
            _fail(f"{path}.required_retain[{index}]", "duplicate media identity")
        retain_seen.add(identity)
    counts = value.get("counts")
    if counts is not None:
        if not isinstance(counts, dict):
            _fail(f"{path}.counts", "expected object or null")
        for field in ("accepted", "retained", "rotated", "rejected"):
            count = counts.get(field)
            if not _is_int(count) or count < 0:
                _fail(f"{path}.counts.{field}", "expected non-negative integer")


def validate_v4(data):
    """Validate the AI Picks v4 contract."""
    if not isinstance(data, dict):
        _fail("$", "expected object")
    if data.get("version") != SCHEMA_VERSION:
        _fail("version", f"expected {SCHEMA_VERSION}")
    revision = data.get("revision")
    if not _is_int(revision) or revision < 0:
        _fail("revision", "expected non-negative integer")
    if not isinstance(data.get("updated_at"), str):
        _fail("updated_at", "expected string")
    presented = data.get("presented_media_ids")
    if not isinstance(presented, list):
        _fail("presented_media_ids", "expected array")
    presented_seen = set()
    for i, identity in enumerate(presented):
        _validate_v3_identity(identity, f"presented_media_ids[{i}]")
        if identity in presented_seen:
            _fail(f"presented_media_ids[{i}]", "duplicate media identity")
        presented_seen.add(identity)
    items = data.get("items")
    if not isinstance(items, list):
        _fail("items", "expected array")
    item_ids = set()
    current_identities = set()
    for i, item in enumerate(items):
        path = f"items[{i}]"
        _validate_item(item, path)
        identity = item.get("identity")
        expected_identity = media_identity(item["type"], item["tmdb_id"])
        if identity != expected_identity:
            _fail(f"{path}.identity", f"expected {expected_identity}")
        expected_item_id = f"ai-{item['type']}-{item['tmdb_id']}"
        if item.get("id") != expected_item_id:
            _fail(f"{path}.id", f"expected {expected_item_id}")
        if item.get("source") != "ai":
            _fail(f"{path}.source", "expected ai")
        if item["id"] in item_ids:
            _fail(f"{path}.id", "duplicate item id")
        item_ids.add(item["id"])
        if identity in current_identities:
            _fail(f"{path}.identity", "duplicate current media identity")
        current_identities.add(identity)
        if identity not in presented_seen:
            _fail(f"{path}.identity", "current media identity must be present in presented_media_ids")
    _validate_generation(data.get("generation"))
    return True


def _migrate_v2_to_v3(v2):
    """Migrate v2 numeric history without discarding any deny entries.

    Numeric history becomes a legacy tombstone checked against both media
    types. Exact composite identities are added for current rows so those
    rows remain self-describing after migration.
    """
    validate_v2(v2)
    doc = copy.deepcopy(v2)
    doc["version"] = SCHEMA_V3_VERSION
    numeric_history = doc.pop("presented_tmdb_ids")
    presented = [_legacy_tombstone(tmdb_id) for tmdb_id in numeric_history]
    for item in doc["items"]:
        identity = media_identity(item["type"], item["tmdb_id"])
        item["identity"] = identity
        item["id"] = f"hermes-{identity.replace(':', '-')}"
        if identity not in presented:
            presented.append(identity)
    doc["presented_media_ids"] = presented
    validate_v3(doc)
    return doc


def migrate_to_v3(raw):
    """Return a v3 document for valid v2 or v3 input without mutating it.

    Legacy v1 / unknown / malformed documents are rejected. Independent
    ``active`` / ``feedback`` / ``request_state`` fields are never inferred
    from a legacy ``status`` value.
    """
    if not isinstance(raw, dict):
        _fail("$", "expected object")
    version = raw.get("version")
    if version == SCHEMA_V3_VERSION:
        validate_v3(raw)
        return copy.deepcopy(raw)
    if version == SCHEMA_V2_VERSION:
        return _migrate_v2_to_v3(raw)
    _fail(
        "version",
        f"unsupported version {version!r}; expected {SCHEMA_V2_VERSION} or {SCHEMA_V3_VERSION}",
    )


def _migrate_v3_to_v4(v3):
    validate_v3(v3)
    doc = copy.deepcopy(v3)
    doc["version"] = SCHEMA_VERSION
    doc["generation"] = None
    for item in doc["items"]:
        item["source"] = "ai"
        item["id"] = f"ai-{item['type']}-{item['tmdb_id']}"
    validate_v4(doc)
    return doc


def migrate_to_v4(raw):
    """Return a validated v4 copy for valid v2, v3, or v4 input."""
    if not isinstance(raw, dict):
        _fail("$", "expected object")
    version = raw.get("version")
    if version == SCHEMA_VERSION:
        validate_v4(raw)
        return copy.deepcopy(raw)
    if version in (SCHEMA_V2_VERSION, SCHEMA_V3_VERSION):
        return _migrate_v3_to_v4(migrate_to_v3(raw))
    _fail(
        "version",
        f"unsupported version {version!r}; expected {SCHEMA_V2_VERSION}, {SCHEMA_V3_VERSION}, or {SCHEMA_VERSION}",
    )


def apply_feedback(item, feedback, now=None):
    """Set feedback fields only; request fields are preserved.

    Any feedback (liked, disliked, watched, skipped) deactivates the item
    so it leaves the Active queue. Liked is treated as watched by Discover
    history consumers; reactivation happens only through generation acceptance.
    """
    if feedback not in FEEDBACK_VALUES:
        raise RecommendationValidationError(
            f"feedback: expected one of {FEEDBACK_VALUES}"
        )
    item["feedback"] = feedback
    item["feedback_at"] = now or utc_now()
    item["active"] = False
    if feedback != "watched":
        event = item.get("trakt_history_event")
        if isinstance(event, dict) and event.get("status") not in (
            "synced",
            "failed",
        ):
            del item["trakt_history_event"]


def apply_request(item, now=None, request_id=None):
    """Set request fields only; feedback fields are preserved."""
    if (
        item.get("request_state") == "requested"
        and item.get("jellyseerr_request_id") == request_id
    ):
        return
    item["request_state"] = "requested"
    item["requested_at"] = now or utc_now()
    if request_id is not None:
        item["jellyseerr_request_id"] = request_id
    item["active"] = False


class RecommendationStore:
    """Transactional storage for a single recommendations.json file."""

    _process_lock = threading.RLock()

    def __init__(self, path):
        self.path = path

    def default_document(self):
        return {
            "version": SCHEMA_VERSION,
            "revision": 0,
            "updated_at": "",
            "presented_media_ids": [],
            "items": [],
            "generation": None,
        }

    def load(self):
        """Return the current document as v4.

        Valid v2/v3 files are migrated in memory only; v4 is persisted on the
        next successful mutation (after validation). Invalid or legacy-v1
        documents raise and leave the on-disk bytes unchanged.
        """
        with self._process_lock:
            return self._load_locked()

    def _load_locked(self):
        if not os.path.isfile(self.path):
            return self.default_document()
        try:
            with open(self.path, encoding="utf-8-sig") as fh:
                raw = json.load(fh)
        except (OSError, ValueError) as e:
            raise RecommendationError(f"cannot read {self.path}: {e}") from e
        # Invalid / legacy-v1 documents raise without rewriting the file.
        return migrate_to_v4(raw)

    def ensure_current(self):
        """Persist valid v2/v3 input as v4 after a non-overwriting backup."""
        with self._process_lock:
            if not os.path.isfile(self.path):
                return self.default_document()
            try:
                with open(self.path, "rb") as fh:
                    original = fh.read()
                raw = json.loads(original.decode("utf-8-sig"))
            except (OSError, ValueError, UnicodeError) as e:
                raise RecommendationError(f"cannot read {self.path}: {e}") from e
            migrated = migrate_to_v4(raw)
            if raw.get("version") == SCHEMA_VERSION:
                return migrated
            backup_path = f"{self.path}.v{raw.get('version')}.bak"
            if not os.path.exists(backup_path):
                directory = os.path.dirname(backup_path)
                if directory:
                    os.makedirs(directory, exist_ok=True)
                try:
                    with open(backup_path, "xb") as fh:
                        fh.write(original)
                        fh.flush()
                        os.fsync(fh.fileno())
                except FileExistsError:
                    pass
            self._atomic_write(migrated)
            return copy.deepcopy(migrated)

    def update(self, mutator):
        """Run one read-modify-write transaction.

        ``mutator`` receives a deep copy of the current v4 document and may
        modify it. On success the candidate is validated, its ``revision`` is
        incremented, ``updated_at`` is refreshed, and it is atomically written.
        If the mutator raises, or validation or the write fails, the file on
        disk is left unchanged. Returns the committed document.
        """
        with self._process_lock:
            current = self._load_locked()
            candidate = copy.deepcopy(current)
            changed = mutator(candidate)
            if changed is False:
                return current
            candidate["revision"] = current.get("revision", 0) + 1
            candidate["updated_at"] = utc_now()
            validate_v4(candidate)
            self._atomic_write(candidate)
            return candidate

    def _atomic_write(self, data):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp_path = f"{self.path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self.path)
            self._fsync_directory(directory)
        except BaseException:
            try:
                if os.path.isfile(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def _fsync_directory(directory):
        """Fsync the containing directory so the rename itself is durable.

        Best-effort: some platforms (Windows) cannot open directories, in
        which case the file-level fsync above is what we get.
        """
        if not directory:
            return
        try:
            dir_fd = os.open(directory, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        except OSError:
            pass
        finally:
            os.close(dir_fd)
