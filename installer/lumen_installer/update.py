"""Small, filesystem-backed update and rollback helpers for the installer."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from .errors import ExitCode, InstallerError, InvalidInputError


PathLike = str | os.PathLike[str]
Callback = Callable[..., object]


_DIGEST_RE = re.compile(r"^sha256:([0-9a-fA-F]{64})$")
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class RollbackValidationError(InvalidInputError, ValueError):
    """A rollback record or state boundary cannot be trusted safely.

    ``ValueError`` remains a compatibility base for the filesystem helper's
    older callers, while the installer-domain base gives the CLI a stable
    exit code and prevents parser/key errors from escaping as tracebacks.
    """

    def __init__(self, message: str = "rollback record is invalid") -> None:
        InvalidInputError.__init__(self, message)


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
        _reject_recursive_backup_destination(path, checkout_root)
    for path in compose_files:
        _validate_manifest_path(path, checkout_root, kind="compose", protected=protected)
    return checkout_root


def _reject_recursive_backup_destination(path: Path, checkout_root: Path) -> None:
    """Keep a manifest source from containing its own update backup target."""

    installer_state = checkout_root / ".state" / "installer"
    backup_root = installer_state / "backups"
    if _is_within(path, backup_root) or _is_within(backup_root, path):
        raise ValueError(
            "manifest path would recursively contain the installer backup destination: "
            f"{path}"
        )


def _validate_manifest_checkout_root(root: Path, manifest: "UpdateManifest") -> None:
    manifest_root = _absolute_path(manifest.env_path).parent
    requested_root = _absolute_path(root)
    if requested_root != manifest_root:
        raise ValueError(
            "manifest checkout does not match the requested checkout: "
            f"{manifest_root} != {requested_root}"
        )


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
    gpu_mode: bool | str
    gpu_environment: dict[str, str]
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
        gpu_mode: bool | str,
        compose_files: Iterable[PathLike],
        gpu_environment: Mapping[str, str] | None = None,
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

        normalized_gpu: bool | str
        if type(gpu_mode) is bool:
            normalized_gpu = gpu_mode
        elif isinstance(gpu_mode, str) and gpu_mode.strip().lower() in {
            "none",
            "auto",
            "nvidia",
            "vaapi",
        }:
            normalized_gpu = gpu_mode.strip().lower()
        else:
            raise ValueError("gpu mode must be none, auto, nvidia, or vaapi")
        normalized_gpu_environment = {
            str(name): str(value).strip()
            for name, value in (gpu_environment or {}).items()
            if str(value).strip()
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
            gpu_mode=normalized_gpu,
            gpu_environment=normalized_gpu_environment,
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
            gpu_mode=value["gpu_mode"],
            gpu_environment={
                str(k): str(v)
                for k, v in dict(value.get("gpu_environment", {})).items()
            },
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
            "gpu_environment": dict(self.gpu_environment),
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


def _invoke_callback(callback: Callback, run_id: str) -> object:
    """Invoke an update lifecycle seam with either its legacy or rich shape.

    Earlier callers supplied zero-argument callbacks.  New lifecycle callers
    receive the generated run id so they can name immutable rollback tags.
    Signature inspection avoids catching a ``TypeError`` raised *inside* a
    callback and accidentally invoking a mutating operation twice.
    """

    try:
        parameters = tuple(inspect.signature(callback).parameters.values())
    except (TypeError, ValueError):
        return callback()
    positional = tuple(
        parameter
        for parameter in parameters
        if parameter.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    )
    accepts_varargs = any(
        parameter.kind is inspect.Parameter.VAR_POSITIONAL for parameter in parameters
    )
    if accepts_varargs or positional:
        return callback(run_id)
    return callback()


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


def _reject_symlink_tree(path: Path) -> None:
    """Reject a backup path if any root or descendant is a symlink."""

    if _has_symlink_component(path) or path.is_symlink():
        raise ValueError(f"rollback backup may not contain symlinks: {path}")
    if not path.is_dir():
        return
    for child in path.iterdir():
        _reject_symlink_tree(child)


def _atomic_copy_env(source: Path, destination: Path) -> None:
    """Replace ``.env`` atomically while enforcing its private mode."""

    if source.is_symlink() or _has_symlink_component(source) or not source.is_file():
        raise ValueError(f"rollback .env source is not a regular file: {source}")
    if _has_symlink_component(destination.parent):
        raise ValueError(
            f"rollback .env parent may not contain symlinks: {destination.parent}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as input_file:
            shutil.copyfileobj(input_file, output)
            output.flush()
            os.fsync(output.fileno())
            os.fchmod(output.fileno(), 0o600)
        os.replace(temporary, destination)
        destination.chmod(0o600)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


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
    tag_callback: Callback | None = None,
) -> dict[str, object]:
    run_id = _run_id()
    result: dict[str, object] = {
        "run_id": run_id,
        "dry_run": bool(dry_run),
        "manifest": manifest.to_dict(),
    }
    root_path = _absolute_path(root)
    _validate_root_path(root_path)
    _validate_manifest_checkout_root(root_path, manifest)
    _manifest_paths(manifest)
    if dry_run:
        return result
    if not confirm:
        raise PermissionError("update requires confirmation")
    _require_immutable_digests(manifest)

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

    try:
        if tag_callback is not None:
            tagged = _invoke_callback(tag_callback, run_id)
            if tagged is not None:
                record = json.loads(update_record.read_text(encoding="utf-8"))
                record["local_rollback_tags"] = tagged
                _write_json(update_record, record)
                result["local_rollback_tags"] = tagged
        if pull_callback is not None:
            _invoke_callback(pull_callback, run_id)
        if recreate_callback is not None:
            _invoke_callback(recreate_callback, run_id)
    except Exception:
        # The backup and manifest record are deliberately durable before any
        # Docker mutation.  Return a stable partial result while retaining
        # the run id so the user can invoke rollback after a failed pull,
        # rebuild, recreate, or health check.
        result.update(
            {
                "status": "failed",
                "exit_code": int(ExitCode.PARTIAL),
                "error": "stack update lifecycle failed; rollback remains available",
            }
        )
    return result


def run_rollback(
    root: PathLike,
    run_id: str,
    confirm: bool,
    stop_callback: Callback | None = None,
    start_callback: Callback | None = None,
    *,
    dry_run: bool = False,
    callback_factory: Callable[[UpdateManifest], tuple[Callback | None, Callback | None]]
    | None = None,
) -> dict[str, object]:
    if dry_run:
        return {"action": "rollback", "dry_run": True, "run_id": _safe_run_id(run_id)}
    if not confirm:
        raise PermissionError("rollback requires confirmation")

    safe_run_id = _safe_run_id(run_id)
    root_path = _absolute_path(root)
    try:
        _validate_root_path(root_path)
    except (OSError, ValueError) as exc:
        raise RollbackValidationError("rollback state boundary is invalid") from exc
    state = _state_dir(root_path)
    record_path = state / "updates" / f"{safe_run_id}.json"

    # Inspect the state boundary before reading a record.  A symlink here
    # could redirect a rollback read (and later writes) outside the checkout.
    try:
        for directory in (
            state.parent,
            state,
            state / "updates",
            state / "backups",
            state / "failed-runs",
            state / "rollback",
        ):
            if directory.is_symlink() or (
                directory.exists() and not directory.is_dir()
            ):
                raise RollbackValidationError("rollback state boundary is invalid")
        if record_path.is_symlink() or not record_path.is_file():
            raise RollbackValidationError("rollback record is invalid")
        record_value = json.loads(record_path.read_text(encoding="utf-8"))
        if not isinstance(record_value, Mapping):
            raise RollbackValidationError("rollback record is invalid")
        if record_value.get("run_id") != safe_run_id:
            raise RollbackValidationError("rollback record is invalid")
        raw_manifest = record_value.get("manifest")
        if not isinstance(raw_manifest, Mapping):
            raise RollbackValidationError("rollback record is invalid")
        manifest = UpdateManifest.from_dict(raw_manifest)
        _validate_manifest_checkout_root(root_path, manifest)
        manifest_paths = _manifest_paths(manifest)
    except RollbackValidationError:
        raise
    except (OSError, UnicodeError, TypeError, ValueError, KeyError, AttributeError) as exc:
        raise RollbackValidationError("rollback record is invalid") from exc

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

    try:
        for path in manifest_paths:
            backup = backup_dir / _backup_name(root_path, path)
            if backup.exists() or backup.is_symlink():
                _reject_symlink_tree(backup)
    except (OSError, ValueError) as exc:
        raise RollbackValidationError("rollback backup is invalid") from exc

    if callback_factory is not None:
        try:
            generated_stop, generated_start = callback_factory(manifest)
        except InstallerError:
            raise
        except Exception as exc:
            raise RollbackValidationError("rollback lifecycle setup failed") from exc
        stop_callback = generated_stop
        start_callback = generated_start

    if stop_callback is not None:
        _invoke_callback(stop_callback, safe_run_id)

    env_path = _absolute_path(manifest.env_path)
    for path in manifest_paths:
        if path.exists() or path.is_symlink():
            failed_path = failed_dir / _backup_name(root_path, path)
            # A previous rollback may have moved this path successfully but
            # failed later (for example in a start callback).  Keep that
            # first post-update snapshot and make retry idempotent.
            backup = backup_dir / _backup_name(root_path, path)
            if path == env_path and (backup.exists() or backup.is_symlink()):
                if not failed_path.exists() and not failed_path.is_symlink():
                    _copy_path(path, failed_path)
            elif not failed_path.exists() and not failed_path.is_symlink():
                _move_path(path, failed_path)

    for path in manifest_paths:
        backup = backup_dir / _backup_name(root_path, path)
        if backup.exists() or backup.is_symlink():
            if path == env_path:
                _atomic_copy_env(backup, path)
            else:
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
        _invoke_callback(start_callback, safe_run_id)
    return {
        "run_id": safe_run_id,
        "override": str(override_path),
    }
