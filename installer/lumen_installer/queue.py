"""Pure, conservative preview classification for staged queue work."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


CLEANUP = "cleanup"
REPLACEMENT = "replacement"
PAUSED = "paused"
PRESERVE_REVIEW = "preserve_review"
_MEDIA_TYPES = frozenset({"episode", "episode_file", "movie", "movie_file", "series", "tv"})
_EPISODE_MEDIA_TYPES = frozenset({"episode", "episode_file"})


@dataclass(frozen=True)
class QueueCandidate:
    """A proposed next action; this type has no execution methods."""

    identifier: str
    action: str
    reason: str
    replacement_episodes: tuple[str, ...] = ()

    @property
    def kind(self) -> str:
        return self.action

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "action": self.action,
            "reason": self.reason,
            "replacement_episodes": list(self.replacement_episodes),
        }


@dataclass(frozen=True)
class QueueClassification:
    """Secret-free counts and reasons for a dry-run queue preview."""

    candidates: tuple[QueueCandidate, ...]

    @property
    def counts(self) -> dict[str, int]:
        counts = {
            CLEANUP: 0,
            REPLACEMENT: 0,
            PAUSED: 0,
            PRESERVE_REVIEW: 0,
        }
        for candidate in self.candidates:
            counts[candidate.action] = counts.get(candidate.action, 0) + 1
        return counts

    @property
    def reasons(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for candidate in self.candidates:
            result[candidate.reason] = result.get(candidate.reason, 0) + 1
        return result

    @property
    def report(self) -> dict[str, Any]:
        return {
            "status": "dry-run",
            "counts": self.counts,
            "reasons": self.reasons,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "mutations": (),
        }

    def as_dict(self) -> dict[str, Any]:
        return self.report


def _value(record: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in record:
            return record[name]
    return None


def _explicit_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "1", "watched"}:
            return True
        if normalized in {"false", "no", "0", "unwatched"}:
            return False
    return None


def _runtime_known(record: Mapping[str, Any]) -> bool:
    value = _value(record, "runtime_minutes", "runtime")
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and value > 0
    )


def _media_type_known(record: Mapping[str, Any]) -> bool:
    value = _value(record, "media_type", "type")
    return isinstance(value, str) and value.strip().casefold() in _MEDIA_TYPES


def _media_type(record: Mapping[str, Any]) -> str | None:
    value = _value(record, "media_type", "type")
    return value.strip().casefold() if isinstance(value, str) else None


def _episodes(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    result_values: list[str] = []
    for item in value:
        if isinstance(item, str):
            candidate = item.strip()
        elif isinstance(item, int) and not isinstance(item, bool) and item > 0:
            candidate = str(item)
        else:
            return None
        if not candidate or any(ord(character) < 32 for character in candidate):
            return None
        result_values.append(candidate)
    result = tuple(result_values)
    return result if result else None


def _identifier(record: Mapping[str, Any]) -> str | None:
    for name in ("id", "hash", "path", "name"):
        if name not in record:
            continue
        value = record[name]
        if isinstance(value, str) and value.strip() and not any(ord(character) < 32 for character in value):
            return value.strip()
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return str(value)
        return None
    return None


def _incomplete_state(record: Mapping[str, Any]) -> bool | None:
    value = _value(record, "incomplete", "is_incomplete")
    if value is not None:
        return _explicit_bool(value)
    status = _value(record, "status", "state")
    if isinstance(status, str):
        normalized = status.strip().casefold()
        if normalized in {"incomplete", "partial", "in-progress", "in progress"}:
            return True
        if normalized in {"complete", "completed"}:
            return False
    return None


def _replacement_episodes(record: Mapping[str, Any]) -> tuple[str, ...] | None:
    missing = _episodes(_value(record, "missing_episodes", "missingEpisodes"))
    if missing is None:
        return None
    watched = _episodes(_value(record, "watched_episodes", "watchedEpisodes"))
    if watched is None:
        return missing
    watched_keys = {item.casefold() for item in watched}
    remaining = tuple(item for item in missing if item.casefold() not in watched_keys)
    return remaining or None


def _candidate(
    record: Mapping[str, Any],
    index: int,
    action: str,
    reason: str,
    episodes: tuple[str, ...] = (),
) -> QueueCandidate:
    identifier = _identifier(record) or f"record-{index + 1}"
    return QueueCandidate(identifier, action, reason, episodes)


def classify_queue(records: Iterable[Mapping[str, Any]]) -> QueueClassification:
    """Classify records without contacting services or mutating queue state.

    Missing facts are deliberately not inferred.  In particular, an absent
    watch state is not treated as unwatched and an absent partial-pack flag is
    not treated as a complete import.
    """

    candidates: list[QueueCandidate] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            candidates.append(
                QueueCandidate(f"record-{index + 1}", PRESERVE_REVIEW, "record data is unknown")
            )
            continue

        if _identifier(record) is None:
            candidates.append(
                QueueCandidate(f"record-{index + 1}", PRESERVE_REVIEW, "record identifier is invalid")
            )
            continue

        imported = _explicit_bool(_value(record, "imported", "is_imported"))
        verified = _explicit_bool(_value(record, "verified", "hash_verified", "is_verified"))
        partial_pack = _explicit_bool(_value(record, "partial_pack", "is_partial_pack"))
        if not (_runtime_known(record) and _media_type_known(record)):
            candidates.append(
                _candidate(record, index, PRESERVE_REVIEW, "runtime or media type is unknown")
            )
            continue
        if imported is None or verified is None or partial_pack is None:
            candidates.append(
                _candidate(record, index, PRESERVE_REVIEW, "import, verification, or pack state is unknown")
            )
            continue
        if partial_pack:
            candidates.append(
                _candidate(record, index, PRESERVE_REVIEW, "partial pack is preserved for review")
            )
            continue

        if imported and verified:
            registered = _explicit_bool(_value(record, "source_registered", "registered"))
            if registered is not True:
                candidates.append(
                    _candidate(record, index, PRESERVE_REVIEW, "unregistered staging source is not a cleanup target")
                )
            else:
                candidates.append(
                    _candidate(
                        record,
                        index,
                        CLEANUP,
                        "imported and verified; cleanup still requires a later verified commit",
                    )
                )
            continue

        disallowed = _explicit_bool(_value(record, "disallowed", "clearly_disallowed"))
        if disallowed is True and not imported:
            incomplete = _incomplete_state(record)
            if incomplete is not True:
                candidates.append(
                    _candidate(record, index, PRESERVE_REVIEW, "replacement requires an explicit incomplete state")
                )
                continue
            if _media_type(record) not in _EPISODE_MEDIA_TYPES:
                candidates.append(
                    _candidate(record, index, PRESERVE_REVIEW, "movie records cannot receive episode replacements")
                )
                continue
            watched = _explicit_bool(_value(record, "watched", "watch_status"))
            episodes = _replacement_episodes(record)
            if watched is False and episodes:
                candidates.append(
                    _candidate(
                        record,
                        index,
                        REPLACEMENT,
                        "disallowed incomplete item; replace only explicitly unwatched missing episodes",
                        episodes,
                    )
                )
            else:
                candidates.append(
                    _candidate(
                        record,
                        index,
                        PRESERVE_REVIEW,
                        "disallowed item has no safe unwatched missing-episode replacement set",
                    )
                )
            continue

        acceptable = _explicit_bool(_value(record, "acceptable", "quality_acceptable"))
        fits = _explicit_bool(_value(record, "fits_capacity", "fits"))
        if acceptable is True and fits is False:
            candidates.append(
                _candidate(record, index, PAUSED, "acceptable item cannot fit current capacity; preserve and pause later")
            )
            continue

        candidates.append(
            _candidate(record, index, PRESERVE_REVIEW, "no conservative action is established")
        )

    return QueueClassification(tuple(candidates))


preview_queue = classify_queue


__all__ = [
    "CLEANUP",
    "PAUSED",
    "PRESERVE_REVIEW",
    "REPLACEMENT",
    "QueueCandidate",
    "QueueClassification",
    "classify_queue",
    "preview_queue",
]
