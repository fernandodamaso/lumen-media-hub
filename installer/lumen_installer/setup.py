"""Phase 1 setup and stack lifecycle orchestration.

The foundation deliberately owns only host discovery, the installer-managed
dotenv keys, storage layout, Docker/Compose lifecycle, and a bounded health
gate.  Service-specific reconciliation belongs to later installer phases.
"""

from __future__ import annotations

import inspect
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .commands import CommandExecutionError, CommandResult, CommandRunner
from .compose import (
    ComposeOptions,
    build as compose_build,
    config as compose_config,
    derive_build_services,
    derive_pull_services,
    down as compose_down,
    pull as compose_pull,
    redeploy_dashboard as compose_redeploy_dashboard,
    up as compose_up,
)
from .docker import DockerPreflight, docker_preflight
from .dotenv import DotEnvDocument, write_atomic
from .environment import EnvironmentPlan, plan_environment
from .errors import DriftError, InvalidInputError, PartialError
from .platform import HostFacts, detect_host
from .state import DEFAULT_STAGES, InstallerState, StageJournal
from .storage import KNOWN_STACK_CONTAINER_NAMES, StaleContainer, find_stale_containers, validate_storage
from .network import plan_network
from .answers import Answers


FOUNDATION_STAGES = tuple(DEFAULT_STAGES)
DEFAULT_HEALTH_TIMEOUT = 120.0
DEFAULT_HEALTH_INTERVAL = 5.0
_ID = re.compile(r"^[0-9a-fA-F]{12,64}$")
_SECRET_KEY = re.compile(
    r"(?:password|secret|token|api[_-]?key|credential|cookie|account[_-]?id|private[_-]?key|oauth)",
    re.IGNORECASE,
)


def _safe_projection(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): "<redacted>" if _SECRET_KEY.search(str(key)) else _safe_projection(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_projection(item) for item in value]
    return value


def _repo(value: str | Path | None) -> Path:
    root = Path(value) if value is not None else Path(__file__).resolve().parents[2]
    if not root.is_absolute():
        raise InvalidInputError("repository root must be an absolute path")
    if "\x00" in str(root):
        raise InvalidInputError("repository root is invalid")
    return Path(os.path.abspath(str(root)))


def _call(factory: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call injectable seams while supporting the tiny no-argument test form."""

    try:
        parameters = tuple(inspect.signature(factory).parameters.values())
    except (TypeError, ValueError):
        return factory(*args, **kwargs)
    if any(item.kind is inspect.Parameter.VAR_KEYWORD for item in parameters):
        return factory(*args, **kwargs)
    accepted = {item.name for item in parameters if item.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)}
    filtered = {key: value for key, value in kwargs.items() if key in accepted}
    positional = [item for item in args[:sum(item.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD) for item in parameters)]]
    return factory(*positional, **filtered)


def _load_document(path: Path) -> DotEnvDocument:
    if not path.exists():
        return DotEnvDocument.parse("")
    try:
        return DotEnvDocument.parse(path)
    except (OSError, UnicodeError, ValueError) as exc:
        raise InvalidInputError("could not read .env") from exc


def _answers(path: str | Path | None, value: Answers | Mapping[str, Any] | None) -> Mapping[str, Any]:
    if value is not None:
        return value
    if path is None:
        return {}
    return Answers.load(path).values


def _inputs(
    answers: Mapping[str, Any],
    *,
    environment: Mapping[str, str],
    root_path: str | Path | None,
    downloads_path: str | Path | None,
    qbt_password: str | None = None,
) -> dict[str, Any]:
    result = dict(answers)
    # Only process environment values with the explicit LUMEN_ namespace are
    # consulted by the Linux installer.  This prevents an unrelated shell
    # credential from becoming an accidental report/input source.
    for key in ("ROOT_PATH", "DOWNLOADS_PATH", "QBT_PASSWORD", "STACK_PASSWORD", "PUBLIC_HOST", "NETWORK_MODE"):
        ref = f"LUMEN_{key}"
        if ref in environment and environment[ref] != "":
            result[key] = environment[ref]
    if root_path is not None:
        result["ROOT_PATH"] = root_path
    if downloads_path is not None:
        result["DOWNLOADS_PATH"] = downloads_path
    if qbt_password is not None:
        result["QBT_PASSWORD"] = qbt_password
    # Answers files may carry a secret reference (``env:NAME`` or
    # ``{"env": "NAME"}``) but never the secret itself.  Resolve it only in
    # memory for the eventual Compose environment and keep all reports
    # redacted by EnvironmentPlan/CommandRunner.
    for key, value in tuple(result.items()):
        reference = None
        if isinstance(value, Mapping):
            for candidate in ("env", "environment", "env_var", "env_var_name", "secret_env"):
                if value.get(candidate):
                    reference = str(value[candidate]).strip()
                    break
        elif isinstance(value, str) and value.startswith("env:"):
            reference = value[4:].strip()
        if reference:
            resolved = environment.get(reference) or environment.get(f"LUMEN_{reference}")
            if resolved is None:
                raise InvalidInputError(f"required secret environment variable is missing: {reference}")
            result[key] = resolved
    return result


def _effective_options(options: ComposeOptions | None, state: InstallerState) -> ComposeOptions:
    requested = options if options is not None else ComposeOptions()
    return requested.resolved(saved_profiles=state.profiles, saved_gpu=state.gpu_mode)


def _secret_values(document: DotEnvDocument) -> tuple[str, ...]:
    values = []
    for key, value in document.values.items():
        if _SECRET_KEY.search(key) and value:
            values.append(value)
    return tuple(values)


def _storage_target_input(
    key: str,
    planned: Any,
    *,
    original: DotEnvDocument,
    inputs: Mapping[str, Any],
    root: Path,
) -> Any:
    """Keep storage's symlink/ownership checks on the user's lexical path."""

    value = inputs.get(key, original.get(key, planned))
    if not isinstance(value, (str, Path)):
        return value
    path = Path(os.path.expandvars(os.path.expanduser(str(value))))
    if not path.is_absolute():
        path = root / path
    return str(path)


def _state_and_journal(
    root: Path,
    options: ComposeOptions,
    dry_run: bool,
    *,
    state: InstallerState | None = None,
) -> tuple[InstallerState, StageJournal]:
    if state is not None:
        current = state
    elif dry_run:
        current = InstallerState.load(
            root,
            allowed_stages=FOUNDATION_STAGES,
            correct_modes=False,
        )
    else:
        current = InstallerState.load(root, allowed_stages=FOUNDATION_STAGES)
    profiles = current.profiles if options.profiles is None else options.selected_profiles
    gpu_mode = current.gpu_mode
    if options.gpu is not None:
        gpu_mode = "nvidia" if options.gpu else "none"
    candidate = replace(current, profiles=profiles, gpu_mode=gpu_mode)
    return candidate, StageJournal(candidate, stages=FOUNDATION_STAGES)


def _host(
    supplied: HostFacts | None,
    *,
    uid: int | None,
    gid: int | None,
    timezone: str | None,
    detector: Callable[..., HostFacts],
) -> HostFacts:
    if supplied is not None:
        return supplied
    return _call(detector, uid=uid, gid=gid, timezone=timezone)


def _preflight(runner: CommandRunner, checker: Callable[..., DockerPreflight]) -> DockerPreflight:
    value = _call(checker, runner)
    if isinstance(value, DockerPreflight):
        return value
    if isinstance(value, Mapping) and value.get("status") == "ok":
        return DockerPreflight(status="ok")
    raise InvalidInputError("Docker preflight returned an invalid result")


def _stale_from_runner(
    runner: CommandRunner,
    root: Path,
    project_name: str | None = None,
) -> tuple[StaleContainer, ...]:
    """Inspect only Docker IDs and metadata needed by Task 6's guard."""

    try:
        listed = runner.run(("docker", "ps", "-aq"))
    except (CommandExecutionError, OSError):
        return ()
    ids = [line.strip() for line in listed.stdout.splitlines() if _ID.fullmatch(line.strip())]
    rows: list[Mapping[str, Any]] = []
    for identifier in ids:
        try:
            inspected = runner.run(("docker", "inspect", identifier))
            payload = json.loads(inspected.stdout)
        except (CommandExecutionError, OSError, TypeError, ValueError):
            continue
        if isinstance(payload, list):
            rows.extend(item for item in payload if isinstance(item, Mapping))
        elif isinstance(payload, Mapping):
            rows.append(payload)
    return find_stale_containers(
        rows,
        root,
        known_names=KNOWN_STACK_CONTAINER_NAMES,
        project_name=project_name or _compose_project_name(root),
    )


def _compose_project_name(root: Path) -> str:
    """Mirror Compose's default project-name normalization for stale checks."""

    name = re.sub(r"[^a-z0-9_-]", "", root.name.lower())
    return name or "media"


def _stale(
    runner: CommandRunner,
    root: Path,
    finder: Callable[..., Any] | None,
    project_name: str | None = None,
) -> tuple[StaleContainer, ...]:
    if finder is None:
        return _stale_from_runner(runner, root, project_name)
    value = _call(finder, runner, root)
    if value is None:
        return ()
    result: list[StaleContainer] = []
    for item in value:
        if isinstance(item, StaleContainer):
            result.append(item)
    return tuple(result)


def _remove_stale(
    stale: Sequence[StaleContainer],
    runner: CommandRunner,
    *,
    dry_run: bool,
) -> tuple[str, ...]:
    removed: list[str] = []
    for item in stale:
        identifier = item.execution_identifier
        # Revalidate the object at the mutation boundary.  The identifier is
        # never accepted from a free-form report or interpolated command.
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
            continue
        if item.name not in KNOWN_STACK_CONTAINER_NAMES:
            continue
        argv = item.execution_argv
        if tuple(argv) != ("docker", "rm", "-f", identifier):
            continue
        if not dry_run:
            runner.run(argv)
        removed.append(item.name)
    return tuple(removed)


def clear_stale_containers(
    runner: CommandRunner | Any,
    repo_root: str | Path,
    *,
    dry_run: bool = False,
    stale_finder: Callable[..., Any] | None = None,
    compose_project: str | None = None,
) -> tuple[str, ...]:
    """Discover and (unless dry-run) remove only Task 6-confirmed stale IDs."""

    root = _repo(repo_root)
    found = _stale(runner, root, stale_finder, compose_project)
    return _remove_stale(found, runner, dry_run=dry_run)


def _health_once() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8085/health", timeout=5) as response:
            return 200 <= int(response.status) < 300
    except (OSError, urllib.error.URLError, ValueError):
        return False


def wait_for_health(
    *,
    probe: Callable[[], Any] | None = None,
    timeout: float = DEFAULT_HEALTH_TIMEOUT,
    interval: float = DEFAULT_HEALTH_INTERVAL,
    sleep: Callable[[float], Any] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> bool:
    """Wait a bounded time for homepage-actions and raise exit 4 on timeout."""

    try:
        limit = max(0.0, float(timeout))
        pause = max(0.0, float(interval))
        if not math.isfinite(limit) or not math.isfinite(pause):
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise InvalidInputError("health timeout and interval must be numeric") from exc
    if probe is None:
        probe = _health_once
    started = monotonic()
    # The attempt cap keeps injected clocks/sleep functions from creating an
    # accidental infinite loop while preserving the real-time deadline.
    attempts = 1 if limit == 0 else min(1000, max(2, int(limit / max(pause, 0.001)) + 2))
    for _ in range(attempts):
        try:
            result = probe()
            if isinstance(result, CommandResult):
                healthy = result.returncode == 0
            else:
                status = getattr(result, "status", None)
                if status is not None:
                    try:
                        healthy = 200 <= int(status) < 300
                    except (TypeError, ValueError):
                        healthy = str(status).lower() in {"ok", "healthy", "true"}
                elif isinstance(result, Mapping) and "status" in result:
                    value = result["status"]
                    healthy = str(value).lower() in {"ok", "healthy", "true", "200"}
                else:
                    healthy = bool(result)
        except (OSError, urllib.error.URLError, TimeoutError, ValueError):
            healthy = False
        if healthy:
            return True
        if monotonic() - started >= limit:
            break
        sleep(min(pause, max(0.0, limit - (monotonic() - started))))
    raise PartialError("homepage-actions health check timed out")


@dataclass(frozen=True)
class FoundationResult:
    status: str
    dry_run: bool
    stages_completed: tuple[str, ...]
    options: ComposeOptions
    pulled_services: tuple[str, ...] = ()
    build_services: tuple[str, ...] = ()
    stale_removed: tuple[str, ...] = ()
    health: str = "not-run"
    planned_commands: tuple[tuple[str, ...], ...] = ()
    environment: Mapping[str, Any] | None = None
    storage: Mapping[str, Any] | None = None
    host: Mapping[str, Any] | None = None
    network: Mapping[str, Any] | None = None
    preflight: Mapping[str, Any] | None = None

    @property
    def stages(self) -> tuple[str, ...]:
        return self.stages_completed

    @property
    def commands(self) -> tuple[tuple[str, ...], ...]:
        return self.planned_commands

    @property
    def report(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "dry_run": self.dry_run,
            "stages_completed": list(self.stages_completed),
            "profiles": list(self.options.selected_profiles),
            "gpu": self.options.gpu_enabled,
            "dev": self.options.dev,
            "pulled_services": list(self.pulled_services),
            "build_services": list(self.build_services),
            "stale_removed": list(self.stale_removed),
            "stale_actions": [
                {"name": name, "action": "remove-confirmed-stale-container"}
                for name in self.stale_removed
            ],
            "health": self.health,
            "planned_commands": [list(item) for item in self.planned_commands],
            "environment": _safe_projection(self.environment or {}),
            "storage": _safe_projection(self.storage or {}),
            "host": _safe_projection(self.host or {}),
            "network": _safe_projection(self.network or {}),
            "preflight": _safe_projection(self.preflight or {}),
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report


def run_foundation(
    repo_root: str | Path | None = None,
    *,
    runner: CommandRunner | Any | None = None,
    options: ComposeOptions | None = None,
    env_file: str | Path | None = None,
    answers: Answers | Mapping[str, Any] | None = None,
    answers_path: str | Path | None = None,
    environment: Mapping[str, str] | None = None,
    host: HostFacts | None = None,
    uid: int | None = None,
    gid: int | None = None,
    timezone: str | None = None,
    root_path: str | Path | None = None,
    downloads_path: str | Path | None = None,
    qbt_password: str | None = None,
    network_mode: str | None = None,
    public_host: str | None = None,
    interactive: bool = False,
    dry_run: bool = False,
    stale_finder: Callable[..., Any] | None = None,
    compose_project: str | None = None,
    host_detector: Callable[..., HostFacts] = detect_host,
    preflight_checker: Callable[..., DockerPreflight] = docker_preflight,
    storage_validator: Callable[..., Any] = validate_storage,
    env_writer: Callable[..., Any] = write_atomic,
    health_probe: Callable[[], Any] | None = None,
    health_timeout: float = DEFAULT_HEALTH_TIMEOUT,
    health_interval: float = DEFAULT_HEALTH_INTERVAL,
    sleep: Callable[[float], Any] = time.sleep,
    state: InstallerState | None = None,
    stage_journal: StageJournal | None = None,
    journal: StageJournal | None = None,
) -> FoundationResult:
    """Run the ordered Phase 1 foundation, with every mutation injectable."""

    root = _repo(repo_root)
    env_path = Path(env_file) if env_file is not None else root / ".env"
    if not env_path.is_absolute():
        env_path = root / env_path
    command_runner = runner if runner is not None else CommandRunner()
    requested = options if options is not None else ComposeOptions()
    if stage_journal is not None and journal is not None:
        raise InvalidInputError("provide only one stage journal")
    if stage_journal is not None or journal is not None:
        active_journal = stage_journal or journal
        assert active_journal is not None
        state = active_journal.state
    else:
        state, active_journal = _state_and_journal(root, requested, dry_run, state=state)
    effective = _effective_options(requested, state)
    # A completed foundation with its environment still present is safely
    # idempotent.  Explicit overrides are the caller's request to reconcile
    # again; otherwise avoid repeating pull/build/up mutations.
    explicit_override = any(
        value is not None
        for value in (
            requested.profiles,
            requested.gpu,
            root_path,
            downloads_path,
            network_mode,
            public_host,
        )
    ) or requested.dev
    if active_journal.is_complete("compose") and env_path.exists() and not dry_run and not explicit_override:
        return FoundationResult(
            status="ok",
            dry_run=False,
            stages_completed=active_journal.completed,
            options=effective,
            health="already-complete",
            environment={},
        )
    # Host discovery is intentionally the first foundation operation.  Only
    # after it succeeds do we read/plan dotenv and answers.
    facts = _host(host, uid=uid, gid=gid, timezone=timezone, detector=host_detector)
    if not active_journal.is_complete("host"):
        if not dry_run:
            # Persist selected profiles/GPU only after host discovery has
            # succeeded; a failed host preflight must not leave a new state.
            state.save()
            active_journal.complete("host")
    original_doc = _load_document(env_path)
    answer_values = _answers(answers_path, answers)
    input_values = _inputs(
        answer_values,
        environment=environment or os.environ,
        root_path=root_path,
        downloads_path=downloads_path,
        qbt_password=qbt_password,
    )

    env_plan: EnvironmentPlan = plan_environment(original_doc, facts, input_values)
    if not active_journal.is_complete("environment"):
        if not dry_run:
            active_journal.complete("environment")

    network_plan = plan_network(
        original_doc,
        network_mode if network_mode is not None else input_values.get("NETWORK_MODE"),
        public_host if public_host is not None else input_values.get("PUBLIC_HOST"),
        interactive,
    )
    for key, value in network_plan.values.items():
        env_plan.document.set(key, value)
    secret_values = _secret_values(env_plan.document)
    if not active_journal.is_complete("network"):
        if not dry_run:
            active_journal.complete("network")

    planned_root = env_plan.get("ROOT_PATH")
    planned_downloads = env_plan.get("DOWNLOADS_PATH")
    storage_root = _storage_target_input(
        "ROOT_PATH", planned_root, original=original_doc, inputs=input_values, root=root
    )
    storage_downloads = _storage_target_input(
        "DOWNLOADS_PATH", planned_downloads, original=original_doc, inputs=input_values, root=root
    )
    if active_journal.is_complete("storage"):
        storage = {}
    else:
        storage = _call(
            storage_validator,
            storage_root,
            storage_downloads,
            repo_root=root,
            uid=facts.uid,
            gid=facts.gid,
            dry_run=dry_run,
        )
    if not active_journal.is_complete("storage"):
        if not dry_run:
            active_journal.complete("storage")

    preflight = _preflight(command_runner, preflight_checker)
    if not preflight.ok:
        raise preflight.error or InvalidInputError("Docker preflight failed")
    if not active_journal.is_complete("preflight"):
        if not dry_run:
            active_journal.complete("preflight")

    project = compose_project
    if project is None:
        project = (environment or os.environ).get("COMPOSE_PROJECT_NAME")
    stale = _stale(command_runner, root, stale_finder, project)
    stale_removed = _remove_stale(stale, command_runner, dry_run=dry_run)

    # The environment is committed only after all discovery/preflight checks
    # pass and immediately before Compose consumes it.  Dry-run never reaches
    # this write boundary.
    if not dry_run:
        rendered = env_plan.render()
        try:
            needs_write = not env_path.exists() or env_path.read_text(encoding="utf-8") != rendered
        except OSError as exc:
            raise InvalidInputError("environment could not be read before commit") from exc
        if needs_write:
            try:
                env_writer(env_path, rendered, mode=0o600)
            except (OSError, ValueError) as exc:
                raise InvalidInputError("environment could not be committed atomically") from exc

    config_payload = compose_config(command_runner, root, env_path, effective, redact=secret_values)
    pull_services = derive_pull_services(config_payload)
    build_services = derive_build_services(config_payload)
    planned = [effective.argv(root, env_path, "pull", *pull_services)]
    if build_services:
        planned.append(effective.argv(root, env_path, "build", *build_services))
    planned.append(effective.argv(root, env_path, "up", "-d", "--remove-orphans"))
    if not dry_run:
        compose_pull(command_runner, root, env_path, effective, pull_services, redact=secret_values)
        if build_services:
            compose_build(command_runner, root, env_path, effective, build_services, redact=secret_values)
        compose_up(command_runner, root, env_path, effective, redact=secret_values)
        wait_for_health(
            probe=health_probe,
            timeout=health_timeout,
            interval=health_interval,
            sleep=sleep,
        )
        health = "healthy"
        if not active_journal.is_complete("compose"):
            active_journal.complete("compose")
    else:
        health = "not-run"

    result = FoundationResult(
        status="dry-run" if dry_run else "ok",
        dry_run=dry_run,
        stages_completed=active_journal.completed,
        options=effective,
        pulled_services=pull_services,
        build_services=build_services,
        stale_removed=stale_removed,
        health=health,
        planned_commands=tuple(planned),
        environment=env_plan.display,
        storage=getattr(storage, "report", storage if isinstance(storage, Mapping) else {}),
        host={
            "uid": facts.uid,
            "gid": facts.gid,
            "timezone": facts.timezone,
            "distro_id": facts.distro_id,
            "arch": facts.arch,
        },
        network=network_plan.report,
        preflight=preflight.report,
    )
    return result


def _load_lifecycle(root: Path, options: ComposeOptions | None) -> tuple[Path, InstallerState, ComposeOptions]:
    env_path = root / ".env"
    state = InstallerState.load(root, allowed_stages=FOUNDATION_STAGES)
    return env_path, state, _effective_options(options, state)


def run_up(
    repo_root: str | Path | None = None,
    *,
    runner: CommandRunner | Any | None = None,
    options: ComposeOptions | None = None,
    env_file: str | Path | None = None,
    dry_run: bool = False,
    stale_finder: Callable[..., Any] | None = None,
    compose_project: str | None = None,
) -> FoundationResult:
    root = _repo(repo_root)
    default_env, state, effective = _load_lifecycle(root, options)
    env_path = Path(env_file) if env_file is not None else default_env
    command_runner = runner if runner is not None else CommandRunner()
    stale_removed = _remove_stale(_stale(command_runner, root, stale_finder, compose_project), command_runner, dry_run=dry_run)
    if not dry_run:
        compose_up(command_runner, root, env_path, effective, redact=_secret_values(_load_document(env_path)))
    return FoundationResult("dry-run" if dry_run else "ok", dry_run, state.completed_stages, effective, stale_removed=stale_removed, planned_commands=(effective.argv(root, env_path, "up", "-d", "--remove-orphans"),))


def run_down(
    repo_root: str | Path | None = None,
    *,
    runner: CommandRunner | Any | None = None,
    options: ComposeOptions | None = None,
    env_file: str | Path | None = None,
    dry_run: bool = False,
) -> FoundationResult:
    root = _repo(repo_root)
    default_env, state, effective = _load_lifecycle(root, options)
    env_path = Path(env_file) if env_file is not None else default_env
    command_runner = runner if runner is not None else CommandRunner()
    if not dry_run:
        compose_down(command_runner, root, env_path, effective, redact=_secret_values(_load_document(env_path)))
    return FoundationResult("dry-run" if dry_run else "ok", dry_run, state.completed_stages, effective, planned_commands=(effective.argv(root, env_path, "down"),))


def run_redeploy_dashboard(
    repo_root: str | Path | None = None,
    *,
    runner: CommandRunner | Any | None = None,
    options: ComposeOptions | None = None,
    env_file: str | Path | None = None,
    dry_run: bool = False,
) -> FoundationResult:
    root = _repo(repo_root)
    default_env, state, effective = _load_lifecycle(root, options)
    env_path = Path(env_file) if env_file is not None else default_env
    effective = replace(effective, dev=False)
    command_runner = runner if runner is not None else CommandRunner()
    if not dry_run:
        compose_redeploy_dashboard(command_runner, root, env_path, effective, redact=_secret_values(_load_document(env_path)))
    return FoundationResult("dry-run" if dry_run else "ok", dry_run, state.completed_stages, effective, planned_commands=(effective.argv(root, env_path, "up", "-d", "--build", "--force-recreate", "--remove-orphans", "dashboard"),))


_NODE_VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?")
_COMPARATOR = re.compile(r"(>=|<=|>|<|=|~\s*|\^\s*)?v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _node_tuple(value: str) -> tuple[int, int, int]:
    match = _NODE_VERSION.match(value.strip())
    if match is None:
        raise InvalidInputError("could not determine Node.js version")
    return tuple(int(item or 0) for item in match.groups())  # type: ignore[return-value]


def node_satisfies(version: str, expression: str) -> bool:
    """Small stdlib semver subset sufficient for Angular CLI engine ranges."""

    actual = _node_tuple(version)
    for alternative in str(expression).split("||"):
        tokens = [item for item in re.split(r"\s+", alternative.strip()) if item]
        if not tokens:
            continue
        valid = True
        for token in tokens:
            match = _COMPARATOR.fullmatch(token)
            if match is None:
                valid = False
                break
            operator = (match.group(1) or "=").replace(" ", "")
            target = tuple(int(item or 0) for item in match.groups()[1:])
            if operator == ">=" and not actual >= target:
                valid = False
            elif operator == "<=" and not actual <= target:
                valid = False
            elif operator == ">" and not actual > target:
                valid = False
            elif operator == "<" and not actual < target:
                valid = False
            elif operator == "=" and not actual[:2] == target[:2]:
                valid = False
            elif operator == "^" and not (actual >= target and actual[0] == target[0]):
                valid = False
            elif operator == "~" and not (actual >= target and actual[:2] == target[:2]):
                valid = False
        if valid:
            return True
    return False


def run_frontend_dev(
    repo_root: str | Path | None = None,
    *,
    runner: CommandRunner | Any | None = None,
    dry_run: bool = False,
) -> FoundationResult:
    root = _repo(repo_root)
    dashboard = root / "dashboard-app"
    command_runner = runner if runner is not None else CommandRunner()
    npm_argv = ("npm", "ci")
    if not dry_run:
        command_runner.run(npm_argv, cwd=str(dashboard))
        node_result = command_runner.run(("node", "--version"), cwd=str(dashboard))
        package_path = dashboard / "node_modules" / "@angular" / "cli" / "package.json"
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
            engine = package.get("engines", {}).get("node")
        except (OSError, ValueError, AttributeError):
            metadata = command_runner.run(
                ("node", "-p", "require('@angular/cli/package.json').engines.node"),
                cwd=str(dashboard),
            )
            engine = metadata.stdout.strip()
        if not isinstance(engine, str) or not node_satisfies(node_result.stdout, engine):
            raise InvalidInputError("host Node.js version does not satisfy Angular CLI engines")
    return FoundationResult("dry-run" if dry_run else "ok", dry_run, (), ComposeOptions(), planned_commands=(npm_argv,))


def doctor_diagnostics(
    repo_root: str | Path | None = None,
    *,
    host_report: Mapping[str, Any] | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Read-only env/network/storage/state diagnostics for ``doctor``."""

    root = _repo(repo_root)
    env_path = root / ".env"
    report: dict[str, Any] = {"host_docker": dict(host_report or {}), "status": "ok"}
    try:
        document = _load_document(env_path)
        values = document.values
        report["environment"] = {
            "present": env_path.exists(),
            "keys": sorted(values),
            "configured": {key: key in values and bool(values[key]) for key in ("ROOT_PATH", "DOWNLOADS_PATH", "ACTIONS_TOKEN")},
        }
        try:
            report["network"] = plan_network(values, None, None, False).report
        except (InvalidInputError, DriftError) as exc:
            report["network"] = {"status": "needs-attention", "error": str(exc)}
        storage_values = (values.get("ROOT_PATH"), values.get("DOWNLOADS_PATH"))
        if all(storage_values):
            try:
                checked = validate_storage(*storage_values, repo_root=root, dry_run=True)
                report["storage"] = checked.report
            except InvalidInputError as exc:
                report["storage"] = {"status": "needs-attention", "error": str(exc)}
        else:
            report["storage"] = {"status": "not-configured"}
    except InvalidInputError as exc:
        report["status"] = "needs-attention"
        report["environment"] = {"status": "needs-attention", "error": str(exc)}
    try:
        state = InstallerState.load(root, allowed_stages=FOUNDATION_STAGES, correct_modes=False)
        report["state"] = state.report
    except InvalidInputError as exc:
        report["status"] = "needs-attention"
        report["state"] = {"status": "needs-attention", "error": str(exc)}
    return report


# Public spelling used by the CLI contract and compatibility aliases for
# integrations that call the phase by its action name.
run_setup = run_foundation
setup = run_foundation
frontend_dev = run_frontend_dev
redeploy_dashboard = run_redeploy_dashboard
run_doctor = doctor_diagnostics


__all__ = [
    "DEFAULT_HEALTH_INTERVAL",
    "DEFAULT_HEALTH_TIMEOUT",
    "FOUNDATION_STAGES",
    "FoundationResult",
    "doctor_diagnostics",
    "run_doctor",
    "clear_stale_containers",
    "node_satisfies",
    "run_down",
    "run_foundation",
    "run_frontend_dev",
    "run_redeploy_dashboard",
    "run_up",
    "run_setup",
    "setup",
    "frontend_dev",
    "redeploy_dashboard",
    "wait_for_health",
]
