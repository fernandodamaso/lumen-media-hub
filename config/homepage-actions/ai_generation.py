#!/usr/bin/env python3
"""Durable AI Picks job orchestration and transactional commits."""

import copy
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from recommendations_store import media_identity, utc_now


ALLOWED_FAILURE_CODES = {
    "candidate_unavailable",
    "empty_pool",
    "invalid_output",
    "model_timeout",
    "provider_failure",
    "stale_revision",
}
MAX_DESIRED_COUNT = 100


def _parse_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _format_timestamp(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_generation(job_id, trigger, desired_count, requested_at):
    return {
        "id": job_id,
        "status": "queued",
        "trigger": trigger,
        "requested_at": requested_at,
        "started_at": None,
        "finished_at": None,
        "desired_count": desired_count,
        "attempt": 0,
        "lease_expires_at": None,
        "lease_token": None,
        "base_revision": None,
        "candidates": [],
        "taste": {},
        "required_retain": [],
        "error_code": None,
        "counts": None,
    }


def public_generation(generation):
    """Return only the safe generation fields intended for browser clients."""
    if generation is None:
        return None
    return {
        key: copy.deepcopy(generation.get(key))
        for key in (
            "id",
            "status",
            "trigger",
            "requested_at",
            "started_at",
            "finished_at",
            "desired_count",
            "attempt",
            "error_code",
            "counts",
        )
    }


class AiGenerationCoordinator:
    """Own one queued/running job and validate all worker output."""

    def __init__(
        self,
        store,
        candidate_builder,
        *,
        commit_exclusions=None,
        now=utc_now,
        lease_token=lambda: secrets.token_urlsafe(32),
        job_id=lambda: str(uuid.uuid4()),
        lease_seconds=300,
    ):
        self.store = store
        self.candidate_builder = candidate_builder
        self.commit_exclusions = commit_exclusions or (lambda _doc: {})
        self.now = now
        self.lease_token = lease_token
        self.job_id = job_id
        self.lease_seconds = lease_seconds

    def queue(self, trigger, desired_count):
        if (
            isinstance(desired_count, bool)
            or not isinstance(desired_count, int)
            or not 1 <= desired_count <= MAX_DESIRED_COUNT
        ):
            raise ValueError(f"desired_count must be between 1 and {MAX_DESIRED_COUNT}")
        result = {}

        def mutate(doc):
            current = doc.get("generation")
            if current and current.get("status") in ("queued", "running"):
                result.update(queued=False, already_pending=True, id=current["id"])
                return False
            generation = _new_generation(
                self.job_id(), trigger, desired_count, self.now()
            )
            doc["generation"] = generation
            result.update(queued=True, already_pending=False, id=generation["id"])

        self.store.update(mutate)
        return result

    def claim(self):
        lease = self.lease_token()
        claimed = {}

        def start(doc):
            generation = doc.get("generation")
            if not generation or generation.get("status") != "queued":
                return False
            timestamp = self.now()
            start_time = _parse_timestamp(timestamp)
            if start_time is None:
                raise ValueError("now() must return an ISO-8601 timestamp")
            generation["status"] = "running"
            generation["started_at"] = timestamp
            generation["finished_at"] = None
            generation["attempt"] += 1
            generation["lease_token"] = lease
            generation["lease_expires_at"] = _format_timestamp(
                start_time + timedelta(seconds=self.lease_seconds)
            )
            generation["error_code"] = None
            generation["counts"] = None
            claimed["id"] = generation["id"]

        self.store.update(start)
        if not claimed:
            return None

        try:
            snapshot = self.candidate_builder(self.store.load())
            candidates = snapshot.get("candidates") if isinstance(snapshot, dict) else None
            if not candidates:
                self.fail(claimed["id"], lease, "empty_pool")
                return None
            taste = snapshot.get("taste", {})
            required_retain = snapshot.get("required_retain", [])
        except Exception as error:
            self.fail(
                claimed["id"],
                lease,
                getattr(error, "code", "candidate_unavailable"),
            )
            return None

        response = {}

        def attach(doc):
            generation = doc.get("generation")
            if not self._owns(generation, claimed["id"], lease):
                return False
            generation["candidates"] = copy.deepcopy(candidates[:100])
            generation["taste"] = copy.deepcopy(taste)
            generation["required_retain"] = list(required_retain)
            # RecommendationStore increments once after this mutator returns.
            generation["base_revision"] = doc["revision"] + 1
            response.update(
                id=generation["id"],
                lease_token=lease,
                desired_count=generation["desired_count"],
                candidates=copy.deepcopy(generation["candidates"]),
                taste=copy.deepcopy(taste),
            )

        self.store.update(attach)
        return response or None

    def complete(self, job_id, lease, picks):
        try:
            exclusions = self.commit_exclusions(self.store.load())
            if not isinstance(exclusions, dict) or exclusions.get("errors"):
                raise ValueError("authoritative exclusions unavailable")
        except Exception:
            failed = self.fail(job_id, lease, "candidate_unavailable")
            if not failed.get("ok"):
                return failed
            return {"ok": False, "code": "candidate_unavailable"}

        denied = set(exclusions.get("tracked", ()))
        denied.update(exclusions.get("in_library", ()))
        denied.update(exclusions.get("watched", ()))
        result = {}

        def mutate(doc):
            generation = doc.get("generation")
            if not self._owns(generation, job_id, lease):
                result.update(ok=False, code="stale_revision")
                return False
            if self._lease_expired(generation):
                self._mark_failed(generation, "provider_failure")
                result.update(ok=False, code="stale_revision")
                return
            if generation.get("base_revision") != doc.get("revision"):
                self._mark_failed(generation, "stale_revision")
                result.update(ok=False, code="stale_revision")
                return

            normalized = self._validate_picks(picks, generation["candidates"])
            if normalized is None:
                self._mark_failed(generation, "invalid_output")
                result.update(ok=False, code="invalid_output")
                return

            candidates = {item["identity"]: item for item in generation["candidates"]}
            existing = {item["identity"]: item for item in doc["items"]}
            required = set(generation.get("required_retain", []))
            selected = {pick["identity"] for pick in normalized}
            if denied.intersection(selected | required):
                self._mark_failed(generation, "stale_revision")
                result.update(ok=False, code="stale_revision")
                return
            retained = []
            for identity in required:
                item = existing.get(identity)
                if item is not None:
                    retained.append(copy.deepcopy(item))

            accepted = []
            for pick in normalized:
                candidate = candidates[pick["identity"]]
                identity = candidate["identity"]
                item_type, tmdb_value = identity.split(":", 1)
                tmdb_id = int(tmdb_value)
                item = {
                    "id": f"ai-{item_type}-{tmdb_id}",
                    "source": "ai",
                    "type": item_type,
                    "title": candidate["title"],
                    "tmdb_id": tmdb_id,
                    "identity": media_identity(item_type, tmdb_id),
                    "reason": pick["reason"],
                    "active": True,
                    "feedback": None,
                    "feedback_at": None,
                    "request_state": None,
                    "requested_at": None,
                    "jellyseerr_request_id": None,
                    "added_at": self.now(),
                }
                for key in (
                    "year", "poster_path", "poster_url", "rating", "overview",
                    "in_library", "jellyfin_id", "notes",
                ):
                    if key in candidate:
                        item[key] = copy.deepcopy(candidate[key])
                accepted.append(item)

            retained_ids = {item["identity"] for item in retained}
            replaced_ids = {item["identity"] for item in accepted}
            history = [
                item for item in doc["items"]
                if item["identity"] not in retained_ids | replaced_ids
            ]
            rotated_count = 0
            for item in history:
                if item.get("active"):
                    item["active"] = False
                    rotated_count += 1
            doc["items"] = history + retained + accepted
            for item in accepted:
                if item["identity"] not in doc["presented_media_ids"]:
                    doc["presented_media_ids"].append(item["identity"])

            counts = {
                "accepted": len(accepted),
                "retained": len(retained),
                "rotated": rotated_count,
                "rejected": len(generation["candidates"]) - len(accepted),
            }
            generation["status"] = "succeeded"
            generation["finished_at"] = self.now()
            generation["lease_token"] = None
            generation["lease_expires_at"] = None
            generation["error_code"] = None
            generation["counts"] = counts
            result.update(ok=True, counts=copy.deepcopy(counts))

        self.store.update(mutate)
        return result

    def fail(self, job_id, lease, code):
        safe_code = code if code in ALLOWED_FAILURE_CODES else "provider_failure"
        result = {}

        def mutate(doc):
            generation = doc.get("generation")
            if not self._owns(generation, job_id, lease):
                result.update(ok=False, code="stale_revision")
                return False
            self._mark_failed(generation, safe_code)
            result.update(ok=True, code=safe_code)

        self.store.update(mutate)
        return result

    def expire_stale(self):
        expired = {}

        def mutate(doc):
            generation = doc.get("generation")
            if generation and generation.get("status") == "running" and self._lease_expired(generation):
                self._mark_failed(generation, "provider_failure")
                expired["value"] = True
                return
            return False

        self.store.update(mutate)
        return bool(expired)

    @staticmethod
    def _owns(generation, job_id, lease):
        return bool(
            generation
            and generation.get("status") == "running"
            and generation.get("id") == job_id
            and secrets.compare_digest(generation.get("lease_token") or "", lease or "")
        )

    def _lease_expired(self, generation):
        expires = _parse_timestamp(generation.get("lease_expires_at"))
        now = _parse_timestamp(self.now())
        return not expires or not now or now >= expires

    def _mark_failed(self, generation, code):
        generation["status"] = "failed"
        generation["finished_at"] = self.now()
        generation["lease_token"] = None
        generation["lease_expires_at"] = None
        generation["error_code"] = code
        generation["counts"] = None

    @staticmethod
    def _validate_picks(picks, candidates):
        if not isinstance(picks, list) or not picks:
            return None
        allowed = {item.get("identity") for item in candidates}
        seen = set()
        normalized = []
        for pick in picks:
            if not isinstance(pick, dict):
                return None
            identity = pick.get("identity")
            reason = pick.get("reason")
            if identity not in allowed or identity in seen:
                return None
            if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 240:
                return None
            seen.add(identity)
            normalized.append({"identity": identity, "reason": reason.strip()})
        return normalized
