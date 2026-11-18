"""Read-only migration preflight and deterministic dry-run manifest.

This module is intentionally a small boundary around the accepted Phase 2-7
contracts.  It reads an explicit fixture/inventory, measures the two requested
filesystem paths, hashes only named files, and emits a stable preview.  It
does not discover every file under staging, call a service, move a path, delete
anything, restart Docker/systemd, or enable a staged feature.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .disk_guard import (
    CapacitySnapshot,
    DEFAULT_LIBRARY_RESERVE_GIB,
    DEFAULT_RESUME_MARGIN_GIB,
    DEFAULT_STAGING_RESERVE_GIB,
    DiskGuard,
    DiskGuardConfig,
    DiskIdentityError,
    FilesystemIdentity,
    GuardItem,
    GIB,
    measure_filesystem,
)
from .queue import classify_queue
from .dotenv import write_atomic


SCHEMA_VERSION = 1
_HASH = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_SECRET_FIELD = re.compile(
    r"(?:password|secret|token|api[_-]?key|credential|cookie|private[_-]?key|oauth)",
    re.IGNORECASE,
)
_TEMP_SUFFIXES = (
    ".part",
    ".partial",
    ".tmp",
    ".crdownload",
    ".!qb",
    ".lumen-tmp",
)
_TEMP_PREFIXES = (".lumen-migration-", ".lumen-copy-", ".incomplete-")


def _absolute(value: Any, field: str) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ValueError(f"{field} is required")
    path = Path(value)
    if not path.is_absolute() or path == Path("/"):
        raise ValueError(f"{field} must be an absolute non-root path")
    if "\x00" in str(path):
        raise ValueError(f"{field} is invalid")
    return Path(os.path.abspath(os.fspath(path)))


def _reject_symlink_components(path: Path, field: str) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ValueError(f"{field} could not be inspected") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"{field} must not contain symlink components")


def _is_temp(path: Path | str) -> bool:
    name = Path(path).name.casefold()
    return name.startswith(tuple(prefix.casefold() for prefix in _TEMP_PREFIXES)) or name.endswith(
        tuple(suffix.casefold() for suffix in _TEMP_SUFFIXES)
    )


def _safe_hash(value: Any) -> str | None:
    if isinstance(value, str) and _HASH.fullmatch(value.strip()):
        return value.strip().lower()
    return None


def _json_value(value: Any) -> Any:
    """Return JSON-safe values while rejecting non-deterministic objects."""

    if isinstance(value, Mapping):
        return {
            str(key): "<redacted>"
            if _SECRET_FIELD.search(str(key))
            else _json_value(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _fingerprint(path: Path) -> dict[str, Any]:
    """Hash one named regular file and re-stat it to establish stability."""

    result: dict[str, Any] = {
        "path": str(path),
        "exists": False,
        "stable": False,
        "size": None,
        "mtime_ns": None,
        "device": None,
        "inode": None,
        "hardlink_count": None,
        "sha256": None,
        "error": None,
    }
    if _is_temp(path):
        result["error"] = "temporary_name_excluded"
        return result
    try:
        before = os.lstat(path)
    except OSError as exc:
        result["error"] = "missing"
        return result
    result.update(
        {
            "exists": True,
            "size": int(before.st_size),
            "mtime_ns": int(before.st_mtime_ns),
            "device": int(before.st_dev),
            "inode": int(before.st_ino),
            "hardlink_count": int(before.st_nlink),
        }
    )
    if not os.path.isfile(path) or os.path.islink(path):
        result["error"] = "not_regular_file"
        return result
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        after = os.lstat(path)
    except OSError:
        result["error"] = "read_failed"
        return result
    stable = (
        before.st_size,
        before.st_mtime_ns,
        before.st_dev,
        before.st_ino,
    ) == (
        after.st_size,
        after.st_mtime_ns,
        after.st_dev,
        after.st_ino,
    )
    result["sha256"] = digest.hexdigest()
    result["stable"] = stable
    if not stable:
        result["error"] = "changed_during_hash"
    return result


def _identity_report(identity: FilesystemIdentity | None, error: str | None) -> dict[str, Any]:
    if identity is None:
        return {"status": "blocked", "error": error or "unavailable", "available_bytes": None}
    return {
        "status": "healthy",
        "path": str(identity.path),
        "device": identity.device,
        "mount_target": str(identity.mount_target),
        "source": identity.source,
        "uuid": identity.uuid,
        "filesystem": identity.filesystem,
        "readonly": identity.readonly,
        "available_bytes": identity.available_bytes,
    }


def _path_in(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class MigrationFile:
    """One explicit library candidate and its source reference."""

    source: Path
    destination: Path
    identifier: str
    selected: bool
    registered: bool
    verified_cleanup: bool
    torrent: Mapping[str, Any]
    arr: Mapping[str, Any]
    queue: Mapping[str, Any]
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class DryRunResult:
    status: str
    blockers: tuple[str, ...]
    manifest: Mapping[str, Any]
    manifest_path: Path | None = None

    @property
    def exit_code(self) -> int:
        return 0 if self.status == "ready" else 4

    @property
    def report(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "dry_run": True,
            "exit_code": self.exit_code,
            "blockers": list(self.blockers),
            "manifest_path": str(self.manifest_path) if self.manifest_path else None,
            "counts": self.manifest.get("counts", {}),
            "mutation": self.manifest.get("mutation", {}),
            "storage": self.manifest.get("storage", {}),
        }


def _parse_files(payload: Mapping[str, Any]) -> tuple[MigrationFile, ...]:
    rows = payload.get("files", payload.get("candidates", ()))
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ValueError("fixture files must be a list")
    parsed: list[MigrationFile] = []
    identifiers: set[str] = set()
    sources: set[Path] = set()
    destinations: set[Path] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"fixture file {index + 1} is invalid")
        source = _absolute(row.get("source"), f"file {index + 1} source")
        destination = _absolute(row.get("destination"), f"file {index + 1} destination")
        identifier = str(row.get("id", row.get("identifier", source))).strip()
        if not identifier:
            raise ValueError(f"fixture file {index + 1} identifier is empty")
        if identifier in identifiers:
            raise ValueError(f"fixture file {index + 1} identifier is duplicated")
        if source in sources:
            raise ValueError(f"fixture file {index + 1} source is duplicated")
        if destination in destinations:
            raise ValueError(f"fixture file {index + 1} destination is duplicated")
        identifiers.add(identifier)
        sources.add(source)
        destinations.add(destination)
        torrent = row.get("torrent") if isinstance(row.get("torrent"), Mapping) else {}
        arr = row.get("arr") if isinstance(row.get("arr"), Mapping) else {}
        queue = row.get("queue") if isinstance(row.get("queue"), Mapping) else {}
        metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
        parsed.append(
            MigrationFile(
                source=source,
                destination=destination,
                identifier=identifier,
                selected=row.get("selected") is True,
                registered=row.get("registered", torrent.get("registered")) is True,
                verified_cleanup=row.get("verified_cleanup", row.get("verified", False)) is True,
                torrent=torrent,
                arr=arr,
                queue=queue,
                metadata=metadata,
            )
        )
    return tuple(sorted(parsed, key=lambda item: (str(item.destination), str(item.source), item.identifier)))


def _measure(
    path: Path,
    *,
    expected_uuid: str | None,
    mount_probe: Callable[[Path], Mapping[str, Any]] | None,
    statvfs_probe: Callable[[Path], Any] | None,
) -> tuple[FilesystemIdentity | None, str | None]:
    try:
        return (
            measure_filesystem(
                path,
                expected_uuid=expected_uuid,
                mount_probe=mount_probe,
                statvfs_probe=statvfs_probe,
            ),
            None,
        )
    except (DiskIdentityError, OSError, ValueError, TypeError) as exc:
        return None, str(exc) or "identity check failed"


def _file_preview(item: MigrationFile, source_root: Path, library_root: Path) -> dict[str, Any]:
    source = _fingerprint(item.source)
    destination = _fingerprint(item.destination)
    # Fixture metadata can inject device identity and shared-extent evidence
    # without pretending a test directory is a second filesystem.  Production
    # dry runs use the observed stat values above.
    if isinstance(item.metadata.get("source_device"), int):
        source["device"] = item.metadata["source_device"]
    if isinstance(item.metadata.get("destination_device"), int):
        destination["device"] = item.metadata["destination_device"]
    source_hash = source.get("sha256")
    destination_hash = destination.get("sha256")
    source_in_scope = _path_in(
        item.source.resolve(strict=False), source_root.resolve(strict=False)
    )
    destination_in_scope = _path_in(
        item.destination.resolve(strict=False), library_root.resolve(strict=False)
    )
    reasons: list[str] = []
    if _is_temp(item.source) or _is_temp(item.destination):
        reasons.append("temporary_name_excluded")
    if not source_in_scope:
        reasons.append("source_outside_staging")
    if not destination_in_scope:
        reasons.append("destination_outside_library")
    if not item.selected:
        reasons.append("file_not_selected")
    if not item.registered:
        reasons.append("orphan_or_unregistered_staging")
    if not item.arr or item.arr.get("service") not in {"sonarr", "radarr"}:
        reasons.append("missing_or_ambiguous_arr_reference")
    if not source["exists"]:
        reasons.append("source_missing")
    if source["exists"] and not source["stable"]:
        reasons.append(str(source.get("error") or "source_unstable"))
    if destination["exists"] and not destination["stable"]:
        reasons.append(str(destination.get("error") or "destination_unstable"))
    if destination["exists"] and source_hash and destination_hash and source_hash != destination_hash:
        reasons.append("destination_collision")
    if destination["exists"] and source_hash == destination_hash and source_hash:
        transition = "reuse_verified_destination"
    elif destination["exists"]:
        transition = "preserve_conflict"
    else:
        transition = "copy_verify_commit_then_delete"
    source_device = source.get("device")
    destination_device = destination.get("device")
    same_inode = bool(
        source["exists"]
        and destination["exists"]
        and source_device == destination_device
        and source.get("inode") == destination.get("inode")
    )
    cross_filesystem = bool(
        source_device is not None
        and destination_device is not None
        and source_device != destination_device
    )
    hardlink_possible = bool(
        source_device is not None
        and destination_device is not None
        and source_device == destination_device
    )
    if cross_filesystem:
        semantics = "copy_verify;cross_filesystem_hardlink_impossible"
    elif hardlink_possible:
        semantics = "same_filesystem_hardlink_or_copy_after_verification"
    else:
        semantics = "copy_verify;filesystem_identity_unknown"
    if same_inode:
        semantics = "existing_shared_inode_reuse"
    if item.verified_cleanup is not True:
        reasons.append("cleanup_not_verified")
    preservation = sorted(set(reasons))
    eligible = not preservation and transition in {"copy_verify_commit_then_delete", "reuse_verified_destination"}
    if not eligible and "destination_collision" in preservation:
        transition = "preserve_conflict"
    size = source.get("size") if isinstance(source.get("size"), int) else 0
    if eligible and transition == "copy_verify_commit_then_delete":
        transitions = {
            "copy": "planned_after_freeze",
            "verify": "planned_full_hash_and_stability",
            "commit": "planned_atomic_destination_rename",
            "delete_source": "blocked_until_verified_cleanup_revalidation",
        }
    elif eligible and transition == "reuse_verified_destination":
        transitions = {
            "copy": "reuse_existing_destination",
            "verify": "planned_full_hash_and_stability",
            "commit": "no_destination_write",
            "delete_source": "blocked_until_verified_cleanup_revalidation",
        }
    else:
        transitions = {
            "copy": "preserved",
            "verify": "preserved",
            "commit": "preserved",
            "delete_source": "never",
        }
    return {
        "id": item.identifier,
        "source": str(item.source),
        "destination": str(item.destination),
        "source_observation": source,
        "destination_observation": destination,
        "selected": item.selected,
        "registered_torrent": item.registered,
        "torrent": _json_value(item.torrent),
        "arr": _json_value(item.arr),
        "transition": transition if eligible else "preserve",
        "transitions": transitions,
        "copy_bytes": size if eligible and transition == "copy_verify_commit_then_delete" else 0,
        "hardlink": {
            "same_inode": same_inode,
            "possible": hardlink_possible,
            "claimed": False if cross_filesystem else same_inode,
            "cross_filesystem": cross_filesystem,
        },
        "shared_extent": {
            "status": item.metadata.get("shared_extent_status", "unknown"),
            "group": item.metadata.get("shared_extent_group"),
            "accounting": "logical_bytes_conservative",
        },
        "preservation_reasons": preservation,
        "would_move": False,
        "would_delete_source": False,
    }


def _contract_report(payload: Mapping[str, Any], files: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    queue_rows = payload.get("queue", ())
    if not isinstance(queue_rows, Sequence) or isinstance(queue_rows, (str, bytes, bytearray)):
        queue_rows = ()
    queue_preview = classify_queue(queue_rows)
    for candidate in queue_preview.candidates:
        if candidate.action in {"preserve_review", "paused"}:
            blockers.append(f"queue:{candidate.identifier}:{candidate.reason}")
    retention = payload.get("retention")
    if not isinstance(retention, Mapping):
        retention = {"status": "blocked", "reason": "incomplete_history"}
    retention_status = str(retention.get("status", "blocked"))
    if retention_status not in {"disabled", "preview"}:
        blockers.append(f"retention:{retention.get('reason', 'unverified')}")
    services = payload.get("services")
    if not isinstance(services, Mapping):
        services = {}
    if str(services.get("radarr_api", "unknown")).casefold() not in {"healthy", "disabled"}:
        blockers.append("radarr_api_degraded")
    if str(services.get("trakt_oauth", "missing")).casefold() not in {"healthy", "disabled"}:
        blockers.append("trakt_oauth_missing")
    if services.get("history_complete") is not True:
        blockers.append("incomplete_history")
    flags = payload.get("flags")
    if not isinstance(flags, Mapping):
        flags = {}
    disabled_defaults = {
        name: flags.get(name, False) is not True
        for name in ("verified_cleanup_enabled", "disk_guard_enabled", "retention_enabled")
    }
    if not all(disabled_defaults.values()):
        blockers.append("destructive_or_guard_flag_enabled_in_dry_run")
    return (
        {
            "queue": queue_preview.report,
            "verified_cleanup": {
                "enabled": flags.get("verified_cleanup_enabled", False) is True,
                "mutation": False,
                "restart_recovery": "preserve_unverified_intent",
                "failure_recovery": "preserve_ambiguous_delete",
            },
            "disk_guard": {
                "enabled": flags.get("disk_guard_enabled", False) is True,
                "mutation": False,
                "failure_recovery": "pause_and_stop_writer_on_guard_failure",
            },
            "retention": {
                "enabled": flags.get("retention_enabled", False) is True,
                "status": retention_status,
                "preview": _json_value(retention),
                "restart_recovery": "preserve_pending_unmonitor_intent",
            },
            "storage_mount": _json_value(payload.get("storage_mount", {"status": "injected-or-local"})),
            "status_view": _json_value(payload.get("status_view", {"read_only": True})),
            "quality": _json_value(payload.get("quality", {"status": "preview-only"})),
        },
        blockers,
    )


def run_dry_run(
    payload: Mapping[str, Any],
    *,
    source_path: Path | str | None = None,
    library_path: Path | str | None = None,
    library_uuid: str | None = None,
    mount_probe: Callable[[Path], Mapping[str, Any]] | None = None,
    statvfs_probe: Callable[[Path], Any] | None = None,
    manifest_path: Path | str | None = None,
) -> DryRunResult:
    """Build a deterministic read-only preflight and optionally write it."""

    if not isinstance(payload, Mapping):
        raise ValueError("migration fixture must be an object")
    storage = payload.get("storage") if isinstance(payload.get("storage"), Mapping) else {}
    staging = _absolute(source_path or storage.get("staging_path"), "staging_path")
    library = _absolute(library_path or storage.get("library_path"), "library_path")
    configured_uuid_value = library_uuid or storage.get("library_uuid")
    if not isinstance(configured_uuid_value, str) or not configured_uuid_value.strip():
        raise ValueError("library_uuid is required")
    configured_uuid = configured_uuid_value.strip()
    staging_identity, staging_error = _measure(
        staging, expected_uuid=None, mount_probe=mount_probe, statvfs_probe=statvfs_probe
    )
    library_identity, library_error = _measure(
        library, expected_uuid=configured_uuid, mount_probe=mount_probe, statvfs_probe=statvfs_probe
    )
    blockers: list[str] = []
    if staging_identity is None:
        blockers.append(f"staging_identity:{staging_error or 'unavailable'}")
    if library_identity is None:
        blockers.append(f"library_identity:{library_error or 'unavailable'}")
    files = _parse_files(payload)
    previews = [_file_preview(item, staging, library) for item in files if not _is_temp(item.source) and not _is_temp(item.destination)]
    excluded_count = len(files) - len(previews)
    for item in previews:
        blockers.extend(f"file:{item['id']}:{reason}" for reason in item["preservation_reasons"])
    orphan_paths = payload.get("orphan_staging_paths", ())
    if not isinstance(orphan_paths, Sequence) or isinstance(orphan_paths, (str, bytes, bytearray)):
        orphan_paths = ()
    orphans = sorted(
        str(_absolute(path, "orphan_staging_path"))
        for path in orphan_paths
        if not _is_temp(path)
    )
    if payload.get("inventory_complete") is not True:
        blockers.append("unknown_library_inventory")
    contracts, contract_blockers = _contract_report(payload, previews)
    blockers.extend(contract_blockers)
    guard_config = DiskGuardConfig(
        staging_path=staging,
        library_path=library,
        library_uuid=configured_uuid,
        staging_reserve_bytes=DEFAULT_STAGING_RESERVE_GIB * GIB,
        library_reserve_bytes=DEFAULT_LIBRARY_RESERVE_GIB * GIB,
        resume_margin_bytes=DEFAULT_RESUME_MARGIN_GIB * GIB,
        enabled=False,
    )
    guard = DiskGuard(guard_config, measure=lambda path, **kwargs: staging_identity if path == staging else library_identity)
    guard_items = [
        GuardItem(
            item["id"],
            staging_bytes=int(item.get("source_observation", {}).get("size") or 0),
            destination_bytes=int(item.get("copy_bytes") or 0),
            guard_paused="unaffordable_capacity" in item["preservation_reasons"],
        )
        for item in previews
    ]
    storage_reason = ""
    if (
        staging_identity is not None
        and library_identity is not None
        and staging_identity.device == library_identity.device
        and staging_identity.source == library_identity.source
    ):
        storage_reason = "storage_not_separate"
    plan = guard.plan(
        guard_items,
        CapacitySnapshot(staging_identity, library_identity, storage_reason),
    )
    admitted = {item.identifier for item in plan.admitted}
    for item in previews:
        if item["id"] not in admitted and not item["preservation_reasons"]:
            item["preservation_reasons"].append("unaffordable_capacity")
            item["transition"] = "preserve"
            item["copy_bytes"] = 0
            item["transitions"] = {
                "copy": "preserved",
                "verify": "preserved",
                "commit": "preserved",
                "delete_source": "never",
            }
            blockers.append(f"file:{item['id']}:unaffordable_capacity")
    capacity = {
        "staging_available_bytes": staging_identity.available_bytes if staging_identity else None,
        "library_available_bytes": library_identity.available_bytes if library_identity else None,
        "staging_reserve_bytes": guard_config.staging_reserve_bytes,
        "library_reserve_bytes": guard_config.library_reserve_bytes,
        "resume_margin_bytes": guard_config.resume_margin_bytes,
        "resume_floor": {
            "staging_bytes": guard_config.staging_reserve_bytes + guard_config.resume_margin_bytes,
            "library_bytes": guard_config.library_reserve_bytes + guard_config.resume_margin_bytes,
        },
        "pending_copy_bytes": sum(int(item.get("copy_bytes") or 0) for item in previews),
        "guard_admitted": sorted(admitted),
        "guard_paused": sorted(item.identifier for item in plan.guard_paused),
        "guard_reason": plan.reason,
    }
    unique_blockers = tuple(sorted(set(str(item) for item in blockers if str(item))))
    mutation = {
        "performed": False,
        "moves": 0,
        "deletes": 0,
        "api_writes": 0,
        "docker_restarts": 0,
        "systemd_changes": 0,
        "temp_names_scanned": False,
    }
    counts = {
        "files": len(previews),
        "temporary_files_excluded": excluded_count,
        "registered_torrents": sum(1 for item in previews if item["registered_torrent"]),
        "orphan_staging_paths": len(orphans),
        "copy_candidates": sum(1 for item in previews if item["transition"] == "copy_verify_commit_then_delete"),
        "conflicts": sum(1 for item in previews if "destination_collision" in item["preservation_reasons"]),
        "preserved": sum(1 for item in previews if item["transition"] == "preserve"),
    }
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "mode": "migration-dry-run",
        "storage": {
            "staging": _identity_report(staging_identity, staging_error),
            "library": _identity_report(library_identity, library_error),
            "semantics": "cross-filesystem-copy-and-verify;hardlinks-never-claimed-across-disks",
            "capacity": capacity,
        },
        "inventory": {
            "scope": "named permanent-library candidates only",
            "staging_recursive_scan": False,
            "registered_torrent_paths": sorted(
                item["source"] for item in previews if item["registered_torrent"]
            ),
            "orphan_staging_paths": orphans,
            "temporary_names_excluded": True,
        },
        "files": previews,
        "contracts": contracts,
        "counts": counts,
        "blockers": list(unique_blockers),
        "preservation_reasons": sorted(
            {
                reason
                for item in previews
                for reason in item["preservation_reasons"]
            }
        ),
        "mutation": mutation,
    }
    output = json.dumps(_json_value(manifest), sort_keys=True, indent=2) + "\n"
    output_path = None
    if manifest_path is not None:
        output_path = _absolute(manifest_path, "manifest_path")
        _reject_symlink_components(output_path, "manifest_path")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _reject_symlink_components(output_path, "manifest_path")
        write_atomic(output_path, output)
    return DryRunResult(
        status="ready" if not unique_blockers else "blocked",
        blockers=unique_blockers,
        manifest=manifest,
        manifest_path=output_path,
    )


def _load(path: Path) -> Mapping[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("migration fixture could not be read") from exc
    if not isinstance(data, Mapping):
        raise ValueError("migration fixture must be an object")
    return data


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Lumen migration preflight")
    parser.add_argument("--fixture", type=Path, required=True, help="JSON inventory fixture")
    parser.add_argument("--staging-path", type=Path)
    parser.add_argument("--library-path", type=Path)
    parser.add_argument("--library-uuid")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true", help="required safety acknowledgement")
    args = parser.parse_args(argv)
    if not args.dry_run:
        parser.error("--dry-run is required; this module has no live mode")
    try:
        result = run_dry_run(
            _load(args.fixture),
            source_path=args.staging_path,
            library_path=args.library_path,
            library_uuid=args.library_uuid,
            manifest_path=args.manifest,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result.report, sort_keys=True))
    return result.exit_code


__all__ = [
    "DryRunResult",
    "MigrationFile",
    "SCHEMA_VERSION",
    "main",
    "run_dry_run",
]


if __name__ == "__main__":
    raise SystemExit(main())
