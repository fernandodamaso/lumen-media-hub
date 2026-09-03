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
import platform as stdlib_platform
import re
import stat
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import fcntl

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
from .gpu import GpuCapabilityError, gpu_diagnostics, gpu_environment, overlay_for_mode, resolve_gpu
from .platform import HostFacts, detect_host
from .state import DEFAULT_STAGES, InstallerState, StageJournal
from .storage import KNOWN_STACK_CONTAINER_NAMES, StaleContainer, find_stale_containers, validate_storage
from .network import plan_network
from .answers import Answers, Resolver


FOUNDATION_STAGES = tuple(DEFAULT_STAGES)
DEFAULT_HEALTH_TIMEOUT = 120.0
DEFAULT_HEALTH_INTERVAL = 5.0
DEFAULT_ROOT_PATH = "/srv/lumen-media"
DEFAULT_DOWNLOADS_PATH = "/srv/lumen-downloads"
_ID = re.compile(r"^[0-9a-fA-F]{12,64}$")
_GPU_GID = re.compile(r"^[0-9]+$")
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


def _direct_answer_value(answers: Mapping[str, Any] | None, key: str) -> tuple[bool, Any]:
    if answers is None:
        return False, None
    for name, value in answers.items():
        if str(name).upper() == key:
            return True, value
    return False, None


def _answer_secret_reference(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            candidate in value and value[candidate]
            for candidate in ("env", "environment", "env_var", "env_var_name", "secret_env")
        )
    return isinstance(value, str) and value.startswith("env:")


def _direct_answers_changed(answers: Mapping[str, Any] | None, env_path: Path) -> bool:
    """Detect effective direct-answer changes without exposing secret values."""

    if answers is None:
        return False
    existing = _load_document(env_path).values
    for key in (
        "ROOT_PATH",
        "DOWNLOADS_PATH",
        "PUID",
        "PGID",
        "TZ",
        "QBT_PASSWORD",
        "STACK_PASSWORD",
        "NETWORK_MODE",
        "PUBLIC_HOST",
    ):
        present, value = _direct_answer_value(answers, key)
        if not present or value is None or (isinstance(value, str) and not value.strip()):
            continue
        # Secret references may resolve from process state and therefore cannot
        # be compared to the persisted value without coupling this read-only
        # invalidation check to credential resolution.  Reconcile safely.
        if key in {"QBT_PASSWORD", "STACK_PASSWORD"} and _answer_secret_reference(value):
            return True
        current = existing.get(key)
        if current is None:
            return True
        if key in {"ROOT_PATH", "DOWNLOADS_PATH"}:
            try:
                candidate = Path(os.path.abspath(os.path.expanduser(os.path.expandvars(str(value)))))
                persisted = Path(os.path.abspath(os.path.expanduser(os.path.expandvars(str(current)))))
            except (TypeError, ValueError, OSError):
                return True
            if candidate != persisted:
                return True
        elif str(value).strip() != str(current).strip():
            return True
    return False


def _inputs(
    answers: Mapping[str, Any],
    *,
    environment: Mapping[str, str],
    root_path: str | Path | None,
    downloads_path: str | Path | None,
    qbt_password: str | None = None,
    existing: Mapping[str, Any] | None = None,
    interactive: bool = False,
    prompt: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    result = dict(answers)
    for name, value in (("ROOT_PATH", root_path), ("DOWNLOADS_PATH", downloads_path)):
        if value is not None and (not isinstance(value, (str, Path)) or not str(value).strip()):
            raise InvalidInputError(f"{name} must not be empty")
    # Only process environment values with the explicit LUMEN_ namespace are
    # consulted by the Linux installer.  This prevents an unrelated shell
    # credential from becoming an accidental report/input source.
    for key in ("QBT_PASSWORD", "STACK_PASSWORD", "PUBLIC_HOST", "NETWORK_MODE"):
        ref = f"LUMEN_{key}"
        if ref in environment and environment[ref] != "":
            result[key] = environment[ref]
    # Resolver is the one source of truth for required paths.  Existing .env
    # values act as defaults for an adopted install, while a fresh install
    # gets safe, explicit defaults only in interactive mode.  CLI values are
    # kept separate so the precedence remains CLI > LUMEN_* > answers >
    # prompt/default.
    cli_values = {
        key: value
        for key, value in {
            "ROOT_PATH": root_path,
            "DOWNLOADS_PATH": downloads_path,
        }.items()
        if value is not None
    }
    defaults: dict[str, Any] = {}
    for key in ("ROOT_PATH", "DOWNLOADS_PATH"):
        existing_value = existing.get(key) if existing is not None else None
        placeholder = str(existing_value).strip() in {
            ".",
            "./downloads",
            "downloads",
        }
        if existing_value and not placeholder:
            defaults[key] = existing_value
        elif interactive:
            defaults[key] = {
                "ROOT_PATH": DEFAULT_ROOT_PATH,
                "DOWNLOADS_PATH": DEFAULT_DOWNLOADS_PATH,
            }[key]
    resolver = Resolver(defaults=defaults, noninteractive=not interactive)
    for key in ("ROOT_PATH", "DOWNLOADS_PATH"):
        result[key] = resolver.get(key, cli_values, environment, answers, prompt)
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


def _commit_gpu_environment(
    path: Path,
    values: Mapping[str, str],
    *,
    writer: Callable[..., Any] = write_atomic,
) -> DotEnvDocument:
    """Atomically add GPU-only Compose values before an activation boundary."""

    document = _load_document(path)
    for key, value in values.items():
        document.set(key, value)
    rendered = document.render()
    try:
        current = path.read_text(encoding="utf-8") if path.exists() else None
        metadata = path.lstat() if path.exists() else None
        mode_needs_fix = (
            metadata is None
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
        )
    except OSError as exc:
        raise InvalidInputError("GPU environment could not be read before commit") from exc
    if current != rendered or mode_needs_fix:
        try:
            writer(path, rendered, mode=0o600)
        except (OSError, ValueError) as exc:
            raise InvalidInputError("GPU environment could not be committed atomically") from exc
    return document


def _planning_gpu_environment(result: Any) -> dict[str, str]:
    """Copy only already-numeric VA-API IDs into a disposable plan.

    Dry-runs intentionally do not call :func:`gpu_environment`: that helper
    enforces activation-time requirements and would reject an injected probe
    that omits host group IDs.  A preview can retain complete injected IDs,
    while the planning environment supplies placeholders for anything absent.
    """

    if getattr(result, "mode", None) != "vaapi":
        return {}
    values: dict[str, str] = {}
    for key, attribute in (("RENDER_GID", "render_gid"), ("VIDEO_GID", "video_gid")):
        value = getattr(result, attribute, None)
        if value is None or isinstance(value, bool):
            continue
        text = str(value).strip()
        if _GPU_GID.fullmatch(text):
            values[key] = text
    return values


@contextmanager
def _compose_planning_environment(
    path: Path,
    document: DotEnvDocument,
    *,
    gpu_mode: str,
    dry_run: bool,
):
    """Provide a disposable, safe Compose env for uncommitted GPU previews."""

    if not dry_run or (gpu_mode != "vaapi" and path.exists()):
        yield path
        return

    planning = DotEnvDocument.parse(document.render())
    # Compose's VA-API overlay requires numeric values even when this is only
    # a preview.  Prefer discovered values, otherwise use inert placeholders
    # solely in the disposable planning file.
    if gpu_mode == "vaapi":
        render_gid = planning.get("RENDER_GID")
        if not isinstance(render_gid, str) or not _GPU_GID.fullmatch(render_gid.strip()):
            planning.set("RENDER_GID", "65534")
        video_gid = planning.get("VIDEO_GID")
        if not isinstance(video_gid, str) or not _GPU_GID.fullmatch(video_gid.strip()):
            planning.set("VIDEO_GID", "65533")

    fd, temporary_name = tempfile.mkstemp(prefix=".lumen-gpu-dry-run-", suffix=".env")
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            fd = -1
            stream.write(planning.render())
            stream.flush()
        yield temporary_path
    except (OSError, ValueError) as exc:
        raise InvalidInputError("GPU planning environment could not be prepared") from exc
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


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
    reset_on_change: bool = False,
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
        gpu_mode = options.gpu_mode
    candidate = replace(current, profiles=profiles, gpu_mode=gpu_mode)
    if reset_on_change and candidate.completed_stages:
        # Answers/host/storage changes invalidate the ordered mutations.  The
        # journal is deliberately reset before the next stage can be marked,
        # so a resumed run cannot skip a validation or commit boundary.
        candidate = replace(candidate, completed_stages=())
    return candidate, StageJournal(candidate, stages=FOUNDATION_STAGES)


@contextmanager
def _lifecycle_lock(root: Path, *, dry_run: bool):
    """Serialize mutating lifecycle runs without making dry-run state."""

    lock_directory = root / ".state" / "installer"
    lock_path = lock_directory / "lifecycle.lock"
    if dry_run and not lock_path.exists():
        # A dry run is discovery-only.  In particular, do not create the
        # ignored state tree merely to take a lock that cannot protect a
        # mutation.
        yield
        return
    fd: int | None = None
    try:
        try:
            if not dry_run:
                for directory in (lock_directory.parent, lock_directory):
                    try:
                        metadata = directory.lstat()
                    except FileNotFoundError:
                        try:
                            directory.mkdir(mode=0o700)
                        except FileExistsError:
                            # Another installer may have won the directory
                            # race; inspect the winner before touching it.
                            pass
                        metadata = directory.lstat()
                    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                        raise InvalidInputError("installer lifecycle lock directory is unsafe")
                    os.chmod(directory, 0o700)
            try:
                lock_metadata = lock_path.lstat()
            except FileNotFoundError:
                lock_metadata = None
            if lock_metadata is not None and (
                stat.S_ISLNK(lock_metadata.st_mode)
                or not stat.S_ISREG(lock_metadata.st_mode)
            ):
                raise InvalidInputError("installer lifecycle lock is not a regular file")
            fd = os.open(
                lock_path,
                os.O_RDWR | (os.O_CREAT if not dry_run else 0) | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            if not dry_run:
                os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_SH if dry_run else fcntl.LOCK_EX)
        except FileNotFoundError:
            if not dry_run:
                raise InvalidInputError("installer lifecycle lock could not be created")
            yield
            return
        except OSError as exc:
            raise InvalidInputError("installer lifecycle lock could not be acquired") from exc
        yield
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(fd)
            except OSError:
                pass


def _guard_storage_targets(root_path: Any, downloads_path: Any, repo: Path) -> None:
    """Reject broad/overlapping targets before an injected validator runs."""

    try:
        media = Path(root_path)
        downloads = Path(downloads_path)
    except (TypeError, ValueError, OSError) as exc:
        raise InvalidInputError("storage paths are invalid") from exc
    if not media.is_absolute() or not downloads.is_absolute():
        raise InvalidInputError("storage paths must be absolute")
    if "\x00" in str(media) or "\x00" in str(downloads):
        raise InvalidInputError("storage paths are invalid")
    media = Path(os.path.abspath(str(media)))
    downloads = Path(os.path.abspath(str(downloads)))
    broad = {
        Path("/"), Path("/bin"), Path("/boot"), Path("/dev"), Path("/etc"),
        Path("/home"), Path("/lib"), Path("/media"), Path("/mnt"), Path("/opt"),
        Path("/proc"), Path("/root"), Path("/run"), Path("/sbin"), Path("/srv"),
        Path("/sys"), Path("/tmp"), Path("/usr"), Path("/var"),
    }
    if media in broad or downloads in broad:
        raise InvalidInputError("storage targets are too broad")
    if media == repo or repo in media.parents or media in repo.parents:
        raise InvalidInputError("media path must be outside the repository")
    if downloads == repo or repo in downloads.parents or downloads in repo.parents:
        raise InvalidInputError("downloads path must be outside the repository")
    if media == downloads or media in downloads.parents or downloads in media.parents:
        raise InvalidInputError("media and downloads must not overlap")
    for path, label in ((media, "ROOT_PATH"), (downloads, "DOWNLOADS_PATH")):
        current = Path(path.anchor)
        for component in path.parts[1:]:
            current /= component
            try:
                metadata = current.lstat()
            except FileNotFoundError:
                continue
            except (OSError, ValueError) as exc:
                raise InvalidInputError(f"{label} cannot be inspected safely") from exc
            if stat.S_ISLNK(metadata.st_mode):
                raise InvalidInputError(f"{label} must not contain symlink components")


def _host(
    supplied: HostFacts | None,
    *,
    uid: int | None,
    gid: int | None,
    timezone: str | None,
    detector: Callable[..., HostFacts],
) -> HostFacts:
    if supplied is not None:
        overrides: dict[str, Any] = {}
        for name, value in (("uid", uid), ("gid", gid), ("timezone", timezone)):
            if value is not None:
                if name in {"uid", "gid"}:
                    try:
                        value = int(value)
                    except (TypeError, ValueError) as exc:
                        raise InvalidInputError(f"{name} must be a nonzero integer") from exc
                    if value <= 0:
                        raise InvalidInputError(f"{name} must be a nonzero integer")
                overrides[name] = value
        return replace(supplied, **overrides) if overrides else supplied
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
    # Compose project names must begin with an alphanumeric character.  Its
    # normalization removes leading separators rather than retaining them.
    name = name.lstrip("_-")
    return name or "media"


def _stale(
    runner: CommandRunner,
    root: Path,
    finder: Callable[..., Any] | None,
    project_name: str | None = None,
) -> tuple[StaleContainer, ...]:
    if finder is None:
        return _stale_from_runner(runner, root, project_name)
    value = _call(finder, runner, root, project_name=project_name)
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
    gpu: Mapping[str, Any] | None = None

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
            "gpu_mode": self.options.gpu_mode,
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
            "gpu_details": _safe_projection(self.gpu or {}),
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report


def _run_foundation_unlocked(
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
    prompt: Callable[..., Any] | None = None,
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
    gpu_detector: Callable[..., Any] | None = None,
    gpu_confirm: bool | Callable[..., Any] = False,
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
    process_environment = environment if environment is not None else os.environ
    answer_values = _answers(answers_path, answers)
    environment_override = environment is not None or any(
        f"LUMEN_{key}" in process_environment
        for key in (
            "ROOT_PATH",
            "DOWNLOADS_PATH",
            "QBT_PASSWORD",
            "STACK_PASSWORD",
            "PUBLIC_HOST",
            "NETWORK_MODE",
        )
    )
    direct_answers_changed = _direct_answers_changed(answer_values, env_path)
    explicit_override = any(
        value is not None
        for value in (
            requested.profiles,
            requested.gpu,
            environment if environment is not None else None,
            env_file,
            uid,
            gid,
            timezone,
            root_path,
            downloads_path,
            qbt_password,
            network_mode,
            public_host,
        )
    ) or requested.dev or environment_override or direct_answers_changed
    if stage_journal is not None and journal is not None:
        raise InvalidInputError("provide only one stage journal")
    if stage_journal is not None or journal is not None:
        active_journal = stage_journal or journal
        assert active_journal is not None
        state = active_journal.state
        if explicit_override:
            profiles = state.profiles if requested.profiles is None else requested.selected_profiles
            gpu_mode = state.gpu_mode
            if requested.gpu is not None:
                gpu_mode = requested.gpu_mode
            state = replace(state, profiles=profiles, gpu_mode=gpu_mode, completed_stages=())
            # A dry run gets a private reconciled view.  Mutating runs keep the
            # caller's journal in sync; the first completed stage then persists
            # this state through the normal atomic path.
            if dry_run:
                active_journal = StageJournal(state, stages=active_journal.stages)
            else:
                active_journal._state = state
    else:
        state, active_journal = _state_and_journal(
            root,
            requested,
            dry_run,
            state=state,
            reset_on_change=explicit_override,
        )
    effective = _effective_options(requested, state)
    # A completed foundation with its environment still present is safely
    # idempotent.  Explicit overrides are the caller's request to reconcile
    # again; otherwise avoid repeating pull/build/up mutations.
    try:
        env_metadata = env_path.lstat()
        env_permissions_ok = (
            stat.S_ISREG(env_metadata.st_mode)
            and stat.S_IMODE(env_metadata.st_mode) == 0o600
        )
    except OSError:
        env_permissions_ok = False
    if (
        active_journal.is_complete("compose")
        and env_permissions_ok
        and not dry_run
        and not explicit_override
    ):
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
    seeded_doc = original_doc
    if not original_doc.values:
        example_path = root / ".env.example"
        if example_path.exists():
            template = _load_document(example_path)
            # The template supplies the Compose defaults, while an empty or
            # comment-only user file still contributes every comment/unknown
            # line to the lossless document before managed keys are changed.
            try:
                template_text = template.render()
                existing_text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
            except OSError as exc:
                raise InvalidInputError("environment could not be read before seeding") from exc
            separator = "" if template_text.endswith(("\n", "\r")) or not existing_text else "\n"
            seeded_doc = DotEnvDocument.parse(template_text + separator + existing_text)
    input_values = _inputs(
        answer_values,
        environment=process_environment,
        root_path=root_path,
        downloads_path=downloads_path,
        qbt_password=qbt_password,
        existing=original_doc.values,
        interactive=interactive,
        prompt=prompt,
    )

    env_plan: EnvironmentPlan = plan_environment(
        seeded_doc,
        facts,
        input_values,
        fresh_setup=not bool(original_doc.values),
        force_host_facts=(
            not bool(original_doc.values)
            or any(value is not None for value in (uid, gid, timezone))
        ),
        force_credentials=(
            qbt_password is not None
            or any(str(key).upper() == "QBT_PASSWORD" for key in input_values)
        ),
    )
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
    _guard_storage_targets(storage_root, storage_downloads, root)
    storage_changed = any(value is not None for value in (root_path, downloads_path))
    if active_journal.is_complete("storage") and not storage_changed:
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

    # GPU probing is read-only and runs after Docker preflight so the NVIDIA
    # container runtime and VA-API ffmpeg checks can use the same injected
    # command boundary.  A detected ``auto`` candidate is never selected
    # without the caller's explicit confirmation.
    gpu_detail: Mapping[str, Any] = {}
    if effective.gpu_mode != "none":
        if dry_run and gpu_detector is None:
            # A foundation dry-run is discovery-only.  Running a Docker GPU
            # probe here can pull an image and mutate the host image cache.
            # Keep the requested overlay visible in the planned command while
            # making its capability explicitly unverified.
            gpu_detail = {
                "requested_mode": effective.gpu_mode,
                "mode": effective.gpu_mode,
                "detected_mode": "none",
                "status": "unverified",
                "available": False,
                "checks": {},
                "overlay": overlay_for_mode(effective.gpu_mode),
                "reason": "GPU probes are skipped during dry-run",
            }
        else:
            facts_arch = facts.arch
            try:
                resolved = resolve_gpu(
                    effective.gpu_mode,
                    detector=gpu_detector,
                    confirm=gpu_confirm,
                    noninteractive=not interactive,
                    runner=command_runner,
                    architecture=facts_arch,
                )
            except (DriftError, GpuCapabilityError):
                if not dry_run:
                    raise
                gpu_detail = {
                    "requested_mode": effective.gpu_mode,
                    "mode": effective.gpu_mode,
                    "detected_mode": "none",
                    "status": "unverified",
                    "available": False,
                    "checks": {},
                    "overlay": overlay_for_mode(effective.gpu_mode),
                    "reason": "GPU activation is skipped during dry-run",
                }
            else:
                effective = replace(effective, gpu=resolved.mode)
                gpu_detail = resolved.report
                if dry_run:
                    gpu_detail = {
                        **gpu_detail,
                        "status": "unverified",
                        "available": False,
                        "overlay": overlay_for_mode(resolved.mode),
                        "reason": "GPU activation is skipped during dry-run",
                    }
                if resolved.mode == "vaapi":
                    planned_gpu_environment = (
                        _planning_gpu_environment(resolved)
                        if dry_run
                        else gpu_environment(resolved)
                    )
                    for key, value in planned_gpu_environment.items():
                        env_plan.document.set(key, value)
                # Save the resolved mode before the next journal stage reads
                # the durable state.  This is especially important for a
                # confirmed ``auto`` choice, which must not remain ``auto``
                # and ask for confirmation on the next lifecycle run.
                if not dry_run and active_journal.state.gpu_mode != resolved.mode:
                    active_journal._state = replace(active_journal.state, gpu_mode=resolved.mode)
                    active_journal._state.save()

    project = compose_project
    if project is None:
        project = process_environment.get("COMPOSE_PROJECT_NAME")
    if project is None:
        project = env_plan.document.get("COMPOSE_PROJECT_NAME")
    if project is None:
        project = original_doc.get("COMPOSE_PROJECT_NAME")
    if isinstance(project, str):
        project = project.strip() or None
    stale = _stale(command_runner, root, stale_finder, project)
    stale_removed = _remove_stale(stale, command_runner, dry_run=dry_run)

    # The environment is committed only after all discovery/preflight checks
    # pass and immediately before Compose consumes it.  Dry-run never reaches
    # this write boundary.
    if not dry_run:
        rendered = env_plan.render()
        try:
            needs_write = not env_path.exists() or env_path.read_text(encoding="utf-8") != rendered
            try:
                mode_needs_fix = (
                    not stat.S_ISREG(env_path.lstat().st_mode)
                    or stat.S_IMODE(env_path.lstat().st_mode) != 0o600
                )
            except OSError:
                mode_needs_fix = True
        except OSError as exc:
            raise InvalidInputError("environment could not be read before commit") from exc
        if needs_write or mode_needs_fix:
            try:
                env_writer(env_path, rendered, mode=0o600)
            except (OSError, ValueError) as exc:
                raise InvalidInputError("environment could not be committed atomically") from exc

    with _compose_planning_environment(
        env_path,
        env_plan.document,
        gpu_mode=effective.gpu_mode,
        dry_run=dry_run,
    ) as planning_env_path:
        config_payload = compose_config(
            command_runner,
            root,
            planning_env_path,
            effective,
            redact=secret_values,
        )
    pull_services = derive_pull_services(config_payload)
    build_services = derive_build_services(config_payload)
    planned = [effective.argv(root, env_path, "pull", *pull_services)]
    if build_services:
        planned.append(effective.argv(root, env_path, "build", *build_services))
    planned.append(effective.argv(root, env_path, "up", "-d"))
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
        gpu=gpu_detail,
    )
    return result


def run_foundation(*args: Any, **kwargs: Any) -> FoundationResult:
    """Run foundation while serializing all lifecycle mutations."""

    repo_value = kwargs.get("repo_root", args[0] if args else None)
    root = _repo(repo_value)
    dry_run = bool(kwargs.get("dry_run", False))
    # Host discovery is intentionally outside the advisory lock: a failed
    # detector must not create installer state, and the foundation order
    # remains host -> dotenv/network planning -> mutations.  Pass the facts
    # through so the unlocked implementation does not detect twice.
    if kwargs.get("host") is None:
        detector = kwargs.get("host_detector", detect_host)
        discovered = _host(
            None,
            uid=kwargs.get("uid"),
            gid=kwargs.get("gid"),
            timezone=kwargs.get("timezone"),
            detector=detector,
        )
        kwargs = dict(kwargs)
        kwargs["host"] = discovered
    with _lifecycle_lock(root, dry_run=dry_run):
        return _run_foundation_unlocked(*args, **kwargs)


def _load_lifecycle(
    root: Path,
    options: ComposeOptions | None,
    *,
    dry_run: bool = False,
) -> tuple[Path, InstallerState, ComposeOptions]:
    env_path = root / ".env"
    state = InstallerState.load(
        root,
        allowed_stages=FOUNDATION_STAGES,
        correct_modes=not dry_run,
    )
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
    gpu_detector: Callable[..., Any] | None = None,
    gpu_confirm: bool | Callable[..., Any] = False,
    gpu_architecture: str | None = None,
    env_writer: Callable[..., Any] = write_atomic,
) -> FoundationResult:
    root = _repo(repo_root)
    with _lifecycle_lock(root, dry_run=dry_run):
        default_env, state, effective = _load_lifecycle(root, options, dry_run=dry_run)
        env_path = Path(env_file) if env_file is not None else default_env
        if not env_path.is_absolute():
            env_path = root / env_path
        command_runner = runner if runner is not None else CommandRunner()
        project = compose_project
        if project is None:
            project = os.environ.get("COMPOSE_PROJECT_NAME")
        if project is None:
            project = _load_document(env_path).get("COMPOSE_PROJECT_NAME")
        if isinstance(project, str):
            project = project.strip() or None
        gpu_detail: Mapping[str, Any] = {}
        gpu_environment_values: Mapping[str, str] = {}
        if effective.gpu_mode != "none":
            # ``up`` is an activation boundary too. Validate hardware before
            # stale cleanup or Compose startup; a dry-run never saves state.
            if dry_run and gpu_detector is None:
                # A lifecycle dry-run is discovery-only.  Running ``docker
                # run`` here could pull a probe image and make a supposedly
                # read-only preview mutate the host image cache.  Keep the
                # requested overlay in the planned argv, but mark capability
                # as unverified so the report cannot be mistaken for a green
                # activation check.
                gpu_detail = {
                    "requested_mode": effective.gpu_mode,
                    "mode": effective.gpu_mode,
                    "detected_mode": "none",
                    "status": "unverified",
                    "available": False,
                    "checks": {},
                    "overlay": overlay_for_mode(effective.gpu_mode),
                    "reason": "GPU probes are skipped during dry-run",
                }
            else:
                try:
                    resolved = resolve_gpu(
                        effective.gpu_mode,
                        detector=gpu_detector,
                        confirm=gpu_confirm,
                        noninteractive=not bool(gpu_confirm),
                        runner=command_runner,
                        architecture=gpu_architecture or stdlib_platform.machine(),
                    )
                except (DriftError, GpuCapabilityError):
                    if not dry_run:
                        raise
                    gpu_detail = {
                        "requested_mode": effective.gpu_mode,
                        "mode": effective.gpu_mode,
                        "detected_mode": "none",
                        "status": "unverified",
                        "available": False,
                        "checks": {},
                        "overlay": overlay_for_mode(effective.gpu_mode),
                        "reason": "GPU activation is skipped during dry-run",
                    }
                else:
                    effective = replace(effective, gpu=resolved.mode)
                    gpu_detail = resolved.report
                    gpu_environment_values = (
                        _planning_gpu_environment(resolved)
                        if dry_run
                        else gpu_environment(resolved)
                    )
                    if dry_run:
                        gpu_detail = {
                            **gpu_detail,
                            "status": "unverified",
                            "available": False,
                            "overlay": overlay_for_mode(resolved.mode),
                            "reason": "GPU activation is skipped during dry-run",
                        }

            if gpu_environment_values:
                gpu_detail = {**gpu_detail, "environment": dict(gpu_environment_values)}
                if not dry_run:
                    _commit_gpu_environment(env_path, gpu_environment_values, writer=env_writer)

        # Persist explicit lifecycle choices just as setup does.  Dry-runs
        # intentionally keep both the environment and state untouched.
        if not dry_run and (
            state.gpu_mode != effective.gpu_mode
            or options is not None
            and (options.gpu is not None or options.profiles is not None)
        ):
            state = replace(
                state,
                gpu_mode=effective.gpu_mode,
                profiles=effective.selected_profiles,
            )
            state.save()
        stale_removed = _remove_stale(_stale(command_runner, root, stale_finder, project), command_runner, dry_run=dry_run)
        if not dry_run:
            compose_up(command_runner, root, env_path, effective, redact=_secret_values(_load_document(env_path)))
        return FoundationResult(
            "dry-run" if dry_run else "ok",
            dry_run,
            state.completed_stages,
            effective,
            stale_removed=stale_removed,
            planned_commands=(effective.argv(root, env_path, "up", "-d"),),
            gpu=gpu_detail,
        )


def run_down(
    repo_root: str | Path | None = None,
    *,
    runner: CommandRunner | Any | None = None,
    options: ComposeOptions | None = None,
    env_file: str | Path | None = None,
    dry_run: bool = False,
) -> FoundationResult:
    root = _repo(repo_root)
    with _lifecycle_lock(root, dry_run=dry_run):
        default_env, state, effective = _load_lifecycle(root, options, dry_run=dry_run)
        env_path = Path(env_file) if env_file is not None else default_env
        if not env_path.is_absolute():
            env_path = root / env_path
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
    with _lifecycle_lock(root, dry_run=dry_run):
        default_env, state, effective = _load_lifecycle(root, options, dry_run=dry_run)
        env_path = Path(env_file) if env_file is not None else default_env
        if not env_path.is_absolute():
            env_path = root / env_path
        effective = replace(effective, dev=False)
        command_runner = runner if runner is not None else CommandRunner()
        if not dry_run:
            compose_redeploy_dashboard(command_runner, root, env_path, effective, redact=_secret_values(_load_document(env_path)))
        return FoundationResult("dry-run" if dry_run else "ok", dry_run, state.completed_stages, effective, planned_commands=(effective.argv(root, env_path, "up", "-d", "--build", "--force-recreate", "dashboard"),))


_NODE_VERSION = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")
_SEMVER_TOKEN = re.compile(
    r"^(?P<operator>>=|<=|>|<|=|~|\^)?\s*v?(?P<major>\d+)"
    r"(?:\.(?P<minor>\d+|[xX*]))?(?:\.(?P<patch>\d+|[xX*]))?$"
)


def _node_tuple(value: str) -> tuple[int, int, int]:
    match = _NODE_VERSION.match(value.strip())
    if match is None:
        raise InvalidInputError("could not determine Node.js version")
    return tuple(int(item or 0) for item in match.groups())  # type: ignore[return-value]


def node_satisfies(version: str, expression: str) -> bool:
    """Small stdlib semver subset sufficient for Angular CLI engine ranges."""

    actual = _node_tuple(version)
    for alternative in str(expression).split("||"):
        # Operators and versions may be separated by whitespace (npm accepts
        # both ``>=22.0.0`` and ``>= 22.0.0``).
        tokens = [item for item in re.findall(r"(?:>=|<=|>|<|=|~|\^)\s*\d[^\s]*|\d[^\s]*", alternative.strip()) if item]
        if not tokens:
            continue
        valid = True
        for token in tokens:
            match = _SEMVER_TOKEN.fullmatch(token)
            if match is None:
                valid = False
                break
            operator = match.group("operator") or "="
            raw_major = match.group("major")
            raw_minor = match.group("minor")
            raw_patch = match.group("patch")
            target_parts = tuple(
                int(item) if item is not None and item not in {"x", "X", "*"} else 0
                for item in (raw_major, raw_minor, raw_patch)
            )
            specified = 1 + (raw_minor is not None) + (raw_patch is not None)
            target = target_parts
            if operator == ">=" and not actual >= target:
                valid = False
            elif operator == "<=" and not actual <= target:
                valid = False
            elif operator == ">" and not actual > target:
                valid = False
            elif operator == "<" and not actual < target:
                valid = False
            elif operator == "=":
                if specified == 1 and actual[0] != target[0]:
                    valid = False
                elif specified == 2 and actual[:2] != target[:2]:
                    valid = False
                elif specified >= 3 and actual != target:
                    valid = False
            elif operator == "^":
                if target[0] != 0:
                    upper = (target[0] + 1, 0, 0)
                elif target[1] != 0:
                    upper = (0, target[1] + 1, 0)
                else:
                    upper = (0, 0, target[2] + 1)
                if not (actual >= target and actual < upper):
                    valid = False
            elif operator == "~":
                upper = (target[0], target[1] + 1, 0) if specified >= 2 else (target[0] + 1, 0, 0)
                if not (actual >= target and actual < upper):
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
    gpu_mode: str | None = None,
    gpu_detector: Callable[..., Any] | None = None,
    runner: CommandRunner | Any | None = None,
) -> dict[str, Any]:
    """Read-only env/network/storage/state diagnostics for ``doctor``."""

    root = _repo(repo_root)
    env_path = root / ".env"
    report: dict[str, Any] = {
        "host_docker": dict(host_report or {}),
        "status": "ok",
        "exit_code": 0,
    }

    def issue(error: Exception, code: int) -> None:
        report["status"] = "needs-attention"
        # A partial/health problem is the most actionable result when several
        # read-only checks fail; otherwise retain the typed drift/invalid code.
        report["exit_code"] = max(int(report.get("exit_code", 0)), code)
        report.setdefault("errors", []).append(str(error))

    def detail_code(detail: Any, *, default: int = 0) -> int:
        """Map nested diagnostic detail to the public severity codes."""

        if not isinstance(detail, Mapping):
            return 0
        nested = detail.get("exit_code")
        nested_code = 0
        if isinstance(nested, int) and not isinstance(nested, bool) and nested > 0:
            nested_code = nested if nested in {2, 3, 4} else 2
        status = str(detail.get("status", "")).strip().lower()
        if detail.get("drift"):
            return max(nested_code, 3)
        status_code = 0
        if status in {"partial", "incomplete", "degraded", "health", "unhealthy"}:
            status_code = 4
        elif "health" in status or "partial" in status or "incomplete" in status:
            status_code = 4
        elif status in {"drift", "warning", "needs-approval", "unapproved"}:
            status_code = 3
        elif status in {
            "invalid", "error", "failed", "failure", "unsupported", "not-configured",
            "missing", "unavailable", "needs-attention",
        } or detail.get("error"):
            status_code = default or 2
        elif status and status not in {"ok", "supported", "healthy", "available", "disabled"}:
            status_code = default
        return max(nested_code, status_code)

    host_code = detail_code(host_report, default=2)
    if host_code:
        issue(InvalidInputError("host or Docker preflight needs attention"), host_code)
    state_mode = "none"
    try:
        document = _load_document(env_path)
        values = document.values
        report["environment"] = {
            "present": env_path.exists(),
            "keys": sorted(values),
            "configured": {key: key in values and bool(values[key]) for key in ("ROOT_PATH", "DOWNLOADS_PATH", "ACTIONS_TOKEN")},
        }
        if not env_path.exists():
            report["environment"]["status"] = "not-configured"
            issue(InvalidInputError(".env is not configured"), 2)
        elif any(not values.get(key) for key in ("ROOT_PATH", "DOWNLOADS_PATH", "ACTIONS_TOKEN")):
            report["environment"]["status"] = "invalid"
            issue(InvalidInputError(".env is missing required installer values"), 2)
        try:
            network_detail = plan_network(values, None, None, False).report
            report["network"] = network_detail
            network_code = detail_code(network_detail, default=2)
            if network_code:
                issue(InvalidInputError("network diagnostics need attention"), network_code)
        except DriftError as exc:
            report["network"] = {"status": "needs-attention", "error": str(exc)}
            issue(exc, 3)
        except InvalidInputError as exc:
            report["network"] = {"status": "needs-attention", "error": str(exc)}
            issue(exc, 2)
        storage_values = (values.get("ROOT_PATH"), values.get("DOWNLOADS_PATH"))
        if all(storage_values):
            try:
                checked = validate_storage(*storage_values, repo_root=root, dry_run=True)
                storage_detail = checked.report
                report["storage"] = storage_detail
                storage_code = detail_code(storage_detail, default=2)
                if storage_code:
                    issue(InvalidInputError("storage diagnostics need attention"), storage_code)
            except DriftError as exc:
                report["storage"] = {"status": "needs-attention", "error": str(exc)}
                issue(exc, 3)
            except PartialError as exc:
                report["storage"] = {"status": "needs-attention", "error": str(exc)}
                issue(exc, 4)
            except InvalidInputError as exc:
                report["storage"] = {"status": "needs-attention", "error": str(exc)}
                issue(exc, 2)
        else:
            report["storage"] = {"status": "not-configured"}
            issue(InvalidInputError("storage paths are not configured"), 2)
    except InvalidInputError as exc:
        issue(exc, 2)
        report["environment"] = {"status": "needs-attention", "error": str(exc)}
    try:
        state = InstallerState.load(root, allowed_stages=FOUNDATION_STAGES, correct_modes=False)
        state_mode = state.gpu_mode
        state_detail = state.report
        state_file_present = (root / ".state" / "installer" / "state.json").is_file()
        missing_stages = [stage for stage in FOUNDATION_STAGES if stage not in state.completed_stages]
        if not state_file_present:
            state_detail = {**state_detail, "status": "not-configured"}
            issue(InvalidInputError("installer state is not configured"), 2)
        elif missing_stages:
            state_detail = {
                **state_detail,
                "status": "incomplete",
                "missing_stages": missing_stages,
            }
            issue(InvalidInputError("installer state is incomplete"), 4)
        report["state"] = state_detail
    except InvalidInputError as exc:
        issue(exc, 2)
        report["state"] = {"status": "needs-attention", "error": str(exc)}
    requested_gpu = gpu_mode if gpu_mode is not None else state_mode
    try:
        report["gpu"] = gpu_diagnostics(
            requested_gpu,
            detector=gpu_detector,
            runner=runner,
            architecture=(host_report or {}).get("host", {}).get("arch") if isinstance(host_report, Mapping) else None,
        )
        gpu_code = detail_code(report["gpu"], default=2)
        if requested_gpu != "none" and gpu_code:
            issue(InvalidInputError("GPU diagnostics need attention"), gpu_code)
    except DriftError as exc:
        report["gpu"] = {"mode": requested_gpu, "status": "needs-confirmation", "available": False, "error": str(exc)}
        issue(exc, 3)
    except InvalidInputError as exc:
        report["gpu"] = {"mode": requested_gpu, "status": "needs-attention", "available": False, "error": str(exc)}
        issue(exc, 2)
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
