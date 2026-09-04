"""Small, filesystem-backed update and rollback helpers for the installer."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


PathLike = str | os.PathLike[str]
Callback = Callable[[], object]


_DIGEST_RE = re.compile(r"^sha256:([0-9a-fA-F]{64})$")
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _absolute_path(value: PathLike, base: Path | None = None) -> Path:
    raw = os.path.expanduser(os.fspath(value))
    if base is not None and not os.path.isabs(raw):
        raw = os.path.join(str(base), raw)
    return Path(os.path.abspath(raw))


def _resolved_path(value: PathLike, base: Path | None = None) -> Path:
    return _absolute_path(value, base).resolve(strict=False)


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _env_file_paths(env_path: Path) -> dict[str, str]:
    """Read only the two path settings needed for backup protection."""

    if not env_path.is_file() or env_path.is_symlink():
        return {}
    values: dict[str, str] = {}
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        name = name.strip()
        if name not in {"ROOT_PATH", "DOWNLOADS_PATH"}:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[name] = value
    return values


def _protected_paths(env_path: Path | None = None) -> tuple[Path, ...]:
    protected: list[Path] = []
    values = {
        variable: os.environ.get(variable, "")
        for variable in ("ROOT_PATH", "DOWNLOADS_PATH")
    }
    if env_path is not None:
        for variable, value in _env_file_paths(env_path).items():
            values.setdefault(variable, value)
            if not values[variable]:
                values[variable] = value
    for variable, value in values.items():
        if value:
            base = env_path.parent if env_path is not None else None
            protected.append(_resolved_path(value, base))
    return tuple(protected)


def _has_symlink_component(path: Path) -> bool:
    """Return whether an existing component of an absolute path is a symlink."""

    absolute = _absolute_path(path)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            return True
    return False


def _validate_root_path(root: Path) -> None:
    if _has_symlink_component(root):
        raise ValueError(f"checkout path may not contain symlinks: {root}")
    if not root.is_dir():
        raise ValueError(f"checkout path is not a directory: {root}")


def _validate_manifest_path(
    path: Path,
    checkout_root: Path,
    *,
    kind: str,
    protected: tuple[Path, ...],
) -> None:
    path = _absolute_path(path)
    checkout_root = _absolute_path(checkout_root)
    _validate_root_path(checkout_root)
    if _has_symlink_component(path):
        raise ValueError(f"manifest path may not contain symlinks: {path}")
    if not _is_within(path, checkout_root):
        raise ValueError(f"manifest path is outside the checkout: {path}")
    if any(_is_within(path.resolve(strict=False), protected) for protected in protected):
        raise ValueError(f"path is under a protected media directory: {path}")

    relative = path.relative_to(checkout_root)
    if kind == "env":
        approved = relative == Path(".env")
    elif kind == "runtime":
        approved = _is_within(path, checkout_root / "config") or _is_within(
            path, checkout_root / ".state" / "installer"
        )
    elif kind == "compose":
        approved = (
            len(relative.parts) == 1
            and relative.name.startswith("docker-compose")
            and relative.suffix in {".yml", ".yaml"}
        )
    else:
        raise ValueError(f"unknown manifest path kind: {kind}")
    if not approved:
        raise ValueError(f"manifest path is not an approved {kind} path: {path}")


def _validate_manifest_inputs(
    env_path: Path,
    runtime_paths: Mapping[str, Path],
    compose_files: Sequence[Path],
) -> Path:
    checkout_root = env_path.parent
    protected = _protected_paths(env_path)
    _validate_manifest_path(env_path, checkout_root, kind="env", protected=protected)
    for path in runtime_paths.values():
        _validate_manifest_path(path, checkout_root, kind="runtime", protected=protected)
    for path in compose_files:
        _validate_manifest_path(path, checkout_root, kind="compose", protected=protected)
    return checkout_root


def _normalize_repo_digest(value: str) -> str:
    """Return a validated Docker sha256 digest without its optional repo."""

    digest = str(value).strip()
    if "@" in digest:
        repository, digest = digest.split("@", 1)
        if not repository or "@" in repository or any(char.isspace() for char in repository):
            raise ValueError("repository digest has an invalid repository")
    match = _DIGEST_RE.fullmatch(digest)
    if match is None:
        raise ValueError("repository digest must be sha256 followed by 64 hex characters")
    return f"sha256:{match.group(1).lower()}"


def _digest_repository(value: str) -> str | None:
    value = str(value).strip()
    if "@" not in value:
        return None
    repository, _ = value.split("@", 1)
    return repository


def _validate_digest_entries(
    image_refs: Mapping[str, str],
    repo_digests: Mapping[str, str],
    local_image_ids: Mapping[str, str],
    *,
    require_registry: bool = True,
) -> dict[str, str]:
    raw_digests = {str(name): str(digest) for name, digest in repo_digests.items()}
    normalized = {
        name: _normalize_repo_digest(digest) for name, digest in raw_digests.items()
    }
    local_services = {str(name) for name in local_image_ids}
    if require_registry:
        for service in image_refs:
            service_name = str(service)
            if service_name not in local_services and service_name not in normalized:
                raise ValueError(
                    f"missing immutable registry digest for service: {service_name}"
                )
    for service in normalized:
        if service not in image_refs and service not in local_services:
            raise ValueError(f"digest has no matching image service: {service}")
    for service in image_refs:
        service_name = str(service)
        if service_name in normalized and service_name in raw_digests:
            repository = _digest_repository(raw_digests[service_name])
            if repository is not None and _repository_name(str(image_refs[service])) != repository:
                raise ValueError(f"digest repository does not match image service: {service_name}")
    return normalized


def _require_immutable_digests(manifest: "UpdateManifest") -> None:
    _validate_digest_entries(
        manifest.image_refs,
        manifest.repo_digests,
        manifest.local_image_ids,
        require_registry=True,
    )


@dataclass(frozen=True)
class UpdateManifest:
    env_path: str
    runtime_paths: dict[str, str]
    image_refs: dict[str, str]
    repo_digests: dict[str, str]
    local_image_ids: dict[str, str]
    profiles: list[str]
    gpu_mode: bool
    compose_files: list[str]

    @classmethod
    def from_inputs(
        cls,
        env_path: PathLike,
        runtime_paths: Mapping[str, PathLike],
        image_refs: Mapping[str, str],
        repo_digests: Mapping[str, str],
        local_image_ids: Mapping[str, str],
        profiles: Sequence[str],
        gpu_mode: bool,
        compose_files: Iterable[PathLike],
    ) -> "UpdateManifest":
        normalized_env = _absolute_path(env_path)
        normalized_runtime = {
            str(name): str(_absolute_path(path)) for name, path in runtime_paths.items()
        }
        normalized_compose = [str(_absolute_path(path)) for path in compose_files]
        _validate_manifest_inputs(
            normalized_env,
            {name: Path(path) for name, path in normalized_runtime.items()},
            [Path(path) for path in normalized_compose],
        )
        normalized_refs = {str(name): str(ref).strip() for name, ref in image_refs.items()}
        normalized_local_ids = {
            str(name): str(image_id) for name, image_id in local_image_ids.items()
        }

        return cls(
            env_path=str(normalized_env),
            runtime_paths=normalized_runtime,
            image_refs=normalized_refs,
            repo_digests=_validate_digest_entries(
                normalized_refs,
                repo_digests,
                normalized_local_ids,
                require_registry=False,
            ),
            local_image_ids=normalized_local_ids,
            profiles=[str(profile) for profile in profiles],
            gpu_mode=bool(gpu_mode),
            compose_files=normalized_compose,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "UpdateManifest":
        # Update records are persisted locally and must not be trusted
        # blindly during rollback.  Re-normalize paths and apply the same
        # media/download protection as fresh input.
        env_path = _absolute_path(str(value["env_path"]))
        runtime_paths = {
            str(k): str(_absolute_path(str(v)))
            for k, v in dict(value["runtime_paths"]).items()
        }
        compose_files = [
            str(_absolute_path(str(path))) for path in list(value["compose_files"])
        ]
        _validate_manifest_inputs(
            env_path,
            {name: Path(path) for name, path in runtime_paths.items()},
            [Path(path) for path in compose_files],
        )
        image_refs = {str(k): str(v).strip() for k, v in dict(value["image_refs"]).items()}
        local_image_ids = {
            str(k): str(v) for k, v in dict(value["local_image_ids"]).items()
        }
        return cls(
            env_path=str(env_path),
            runtime_paths=runtime_paths,
            image_refs=image_refs,
            repo_digests=_validate_digest_entries(
                image_refs,
                dict(value["repo_digests"]),
                local_image_ids,
                require_registry=False,
            ),
            local_image_ids=local_image_ids,
            profiles=[str(profile) for profile in list(value["profiles"])],
            gpu_mode=bool(value["gpu_mode"]),
            compose_files=compose_files,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "env_path": self.env_path,
            "runtime_paths": dict(self.runtime_paths),
            "image_refs": dict(self.image_refs),
            "repo_digests": dict(self.repo_digests),
            "local_image_ids": dict(self.local_image_ids),
            "profiles": list(self.profiles),
            "gpu_mode": self.gpu_mode,
            "compose_files": list(self.compose_files),
        }


def _manifest_paths(manifest: UpdateManifest) -> list[Path]:
    env_path = _absolute_path(manifest.env_path)
    runtime_paths = {
        str(name): _absolute_path(path)
        for name, path in manifest.runtime_paths.items()
    }
    compose_files = [_absolute_path(path) for path in manifest.compose_files]
    _validate_manifest_inputs(env_path, runtime_paths, compose_files)
    candidates = [env_path]
    candidates.extend(runtime_paths.values())
    candidates.extend(compose_files)

    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)

    # A parent contains all of its children, so backing up or moving the
    # parent is sufficient and avoids duplicate/conflicting operations.
    unique.sort(key=lambda path: len(path.parts))
    result: list[Path] = []
    for candidate in unique:
        if not any(_is_within(candidate, parent) for parent in result):
            result.append(candidate)
    return result


def _state_dir(root: Path) -> Path:
    return root / ".state" / "installer"


def _ensure_private_dir(path: Path) -> None:
    """Create one installer-owned directory and force mode 0700.

    ``mkdir(mode=...)`` is still filtered by the process umask, and an
    existing directory keeps its old mode, so both creation and hardening
    are explicit.  Callers establish each state-directory component before
    creating children; this also lets us reject a symlinked state boundary.
    """

    if path.is_symlink():
        raise ValueError(f"installer state directory may not be a symlink: {path}")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError(f"installer state path is not a directory: {path}")
    path.chmod(0o700)


def _harden_tree(path: Path) -> None:
    """Force private permissions throughout a copied state tree."""

    if path.is_symlink():
        return
    if path.is_dir():
        path.chmod(0o700)
        for child in path.iterdir():
            _harden_tree(child)
        return
    if path.exists():
        path.chmod(0o600)


def _safe_run_id(run_id: str) -> str:
    if not run_id or not _SAFE_RUN_ID_RE.fullmatch(run_id):
        raise ValueError("invalid run id")
    return run_id


def _run_id() -> str:
    return uuid.uuid4().hex


def _backup_name(root: Path, path: Path) -> Path:
    try:
        relative = path.relative_to(root)
        return relative if relative != Path(".") else Path("__root__")
    except ValueError:
        digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
        return Path("__external__") / digest / path.name


def _copy_path(source: Path, destination: Path, *, private_destination: bool = True) -> None:
    if private_destination:
        _ensure_private_dir(destination.parent)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir() and not source.is_symlink():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination, follow_symlinks=False)
    if private_destination:
        _harden_tree(destination)


def _move_path(source: Path, destination: Path) -> None:
    _ensure_private_dir(destination.parent)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    shutil.move(str(source), str(destination))
    _harden_tree(destination)


def _remove_path(path: Path) -> None:
    """Remove one approved rollback target without following symlinks."""

    if path.is_symlink() or not path.exists():
        if path.is_symlink():
            path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    _ensure_private_dir(path.parent)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _write_private_text(path: Path, value: str) -> None:
    _ensure_private_dir(path.parent)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _repository_name(image_ref: str) -> str:
    image_ref = image_ref.split("@", 1)[0]
    slash = image_ref.rfind("/")
    colon = image_ref.rfind(":")
    if colon > slash:
        return image_ref[:colon]
    return image_ref


def _registry_image(service: str, manifest: UpdateManifest) -> str:
    reference = manifest.image_refs.get(service, service)
    digest = manifest.repo_digests.get(service, "")
    if not digest:
        raise ValueError(f"missing immutable registry digest for service: {service}")
    return f"{_repository_name(reference)}@{_normalize_repo_digest(digest)}"


def render_rollback_override(
    manifest: UpdateManifest,
    run_id: str,
    local_services: Iterable[str],
) -> str:
    _safe_run_id(run_id)
    local = {str(service) for service in local_services}
    local_ids = dict(manifest.local_image_ids)
    local_ids.update({service: "rollback-local" for service in local})
    _validate_digest_entries(manifest.image_refs, manifest.repo_digests, local_ids)
    services = list(
        dict.fromkeys(
            (
                *manifest.image_refs.keys(),
                *manifest.repo_digests.keys(),
                *manifest.local_image_ids.keys(),
            )
        )
    )

    lines = ["services:"]
    for service in services:
        image = (
            f"lumen-rollback/{service}:{run_id}"
            if service in local
            else _registry_image(service, manifest)
        )
        lines.extend(
            [
                f"  {service}:",
                f"    image: {image}",
                "    pull_policy: never",
                "    build: !reset null",
            ]
        )
    return "\n".join(lines) + "\n"


def run_update(
    root: PathLike,
    manifest: UpdateManifest,
    dry_run: bool,
    confirm: bool,
    pull_callback: Callback | None = None,
    recreate_callback: Callback | None = None,
) -> dict[str, object]:
    run_id = _run_id()
    result: dict[str, object] = {
        "run_id": run_id,
        "dry_run": bool(dry_run),
        "manifest": manifest.to_dict(),
    }
    if dry_run:
        return result
    if not confirm:
        raise PermissionError("update requires confirmation")
    _require_immutable_digests(manifest)

    root_path = _absolute_path(root)
    _validate_root_path(root_path)
    manifest_paths = _manifest_paths(manifest)
    state = _state_dir(root_path)
    _ensure_private_dir(state.parent)
    _ensure_private_dir(state)
    _ensure_private_dir(state / "backups")
    _ensure_private_dir(state / "updates")
    backup_dir = state / "backups" / run_id
    update_record = state / "updates" / f"{run_id}.json"
    _ensure_private_dir(backup_dir)

    for path in manifest_paths:
        if path.exists() or path.is_symlink():
            _copy_path(path, backup_dir / _backup_name(root_path, path))

    _write_json(
        update_record,
        {
            "run_id": run_id,
            "manifest": manifest.to_dict(),
        },
    )
    result["record"] = str(update_record)
    result["backup"] = str(backup_dir)

    if pull_callback is not None:
        pull_callback()
    if recreate_callback is not None:
        recreate_callback()
    return result


def run_rollback(
    root: PathLike,
    run_id: str,
    confirm: bool,
    stop_callback: Callback | None = None,
    start_callback: Callback | None = None,
) -> dict[str, object]:
    if not confirm:
        raise PermissionError("rollback requires confirmation")

    safe_run_id = _safe_run_id(run_id)
    root_path = _absolute_path(root)
    _validate_root_path(root_path)
    state = _state_dir(root_path)
    record_path = state / "updates" / f"{safe_run_id}.json"

    # Inspect the state boundary before reading a record.  A symlink here
    # could redirect a rollback read (and later writes) outside the checkout.
    for directory in (state.parent, state, state / "updates"):
        if directory.is_symlink():
            raise ValueError(f"installer state directory may not be a symlink: {directory}")
        if directory.exists() and not directory.is_dir():
            raise ValueError(f"installer state path is not a directory: {directory}")
    if record_path.is_symlink():
        raise ValueError(f"installer update record may not be a symlink: {record_path}")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    manifest = UpdateManifest.from_dict(record["manifest"])
    manifest_paths = _manifest_paths(manifest)

    _ensure_private_dir(state.parent)
    _ensure_private_dir(state)
    _ensure_private_dir(state / "updates")
    if record_path.exists():
        record_path.chmod(0o600)
    _ensure_private_dir(state / "backups")
    _ensure_private_dir(state / "failed-runs")
    failed_dir = state / "failed-runs" / safe_run_id
    _ensure_private_dir(failed_dir)
    backup_dir = state / "backups" / safe_run_id
    if backup_dir.exists() or backup_dir.is_symlink():
        _ensure_private_dir(backup_dir)

    if stop_callback is not None:
        stop_callback()

    for path in manifest_paths:
        if path.exists() or path.is_symlink():
            failed_path = failed_dir / _backup_name(root_path, path)
            # A previous rollback may have moved this path successfully but
            # failed later (for example in a start callback).  Keep that
            # first post-update snapshot and make retry idempotent.
            if not failed_path.exists() and not failed_path.is_symlink():
                _move_path(path, failed_path)

    for path in manifest_paths:
        backup = backup_dir / _backup_name(root_path, path)
        if backup.exists() or backup.is_symlink():
            if path.exists() or path.is_symlink():
                _remove_path(path)
            _copy_path(backup, path, private_destination=False)

    override_path = state / "rollback" / f"{safe_run_id}.yml"
    local_services = set(manifest.local_image_ids)
    _write_private_text(
        override_path,
        render_rollback_override(manifest, safe_run_id, local_services),
    )

    if start_callback is not None:
        start_callback()
    return {
        "run_id": safe_run_id,
        "override": str(override_path),
    }
