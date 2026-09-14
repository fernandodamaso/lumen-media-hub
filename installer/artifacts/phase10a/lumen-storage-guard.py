#!/usr/bin/env python3
"""Live Phase 10A guard for the fixed internal Lumen storage layout."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


REPO = Path(os.environ.get("LUMEN_REPO", "/home/admin/Projects/lumen-media-hub"))
sys.path.insert(0, str(REPO / "installer"))

from lumen_installer.compose import validate_storage_mounts, validate_storage_writer_policy
from lumen_installer.disk_guard import DiskGuard, DiskGuardConfig, GuardItem, GuardSupervisor
from lumen_installer.dotenv import DotEnvDocument


EXPECTED_ROOT = Path("/home/admin/media")
EXPECTED_DOWNLOADS = Path("/home/admin/lumen-downloads")
EXPECTED_UUID = "33e8776315094a8da779ef612107500b"
WRITER_SERVICES = ("qbittorrent", "sonarr", "radarr", "bazarr")
KNOWN_SERVICES = set(WRITER_SERVICES) | {"unpackerr"}
ACTIVE_STATES = {
    "downloading", "forcedDL", "metaDL", "stalledDL", "checkingDL",
    "queuedDL", "allocating", "moving",
}
PAUSED_STATES = {"pausedDL", "pausedUP", "stoppedDL", "stoppedUP"}


class GuardFailure(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def boolean(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def load_values() -> dict[str, str]:
    try:
        values = DotEnvDocument.parse(REPO / ".env").values
    except (OSError, UnicodeError) as exc:
        raise GuardFailure(".env could not be read") from exc
    if values.get("STORAGE_MODE", "").strip().lower() != "separate":
        raise GuardFailure("STORAGE_MODE must be separate")
    if Path(values.get("ROOT_PATH", "")) != EXPECTED_ROOT:
        raise GuardFailure("ROOT_PATH is not the fixed internal path")
    if Path(values.get("DOWNLOADS_PATH", "")) != EXPECTED_DOWNLOADS:
        raise GuardFailure("DOWNLOADS_PATH is not the fixed internal path")
    if values.get("LIBRARY_MOUNT_UUID", "").replace("-", "").lower() != EXPECTED_UUID:
        raise GuardFailure("LIBRARY_MOUNT_UUID is not the fixed internal UUID")
    if not boolean(values.get("DISK_GUARD_ENABLED")):
        raise GuardFailure("DISK_GUARD_ENABLED is false")
    return values


def compose_command(values: Mapping[str, str], *args: str) -> list[str]:
    command = [
        "/usr/bin/docker", "compose", "--env-file", str(REPO / ".env"),
        "-f", str(REPO / "docker-compose.yml"),
        "-f", str(REPO / "docker-compose.separate.yml"),
    ]
    if boolean(values.get("BAZARR_ENABLED")):
        command += ["--profile", "subtitles"]
    return command + list(args)


def render(values: Mapping[str, str]) -> tuple[dict[str, Any], tuple[str, ...]]:
    result = subprocess.run(
        compose_command(values, "config", "--format", "json"),
        cwd=REPO, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise GuardFailure("effective separate Compose render failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GuardFailure("effective Compose render was not JSON") from exc
    validate_storage_mounts(
        payload, root_path=str(EXPECTED_ROOT), downloads_path=str(EXPECTED_DOWNLOADS),
        storage_mode="separate",
    )
    services = ["qbittorrent", "sonarr", "radarr"]
    if boolean(values.get("BAZARR_ENABLED")):
        services.append("bazarr")
    validate_storage_writer_policy(payload, services)
    if "ARQUIVOS" in result.stdout or "nvme1n1" in result.stdout:
        raise GuardFailure("forbidden hardware reference in effective Compose render")
    return payload, tuple(services)


def inspect_container(name: str) -> tuple[str, str] | None:
    result = subprocess.run(
        ["/usr/bin/docker", "inspect", "--format",
         "{{.State.Status}}|{{.HostConfig.RestartPolicy.Name}}", name],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return None
    state, _, policy = result.stdout.strip().partition("|")
    return state, policy


class DockerRunner:
    """The only Docker mutation boundary used by the live supervisor."""

    def __init__(self, values: Mapping[str, str], writer_services: Iterable[str]) -> None:
        self.values = values
        self.writer_services = tuple(writer_services)
        self.suspended: tuple[str, ...] = ()

    def _check_writer_policy(self) -> None:
        render(self.values)
        for service in self.writer_services:
            state = inspect_container(service)
            if state is not None and state[1] != "no":
                raise GuardFailure(f"writer restart policy is not no: {service}={state[1]}")

    def _run(self, *args: str) -> None:
        result = subprocess.run(args, cwd=REPO, check=False, capture_output=True, text=True)
        if result.returncode != 0 and "No such container" not in result.stderr:
            raise GuardFailure(f"Docker command failed: {' '.join(args)}")

    def stop_downloader(self) -> None:
        self._check_writer_policy()
        self._run("/usr/bin/docker", "container", "stop", "--time", "60", "qbittorrent")

    def stop_container(self, name: str) -> None:
        if name not in KNOWN_SERVICES:
            raise GuardFailure(f"refusing unmanaged container: {name}")
        self._check_writer_policy()
        self._run("/usr/bin/docker", "container", "stop", "--time", "60", name)

    def start_container(self, name: str) -> None:
        if name != "qbittorrent":
            raise GuardFailure(f"refusing automatic start of writer: {name}")
        self._check_writer_policy()
        self._run(*compose_command(self.values, "up", "-d", name))

    def suspend_writers(self) -> None:
        self._check_writer_policy()
        running = []
        for name in self.writer_services:
            if name == "qbittorrent":
                continue
            state = inspect_container(name)
            if state is not None and state[0] == "running":
                running.append(name)
        self.suspended = tuple(running)
        for name in running:
            self._run("/usr/bin/docker", "container", "stop", "--time", "60", name)

    def resume_writers(self) -> None:
        if not self.suspended:
            return
        self._check_writer_policy()
        self._run(*compose_command(self.values, "up", "-d", *self.suspended))
        self.suspended = ()


class QbitClient:
    def __init__(self, values: Mapping[str, str]) -> None:
        address = values.get("MANAGEMENT_BIND_ADDRESS", "127.0.0.1")
        port = values.get("QBITTORRENT_WEBUI_PORT", "8081")
        self.base = f"http://{address}:{port}"
        self.password = values.get("QBT_PASSWORD", "")
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        self.logged_in = False

    def _request(self, path: str, *, data: Mapping[str, Any] | None = None) -> str:
        body = None if data is None else urllib.parse.urlencode(data).encode()
        request = urllib.request.Request(self.base + path, data=body, method="POST" if body else "GET")
        request.add_header("Referer", self.base + "/")
        if body is not None:
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with self.opener.open(request, timeout=10) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise GuardFailure(f"qBittorrent API HTTP {exc.code}") from exc
        except (OSError, TimeoutError) as exc:
            raise GuardFailure("qBittorrent API unavailable") from exc

    def login(self) -> None:
        body = self._request(
            "/api/v2/auth/login", data={"username": "admin", "password": self.password}
        )
        if body.strip() == "Fails.":
            raise GuardFailure("qBittorrent API authentication failed")
        self.logged_in = True

    def json(self, path: str, query: Mapping[str, Any] | None = None) -> Any:
        if not self.logged_in:
            self.login()
        if query:
            path += "?" + urllib.parse.urlencode(query)
        try:
            return json.loads(self._request(path))
        except GuardFailure:
            self.logged_in = False
            self.login()
            return json.loads(self._request(path))
        except json.JSONDecodeError as exc:
            raise GuardFailure("qBittorrent API returned invalid JSON") from exc

    def post(self, path: str, **params: Any) -> None:
        if not self.logged_in:
            self.login()
        self._request(path, data=params)

    def inventory(self) -> list[Mapping[str, Any]]:
        if not self.logged_in:
            self.login()
        version = self._request("/api/v2/app/version")
        if not version.strip():
            raise GuardFailure("qBittorrent API returned no version")
        rows = self.json("/api/v2/torrents/info")
        if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
            raise GuardFailure("qBittorrent torrent inventory is malformed")
        for row in rows:
            for key in ("hash", "save_path", "content_path"):
                if not isinstance(row.get(key), str):
                    raise GuardFailure(f"qBittorrent row lacks {key}")
            for key in ("save_path", "content_path"):
                path = PurePosixPath(str(row[key]))
                if path != PurePosixPath("/downloads") and PurePosixPath("/downloads") not in path.parents:
                    raise GuardFailure(f"qBittorrent path is outside /downloads: {row[key]}")
        return rows

    def pause(self, hashes: Iterable[str]) -> None:
        values = [item for item in hashes if item]
        if values:
            self.post("/api/v2/torrents/pause", hashes="|".join(values))

    def resume(self, hashes: Iterable[str]) -> None:
        values = [item for item in hashes if item]
        if values:
            self.post("/api/v2/torrents/resume", hashes="|".join(values))


def state_path() -> Path:
    value = os.environ.get("DISK_GUARD_STATE_PATH", "")
    path = Path(value) if value else REPO / ".state" / "guard" / "disk-guard-state.json"
    if not path.is_absolute() or EXPECTED_DOWNLOADS in path.parents or EXPECTED_ROOT in path.parents:
        raise GuardFailure("DISK_GUARD_STATE_PATH must be outside media/download trees")
    return path


def write_state(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def item_for(row: Mapping[str, Any], guard_hashes: set[str]) -> GuardItem:
    state = str(row.get("state", ""))
    identifier = str(row["hash"])
    remaining = int(row.get("amount_left") or 0)
    return GuardItem(
        identifier,
        staging_bytes=max(0, remaining) if state in ACTIVE_STATES else 0,
        manual_paused=state in PAUSED_STATES and identifier not in guard_hashes,
        guard_paused=identifier in guard_hashes,
    )


class LiveGuard:
    def __init__(self, values: Mapping[str, str], *, observe_only: bool = False) -> None:
        self.values = values
        self.observe_only = observe_only
        config_values = {**values, "DISK_GUARD_ENABLED": "true"}
        self.config = DiskGuardConfig.from_env(config_values)
        self.guard = DiskGuard(self.config)
        _, services = render(values)
        self.runner = DockerRunner(values, services)
        self.qbit = QbitClient(values)
        self.guard_hashes: set[str] = set()
        self.state_file = state_path()
        if self.state_file.is_file():
            try:
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                self.guard_hashes = {str(value) for value in data.get("guard_paused_hashes", [])}
            except (OSError, ValueError, TypeError):
                self.guard_hashes = set()
        self._qbit_healthy = False
        self._rows: list[Mapping[str, Any]] = []
        self.supervisor = GuardSupervisor(
            self.config, self.guard.snapshot, lambda: self._qbit_healthy, self.runner, guard=self.guard
        )

    def cycle(self) -> Mapping[str, Any]:
        self._qbit_healthy = False
        qbit_error = ""
        try:
            self._rows = self.qbit.inventory()
            self._qbit_healthy = True
        except GuardFailure as exc:
            qbit_error = str(exc)
            self._rows = []
        snapshot = self.guard.snapshot()
        resume = bool(
            snapshot.staging
            and snapshot.staging.available_bytes
            >= self.config.staging_reserve_bytes + self.config.resume_margin_bytes
        )
        result = self.supervisor.cycle(self._items(), resume=resume)
        actions = list(result.actions)
        plan = result.plan
        mutation_error = ""
        if plan is not None and not self.observe_only:
            try:
                to_pause = [item.identifier for item in plan.guard_paused if not item.manual_paused]
                self.qbit.pause(to_pause)
                if to_pause:
                    self.guard_hashes.update(to_pause)
                    actions.append(f"pause_guard:{len(to_pause)}")
                to_resume = [item.identifier for item in plan.admitted if item.identifier in self.guard_hashes]
                self.qbit.resume(to_resume)
                if to_resume:
                    self.guard_hashes.difference_update(to_resume)
                    actions.append(f"resume_guard:{len(to_resume)}")
            except GuardFailure as exc:
                mutation_error = str(exc)
                self.runner.stop_container("qbittorrent")
                self.runner.suspend_writers()
                actions.extend(("stop_container:qbittorrent", "suspend_writers"))
        status = {
            "schema": 1,
            "updated_at": now(),
            "status": "guard-failed" if mutation_error else result.status,
            "reason": mutation_error or result.reason or qbit_error,
            "actions": actions,
            "observe_only": self.observe_only,
            "guard_paused_hashes": sorted(self.guard_hashes),
            "qbit": {
                "status": "healthy" if self._qbit_healthy else "unavailable",
                "torrent_count": len(self._rows),
                "active_count": sum(str(row.get("state")) in ACTIVE_STATES for row in self._rows),
                "manual_paused_count": sum(
                    str(row.get("state")) in PAUSED_STATES and str(row.get("hash")) not in self.guard_hashes
                    for row in self._rows
                ),
            },
            "capacity": {
                "staging_available_bytes": snapshot.staging.available_bytes if snapshot.staging else None,
                "library_available_bytes": snapshot.library.available_bytes if snapshot.library else None,
                "staging_floor_bytes": self.config.staging_reserve_bytes,
                "resume_threshold_bytes": self.config.staging_reserve_bytes + self.config.resume_margin_bytes,
                "identity_healthy": snapshot.healthy,
            },
        }
        write_state(self.state_file, status)
        return status

    def _items(self) -> tuple[GuardItem, ...]:
        return tuple(item_for(row, self.guard_hashes) for row in self._rows)

    def run(self) -> None:
        while True:
            self.cycle()
            time.sleep(self.config.interval_seconds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    try:
        values = load_values()
        live = LiveGuard(values, observe_only=args.observe_only)
        if args.once:
            print(json.dumps(live.cycle(), sort_keys=True))
        else:
            live.run()
    except (GuardFailure, OSError, ValueError) as exc:
        print(f"lumen-storage-guard: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
