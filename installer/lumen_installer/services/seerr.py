"""Safe migration and runtime reconciliation for the Seerr request service.

The Compose service intentionally keeps the historical ``jellyseerr`` key and
container name.  This module keeps the host-side config migration equally
conservative: an adopted config is copied before ownership changes, and the
official Seerr image's numeric runtime owner is applied only after an explicit
decision.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..errors import DriftError, InstallerError, InvalidInputError
from ..http import HttpResponse, HttpStatusError, HttpTransportError
from .base import ServiceCheckpoint, ServiceResult


SERVICE_NAME = "jellyseerr"
CONTAINER_NAME = "jellyseerr"
SEERR_IMAGE = "ghcr.io/seerr-team/seerr:latest"
SEERR_CONFIG_PATH = Path("config/jellyseerr")
SEERR_CONFIG_MOUNT = "/app/config"
SEERR_UID = 1000
SEERR_GID = 1000
SEERR_PORT = 5055
SEERR_INTERNAL_URL = "http://jellyseerr:5055"
SEERR_MINIMUM_VERSION = (2, 0, 0)

_INTEGRATIONS = ("jellyfin", "sonarr", "radarr")
_DEFAULT_INTEGRATION_PATHS = {
    "jellyfin": "/api/v1/settings/jellyfin",
    "sonarr": "/api/v1/settings/sonarr",
    "radarr": "/api/v1/settings/radarr",
}
_DEFAULT_INTEGRATION_URLS = {
    "jellyfin": "http://jellyfin:8096",
    "sonarr": "http://sonarr:8989",
    "radarr": "http://radarr:7878",
}
_DEFAULT_PORTS = {"jellyfin": 8096, "sonarr": 8989, "radarr": 7878}
_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")


class SeerrError(InstallerError):
    """Base class for sanitized Seerr failures."""

    code = "seerr-error"

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        self.code = code or type(self).code
        InstallerError.__init__(self, self.code)

    @property
    def report(self) -> dict[str, str]:
        return {"error": self.code}

    @property
    def redacted(self) -> dict[str, str]:
        return self.report


class SeerrConfigError(InvalidInputError, SeerrError):
    code = "seerr-config"

    def __init__(self, message: str | None = None) -> None:
        self.code = type(self).code
        InvalidInputError.__init__(self, self.code)


class SeerrCapabilityError(InvalidInputError, SeerrError):
    code = "seerr-capability"

    def __init__(self, message: str | None = None) -> None:
        self.code = type(self).code
        InvalidInputError.__init__(self, self.code)


class SeerrSchemaError(InvalidInputError, SeerrError):
    code = "seerr-schema"

    def __init__(self, message: str | None = None) -> None:
        self.code = type(self).code
        InvalidInputError.__init__(self, self.code)


class SeerrConflictError(DriftError, SeerrError):
    code = "seerr-conflict"

    def __init__(self, message: str | None = None) -> None:
        self.code = type(self).code
        DriftError.__init__(self, self.code)


SeerrOwnershipError = SeerrConflictError


@dataclass(frozen=True, repr=False)
class OwnershipInspection:
    """Numeric ownership facts for one exact config directory."""

    path: Path
    exists: bool
    uid: int | None = None
    gid: int | None = None
    entries: int = 0
    mismatched_entries: int = 0

    @property
    def matches_runtime_owner(self) -> bool:
        return self.exists and self.mismatched_entries == 0

    @property
    def adopted(self) -> bool:
        return self.exists

    @property
    def report(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "exists": self.exists,
            "uid": self.uid,
            "gid": self.gid,
            "entries": self.entries,
            "mismatched_entries": self.mismatched_entries,
            "matches_runtime_owner": self.matches_runtime_owner,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report

    def __repr__(self) -> str:
        return (
            f"OwnershipInspection(path={str(self.path)!r}, exists={self.exists!r}, "
            f"uid={self.uid!r}, gid={self.gid!r}, mismatched_entries={self.mismatched_entries!r})"
        )


@dataclass(frozen=True, repr=False)
class SeerrConfigResult:
    """Secret-free result of the exact config migration boundary."""

    status: str
    path: Path
    ownership: OwnershipInspection
    actions: tuple[str, ...] = ()
    backup_path: Path | None = None
    requires_confirmation: bool = False
    dry_run: bool = False
    error: SeerrError | None = field(default=None, repr=False, compare=False)

    @property
    def report(self) -> dict[str, Any]:
        return {
            "service": SERVICE_NAME,
            "status": self.status,
            "path": str(self.path),
            "ownership": self.ownership.report,
            "actions": list(self.actions),
            "backup_path": str(self.backup_path) if self.backup_path is not None else None,
            "requires_confirmation": self.requires_confirmation,
            "dry_run": self.dry_run,
            "error": self.error.code if self.error is not None else None,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report

    @property
    def steps(self) -> tuple[str, ...]:
        return self.actions

    def __repr__(self) -> str:
        return (
            f"SeerrConfigResult(status={self.status!r}, path={str(self.path)!r}, "
            f"actions={self.actions!r}, dry_run={self.dry_run!r})"
        )


@dataclass(frozen=True, repr=False)
class SeerrCapability:
    """Non-sensitive runtime capability facts returned by the status probe."""

    version: str
    integrations: tuple[str, ...] = _INTEGRATIONS
    supported: bool = True

    @property
    def report(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "integrations": list(self.integrations),
            "supported": self.supported,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report

    def __repr__(self) -> str:
        return f"SeerrCapability(version={self.version!r}, integrations={self.integrations!r}, supported={self.supported!r})"


@dataclass(frozen=True)
class SeerrResult(ServiceResult):
    """Operation result with a stable Seerr-specific representation."""

    supported: bool | None = field(default=None, repr=False, compare=False)

    @property
    def report(self) -> dict[str, Any]:
        report = super().report
        if self.supported is not None:
            report["supported"] = self.supported
        return report

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report

    def __repr__(self) -> str:
        return (
            f"SeerrResult(service={self.service!r}, status={self.status!r}, "
            f"actions={self.actions!r}, dry_run={self.dry_run!r})"
        )


def _absolute_directory_path(value: str | os.PathLike[str], *, name: str) -> Path:
    try:
        path = Path(value)
    except (TypeError, ValueError, OSError) as exc:
        raise SeerrConfigError() from exc
    if not path.is_absolute() or "\x00" in str(path):
        raise SeerrConfigError()
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            if current.is_symlink():
                raise SeerrConfigError()
        except OSError:
            raise SeerrConfigError() from None
    return Path(os.path.abspath(str(path)))


def _validate_backup_location(source: Path, destination: Path) -> None:
    if destination == source or source in destination.parents:
        raise SeerrConfigError()
    if destination.exists():
        raise SeerrConfigError()


def inspect_config_ownership(
    config_path: str | os.PathLike[str],
    *,
    runtime_uid: int = SEERR_UID,
    runtime_gid: int = SEERR_GID,
) -> OwnershipInspection:
    """Inspect an exact config directory without following symlinks."""

    path = _absolute_directory_path(config_path, name="Seerr config")
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return OwnershipInspection(path=path, exists=False)
    except OSError:
        raise SeerrConfigError() from None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise SeerrConfigError()

    entries = 0
    mismatched = 0
    first_uid = int(metadata.st_uid)
    first_gid = int(metadata.st_gid)
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            current_metadata = os.lstat(current)
        except OSError:
            raise SeerrConfigError() from None
        if stat.S_ISLNK(current_metadata.st_mode):
            continue
        entries += 1
        if current_metadata.st_uid != runtime_uid or current_metadata.st_gid != runtime_gid:
            mismatched += 1
        if stat.S_ISDIR(current_metadata.st_mode):
            try:
                children = tuple(current.iterdir())
            except OSError:
                raise SeerrConfigError() from None
            stack.extend(children)
    return OwnershipInspection(
        path=path,
        exists=True,
        uid=first_uid,
        gid=first_gid,
        entries=entries,
        mismatched_entries=mismatched,
    )


def backup_config(
    config_path: str | os.PathLike[str],
    backup_path: str | os.PathLike[str],
) -> Path:
    """Copy one exact config tree without overwriting an existing backup."""

    source = _absolute_directory_path(config_path, name="Seerr config")
    destination = _absolute_directory_path(backup_path, name="Seerr config backup")
    _validate_backup_location(source, destination)
    try:
        metadata = os.lstat(source)
    except (FileNotFoundError, OSError):
        raise SeerrConfigError() from None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise SeerrConfigError()
    try:
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(destination.parent, 0o700)
        shutil.copytree(source, destination, symlinks=True, copy_function=shutil.copy2)
    except (OSError, shutil.Error):
        raise SeerrConfigError() from None
    return destination


def _recursive_chown(
    config_path: Path,
    uid: int,
    gid: int,
    *,
    chown: Callable[..., Any] = os.chown,
) -> None:
    stack = [config_path]
    while stack:
        current = stack.pop()
        try:
            metadata = os.lstat(current)
        except OSError:
            raise SeerrConfigError() from None
        if stat.S_ISLNK(metadata.st_mode):
            try:
                chown(current, uid, gid, follow_symlinks=False)
            except OSError:
                raise SeerrConfigError() from None
            continue
        try:
            chown(current, uid, gid, follow_symlinks=False)
        except OSError:
            raise SeerrConfigError() from None
        if stat.S_ISDIR(metadata.st_mode):
            try:
                stack.extend(current.iterdir())
            except OSError:
                raise SeerrConfigError() from None


def _owner_id(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise InvalidInputError(f"{name} must be a positive integer")
    return value


def prepare_seerr_config(
    config_path: str | os.PathLike[str],
    *,
    backup_path: str | os.PathLike[str] | None = None,
    confirm: bool = False,
    dry_run: bool = False,
    runtime_uid: int = SEERR_UID,
    runtime_gid: int = SEERR_GID,
    backup: Callable[[str | os.PathLike[str], str | os.PathLike[str]], Path] | None = None,
    chown: Callable[..., Any] | None = None,
) -> SeerrConfigResult:
    """Prepare a fresh/adopted config with backup-first ownership policy."""

    if type(confirm) is not bool or type(dry_run) is not bool:
        raise InvalidInputError("Seerr confirmation and dry-run values must be booleans")
    uid = _owner_id(runtime_uid, "Seerr UID")
    gid = _owner_id(runtime_gid, "Seerr GID")
    selected_backup_fn = backup or backup_config
    selected_chown = chown or os.chown
    path = _absolute_directory_path(config_path, name="Seerr config")
    selected_backup = (
        _absolute_directory_path(backup_path, name="Seerr config backup")
        if backup_path is not None
        else None
    )
    ownership = inspect_config_ownership(path, runtime_uid=uid, runtime_gid=gid)

    if not ownership.exists:
        actions = ["inspect-ownership", "create-config-directory", "set-runtime-owner"]
        if dry_run:
            return SeerrConfigResult(
                status="dry-run",
                path=path,
                ownership=ownership,
                actions=tuple(actions),
                dry_run=True,
            )
        try:
            path.mkdir(mode=0o700, parents=True, exist_ok=False)
            os.chmod(path, 0o700)
            selected_chown(path, uid, gid, follow_symlinks=False)
        except FileExistsError:
            raise SeerrConfigError() from None
        except OSError:
            raise SeerrConfigError() from None
        return SeerrConfigResult(
            status="ok",
            path=path,
            ownership=inspect_config_ownership(path, runtime_uid=uid, runtime_gid=gid),
            actions=tuple(actions),
        )

    if selected_backup is None:
        raise SeerrConfigError()
    _validate_backup_location(path, selected_backup)
    mismatched = not ownership.matches_runtime_owner
    actions = ["inspect-ownership"]
    if dry_run:
        actions.append("backup-config-unverified")
        if mismatched:
            actions.append("await-ownership-confirmation")
        else:
            actions.append("reuse-config")
        return SeerrConfigResult(
            status="dry-run",
            path=path,
            ownership=ownership,
            actions=tuple(actions),
            backup_path=selected_backup,
            requires_confirmation=mismatched,
            dry_run=True,
        )

    # The backup is deliberately taken for every adopted run, including a
    # no-op ownership match.  It is the recoverable snapshot for any later
    # Seerr start/update operation and always precedes a chown.
    selected_backup_fn(path, selected_backup)
    actions.append("backup-config")
    if not mismatched:
        actions.append("reuse-config")
        return SeerrConfigResult(
            status="ok",
            path=path,
            ownership=ownership,
            actions=tuple(actions),
            backup_path=selected_backup,
        )
    if not confirm:
        actions.append("await-ownership-confirmation")
        return SeerrConfigResult(
            status="drift",
            path=path,
            ownership=ownership,
            actions=tuple(actions),
            backup_path=selected_backup,
            requires_confirmation=True,
            error=SeerrConflictError(),
        )
    _recursive_chown(path, uid, gid, chown=selected_chown)
    actions.append("chown-config-recursive")
    return SeerrConfigResult(
        status="ok",
        path=path,
        ownership=inspect_config_ownership(path, runtime_uid=uid, runtime_gid=gid),
        actions=tuple(actions),
        backup_path=selected_backup,
    )


prepare_config = prepare_seerr_config


def _base_url(value: Any, *, service: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidInputError(f"{service} URL is required")
    candidate = value.strip().rstrip("/")
    try:
        parsed = urllib.parse.urlsplit(candidate)
        _ = parsed.port
    except (TypeError, ValueError):
        raise InvalidInputError(f"{service} URL is invalid") from None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise InvalidInputError(f"{service} URL is invalid")
    return candidate


def seerr_service_urls() -> dict[str, str]:
    """Return the Compose-DNS URLs used by supported Seerr integrations."""

    return dict(_DEFAULT_INTEGRATION_URLS)


def _version(value: str) -> tuple[int, int, int] | None:
    match = _VERSION_RE.fullmatch(value.strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def _json(response: Any) -> Any:
    if isinstance(response, Mapping) and not isinstance(response, HttpResponse):
        if "body" not in response:
            return response
        body = response["body"]
        if isinstance(body, (Mapping, list)):
            return body
        try:
            return json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
        except (TypeError, UnicodeError, ValueError, json.JSONDecodeError):
            raise SeerrSchemaError() from None
    decoder = getattr(response, "json", None)
    if not callable(decoder):
        raise SeerrSchemaError() from None
    try:
        return decoder()
    except Exception:
        raise SeerrSchemaError() from None


class SeerrAdapter:
    """Capability-gated Seerr integration reconciler."""

    service = SERVICE_NAME

    def __init__(
        self,
        base_url: str,
        transport: Any,
        *,
        api_key: str | None = None,
        jellyfin_url: str = _DEFAULT_INTEGRATION_URLS["jellyfin"],
        jellyfin_api_key: str | None = None,
        sonarr_url: str = _DEFAULT_INTEGRATION_URLS["sonarr"],
        sonarr_api_key: str | None = None,
        radarr_url: str = _DEFAULT_INTEGRATION_URLS["radarr"],
        radarr_api_key: str | None = None,
    ) -> None:
        if transport is None or not callable(getattr(transport, "request", None)):
            raise InvalidInputError("Seerr transport is required")
        self.base_url = _base_url(base_url, service="Seerr")
        if api_key is not None and (not isinstance(api_key, str) or not api_key.strip()):
            raise InvalidInputError("Seerr API key is invalid")
        self._transport = transport
        self._api_key = api_key.strip() if isinstance(api_key, str) else None
        self._integration_urls = {
            "jellyfin": _base_url(jellyfin_url, service="Jellyfin"),
            "sonarr": _base_url(sonarr_url, service="Sonarr"),
            "radarr": _base_url(radarr_url, service="Radarr"),
        }
        self._integration_keys = {
            "jellyfin": jellyfin_api_key,
            "sonarr": sonarr_api_key,
            "radarr": radarr_api_key,
        }
        for service, key in self._integration_keys.items():
            if key is not None and (not isinstance(key, str) or not key.strip()):
                raise InvalidInputError(f"{service} API key is invalid")
        self._capability: SeerrCapability | None = None

    def __repr__(self) -> str:
        return "SeerrAdapter(configured=True)"

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, *, body: Any = None) -> Any:
        url = self._url(path)
        headers = {"Accept": "application/json"}
        if self._api_key:
            headers["X-Api-Key"] = self._api_key
        kwargs: dict[str, Any] = {"headers": headers}
        if body is not None:
            kwargs["json_body"] = body
        try:
            response = self._transport.request(method, url, **kwargs)
        except HttpTransportError:
            raise
        except Exception:
            raise SeerrError(code="seerr-transport") from None
        status = getattr(response, "status", None)
        if status is None and isinstance(response, Mapping):
            status = response.get("status", 200)
        try:
            status = int(200 if status is None else status)
        except (TypeError, ValueError):
            raise SeerrSchemaError() from None
        if not 200 <= status < 300:
            raise HttpStatusError(method=method, url=url, status=status)
        return response

    @staticmethod
    def _supported_integrations(payload: Mapping[str, Any]) -> tuple[str, ...]:
        raw = payload.get("capabilities", payload.get("integrations", payload.get("features")))
        if raw is None:
            return _INTEGRATIONS
        if isinstance(raw, Mapping):
            values = tuple(name for name in _INTEGRATIONS if raw.get(name, True) is True)
            return values
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
            values = tuple(name for name in _INTEGRATIONS if name in raw)
            return values
        raise SeerrSchemaError() from None

    def probe_capability(self) -> SeerrCapability:
        payload = _json(self._request("GET", "/api/v1/status"))
        if not isinstance(payload, Mapping):
            raise SeerrCapabilityError() from None
        version = payload.get("version")
        if not isinstance(version, str) or not version.strip():
            raise SeerrCapabilityError() from None
        parsed_version = _version(version)
        if parsed_version is None or parsed_version < SEERR_MINIMUM_VERSION:
            raise SeerrCapabilityError() from None
        integrations = self._supported_integrations(payload)
        if not integrations:
            raise SeerrCapabilityError() from None
        self._capability = SeerrCapability(version=version.strip(), integrations=integrations)
        return self._capability

    capability = probe_capability

    @staticmethod
    def _settings_payload(
        current: Mapping[str, Any],
        service: str,
        url: str,
        api_key: str,
    ) -> dict[str, Any]:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname
        if not host:
            raise InvalidInputError(f"{service} URL is invalid")
        port = parsed.port or _DEFAULT_PORTS[service]
        payload = dict(current)
        payload.update(
            {
                "hostname": host,
                "port": port,
                "useSsl": parsed.scheme.casefold() == "https",
                "apiKey": api_key,
            }
        )
        if parsed.path and parsed.path != "/":
            payload["urlBase"] = parsed.path.rstrip("/")
        return payload

    def configure_integrations(
        self,
        *,
        jellyfin_url: str | None = None,
        jellyfin_api_key: str | None = None,
        sonarr_url: str | None = None,
        sonarr_api_key: str | None = None,
        radarr_url: str | None = None,
        radarr_api_key: str | None = None,
        dry_run: bool = False,
    ) -> ServiceResult:
        keys = {
            "jellyfin": jellyfin_api_key if jellyfin_api_key is not None else self._integration_keys["jellyfin"],
            "sonarr": sonarr_api_key if sonarr_api_key is not None else self._integration_keys["sonarr"],
            "radarr": radarr_api_key if radarr_api_key is not None else self._integration_keys["radarr"],
        }
        urls = {
            "jellyfin": _base_url(jellyfin_url, service="Jellyfin") if jellyfin_url is not None else self._integration_urls["jellyfin"],
            "sonarr": _base_url(sonarr_url, service="Sonarr") if sonarr_url is not None else self._integration_urls["sonarr"],
            "radarr": _base_url(radarr_url, service="Radarr") if radarr_url is not None else self._integration_urls["radarr"],
        }
        actions = tuple(["probe-capability", *[f"configure-{name}" for name in _INTEGRATIONS]])
        if dry_run:
            return SeerrResult(
                service=self.service,
                status="dry-run",
                actions=actions,
                dry_run=True,
            )
        for service, key in keys.items():
            if not isinstance(key, str) or not key.strip():
                raise InvalidInputError(f"{service} API key is required")
        try:
            capability = self.probe_capability()
        except SeerrCapabilityError as error:
            return SeerrResult(
                service=self.service,
                status="unsupported",
                actions=("probe-capability",),
                supported=False,
                error=error,
            )
        except (SeerrSchemaError, HttpTransportError, SeerrError) as error:
            return SeerrResult(
                service=self.service,
                status="partial",
                actions=("probe-capability",),
                error=error,
            )

        completed: list[str] = ["probe-capability"]
        try:
            for service in _INTEGRATIONS:
                if service not in capability.integrations:
                    completed.append(f"skip-{service}-unsupported")
                    continue
                current = _json(self._request("GET", _DEFAULT_INTEGRATION_PATHS[service]))
                if not isinstance(current, Mapping):
                    raise SeerrSchemaError() from None
                desired = self._settings_payload(current, service, urls[service], keys[service])
                if dict(current) == desired:
                    completed.append(f"reuse-{service}")
                    continue
                self._request("PUT", _DEFAULT_INTEGRATION_PATHS[service], body=desired)
                completed.append(f"update-{service}")
        except (SeerrSchemaError, HttpTransportError, SeerrError) as error:
            return SeerrResult(
                service=self.service,
                status="partial",
                actions=tuple(completed),
                error=error,
            )
        return SeerrResult(
            service=self.service,
            status="ok",
            actions=tuple(completed),
            supported=True,
        )

    configure = configure_integrations


def configure_seerr(
    base_url: str | None = None,
    transport: Any | None = None,
    *,
    adapter: SeerrAdapter | None = None,
    api_key: str | None = None,
    **kwargs: Any,
) -> ServiceResult:
    """Functional facade for callers that do not retain an adapter."""

    if adapter is None:
        adapter_options = kwargs.pop("adapter_kwargs", {})
        if not isinstance(adapter_options, Mapping):
            raise InvalidInputError("Seerr adapter options must be a mapping")
        if base_url is None or transport is None:
            raise InvalidInputError("Seerr URL and transport are required")
        adapter_options = dict(adapter_options)
        if api_key is not None:
            adapter_options["api_key"] = api_key
        adapter = SeerrAdapter(base_url, transport, **adapter_options)
    return adapter.configure_integrations(**kwargs)


__all__ = [
    "CONTAINER_NAME",
    "OwnershipInspection",
    "SEERR_CONFIG_MOUNT",
    "SEERR_CONFIG_PATH",
    "SEERR_GID",
    "SEERR_IMAGE",
    "SEERR_INTERNAL_URL",
    "SEERR_MINIMUM_VERSION",
    "SEERR_PORT",
    "SEERR_UID",
    "SERVICE_NAME",
    "SeerrAdapter",
    "SeerrCapability",
    "SeerrCapabilityError",
    "SeerrConfigError",
    "SeerrConfigResult",
    "SeerrConflictError",
    "SeerrError",
    "SeerrOwnershipError",
    "SeerrResult",
    "SeerrSchemaError",
    "backup_config",
    "configure_seerr",
    "inspect_config_ownership",
    "prepare_config",
    "prepare_seerr_config",
    "seerr_service_urls",
]
