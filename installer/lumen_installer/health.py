"""Bounded stack readiness verification for update and rollback."""

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
