"""Read-only Storage Guardian inventory normalization and deterministic policy evaluation."""
from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.parse
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

from clients import jellyfin as jellyfin_client


SCHEMA_VERSION = 1
JELLYFIN_PAGE_SIZE = 100
MAX_PINNED_IDS = 5000
MAX_DAYS = 3650
MAX_KEEP_LATEST = 100
MAX_BYTES = 1 << 60
CANDIDATE_ID_RE = re.compile(r"^sg_[0-9a-f]{24}$")

RULE_CODES = (
    "watched_movie_expired",
    "watched_episode_expired",
    "large_watched_file_stale",
)

BLOCK_CODES = (
    "in_progress",
    "never_watched",
    "favorite",
    "manual_pin",
    "recent_addition",
    "no_matching_rule",
)


class CleanupValidationError(ValueError):
    """The requested policy is malformed or outside supported v1 bounds."""


class CleanupInventoryError(RuntimeError):
    """The inventory could not be completed safely."""


def _as_non_negative_int(value: Any, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CleanupValidationError(f"{field} must be a finite non-negative integer")
    if not math.isfinite(value) or int(value) != value:
        raise CleanupValidationError(f"{field} must be a finite non-negative integer")
    normalized = int(value)
    if normalized < 0 or normalized > maximum:
        raise CleanupValidationError(f"{field} must be between 0 and {maximum}")
    return normalized


def _require_record(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CleanupValidationError(f"{field} must be an object")
    return value


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise CleanupValidationError(f"{field} must be boolean")
    return value


def validate_cleanup_request(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise CleanupValidationError("Body must be an object")
    if set(raw) != {"schemaVersion", "targetFreeBytes", "rules", "protections"}:
        raise CleanupValidationError("Body fields do not match cleanup preview schema v1")
    if raw.get("schemaVersion") != SCHEMA_VERSION:
        raise CleanupValidationError("schemaVersion must be 1")

    rules = _require_record(raw["rules"], "rules")
    protections = _require_record(raw["protections"], "protections")
    if set(rules) != {"watchedMovies", "watchedEpisodes", "largeWatchedFiles"}:
        raise CleanupValidationError("rules fields do not match cleanup preview schema v1")
    if set(protections) != {"recentAdditionGraceDays", "pinnedCandidateIds"}:
        raise CleanupValidationError("protections fields do not match cleanup preview schema v1")

    movies = _require_record(rules["watchedMovies"], "rules.watchedMovies")
    episodes = _require_record(rules["watchedEpisodes"], "rules.watchedEpisodes")
    large = _require_record(rules["largeWatchedFiles"], "rules.largeWatchedFiles")
    if set(movies) != {"enabled", "retentionDays"}:
        raise CleanupValidationError("rules.watchedMovies is malformed")
    if set(episodes) != {"enabled", "retentionDays", "keepLatestPerSeries"}:
        raise CleanupValidationError("rules.watchedEpisodes is malformed")
    if set(large) != {"enabled", "minimumBytes", "idleDays"}:
        raise CleanupValidationError("rules.largeWatchedFiles is malformed")

    pinned = protections["pinnedCandidateIds"]
    if not isinstance(pinned, list) or len(pinned) > MAX_PINNED_IDS:
        raise CleanupValidationError(f"protections.pinnedCandidateIds must contain at most {MAX_PINNED_IDS} IDs")
    normalized_pins: list[str] = []
    seen_pins: set[str] = set()
    for value in pinned:
        if not isinstance(value, str) or not CANDIDATE_ID_RE.fullmatch(value):
            raise CleanupValidationError("protections.pinnedCandidateIds contains an invalid candidate ID")
        if value not in seen_pins:
            normalized_pins.append(value)
            seen_pins.add(value)

    return {
        "schemaVersion": SCHEMA_VERSION,
        "targetFreeBytes": _as_non_negative_int(raw["targetFreeBytes"], "targetFreeBytes", maximum=MAX_BYTES),
        "rules": {
            "watchedMovies": {
                "enabled": _require_bool(movies["enabled"], "rules.watchedMovies.enabled"),
                "retentionDays": _as_non_negative_int(
                    movies["retentionDays"], "rules.watchedMovies.retentionDays", maximum=MAX_DAYS
                ),
            },
            "watchedEpisodes": {
                "enabled": _require_bool(episodes["enabled"], "rules.watchedEpisodes.enabled"),
                "retentionDays": _as_non_negative_int(
                    episodes["retentionDays"], "rules.watchedEpisodes.retentionDays", maximum=MAX_DAYS
                ),
                "keepLatestPerSeries": _as_non_negative_int(
                    episodes["keepLatestPerSeries"],
                    "rules.watchedEpisodes.keepLatestPerSeries",
                    maximum=MAX_KEEP_LATEST,
                ),
            },
            "largeWatchedFiles": {
                "enabled": _require_bool(large["enabled"], "rules.largeWatchedFiles.enabled"),
                "minimumBytes": _as_non_negative_int(
                    large["minimumBytes"], "rules.largeWatchedFiles.minimumBytes", maximum=MAX_BYTES
                ),
                "idleDays": _as_non_negative_int(
                    large["idleDays"], "rules.largeWatchedFiles.idleDays", maximum=MAX_DAYS
                ),
            },
        },
        "protections": {
            "recentAdditionGraceDays": _as_non_negative_int(
                protections["recentAdditionGraceDays"],
                "protections.recentAdditionGraceDays",
                maximum=MAX_DAYS,
            ),
            "pinnedCandidateIds": normalized_pins,
        },
    }


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _candidate_id(physical_key: str) -> str:
    return "sg_" + hashlib.sha256(physical_key.encode("utf-8")).hexdigest()[:24]


def _unresolved_id(identity: str) -> str:
    return "unresolved_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def _safe_title(raw: dict[str, Any]) -> str:
    name = raw.get("Name")
    if isinstance(name, str) and name.strip():
        return name.strip()[:240]
    series = raw.get("SeriesName")
    if isinstance(series, str) and series.strip():
        return series.strip()[:240]
    return "Unknown Jellyfin item"


def _kind(raw: dict[str, Any]) -> str | None:
    value = raw.get("Type")
    if value == "Movie":
        return "movie"
    if value == "Episode":
        return "episode"
    return None


def _physical_key(path: str) -> str:
    # Used only in memory for grouping/hashing. It is never returned by this module.
    return path.strip().replace("\\", "/")


def _is_strm(path: str, source: dict[str, Any]) -> bool:
    container = source.get("Container")
    if isinstance(container, str) and container.casefold() == "strm":
        return True
    return path.casefold().endswith(".strm")


def _local_sources(raw: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    if raw.get("IsPlaceHolder") is True:
        return [], "excluded"
    if raw.get("LocationType") in {"Remote", "Virtual"}:
        return [], "excluded"
    sources = raw.get("MediaSources")
    if not isinstance(sources, list):
        return [], "malformed_media_sources"

    local_by_key: dict[str, dict[str, Any]] = {}
    malformed = False
    for source in sources:
        if not isinstance(source, dict):
            malformed = True
            continue
        if source.get("IsRemote") is True or source.get("Protocol") in {"Http", "Rtmp", "Rtsp", "Udp"}:
            continue
        path = source.get("Path") or raw.get("Path")
        if not isinstance(path, str) or not path.strip():
            malformed = True
            continue
        if _is_strm(path, source):
            continue
        size = source.get("Size")
        if isinstance(size, bool) or not isinstance(size, (int, float)) or not math.isfinite(size) or int(size) != size or size <= 0:
            malformed = True
            continue
        key = _physical_key(path)
        normalized = dict(source)
        normalized["_physicalKey"] = key
        normalized["_sizeBytes"] = int(size)
        local_by_key[key] = normalized

    if len(local_by_key) > 1:
        return list(local_by_key.values()), "ambiguous_versions"
    if malformed and local_by_key:
        return list(local_by_key.values()), "malformed_media_sources"
    if len(local_by_key) == 1:
        return list(local_by_key.values()), None
    return [], "malformed_media_source" if malformed else "excluded"


def _normalize_member(raw: dict[str, Any], source: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    kind = _kind(raw)
    if kind is None:
        return None, "unsupported_item"
    item_id = raw.get("Id")
    if not isinstance(item_id, str) or not item_id.strip():
        return None, "missing_item_id"

    date_added = _parse_timestamp(raw.get("DateCreated"))
    user = raw.get("UserData")
    if date_added is None or not isinstance(user, dict):
        return None, "malformed_metadata"
    played = user.get("Played")
    favorite = user.get("IsFavorite")
    if not isinstance(played, bool) or not isinstance(favorite, bool):
        return None, "malformed_watch_metadata"

    position = user.get("PlaybackPositionTicks", 0)
    if isinstance(position, bool) or not isinstance(position, (int, float)) or not math.isfinite(position) or position < 0:
        return None, "malformed_watch_metadata"

    last_played = _parse_timestamp(user.get("LastPlayedDate"))
    if played and last_played is None:
        return None, "malformed_watch_metadata"

    series_id = raw.get("SeriesId")
    season = raw.get("ParentIndexNumber")
    episode = raw.get("IndexNumber")
    end_episode = raw.get("EndIndexNumber")
    if kind == "episode":
        if not isinstance(series_id, str) or not series_id:
            return None, "malformed_episode_identity"
        if isinstance(season, bool) or not isinstance(season, int) or season < 0:
            return None, "malformed_episode_identity"
        if isinstance(episode, bool) or not isinstance(episode, int) or episode < 0:
            return None, "malformed_episode_identity"
        if end_episode is not None and (
            isinstance(end_episode, bool) or not isinstance(end_episode, int) or end_episode < episode
        ):
            return None, "malformed_episode_identity"

    return {
        "itemId": item_id.strip(),
        "kind": kind,
        "name": _safe_title(raw),
        "seriesId": series_id if isinstance(series_id, str) else None,
        "seriesName": raw.get("SeriesName") if isinstance(raw.get("SeriesName"), str) else None,
        "seasonNumber": season if kind == "episode" else None,
        "episodeNumber": episode if kind == "episode" else None,
        "endEpisodeNumber": end_episode if kind == "episode" and isinstance(end_episode, int) else None,
        "productionYear": raw.get("ProductionYear") if isinstance(raw.get("ProductionYear"), int) else None,
        "dateAdded": date_added,
        "lastPlayed": last_played,
        "played": played,
        "favorite": favorite,
        "playbackPositionTicks": int(position),
        "physicalKey": source["_physicalKey"],
        "sizeBytes": source["_sizeBytes"],
    }, None


def normalize_jellyfin_inventory(raw_items: list[Any]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unresolved: list[dict[str, Any]] = []

    for index, value in enumerate(raw_items):
        if not isinstance(value, dict):
            unresolved.append({
                "id": _unresolved_id(f"record:{index}"),
                "title": "Unknown Jellyfin item",
                "kind": "unknown",
                "reason": "malformed_item",
            })
            continue
        sources, source_problem = _local_sources(value)
        if source_problem == "excluded":
            continue
        if source_problem is not None:
            unresolved.append({
                "id": _unresolved_id(f"{value.get('Id', index)}:{source_problem}"),
                "title": _safe_title(value),
                "kind": _kind(value) or "unknown",
                "reason": source_problem,
            })
            continue
        member, member_problem = _normalize_member(value, sources[0])
        if member_problem is not None or member is None:
            unresolved.append({
                "id": _unresolved_id(f"{value.get('Id', index)}:{member_problem}"),
                "title": _safe_title(value),
                "kind": _kind(value) or "unknown",
                "reason": member_problem or "malformed_item",
            })
            continue
        groups[member["physicalKey"]].append(member)

    files: list[dict[str, Any]] = []
    for key, members in groups.items():
        kinds = {member["kind"] for member in members}
        sizes = {member["sizeBytes"] for member in members}
        series_ids = {member["seriesId"] for member in members if member["kind"] == "episode"}
        if len(kinds) != 1 or len(sizes) != 1 or (kinds == {"episode"} and len(series_ids) != 1):
            unresolved.append({
                "id": _unresolved_id(f"group:{key}"),
                "title": members[0]["name"],
                "kind": members[0]["kind"],
                "reason": "ambiguous_physical_file",
            })
            continue

        unique_members: dict[tuple[Any, ...], dict[str, Any]] = {}
        for member in members:
            identity = (
                member["itemId"],
                member["seasonNumber"],
                member["episodeNumber"],
                member["endEpisodeNumber"],
            )
            unique_members[identity] = member
        collapsed = sorted(
            unique_members.values(),
            key=lambda member: (
                member["seasonNumber"] if member["seasonNumber"] is not None else -1,
                member["episodeNumber"] if member["episodeNumber"] is not None else -1,
                member["itemId"],
            ),
        )
        files.append({
            "id": _candidate_id(key),
            "physicalKey": key,
            "kind": collapsed[0]["kind"],
            "sizeBytes": next(iter(sizes)),
            "members": collapsed,
        })

    files.sort(key=lambda item: item["id"])
    unresolved.sort(key=lambda item: item["id"])
    return {"files": files, "unresolved": unresolved}


def _jellyfin_items_path() -> str:
    user_id = jellyfin_client._jellyfin_user_id_for_queries()
    return f"/Users/{user_id}/Items" if user_id else "/Items"


def fetch_jellyfin_cleanup_inventory(
    get: Callable[[str, dict[str, str] | None], Any] | None = None,
) -> dict[str, Any]:
    fetch = get or jellyfin_client.jellyfin_get
    path = _jellyfin_items_path()
    raw_items: list[Any] = []
    fields = (
        "Path,MediaSources,DateCreated,UserData,SeriesId,SeriesName,"
        "ParentIndexNumber,IndexNumber,EndIndexNumber,LocationType,Type,ProductionYear,IsPlaceHolder"
    )
    for item_type in ("Movie", "Episode"):
        start = 0
        while True:
            try:
                data = fetch(
                    path,
                    {
                        "Recursive": "true",
                        "IncludeItemTypes": item_type,
                        "StartIndex": str(start),
                        "Limit": str(JELLYFIN_PAGE_SIZE),
                        "SortBy": "SortName",
                        "SortOrder": "Ascending",
                        "Fields": fields,
                    },
                )
            except Exception as error:
                raise CleanupInventoryError("Jellyfin cleanup inventory is unavailable") from error
            if not isinstance(data, dict) or not isinstance(data.get("Items"), list):
                raise CleanupInventoryError("Jellyfin cleanup inventory response is malformed")
            batch = data["Items"]
            raw_items.extend(batch)
            total = data.get("TotalRecordCount")
            if isinstance(total, bool) or not isinstance(total, int) or total < 0:
                raise CleanupInventoryError("Jellyfin cleanup inventory count is malformed")
            start += len(batch)
            if start >= total:
                break
            if not batch:
                raise CleanupInventoryError("Jellyfin cleanup inventory pagination ended early")

    return normalize_jellyfin_inventory(raw_items)


def _age_days(timestamp: datetime, evaluated_at: datetime) -> float:
    return max(0.0, (evaluated_at - timestamp).total_seconds() / 86400.0)


def _latest_episode_ids(files: list[dict[str, Any]], keep_latest: int) -> set[str]:
    if keep_latest <= 0:
        return set()
    by_series: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    for file in files:
        if file["kind"] != "episode":
            continue
        for member in file["members"]:
            if member["seasonNumber"] <= 0:
                continue
            start = member["episodeNumber"]
            end = member["endEpisodeNumber"] or start
            for number in range(start, end + 1):
                by_series[member["seriesId"]].append((member["seasonNumber"], number, member["itemId"]))

    protected: set[str] = set()
    for entries in by_series.values():
        entries.sort(key=lambda value: (value[0], value[1], value[2]), reverse=True)
        for _, _, item_id in entries[:keep_latest]:
            protected.add(item_id)
    return protected


def _reason(code: str, **evidence: int) -> dict[str, Any]:
    return {"code": code, "evidence": evidence}


def _member_rule_reasons(
    member: dict[str, Any],
    size_bytes: int,
    rules: dict[str, Any],
    latest_protected: set[str],
    evaluated_at: datetime,
) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    last_played = member["lastPlayed"]
    if last_played is None:
        return reasons
    last_played_age = _age_days(last_played, evaluated_at)
    if member["kind"] == "movie":
        rule = rules["watchedMovies"]
        if rule["enabled"] and last_played_age >= rule["retentionDays"]:
            reasons.append(_reason("watched_movie_expired", retentionDays=rule["retentionDays"]))
    else:
        rule = rules["watchedEpisodes"]
        if (
            rule["enabled"]
            and member["seasonNumber"] > 0
            and member["itemId"] not in latest_protected
            and last_played_age >= rule["retentionDays"]
        ):
            reasons.append(_reason(
                "watched_episode_expired",
                retentionDays=rule["retentionDays"],
                keepLatestPerSeries=rule["keepLatestPerSeries"],
            ))

    large = rules["largeWatchedFiles"]
    if (
        large["enabled"]
        and size_bytes >= large["minimumBytes"]
        and last_played_age >= large["idleDays"]
    ):
        reasons.append(_reason(
            "large_watched_file_stale",
            minimumBytes=large["minimumBytes"],
            idleDays=large["idleDays"],
        ))
    return reasons


def _block_reason(
    file: dict[str, Any],
    policy: dict[str, Any],
    evaluated_at: datetime,
) -> str | None:
    if file["id"] in set(policy["protections"]["pinnedCandidateIds"]):
        return "manual_pin"
    grace = policy["protections"]["recentAdditionGraceDays"]
    members = file["members"]
    if any(member["favorite"] for member in members):
        return "favorite"
    if any(not member["played"] and member["playbackPositionTicks"] > 0 for member in members):
        return "in_progress"
    if any(not member["played"] for member in members):
        return "never_watched"
    if any(_age_days(member["dateAdded"], evaluated_at) < grace for member in members):
        return "recent_addition"
    return None


def _display(file: dict[str, Any], external_url: str | None) -> tuple[str, str, str | None]:
    members = file["members"]
    member = members[0]
    href = None
    if external_url:
        base = external_url.rstrip("/")
        href = f"{base}/web/index.html#!/details?id={urllib.parse.quote(member['itemId'], safe='')}"
    if file["kind"] == "movie":
        year = member["productionYear"]
        subtitle = "Movie" + (f" · {year}" if year else "")
        return member["name"], subtitle, href

    series = member["seriesName"] or member["name"]
    season = member["seasonNumber"]
    start = member["episodeNumber"]
    end = member["endEpisodeNumber"]
    episode_label = f"S{season:02d}E{start:02d}"
    if end is not None and end != start:
        episode_label += f"–E{end:02d}"
    if len(members) > 1:
        last = members[-1]
        episode_label = f"S{season:02d}E{start:02d}–E{last['endEpisodeNumber'] or last['episodeNumber']:02d}"
    return series, f"Episode · {episode_label}", href


def _aggregate_blocked(entries: list[tuple[str, int]]) -> list[dict[str, Any]]:
    aggregate: dict[str, dict[str, Any]] = {}
    for code, size in entries:
        summary = aggregate.setdefault(code, {"code": code, "count": 0, "bytes": 0})
        summary["count"] += 1
        summary["bytes"] += size
    return [aggregate[code] for code in BLOCK_CODES if code in aggregate]


def evaluate_cleanup_preview(
    inventory: dict[str, Any],
    storage: dict[str, Any],
    policy: dict[str, Any],
    *,
    evaluated_at: datetime,
    jellyfin_external_url: str | None = None,
) -> dict[str, Any]:
    if evaluated_at.tzinfo is None:
        evaluated_at = evaluated_at.replace(tzinfo=timezone.utc)
    evaluated_at = evaluated_at.astimezone(timezone.utc)

    total = _as_non_negative_int(storage.get("total"), "storage.total", maximum=MAX_BYTES)
    used = _as_non_negative_int(storage.get("used"), "storage.used", maximum=MAX_BYTES)
    free = _as_non_negative_int(storage.get("free"), "storage.free", maximum=MAX_BYTES)
    if used > total or free > total or used + free > total + 4096:
        raise CleanupInventoryError("Storage capacity is inconsistent")

    files = list(inventory.get("files") or [])
    unresolved = list(inventory.get("unresolved") or [])
    latest = _latest_episode_ids(files, policy["rules"]["watchedEpisodes"]["keepLatestPerSeries"])
    blocked_entries: list[tuple[str, int]] = []
    eligible: list[dict[str, Any]] = []

    for file in files:
        block = _block_reason(file, policy, evaluated_at)
        if block:
            blocked_entries.append((block, file["sizeBytes"]))
            continue

        member_reasons = [
            _member_rule_reasons(member, file["sizeBytes"], policy["rules"], latest, evaluated_at)
            for member in file["members"]
        ]
        if not member_reasons or any(not reasons for reasons in member_reasons):
            blocked_entries.append(("no_matching_rule", file["sizeBytes"]))
            continue

        reason_by_code: dict[str, dict[str, Any]] = {}
        for reasons in member_reasons:
            for reason in reasons:
                reason_by_code[reason["code"]] = reason

        last_played = max(member["lastPlayed"] for member in file["members"] if member["lastPlayed"] is not None)
        date_added = max(member["dateAdded"] for member in file["members"])
        title, subtitle, href = _display(file, jellyfin_external_url)
        eligible.append({
            "id": file["id"],
            "mediaKind": file["kind"],
            "title": title,
            "subtitle": subtitle,
            "href": href,
            "sizeBytes": file["sizeBytes"],
            "dateAdded": _iso(date_added),
            "lastPlayedAt": _iso(last_played),
            "recommended": False,
            "reasons": [reason_by_code[code] for code in RULE_CODES if code in reason_by_code],
        })

    eligible.sort(key=lambda item: (
        item["lastPlayedAt"],
        -item["sizeBytes"],
        item["id"],
    ))

    target = policy["targetFreeBytes"]
    required = max(0, target - free)
    recommended_bytes = 0
    recommended_files = 0
    if required > 0:
        for candidate in eligible:
            if recommended_bytes >= required:
                break
            candidate["recommended"] = True
            recommended_bytes += candidate["sizeBytes"]
            recommended_files += 1

    eligible_bytes = sum(item["sizeBytes"] for item in eligible)
    projected = min(total, free + recommended_bytes)
    shortfall = max(0, target - projected)
    unresolved_safe = [
        {
            "id": str(item.get("id", "")),
            "title": str(item.get("title", "Unknown Jellyfin item"))[:240],
            "mediaKind": item.get("kind") if item.get("kind") in {"movie", "episode"} else "unknown",
            "reason": str(item.get("reason", "unresolved")),
        }
        for item in unresolved
    ]
    warnings: list[str] = []
    if unresolved_safe:
        warnings.append(f"{len(unresolved_safe)} Jellyfin item(s) need review and were excluded from recommendations.")
    if shortfall > 0:
        warnings.append("Safe candidates cannot currently restore the configured free-space target.")

    generated = _iso(evaluated_at)
    preview_material = {
        "generatedAt": generated,
        "policy": policy,
        "storage": {"total": total, "used": used, "free": free},
        "candidateIds": [item["id"] for item in eligible],
        "unresolvedIds": [item["id"] for item in unresolved_safe],
    }
    preview_id = "sgp_" + hashlib.sha256(
        json.dumps(preview_material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]

    return {
        "schemaVersion": SCHEMA_VERSION,
        "previewId": preview_id,
        "generatedAt": generated,
        "status": "degraded" if unresolved_safe else "complete",
        "storage": {
            "totalBytes": total,
            "usedBytes": used,
            "freeBytes": free,
            "targetFreeBytes": target,
            "requiredReclaimBytes": required,
            "eligibleBytes": eligible_bytes,
            "recommendedBytes": recommended_bytes,
            "projectedFreeBytes": projected,
            "remainingShortfallBytes": shortfall,
        },
        "summary": {
            "scannedFiles": len(files) + len(unresolved_safe),
            "eligibleFiles": len(eligible),
            "recommendedFiles": recommended_files,
            "protectedFiles": len(blocked_entries),
            "unresolvedFiles": len(unresolved_safe),
        },
        "candidates": eligible,
        "blocked": _aggregate_blocked(blocked_entries),
        "unresolved": unresolved_safe,
        "warnings": warnings,
    }
