from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one source block, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_all(path: str, old: str, new: str, *, minimum: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count < minimum:
        raise SystemExit(f"{path}: expected at least {minimum} occurrences, found {count}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


# Secure production prompt boundary.
write(
    "installer/lumen_installer/prompts.py",
    '''"""Interactive terminal prompts for the Linux installer."""

from __future__ import annotations

import getpass
import re
from typing import Any

_SECRET_FIELD = re.compile(
    r"(?:password|secret|token|api[_-]?key|credential|cookie|private[_-]?key|oauth)",
    re.IGNORECASE,
)


def terminal_prompt(name: str, default: Any = None) -> Any:
    """Read one installer value, hiding credential-like fields from the TTY."""

    field = str(name).strip()
    if not field:
        raise ValueError("prompt field is required")
    label = field.replace("_", " ").title()
    if _SECRET_FIELD.search(field):
        value = getpass.getpass(f"{label}: ")
    else:
        suffix = f" [{default}]" if default is not None else ""
        value = input(f"{label}{suffix}: ")
    return value if value != "" else default


__all__ = ["terminal_prompt"]
''',
)

# Per-service update/rollback health gate.
write(
    "installer/lumen_installer/health.py",
    '''"""Bounded stack readiness verification for update and rollback."""

from __future__ import annotations

import json
import socket
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .commands import CommandResult
from .compose import ComposeOptions
from .errors import InvalidInputError, PartialError

DEFAULT_TIMEOUT = 120.0
DEFAULT_INTERVAL = 2.0

_HOST_PORTS: dict[str, tuple[str | None, int]] = {
    "jellyfin": ("JELLYFIN_PORT", 8096),
    "qbittorrent": ("QBITTORRENT_WEBUI_PORT", 8081),
    "sonarr": ("SONARR_PORT", 8989),
    "radarr": ("RADARR_PORT", 7878),
    "prowlarr": ("PROWLARR_PORT", 9696),
    "flaresolverr": ("FLARESOLVERR_PORT", 8191),
    "bazarr": ("BAZARR_PORT", 6767),
    "jellyseerr": ("JELLYSEERR_PORT", 5055),
    "maintainerr": ("MAINTAINERR_PORT", 6246),
    "homepage-actions": (None, 8085),
    "dashboard": ("DASHBOARD_PORT", 3000),
}


def _parse_ps(value: str) -> list[Mapping[str, Any]]:
    text = value.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        entries: list[Mapping[str, Any]] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise InvalidInputError("docker compose ps returned invalid JSON") from exc
            if not isinstance(item, Mapping):
                raise InvalidInputError("docker compose ps returned invalid JSON")
            entries.append(item)
        return entries
    if isinstance(parsed, Mapping):
        return [parsed]
    if isinstance(parsed, list) and all(isinstance(item, Mapping) for item in parsed):
        return list(parsed)
    raise InvalidInputError("docker compose ps returned invalid JSON")


def _port(environment: Mapping[str, Any], key: str | None, default: int) -> int:
    raw = default if key is None else environment.get(key, default)
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise InvalidInputError("stack health port is invalid") from exc
    if not 1 <= value <= 65535:
        raise InvalidInputError("stack health port is invalid")
    return value


def _tcp_connect(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _ready_once(
    runner: Any,
    repo_root: str | Path,
    env_file: str | Path,
    options: ComposeOptions,
    services: Sequence[str],
    environment: Mapping[str, Any],
    connect: Callable[[str, int, float], Any],
) -> bool:
    names = tuple(dict.fromkeys(str(name) for name in services if str(name)))
    if not names:
        raise InvalidInputError("stack health requires service names")
    result = runner.run(options.argv(repo_root, env_file, "ps", "--format", "json", *names))
    if not isinstance(result, CommandResult):
        stdout = getattr(result, "stdout", "")
    else:
        stdout = result.stdout
    entries = _parse_ps(str(stdout))
    by_service: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        name = entry.get("Service", entry.get("service"))
        if isinstance(name, str) and name:
            by_service[name] = entry
    for service in names:
        entry = by_service.get(service)
        if entry is None:
            return False
        state = str(entry.get("State", entry.get("state", ""))).strip().lower()
        if state != "running":
            return False
        health = str(entry.get("Health", entry.get("health", ""))).strip().lower()
        if health and health != "healthy":
            return False
        host_port = _HOST_PORTS.get(service)
        if host_port is not None:
            key, default = host_port
            if not bool(connect("127.0.0.1", _port(environment, key, default), 2.0)):
                return False
    return True


def wait_for_stack_health(
    runner: Any,
    repo_root: str | Path,
    env_file: str | Path,
    options: ComposeOptions,
    *,
    services: Sequence[str],
    environment: Mapping[str, Any],
    connect: Callable[[str, int, float], Any] = _tcp_connect,
    timeout: float = DEFAULT_TIMEOUT,
    interval: float = DEFAULT_INTERVAL,
    sleep: Callable[[float], Any] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> bool:
    """Require every selected service to be running and every host UI reachable."""

    try:
        limit = max(0.0, float(timeout))
        pause = max(0.0, float(interval))
    except (TypeError, ValueError) as exc:
        raise InvalidInputError("stack health timeout and interval must be numeric") from exc
    started = monotonic()
    while True:
        try:
            if _ready_once(runner, repo_root, env_file, options, services, environment, connect):
                return True
        except InvalidInputError:
            raise
        except Exception:
            pass
        elapsed = monotonic() - started
        if elapsed >= limit:
            raise PartialError("stack service health check timed out")
        sleep(min(pause, max(0.0, limit - elapsed)))


__all__ = ["wait_for_stack_health"]
''',
)

# Per-operation process timeout support.
replace_once(
    "installer/lumen_installer/commands.py",
    'DEFAULT_TIMEOUT = 30.0\n',
    'DEFAULT_TIMEOUT = 30.0\nLONG_COMMAND_TIMEOUT = 1800.0\n',
)
replace_once(
    "installer/lumen_installer/commands.py",
    '''    def run(\n        self,\n        argv: Sequence[str],\n        *,\n        input_text: str | None = None,\n        redact: Iterable[Any] | Any = (),\n        cwd: str | None = None,\n    ) -> CommandResult:\n''',
    '''    def run(\n        self,\n        argv: Sequence[str],\n        *,\n        input_text: str | None = None,\n        redact: Iterable[Any] | Any = (),\n        cwd: str | None = None,\n        timeout: float | None = None,\n    ) -> CommandResult:\n''',
)
replace_once(
    "installer/lumen_installer/commands.py",
    '''        vector = _validate_argv(argv)\n        secrets = _redaction_values(redact)\n        try:\n''',
    '''        vector = _validate_argv(argv)\n        secrets = _redaction_values(redact)\n        selected_timeout = self.timeout\n        if timeout is not None:\n            try:\n                selected_timeout = float(timeout)\n            except (TypeError, ValueError) as exc:\n                raise ValueError("command timeout must be a positive finite number") from exc\n            if not math.isfinite(selected_timeout) or selected_timeout <= 0:\n                raise ValueError("command timeout must be a positive finite number")\n        try:\n''',
)
replace_all(
    "installer/lumen_installer/commands.py",
    "self._executor, vector, input_text, self.timeout, cwd",
    "self._executor, vector, input_text, selected_timeout, cwd",
)
replace_all(
    "installer/lumen_installer/commands.py",
    "timeout=self.timeout,",
    "timeout=selected_timeout,",
    minimum=2,
)
replace_once(
    "installer/lumen_installer/commands.py",
    '    "CommandResult",\n',
    '    "CommandResult",\n    "LONG_COMMAND_TIMEOUT",\n',
)

# Compose only extends timeouts for operations that legitimately take minutes.
replace_once(
    "installer/lumen_installer/compose.py",
    'import json\n',
    'import inspect\nimport json\n',
)
replace_once(
    "installer/lumen_installer/compose.py",
    'from .commands import CommandResult, CommandRunner, normalize_stream\n',
    'from .commands import CommandResult, CommandRunner, LONG_COMMAND_TIMEOUT, normalize_stream\n',
)
replace_once(
    "installer/lumen_installer/compose.py",
    '''def run_compose(\n    runner: CommandRunner,\n    repo_root: str | Path,\n    env_file: str | Path,\n    options: ComposeOptions,\n    *command: str,\n    redact: Sequence[Any] = (),\n) -> CommandResult:\n    """Execute one safe Compose command through the injected runner."""\n\n    argv = options.argv(repo_root, env_file, *command)\n    if redact:\n        return runner.run(argv, redact=redact)\n    return runner.run(argv)\n''',
    '''def run_compose(\n    runner: CommandRunner,\n    repo_root: str | Path,\n    env_file: str | Path,\n    options: ComposeOptions,\n    *command: str,\n    redact: Sequence[Any] = (),\n    timeout: float | None = None,\n) -> CommandResult:\n    """Execute one safe Compose command through the injected runner."""\n\n    argv = options.argv(repo_root, env_file, *command)\n    kwargs: dict[str, Any] = {}\n    if redact:\n        kwargs["redact"] = redact\n    if timeout is not None:\n        try:\n            parameters = tuple(inspect.signature(runner.run).parameters.values())\n        except (TypeError, ValueError):\n            parameters = ()\n        if "timeout" in {parameter.name for parameter in parameters} or any(\n            parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters\n        ):\n            kwargs["timeout"] = timeout\n    return runner.run(argv, **kwargs)\n''',
)
replace_once(
    "installer/lumen_installer/compose.py",
    '    return run_compose(runner, repo_root, env_file, options, "pull", *names, redact=redact)\n',
    '    return run_compose(runner, repo_root, env_file, options, "pull", *names, redact=redact, timeout=LONG_COMMAND_TIMEOUT)\n',
)
replace_once(
    "installer/lumen_installer/compose.py",
    '    return run_compose(runner, repo_root, env_file, options, "build", *names, redact=redact)\n',
    '    return run_compose(runner, repo_root, env_file, options, "build", *names, redact=redact, timeout=LONG_COMMAND_TIMEOUT)\n',
)
replace_once(
    "installer/lumen_installer/compose.py",
    '    return run_compose(runner, repo_root, env_file, options, *command, redact=redact)\n',
    '    return run_compose(runner, repo_root, env_file, options, *command, redact=redact, timeout=LONG_COMMAND_TIMEOUT)\n',
)

# Setup prompts, network decision and storage threshold.
replace_once(
    "installer/lumen_installer/setup.py",
    'from .commands import CommandExecutionError, CommandResult, CommandRunner\n',
    'from .commands import CommandExecutionError, CommandResult, CommandRunner, LONG_COMMAND_TIMEOUT\n',
)
replace_once(
    "installer/lumen_installer/setup.py",
    '''    input_values = _inputs(\n        answer_values,\n        environment=process_environment,\n        root_path=root_path,\n        downloads_path=downloads_path,\n        qbt_password=qbt_password,\n        existing=original_doc.values,\n        interactive=interactive,\n        prompt=prompt,\n    )\n\n    env_plan: EnvironmentPlan = plan_environment(\n''',
    '''    input_values = _inputs(\n        answer_values,\n        environment=process_environment,\n        root_path=root_path,\n        downloads_path=downloads_path,\n        qbt_password=qbt_password,\n        existing=original_doc.values,\n        interactive=interactive,\n        prompt=prompt,\n    )\n    fresh_setup = not bool(original_doc.values)\n    seeded_qbt = seeded_doc.get("QBT_PASSWORD")\n    qbt_placeholder = (\n        isinstance(seeded_qbt, str)\n        and seeded_qbt.strip().casefold() in {"changeme", "change-me", "password", "default"}\n    )\n    if fresh_setup and qbt_placeholder and not input_values.get("QBT_PASSWORD"):\n        input_values["QBT_PASSWORD"] = Resolver(noninteractive=not interactive).get(\n            "QBT_PASSWORD", {}, process_environment, answer_values, prompt\n        )\n\n    env_plan: EnvironmentPlan = plan_environment(\n''',
)
replace_once(
    "installer/lumen_installer/setup.py",
    '''    network_plan = plan_network(\n        original_doc,\n        network_mode if network_mode is not None else input_values.get("NETWORK_MODE"),\n        public_host if public_host is not None else input_values.get("PUBLIC_HOST"),\n        interactive,\n    )\n''',
    '''    selected_network_mode = network_mode if network_mode is not None else input_values.get("NETWORK_MODE")\n    selected_public_host = public_host if public_host is not None else input_values.get("PUBLIC_HOST")\n    legacy_network = bool(original_doc.values) and not bool(original_doc.get("JELLYFIN_BIND_ADDRESS"))\n    if selected_network_mode is None and legacy_network and interactive and prompt is not None:\n        selected_network_mode = Resolver(\n            defaults={"NETWORK_MODE": "preserve-lan"}, noninteractive=False\n        ).get("NETWORK_MODE", {}, process_environment, answer_values, prompt)\n    if (\n        selected_network_mode in {"lan", "preserve-lan"}\n        and selected_public_host is None\n        and interactive\n        and prompt is not None\n    ):\n        defaults = {}\n        existing_public = original_doc.get("PUBLIC_HOST")\n        if isinstance(existing_public, str) and existing_public.strip():\n            defaults["PUBLIC_HOST"] = existing_public.strip()\n        selected_public_host = Resolver(defaults=defaults, noninteractive=False).get(\n            "PUBLIC_HOST", {}, process_environment, answer_values, prompt\n        )\n    network_plan = plan_network(\n        original_doc,\n        selected_network_mode,\n        selected_public_host,\n        interactive,\n    )\n''',
)
replace_once(
    "installer/lumen_installer/setup.py",
    '''            uid=facts.uid,\n            gid=facts.gid,\n            dry_run=dry_run,\n        )\n''',
    '''            uid=facts.uid,\n            gid=facts.gid,\n            required_free_gib=env_plan.document.get("MIN_FREE_SPACE_GIB") or 0,\n            dry_run=dry_run,\n        )\n''',
)
replace_once(
    "installer/lumen_installer/setup.py",
    '        command_runner.run(npm_argv, cwd=str(dashboard))\n',
    '        command_runner.run(npm_argv, cwd=str(dashboard), timeout=LONG_COMMAND_TIMEOUT)\n',
)
replace_once(
    "installer/lumen_installer/setup.py",
    '                checked = validate_storage(*storage_values, repo_root=root, dry_run=True)\n',
    '                checked = validate_storage(\n                    *storage_values,\n                    repo_root=root,\n                    required_free_gib=values.get("MIN_FREE_SPACE_GIB") or 0,\n                    dry_run=True,\n                )\n',
)

# CLI owns the real terminal prompt and update/rollback readiness gates.
replace_once(
    "installer/lumen_installer/cli.py",
    'from .commands import CommandExecutionError, CommandRunner\n',
    'from .commands import CommandExecutionError, CommandRunner, LONG_COMMAND_TIMEOUT\n',
)
replace_once(
    "installer/lumen_installer/cli.py",
    'from .gpu import GPU_MODES\n',
    'from .gpu import GPU_MODES\nfrom .health import wait_for_stack_health\nfrom .prompts import terminal_prompt\n',
)
replace_once(
    "installer/lumen_installer/cli.py",
    '''def _setup(args: argparse.Namespace) -> int:\n    requested_options = _compose_options(args)\n    foundation = run_foundation(\n        options=requested_options,\n        answers_path=getattr(args, "answers", None),\n        uid=getattr(args, "uid", None),\n        gid=getattr(args, "gid", None),\n        timezone=getattr(args, "timezone", None),\n        root_path=getattr(args, "root_path", None),\n        downloads_path=getattr(args, "downloads_path", None),\n        network_mode=getattr(args, "network_mode", None),\n        public_host=getattr(args, "public_host", None),\n        interactive=not bool(getattr(args, "noninteractive", False)),\n        gpu_confirm=bool(getattr(args, "gpu_confirm", False)),\n        confirm=bool(getattr(args, "confirm", False)),\n        dry_run=bool(getattr(args, "dry_run", False)),\n    )\n    configured = run_configure(\n        options=getattr(foundation, "options", requested_options),\n        interactive=not bool(getattr(args, "noninteractive", False)),\n        dry_run=bool(getattr(args, "dry_run", False)),\n    )\n''',
    '''def _setup(args: argparse.Namespace) -> int:\n    requested_options = _compose_options(args)\n    interactive = not bool(getattr(args, "noninteractive", False))\n    prompt = terminal_prompt if interactive else None\n    selected_network_mode = getattr(args, "network_mode", None)\n    selected_public_host = getattr(args, "public_host", None)\n    if prompt is not None and selected_network_mode is None:\n        selected_network_mode = str(prompt("NETWORK_MODE", "local") or "local").strip().lower()\n        if selected_network_mode not in {"local", "lan", "preserve-lan"}:\n            raise InvalidInputError("network mode must be local or lan")\n    if prompt is not None and selected_network_mode in {"lan", "preserve-lan"} and selected_public_host is None:\n        selected_public_host = prompt("PUBLIC_HOST", None)\n    foundation = run_foundation(\n        options=requested_options,\n        answers_path=getattr(args, "answers", None),\n        uid=getattr(args, "uid", None),\n        gid=getattr(args, "gid", None),\n        timezone=getattr(args, "timezone", None),\n        root_path=getattr(args, "root_path", None),\n        downloads_path=getattr(args, "downloads_path", None),\n        network_mode=selected_network_mode,\n        public_host=selected_public_host,\n        interactive=interactive,\n        prompt=prompt,\n        gpu_confirm=bool(getattr(args, "gpu_confirm", False)),\n        confirm=bool(getattr(args, "confirm", False)),\n        dry_run=bool(getattr(args, "dry_run", False)),\n    )\n    configured = run_configure(\n        options=getattr(foundation, "options", requested_options),\n        interactive=interactive,\n        prompt=prompt,\n        dry_run=bool(getattr(args, "dry_run", False)),\n    )\n''',
)
replace_once(
    "installer/lumen_installer/cli.py",
    '''def _configure(args: argparse.Namespace) -> int:\n    result = run_configure(\n        options=_compose_options(args),\n        interactive=not bool(getattr(args, "noninteractive", False)),\n        confirm=bool(getattr(args, "confirm", False)),\n        dry_run=bool(getattr(args, "dry_run", False)),\n    )\n''',
    '''def _configure(args: argparse.Namespace) -> int:\n    interactive = not bool(getattr(args, "noninteractive", False))\n    result = run_configure(\n        options=_compose_options(args),\n        interactive=interactive,\n        prompt=terminal_prompt if interactive else None,\n        confirm=bool(getattr(args, "confirm", False)),\n        dry_run=bool(getattr(args, "dry_run", False)),\n    )\n''',
)
replace_once(
    "installer/lumen_installer/cli.py",
    '''        compose_up(\n            runner,\n            root,\n            env_path,\n            options,\n            force_recreate=True,\n            redact=redact,\n        )\n        wait_for_health()\n''',
    '''        compose_up(\n            runner,\n            root,\n            env_path,\n            options,\n            force_recreate=True,\n            redact=redact,\n        )\n        wait_for_stack_health(\n            runner,\n            root,\n            env_path,\n            options,\n            services=tuple(payload.get("services", {})),\n            environment=values,\n        )\n''',
)
replace_once(
    "installer/lumen_installer/cli.py",
    '''        runner.run(argv, redact=redact)\n        wait_for_health()\n''',
    '''        runner.run(argv, redact=redact, timeout=LONG_COMMAND_TIMEOUT)\n        wait_for_stack_health(\n            runner,\n            root,\n            env_path,\n            options,\n            services=services,\n            environment=values,\n        )\n''',
)
replace_once(
    "installer/lumen_installer/cli.py",
    '''    if rollback_id is not None and dry_run:\n        result: dict[str, object] = {\n            "action": "rollback",\n            "dry_run": True,\n            "run_id": safe_rollback_id,\n        }\n    elif rollback_id is not None:\n        runner = CommandRunner()\n        try:\n            result = run_rollback(\n                root,\n                safe_rollback_id,\n                confirm=confirm,\n                callback_factory=lambda rollback_manifest: _rollback_callbacks(\n                    root, rollback_manifest, args, runner\n                ),\n            )\n        except (CommandExecutionError, OSError) as error:\n            raise PartialError("stack rollback lifecycle failed") from error\n''',
    '''    if rollback_id is not None:\n        runner = CommandRunner()\n        try:\n            result = run_rollback(\n                root,\n                safe_rollback_id,\n                confirm=confirm,\n                dry_run=dry_run,\n                callback_factory=(\n                    None\n                    if dry_run\n                    else lambda rollback_manifest: _rollback_callbacks(\n                        root, rollback_manifest, args, runner\n                    )\n                ),\n            )\n        except (CommandExecutionError, OSError) as error:\n            raise PartialError("stack rollback lifecycle failed") from error\n''',
)

# Configure prompts transient Jellyfin credentials and forwards qBittorrent's effective port.
replace_once(
    "installer/lumen_installer/configure.py",
    '''            adapter = ProwlarrAdapter(\n                _service_url(current_environment, "prowlarr"),\n                selected_transport,\n                api_key=api_key,\n                qbit_password=password,\n''',
    '''            adapter = ProwlarrAdapter(\n                _service_url(current_environment, "prowlarr"),\n                selected_transport,\n                api_key=api_key,\n                qbit_password=password,\n                qbit_port=_service_port(current_environment, "qbittorrent"),\n''',
)
replace_once(
    "installer/lumen_installer/configure.py",
    '''            password = jellyfin_admin_password or _configured_value(\n                environment,\n                "JELLYFIN_ADMIN_PASSWORD",\n                "JELLYFIN_PASSWORD",\n            )\n            bind = _configured_value(environment, "JELLYFIN_BIND_ADDRESS")\n''',
    '''            password = jellyfin_admin_password or _configured_value(\n                environment,\n                "JELLYFIN_ADMIN_PASSWORD",\n                "JELLYFIN_PASSWORD",\n            )\n            if interactive and not dry_run and prompt is not None:\n                if name is None:\n                    name = _call_with_keywords(prompt, "JELLYFIN_ADMIN_NAME", default="admin")\n                if password is None:\n                    password = _call_with_keywords(prompt, "JELLYFIN_ADMIN_PASSWORD", default=None)\n            bind = _configured_value(environment, "JELLYFIN_BIND_ADDRESS")\n''',
)
replace_once(
    "installer/lumen_installer/configure.py",
    '''                api_key=api_key,\n                qbit_password=password or "",\n            )\n''',
    '''                api_key=api_key,\n                qbit_password=password or "",\n                qbit_port=_service_port(environment, "qbittorrent"),\n            )\n''',
)

# Servarr: use configured port and always refresh an opaque/stale managed credential.
replace_once(
    "installer/lumen_installer/services/servarr.py",
    '''        *,\n        api_key: str,\n        qbit_password: str,\n    ) -> None:\n''',
    '''        *,\n        api_key: str,\n        qbit_password: str,\n        qbit_port: int = 8081,\n    ) -> None:\n''',
)
replace_once(
    "installer/lumen_installer/services/servarr.py",
    '''        self._api_key = api_key.strip()\n        self._qbit_password = qbit_password\n''',
    '''        self._api_key = api_key.strip()\n        self._qbit_password = qbit_password\n        if isinstance(qbit_port, bool) or not isinstance(qbit_port, int) or not 1 <= qbit_port <= 65535:\n            raise InvalidInputError("qBittorrent port is invalid")\n        self._qbit_port = qbit_port\n''',
)
replace_all(
    "installer/lumen_installer/services/servarr.py",
    '"port": 8081,',
    '"port": self._qbit_port,',
    minimum=3,
)
replace_once(
    "installer/lumen_installer/services/servarr.py",
    '''            drift = drift_records\n            client_payload = self._updated_client_payload(existing, schema)\n            if drift:\n                client_action = "update-download-client"\n                if not confirm:\n                    return ServarrResult(\n                        service=self.service,\n                        status="drift",\n                        actions=tuple(actions),\n                        drift=drift,\n                        error=ServarrConflictError(),\n                    )\n\n        if existing is not None and not drift:\n''',
    '''            drift = drift_records\n            client_payload = self._updated_client_payload(existing, schema)\n            credential_matches = existing_values.get("password") == self._qbit_password\n            if drift:\n                client_action = "update-download-client"\n                if not confirm:\n                    return ServarrResult(\n                        service=self.service,\n                        status="drift",\n                        actions=tuple(actions),\n                        drift=drift,\n                        error=ServarrConflictError(),\n                    )\n            elif not credential_matches:\n                # Servarr commonly masks or omits stored secrets. The selected\n                # qBittorrent password is authoritative, so test and refresh it\n                # instead of treating an opaque credential as a reusable match.\n                client_action = "update-download-client"\n\n        if existing is not None and not drift and client_action == "reuse-download-client":\n''',
)

# Prowlarr: configurable port and no false reuse of omitted/masked credentials.
replace_once(
    "installer/lumen_installer/services/prowlarr.py",
    '''        qbit_password: str | None = None,\n        password: str | None = None,\n        sonarr_api_key: str | None = None,\n''',
    '''        qbit_password: str | None = None,\n        password: str | None = None,\n        qbit_port: int = DEFAULT_QBIT_PORT,\n        sonarr_api_key: str | None = None,\n''',
)
replace_once(
    "installer/lumen_installer/services/prowlarr.py",
    '''        self._qbit_password = _secret(selected_qbit_password)\n        if self._qbit_password is None:\n            raise InvalidInputError("qBittorrent password is required")\n\n        key_sources = [application_api_keys, app_api_keys]\n''',
    '''        self._qbit_password = _secret(selected_qbit_password)\n        if self._qbit_password is None:\n            raise InvalidInputError("qBittorrent password is required")\n        if isinstance(qbit_port, bool) or not isinstance(qbit_port, int) or not 1 <= qbit_port <= 65535:\n            raise InvalidInputError("qBittorrent port is invalid")\n        self._qbit_port = qbit_port\n\n        key_sources = [application_api_keys, app_api_keys]\n''',
)
replace_once(
    "installer/lumen_installer/services/prowlarr.py",
    '            ("port",): DEFAULT_QBIT_PORT,\n',
    '            ("port",): self._qbit_port,\n',
)
replace_once(
    "installer/lumen_installer/services/prowlarr.py",
    '''        # Prowlarr commonly masks or omits an existing password.  Do not turn\n        # that unknown value into a conflict; a known non-empty value is still\n        # protected by the normal managed-field confirmation gate.\n        drift = self._resource_drift(\n            "download-client",\n            fields,\n            desired,\n            ignore_unknown=("password", "pass"),\n        )\n        payload = self._payload_from_existing(existing, schema, desired)\n        if not drift:\n            action = "reuse-download-client"\n        else:\n            action = "update-download-client"\n''',
    '''        # Prowlarr commonly masks or omits the existing password. Compare\n        # non-secret managed fields normally, but always refresh the managed\n        # credential unless the API returned the exact selected value.\n        non_secret_desired = {\n            aliases: value\n            for aliases, value in desired.items()\n            if "password" not in {_normalized_name(alias) for alias in aliases}\n            and "pass" not in {_normalized_name(alias) for alias in aliases}\n        }\n        drift = self._resource_drift(\n            "download-client",\n            fields,\n            non_secret_desired,\n        )\n        payload = self._payload_from_existing(existing, schema, desired)\n        current_password = _field_value(fields, ("password", "pass"))\n        credential_matches = current_password is not _MISSING and current_password == self._qbit_password\n        if not drift and credential_matches:\n            action = "reuse-download-client"\n        else:\n            action = "update-download-client"\n''',
)

# Management deep links must match their loopback-only publication contract.
for old, new in (
    ('SONARR_EXTERNAL_URL=http://${PUBLIC_HOST:-127.0.0.1}:${SONARR_PORT}', 'SONARR_EXTERNAL_URL=http://127.0.0.1:${SONARR_PORT}'),
    ('RADARR_EXTERNAL_URL=http://${PUBLIC_HOST:-127.0.0.1}:${RADARR_PORT}', 'RADARR_EXTERNAL_URL=http://127.0.0.1:${RADARR_PORT}'),
    ('PROWLARR_EXTERNAL_URL=http://${PUBLIC_HOST:-127.0.0.1}:${PROWLARR_PORT}', 'PROWLARR_EXTERNAL_URL=http://127.0.0.1:${PROWLARR_PORT}'),
    ('BAZARR_EXTERNAL_URL=http://${PUBLIC_HOST:-127.0.0.1}:${BAZARR_PORT}', 'BAZARR_EXTERNAL_URL=http://127.0.0.1:${BAZARR_PORT}'),
    ('QBITTORRENT_EXTERNAL_URL=http://${PUBLIC_HOST:-127.0.0.1}:${QBITTORRENT_WEBUI_PORT}', 'QBITTORRENT_EXTERNAL_URL=http://127.0.0.1:${QBITTORRENT_WEBUI_PORT}'),
):
    replace_once("docker-compose.yml", old, new)

# Rollback dry-run performs the complete read-only validation before reporting success.
replace_once(
    "installer/lumen_installer/update.py",
    '''    if dry_run:\n        return {"action": "rollback", "dry_run": True, "run_id": _safe_run_id(run_id)}\n    if not confirm:\n        raise InvalidInputError("rollback requires confirmation")\n\n    safe_run_id = _safe_run_id(run_id)\n''',
    '''    if not dry_run and not confirm:\n        raise InvalidInputError("rollback requires confirmation")\n\n    safe_run_id = _safe_run_id(run_id)\n''',
)
replace_once(
    "installer/lumen_installer/update.py",
    '''    except RollbackValidationError:\n        raise\n    except (OSError, ValueError, TypeError) as exc:\n        raise RollbackValidationError("rollback image metadata is invalid") from exc\n\n    _ensure_private_dir(state.parent)\n''',
    '''    except RollbackValidationError:\n        raise\n    except (OSError, ValueError, TypeError) as exc:\n        raise RollbackValidationError("rollback image metadata is invalid") from exc\n\n    if dry_run:\n        return {"action": "rollback", "dry_run": True, "run_id": safe_run_id}\n\n    _ensure_private_dir(state.parent)\n''',
)

# Update existing tests that intentionally encoded the old behavior.
replace_once(
    "installer/tests/test_network.py",
    '        self.assertEqual(environment["QBITTORRENT_EXTERNAL_URL"], "http://media.example.test:18081")\n',
    '        self.assertEqual(environment["QBITTORRENT_EXTERNAL_URL"], "http://127.0.0.1:18081")\n',
)
replace_all(
    "installer/tests/test_cli.py",
    '"wait_for_health"',
    '"wait_for_stack_health"',
    minimum=4,
)
replace_all(
    "installer/tests/test_cli.py",
    'health.assert_called_once_with()',
    'health.assert_called_once()',
    minimum=2,
)
replace_once(
    "installer/tests/test_cli.py",
    '''        with mock.patch.object(cli, "run_rollback") as run_rollback:\n            with contextlib.redirect_stdout(output):\n                result = cli.main(["update", "--rollback", "run-7", "--dry-run"])\n\n        self.assertEqual(result, int(ExitCode.OK))\n        run_rollback.assert_not_called()\n        report = json.loads(output.getvalue())\n''',
    '''        with mock.patch.object(\n            cli,\n            "run_rollback",\n            return_value={"action": "rollback", "dry_run": True, "run_id": "run-7"},\n        ) as run_rollback:\n            with contextlib.redirect_stdout(output):\n                result = cli.main(["update", "--rollback", "run-7", "--dry-run"])\n\n        self.assertEqual(result, int(ExitCode.OK))\n        run_rollback.assert_called_once()\n        self.assertTrue(run_rollback.call_args.kwargs["dry_run"])\n        report = json.loads(output.getvalue())\n''',
)
replace_once(
    "installer/tests/test_update.py",
    '''    def test_rollback_dry_run_is_read_only_even_without_confirmation(self):\n        with tempfile.TemporaryDirectory() as temp_dir:\n            root = Path(temp_dir)\n            calls = []\n            result = run_rollback(\n                root,\n                "run-7",\n                False,\n                lambda: calls.append("stop"),\n                lambda: calls.append("start"),\n                dry_run=True,\n            )\n            self.assertEqual(\n                {"action": "rollback", "dry_run": True, "run_id": "run-7"}, result\n            )\n''',
    '''    def test_rollback_dry_run_is_read_only_even_without_confirmation(self):\n        with tempfile.TemporaryDirectory() as temp_dir:\n            root = Path(temp_dir)\n            manifest, _ = self._manifest(root)\n            updated = self._update(root, manifest)\n            calls = []\n            result = run_rollback(\n                root,\n                updated["run_id"],\n                False,\n                lambda: calls.append("stop"),\n                lambda: calls.append("start"),\n                dry_run=True,\n            )\n            self.assertEqual(\n                {"action": "rollback", "dry_run": True, "run_id": updated["run_id"]}, result\n            )\n            self.assertEqual([], calls)\n            self.assertFalse((root / ".state" / "installer" / "failed-runs").exists())\n''',
)

# Keep docs aligned with the actual guided checkpoints.
replace_once(
    "dashboard-app/docs/linux-installation.md",
    '''The interactive setup asks for the media and download locations, network\nexposure, optional profiles, and GPU mode. It shows a summary before changing\nthe host.\n''',
    '''The interactive setup asks for the media and download locations, a secure\nqBittorrent password, Jellyfin administrator credentials, and any unresolved\nnetwork exposure decision. Optional profiles and GPU mode remain explicit CLI\nchoices. It shows a summary before changing the host.\n''',
)

print("PR 59 production fixes applied")
