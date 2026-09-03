"""Ordered core-service reconciliation for the Linux installer.

The configure boundary owns the transaction around the service adapters.  An
adapter may change its service, but the installer environment is committed in
one distinct step after every dependent credential has been validated.
"""

from __future__ import annotations

import re
import json
import stat
import inspect
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .commands import CommandRunner
from .compose import ComposeOptions, run_compose
from .dotenv import DotEnvDocument, write_atomic
from .errors import ExitCode, InvalidInputError, PartialError
from .http import HttpTransport
from .services.base import ServiceCheckpoint, ServiceResult
from .services.jellyfin import JellyfinAdapter
from .services.prowlarr import ProwlarrAdapter, read_prowlarr_api_key
from .services.qbittorrent import QbittorrentAdapter
from .services.servarr import RadarrAdapter, SonarrAdapter, read_servarr_api_key


CORE_ORDER = (
    "jellyfin",
    "qbittorrent",
    "sonarr",
    "radarr",
    "prowlarr",
    "torznab",
)

CONFIGURE_ORDER = CORE_ORDER + ("env-commit", "restart", "direct-health", "proxy-health")

_SECRET_KEY = re.compile(
    r"(?:password|secret|token|api[_-]?key|credential|cookie|private[_-]?key|oauth|error|message)",
    re.IGNORECASE,
)

DEFAULT_SERVICE_URLS = {
    "jellyfin": "http://127.0.0.1:8096",
    "qbittorrent": "http://127.0.0.1:8081",
    "sonarr": "http://127.0.0.1:8989",
    "radarr": "http://127.0.0.1:7878",
    "prowlarr": "http://127.0.0.1:9696",
}
DEFAULT_DIRECT_HEALTH_URL = "http://127.0.0.1:8085/health"
DEFAULT_PROXY_HEALTH_URL = "http://127.0.0.1:3000/api/health"
DEFAULT_HEALTH_TIMEOUT = 30.0
DEFAULT_HEALTH_INTERVAL = 1.0
_TRANSIENT_ENV_KEYS = frozenset(
    {
        "JELLYFIN_ADMIN_NAME",
        "JELLYFIN_ADMIN_PASSWORD",
        "JELLYFIN_USERNAME",
        "JELLYFIN_PASSWORD",
    }
)


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "<redacted>" if _SECRET_KEY.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _result_status(result: Any) -> str:
    if isinstance(result, Mapping):
        return str(result.get("status", "ok")).strip().lower() or "ok"
    return str(getattr(result, "status", "ok")).strip().lower() or "ok"


def _result_report(result: Any) -> dict[str, Any]:
    report = getattr(result, "report", result)
    if isinstance(report, Mapping):
        return _redact(report)
    return {"status": _result_status(result)}


def _status_code(status: str) -> ExitCode:
    if status in {"drift", "conflict", "needs-approval", "unapproved"}:
        return ExitCode.DRIFT
    if status in {"guided", "partial", "degraded", "unhealthy", "health"}:
        return ExitCode.PARTIAL
    if status in {"invalid", "error", "failed", "failure", "unsupported", "missing"}:
        return ExitCode.INVALID
    return ExitCode.OK


def commit_environment(
    path: str | Path,
    document: DotEnvDocument,
    *,
    writer: Callable[..., Any] = write_atomic,
) -> bool:
    """Commit the prepared dotenv document at one atomic 0600 boundary."""

    if not isinstance(document, DotEnvDocument):
        raise InvalidInputError("environment document is invalid")
    destination = Path(path)
    if not destination.is_absolute():
        raise InvalidInputError("environment path must be absolute")
    rendered = document.render()
    try:
        current = destination.read_text(encoding="utf-8") if destination.exists() else None
        metadata = destination.lstat() if destination.exists() else None
        if metadata is not None and not stat.S_ISREG(metadata.st_mode):
            raise InvalidInputError("environment path is not a regular file")
        mode_needs_fix = metadata is None or stat.S_IMODE(metadata.st_mode) != 0o600
    except InvalidInputError:
        raise
    except (OSError, UnicodeError) as exc:
        raise InvalidInputError("environment could not be read before commit") from exc
    if current == rendered and not mode_needs_fix:
        return False
    try:
        writer(destination, rendered, mode=0o600)
    except (OSError, ValueError, TypeError) as exc:
        raise InvalidInputError("environment could not be committed atomically") from exc
    return True


class ConfigureJournal:
    """Small ordered checkpoint journal separate from foundation state."""

    def __init__(self, repo_root: str | Path, *, stages: Sequence[str] = CONFIGURE_ORDER) -> None:
        root = Path(repo_root)
        if not root.is_absolute():
            raise InvalidInputError("repository root must be an absolute path")
        self.repo_root = Path(root)
        self.stages = tuple(stages)
        if self.stages != CONFIGURE_ORDER or len(set(self.stages)) != len(self.stages):
            raise InvalidInputError("configure journal stages are invalid")
        self.path = self.repo_root / ".state" / "installer" / "configure.json"
        self._pending_environment: tuple[str, ...] = ()
        self._completed = self._load()

    def _load(self) -> tuple[str, ...]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ()
        except (OSError, UnicodeError) as exc:
            raise InvalidInputError("configure journal could not be read") from exc
        try:
            document = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise InvalidInputError("configure journal is invalid") from exc
        if not isinstance(document, Mapping) or document.get("schema_version") != 1:
            raise InvalidInputError("configure journal schema is unsupported")
        completed = document.get("completed_stages")
        if not isinstance(completed, list) or tuple(completed) != self.stages[: len(completed)]:
            raise InvalidInputError("configure journal stages are invalid")
        pending = document.get("pending_environment_stages", [])
        if (
            not isinstance(pending, list)
            or any(stage not in CORE_ORDER for stage in pending)
            or any(stage not in completed for stage in pending)
            or tuple(pending) != tuple(stage for stage in CORE_ORDER if stage in pending)
        ):
            raise InvalidInputError("configure journal environment checkpoints are invalid")
        self._pending_environment = tuple(pending)
        return tuple(completed)

    @property
    def completed(self) -> tuple[str, ...]:
        return self._completed

    @property
    def pending_environment(self) -> tuple[str, ...]:
        """Completed services whose in-memory env updates still need commit."""

        return self._pending_environment

    def is_complete(self, stage: str) -> bool:
        if stage not in self.stages:
            raise InvalidInputError("unknown configure stage")
        return stage in self._completed

    def _save(
        self,
        completed: tuple[str, ...],
        pending_environment: tuple[str, ...],
    ) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_atomic(
            self.path,
            json.dumps(
                {
                    "schema_version": 1,
                    "completed_stages": list(completed),
                    "pending_environment_stages": list(pending_environment),
                },
                sort_keys=True,
            )
            + "\n",
            mode=0o600,
        )

    def complete(self, stage: str, *, environment_pending: bool | None = None) -> bool:
        if stage not in self.stages:
            raise InvalidInputError("unknown configure stage")
        if stage in self._completed:
            return False
        expected = self.stages[len(self._completed)]
        if stage != expected:
            raise InvalidInputError("configure stages must be completed in order")
        candidate = self._completed + (stage,)
        pending = self._pending_environment
        if environment_pending is True and stage in CORE_ORDER:
            pending = pending + (stage,)
        elif environment_pending is False:
            pending = ()
        self._save(candidate, pending)
        self._completed = candidate
        self._pending_environment = pending
        return True

    def update_environment_pending(self, stage: str, pending: bool) -> None:
        """Update a completed service's replay marker without storing secrets."""

        if stage not in CORE_ORDER or stage not in self._completed:
            raise InvalidInputError("unknown configure environment checkpoint")
        values = [item for item in self._pending_environment if item != stage]
        if pending:
            values.append(stage)
        ordered = tuple(item for item in CORE_ORDER if item in values)
        self._save(self._completed, ordered)
        self._pending_environment = ordered

    def clear_environment_pending(self) -> None:
        if not self._pending_environment:
            return
        self._save(self._completed, ())
        self._pending_environment = ()


@dataclass(frozen=True)
class ConfigureResult:
    """Secret-free summary of one configure attempt."""

    status: str
    dry_run: bool
    stages_completed: tuple[str, ...] = ()
    services: Mapping[str, Any] = field(default_factory=dict)
    environment_committed: bool = False
    restarted: bool = False
    health: Mapping[str, Any] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return int(_status_code(self.status))

    @property
    def report(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "dry_run": self.dry_run,
            "stages_completed": list(self.stages_completed),
            "services": _redact(dict(self.services)),
            "environment_committed": self.environment_committed,
            "restarted": self.restarted,
            "health": _redact(dict(self.health)),
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report


def _invoke_reconcile(
    reconcile: Callable[..., Any],
    service: str,
    *,
    environment: MutableMapping[str, Any],
    dry_run: bool,
) -> Any:
    """Invoke a test seam or adapter callback with only accepted keywords."""

    try:
        parameters = tuple(inspect.signature(reconcile).parameters.values())
    except (TypeError, ValueError):
        return reconcile(service, environment=environment, dry_run=dry_run)
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return reconcile(service, environment=environment, dry_run=dry_run)
    accepted = {
        parameter.name
        for parameter in parameters
        if parameter.kind
        in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}
    }
    return reconcile(
        service,
        **{
            key: value
            for key, value in {"environment": environment, "dry_run": dry_run}.items()
            if key in accepted
        },
    )


def _environment_update(result: Any) -> Mapping[str, Any]:
    update = result.get("environment_update") if isinstance(result, Mapping) else getattr(result, "environment_update", None)
    if update is None:
        return {}
    if callable(getattr(update, "as_dict", None)):
        update = update.as_dict()
    if not isinstance(update, Mapping):
        return {}
    return {str(key): value for key, value in update.items() if isinstance(key, str)}


def _call_with_keywords(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        parameters = tuple(inspect.signature(function).parameters.values())
    except (TypeError, ValueError):
        return function(*args, **kwargs)
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return function(*args, **kwargs)
    accepted = {
        parameter.name
        for parameter in parameters
        if parameter.kind
        in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}
    }
    return function(*args, **{key: value for key, value in kwargs.items() if key in accepted})


def _configured_value(environment: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = environment.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _service_status(result: Any) -> str:
    return _result_status(result)


def _guided(service: str, code: str, reason: str) -> ServiceResult:
    return ServiceResult(
        service=service,
        status="guided",
        checkpoints=(
            ServiceCheckpoint(
                code=code,
                reason=reason,
                action="retry",
                severity="error",
            ),
        ),
    )


class _JellyfinReconciler:
    def __init__(self, adapter: JellyfinAdapter, *, network_state: str, confirm: bool) -> None:
        self.adapter = adapter
        self.network_state = network_state
        self.confirm = confirm

    def configure(self, *, dry_run: bool = False, confirm: bool = False) -> Any:
        selected_confirm = bool(confirm or self.confirm)
        result = self.adapter.configure(dry_run=dry_run)
        if _service_status(result) != "ok":
            return result
        if dry_run:
            return result

        actions = list(getattr(result, "actions", ()))
        api_result = self.adapter.reconcile_api_key(dry_run=False)
        if _service_status(api_result) != "ok":
            return api_result
        actions.extend(getattr(api_result, "actions", ()))
        handoff = self.adapter.api_key_handoff
        if handoff is None:
            return _guided(
                "jellyfin",
                "jellyfin-api-key-missing",
                "Jellyfin did not return the managed API key; retry reconciliation.",
            )
        api_key = handoff.consume()

        library_result = self.adapter.reconcile_libraries(
            confirm_drift=selected_confirm,
            dry_run=False,
        )
        if _service_status(library_result) != "ok":
            return library_result
        actions.extend(getattr(library_result, "actions", ()))

        remote_plan = self.adapter.plan_remote_access(self.network_state)
        remote_result = self.adapter.apply_remote_access(
            remote_plan,
            confirm_drift=selected_confirm,
        )
        if _service_status(remote_result) != "ok":
            return remote_result
        actions.extend(getattr(remote_result, "actions", ()))
        return {
            "service": "jellyfin",
            "status": "ok",
            "actions": actions,
            "environment_update": {"JELLYFIN_API_KEY": api_key},
        }


class _ProwlarrReconciler:
    def __init__(self, adapter: ProwlarrAdapter, *, confirm: bool) -> None:
        self.adapter = adapter
        self.confirm = confirm
        self.last_result: Any = None

    def configure(self, *, dry_run: bool = False, confirm: bool = False) -> Any:
        result = self.adapter.configure(
            confirm=bool(confirm or self.confirm),
            dry_run=dry_run,
        )
        self.last_result = result
        return result


class _TorznabReconciler:
    def __init__(self, prowlarr: _ProwlarrReconciler | None, *, configured: bool) -> None:
        self.prowlarr = prowlarr
        self.configured = configured

    def configure(self, *, dry_run: bool = False, confirm: bool = False) -> Any:
        if dry_run:
            return ServiceResult(
                service="torznab",
                status="dry-run",
                actions=("reconcile-generic-torznab",),
                dry_run=True,
            )
        if not self.configured:
            return _guided(
                "torznab",
                "torznab-credentials",
                "Provide the Generic Torznab URL and API key, then retry configure.",
            )
        if self.prowlarr is not None and self.prowlarr.last_result is None:
            return _guided(
                "torznab",
                "torznab-prowlarr-order",
                "Prowlarr must be reconciled before its Generic Torznab indexer.",
            )
        return {
            "service": "torznab",
            "status": "ok",
            "actions": ["reconcile-generic-torznab"],
        }


def build_adapter_factory(
    repo_root: str | Path,
    *,
    environment: MutableMapping[str, Any],
    transport: Any | None = None,
    interactive: bool = True,
    confirm: bool = False,
    jellyfin_admin_name: str | None = None,
    jellyfin_admin_password: str | None = None,
    prompt: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Build the ordered service-adapter factory used by ``configure``."""

    root = Path(repo_root)
    if not root.is_absolute():
        raise InvalidInputError("repository root must be an absolute path")
    if not isinstance(environment, MutableMapping):
        raise InvalidInputError("configure environment must be mutable")
    selected_transport = transport if transport is not None else HttpTransport()
    selected_confirm = bool(confirm)
    p_wrapped: _ProwlarrReconciler | None = None
    torznab_url = _configured_value(environment, "TORZNAB_URL", "GENERIC_TORZNAB_URL")
    torznab_key = _configured_value(
        environment,
        "TORZNAB_API_KEY",
        "GENERIC_TORZNAB_API_KEY",
    )
    torznab_configured = torznab_url is not None and torznab_key is not None

    def factory(service: str, *, environment: MutableMapping[str, Any], dry_run: bool = False, confirm: bool = False) -> Any:
        nonlocal p_wrapped
        if service == "jellyfin":
            name = jellyfin_admin_name or _configured_value(
                environment,
                "JELLYFIN_ADMIN_NAME",
                "JELLYFIN_USERNAME",
            )
            password = jellyfin_admin_password or _configured_value(
                environment,
                "JELLYFIN_ADMIN_PASSWORD",
                "JELLYFIN_PASSWORD",
            )
            bind = _configured_value(environment, "JELLYFIN_BIND_ADDRESS")
            remote = _configured_value(environment, "JELLYFIN_REMOTE_ACCESS")
            network_state = "lan" if remote and remote.casefold() in {"1", "true", "yes", "on"} else "local"
            if bind and bind not in {"127.0.0.1", "localhost"}:
                network_state = "lan"
            return _JellyfinReconciler(
                JellyfinAdapter(
                    _configured_value(environment, "JELLYFIN_URL") or DEFAULT_SERVICE_URLS[service],
                    selected_transport,
                    admin_name=name,
                    admin_password=password,
                    interactive=interactive,
                ),
                network_state=network_state,
                confirm=bool(confirm or selected_confirm),
            )
        if service == "qbittorrent":
            return QbittorrentAdapter(
                _configured_value(environment, "QBITTORRENT_URL") or DEFAULT_SERVICE_URLS[service],
                selected_transport,
                env=environment,
                prompt=prompt,
                interactive=interactive,
            )
        if service in {"sonarr", "radarr"}:
            api_key = read_servarr_api_key(service, root)
            environment[f"{service.upper()}_API_KEY"] = api_key
            password = _configured_value(environment, "QBT_PASSWORD", "STACK_PASSWORD")
            adapter_type = SonarrAdapter if service == "sonarr" else RadarrAdapter
            return adapter_type(
                _configured_value(environment, f"{service.upper()}_URL") or DEFAULT_SERVICE_URLS[service],
                selected_transport,
                api_key=api_key,
                qbit_password=password or "",
            )
        if service == "prowlarr":
            api_key = read_prowlarr_api_key(root)
            environment["PROWLARR_API_KEY"] = api_key
            password = _configured_value(environment, "QBT_PASSWORD", "STACK_PASSWORD")
            adapter = ProwlarrAdapter(
                _configured_value(environment, "PROWLARR_URL") or DEFAULT_SERVICE_URLS[service],
                selected_transport,
                api_key=api_key,
                qbit_password=password,
                sonarr_api_key=_configured_value(environment, "SONARR_API_KEY"),
                radarr_api_key=_configured_value(environment, "RADARR_API_KEY"),
                generic_torznab_url=torznab_url if torznab_configured else None,
                generic_torznab_api_key=torznab_key if torznab_configured else None,
            )
            p_wrapped = _ProwlarrReconciler(adapter, confirm=confirm)
            return p_wrapped
        if service == "torznab":
            return _TorznabReconciler(p_wrapped, configured=torznab_configured)
        raise InvalidInputError("unknown configure service")

    return factory


def _load_environment_document(path: Path) -> DotEnvDocument:
    if not path.exists():
        return DotEnvDocument.parse("")
    try:
        return DotEnvDocument.parse(path)
    except (OSError, UnicodeError, ValueError) as exc:
        raise InvalidInputError("could not read .env") from exc


def _secret_values(document: DotEnvDocument) -> tuple[str, ...]:
    return tuple(
        value
        for key, value in document.values.items()
        if _SECRET_KEY.search(key) and isinstance(value, str) and value
    )


def _health_once(
    url: str,
    *,
    opener: Callable[..., Any],
    token: str | None = None,
    timeout: float = 5.0,
) -> bool:
    headers = {"X-Actions-Token": token} if token else {}
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with opener(request, timeout=timeout) as response:
            return 200 <= int(getattr(response, "status", 0)) < 300
    except (OSError, urllib.error.URLError, TimeoutError, ValueError, TypeError):
        return False


def _wait_health(
    probe: Callable[[], Any],
    *,
    timeout: float,
    interval: float,
    sleep: Callable[[float], Any],
    monotonic: Callable[[], float],
) -> bool:
    try:
        limit = max(0.0, float(timeout))
        pause = max(0.0, float(interval))
    except (TypeError, ValueError) as exc:
        raise InvalidInputError("configure health timeout and interval must be numeric") from exc
    started = monotonic()
    while True:
        if bool(probe()):
            return True
        elapsed = monotonic() - started
        if elapsed >= limit:
            return False
        sleep(min(pause, max(0.0, limit - elapsed)))


def run_configure(
    repo_root: str | Path | None = None,
    *,
    env_file: str | Path | None = None,
    env_document: DotEnvDocument | None = None,
    env_writer: Callable[..., Any] = write_atomic,
    runner: CommandRunner | Any | None = None,
    options: ComposeOptions | None = None,
    transport: Any | None = None,
    interactive: bool = True,
    jellyfin_admin_name: str | None = None,
    jellyfin_admin_password: str | None = None,
    prompt: Callable[..., Any] | None = None,
    dry_run: bool = False,
    reconcile: Callable[..., Any] | None = None,
    adapter_factory: Callable[..., Any] | None = None,
    environment: Mapping[str, Any] | None = None,
    confirm: bool = False,
    env_commit: Callable[..., Any] | None = None,
    restart: Callable[..., Any] | None = None,
    direct_health: Callable[..., Any] | None = None,
    proxy_health: Callable[..., Any] | None = None,
    health_opener: Callable[..., Any] | None = None,
    health_timeout: float = DEFAULT_HEALTH_TIMEOUT,
    health_interval: float = DEFAULT_HEALTH_INTERVAL,
    sleep: Callable[[float], Any] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    journal: ConfigureJournal | Any | None = None,
) -> ConfigureResult:
    """Run the ordered configure transaction through injected boundaries."""

    if repo_root is not None and not Path(repo_root).is_absolute():
        raise InvalidInputError("repository root must be an absolute path")
    if not isinstance(dry_run, bool):
        raise InvalidInputError("dry_run must be a boolean")
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[2]
    if not root.is_absolute():
        raise InvalidInputError("repository root must be an absolute path")
    active_journal = journal if journal is not None else ConfigureJournal(root)
    if all(active_journal.is_complete(stage) for stage in CONFIGURE_ORDER):
        return ConfigureResult(
            status="dry-run" if dry_run else "ok",
            dry_run=dry_run,
            stages_completed=CONFIGURE_ORDER,
            services={stage: {"status": "already-complete"} for stage in CORE_ORDER},
            health={"direct": {"status": "healthy"}, "proxy": {"status": "healthy"}},
        )
    env_path = Path(env_file) if env_file is not None else root / ".env"
    if not env_path.is_absolute():
        env_path = root / env_path
    document = env_document.copy() if env_document is not None else _load_environment_document(env_path)
    if dry_run:
        working_environment: MutableMapping[str, Any] = (
            dict(environment) if environment is not None else dict(document.values)
        )
    else:
        working_environment = (
            environment
            if isinstance(environment, MutableMapping)
            else dict(environment or document.values)
        )
        if environment is None:
            working_environment.update(document.values)
    if not isinstance(interactive, bool):
        raise InvalidInputError("interactive must be a boolean")
    for key in (
        "QBT_PASSWORD",
        "STACK_PASSWORD",
        "JELLYFIN_ADMIN_NAME",
        "JELLYFIN_ADMIN_PASSWORD",
        "TORZNAB_URL",
        "TORZNAB_API_KEY",
    ):
        override = os.environ.get(f"LUMEN_{key}")
        if override:
            working_environment[key] = override
    health_opener = health_opener or urllib.request.urlopen
    if reconcile is None:
        if adapter_factory is None:
            adapter_factory = build_adapter_factory(
                root,
                environment=working_environment,
                transport=transport,
                interactive=interactive,
                confirm=confirm,
                jellyfin_admin_name=jellyfin_admin_name,
                jellyfin_admin_password=jellyfin_admin_password,
                prompt=prompt,
            )
        def reconcile(service: str, *, environment, dry_run):
            adapter = _call_with_keywords(
                adapter_factory,
                service,
                environment=environment,
                dry_run=dry_run,
                confirm=confirm,
            )
            configure_method = getattr(adapter, "configure", adapter)
            return _call_with_keywords(
                configure_method,
                dry_run=dry_run,
                confirm=confirm,
            )
    if env_commit is None:
        def env_commit() -> bool:
            for key, value in working_environment.items():
                if (
                    isinstance(key, str)
                    and key.upper() not in _TRANSIENT_ENV_KEYS
                    and isinstance(value, str)
                ):
                    document.set(key, value)
            return commit_environment(env_path, document, writer=env_writer)
    command_runner = runner if runner is not None else CommandRunner()
    compose_options = options if options is not None else ComposeOptions()
    if restart is None:
        def restart() -> Any:
            return run_compose(
                command_runner,
                root,
                env_path,
                compose_options,
                "restart",
                "homepage-actions",
                "dashboard",
                redact=_secret_values(document),
            )
    services: dict[str, Any] = {}
    completed: list[str] = list(getattr(active_journal, "completed", ()))
    for service in CORE_ORDER:
        service_complete = active_journal.is_complete(service)
        environment_pending = service in getattr(active_journal, "pending_environment", ())
        if service_complete and not environment_pending:
            services[service] = {"service": service, "status": "already-complete"}
            continue
        environment_before = dict(working_environment)
        document_before = document.render()
        result = _invoke_reconcile(
            reconcile,
            service,
            environment=working_environment,
            dry_run=dry_run,
        )
        update = _environment_update(result)
        if update:
            working_environment.update(update)
            for key, value in update.items():
                if isinstance(value, str):
                    document.set(key, value)
        services[service] = _result_report(result)
        status = _result_status(result)
        code = _status_code(status)
        if code is not ExitCode.OK:
            result_status = {
                ExitCode.DRIFT: "drift",
                ExitCode.PARTIAL: "guided",
                ExitCode.INVALID: "invalid",
            }[code]
            return ConfigureResult(
                status=result_status,
                dry_run=dry_run,
                stages_completed=tuple(completed),
                services=services,
            )
        environment_changed = (
            bool(update)
            or dict(working_environment) != environment_before
            or document.render() != document_before
        )
        if not dry_run:
            if service_complete:
                updater = getattr(active_journal, "update_environment_pending", None)
                if callable(updater):
                    updater(service, environment_changed)
            else:
                _call_with_keywords(
                    active_journal.complete,
                    service,
                    environment_pending=environment_changed,
                )
                completed.append(service)
        else:
            if not service_complete:
                completed.append(service)

    if active_journal.is_complete("env-commit"):
        environment_committed = False
    elif not dry_run:
        if env_commit is not None:
            env_commit()
            environment_committed = True
        else:
            environment_committed = False
        _call_with_keywords(
            active_journal.complete,
            "env-commit",
            environment_pending=False,
        )
        completed.append("env-commit")
    else:
        environment_committed = False

    restarted = False
    if active_journal.is_complete("restart"):
        restarted = False
    elif not dry_run:
        if restart is not None:
            restart()
            restarted = True
        else:
            restarted = False
        active_journal.complete("restart")
        completed.append("restart")

    health: dict[str, Any] = {}
    default_probes = {
        "direct": lambda: _health_once(
            DEFAULT_DIRECT_HEALTH_URL,
            opener=health_opener,
        ),
        "proxy": lambda: _health_once(
            DEFAULT_PROXY_HEALTH_URL,
            opener=health_opener,
            token=_configured_value(working_environment, "ACTIONS_TOKEN"),
        ),
    }
    for name, stage, probe in (
        ("direct", "direct-health", direct_health),
        ("proxy", "proxy-health", proxy_health),
    ):
        if active_journal.is_complete(stage):
            healthy = True
        else:
            selected_probe = probe or default_probes[name]
            healthy = _wait_health(
                selected_probe,
                timeout=health_timeout,
                interval=health_interval,
                sleep=sleep,
                monotonic=monotonic,
            )
        health[name] = {"status": "healthy" if healthy else "unhealthy"}
        if not healthy:
            return ConfigureResult(
                status="partial",
                dry_run=dry_run,
                stages_completed=tuple(completed),
                services=services,
                environment_committed=environment_committed,
                restarted=restarted,
                health=health,
            )
        if not dry_run:
            active_journal.complete(stage)
        completed.append(stage)

    return ConfigureResult(
        status="dry-run" if dry_run else "ok",
        dry_run=dry_run,
        stages_completed=tuple(completed),
        services=services,
        environment_committed=environment_committed,
        restarted=restarted,
        health=health,
    )


__all__ = [
    "CONFIGURE_ORDER",
    "CORE_ORDER",
    "ConfigureJournal",
    "ConfigureResult",
    "DotEnvDocument",
    "build_adapter_factory",
    "commit_environment",
    "run_configure",
]
