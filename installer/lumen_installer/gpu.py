"""Read-only GPU capability detection and Compose overlay planning.

GPU support is intentionally kept separate from Jellyfin configuration.  This
module can establish that a host/container path is usable, but it never edits
Jellyfin encoding settings.  Every process probe is an argument vector and
accepts injectable seams so doctor and setup remain testable without hardware.
"""

from __future__ import annotations

import inspect
import math
import os
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .commands import CommandExecutionError, CommandResult, CommandRunner, normalize_stream
from .docker import inspect_manifest_architectures
from .errors import DriftError, InvalidInputError, PreflightError


GPU_MODES = ("auto", "none", "nvidia", "vaapi")
GPU_MODE_SET = frozenset(GPU_MODES)
DEFAULT_JELLYFIN_IMAGE = "lscr.io/linuxserver/jellyfin:latest"
DEFAULT_NVIDIA_PROBE_IMAGE = "nvidia/cuda:12.4.1-base-ubuntu22.04"
DEFAULT_GPU_PROBE_TIMEOUT = 15.0

_ARCHITECTURES = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "x86-64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
}
_GPU_ID = re.compile(r"^[0-9]+$")


class GpuError(PreflightError):
    """A GPU capability or runtime preflight could not be satisfied."""


class GpuCapabilityError(GpuError):
    """The requested GPU mode is not usable on this host."""


def validate_gpu_mode(value: Any) -> str:
    """Normalize a requested mode and reject unknown values."""

    if not isinstance(value, str) or value.strip().lower() not in GPU_MODE_SET:
        raise InvalidInputError("gpu mode must be one of auto, none, nvidia, or vaapi")
    return value.strip().lower()


def _call(factory: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Call a supplied seam without guessing at an internal TypeError."""

    try:
        parameters = tuple(inspect.signature(factory).parameters.values())
    except (TypeError, ValueError):
        return factory(*args, **kwargs)
    if any(item.kind is inspect.Parameter.VAR_KEYWORD for item in parameters):
        return factory(*args, **kwargs)
    positional_count = sum(
        item.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for item in parameters
    )
    positional = list(args[:positional_count])
    accepted = {
        item.name
        for item in parameters
        if item.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    return factory(*positional, **{key: value for key, value in kwargs.items() if key in accepted})


def _run(
    runner: CommandRunner | Any,
    argv: Sequence[str],
    *,
    timeout: float = DEFAULT_GPU_PROBE_TIMEOUT,
) -> Any:
    """Run one bounded command through an injected command runner."""

    run = getattr(runner, "run", runner)
    return _call(run, tuple(argv), timeout=timeout)


def _timeout(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidInputError("GPU probe timeout must be positive") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise InvalidInputError("GPU probe timeout must be positive")
    # Hardware probes must not hold setup/doctor indefinitely, even when a
    # caller supplies an overly generous timeout.
    return min(parsed, 30.0)


def _success(value: Any, *, require_vaapi: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, CommandResult):
        if value.returncode != 0:
            return False
        output = value.stdout
    elif isinstance(value, Mapping):
        if "returncode" in value:
            try:
                if int(value["returncode"]) != 0:
                    return False
            except (TypeError, ValueError):
                return False
        if "status" in value:
            status = str(value["status"]).strip().lower()
            if status not in {"ok", "available", "healthy", "supported", "true", "0"}:
                return False
        output = value.get("stdout", value.get("output", value.get("capabilities", "")))
    else:
        returncode = getattr(value, "returncode", None)
        if returncode is not None:
            try:
                if int(returncode) != 0:
                    return False
            except (TypeError, ValueError):
                return False
        status = getattr(value, "status", None)
        if status is not None and str(status).strip().lower() not in {
            "ok", "available", "healthy", "supported", "true", "0"
        }:
            return False
        output = getattr(value, "stdout", getattr(value, "capabilities", value))
    if require_vaapi:
        return "vaapi" in normalize_stream(output, name="ffmpeg output", strict=False).lower()
    return True


def _failure(value: Any) -> str:
    """Return a bounded generic reason without exposing process output."""

    if isinstance(value, (CommandExecutionError, subprocess.SubprocessError, OSError, TimeoutError)):
        return "probe failed"
    if isinstance(value, Mapping) and value.get("status"):
        return str(value["status"]).strip().lower()[:64]
    return "probe failed"


@dataclass(frozen=True)
class GpuProbe:
    """Secret-free result of one GPU capability probe."""

    mode: str
    status: str
    available: bool
    checks: Mapping[str, Any] = field(default_factory=dict)
    render_gid: int | None = None
    video_gid: int | None = None
    image: str = DEFAULT_JELLYFIN_IMAGE
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", validate_gpu_mode(self.mode))
        object.__setattr__(self, "checks", dict(self.checks))

    @property
    def supported(self) -> bool:
        return self.available

    @property
    def report(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "status": self.status,
            "available": self.available,
            "checks": dict(self.checks),
            "render_gid": self.render_gid,
            "video_gid": self.video_gid,
            "image": self.image,
            "reason": self.reason,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report


@dataclass(frozen=True)
class GpuDetection:
    """Resolved mode after detection and (when needed) user confirmation."""

    requested_mode: str
    mode: str
    status: str
    available: bool
    checks: Mapping[str, Any] = field(default_factory=dict)
    render_gid: int | None = None
    video_gid: int | None = None
    image: str = DEFAULT_JELLYFIN_IMAGE
    detected_mode: str = "none"
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "requested_mode", validate_gpu_mode(self.requested_mode))
        object.__setattr__(self, "mode", validate_gpu_mode(self.mode))
        object.__setattr__(self, "detected_mode", validate_gpu_mode(self.detected_mode))
        object.__setattr__(self, "checks", dict(self.checks))

    @property
    def supported(self) -> bool:
        return self.available

    @property
    def report(self) -> dict[str, Any]:
        return {
            "requested_mode": self.requested_mode,
            "mode": self.mode,
            "detected_mode": self.detected_mode,
            "status": self.status,
            "available": self.available,
            "checks": dict(self.checks),
            "render_gid": self.render_gid,
            "video_gid": self.video_gid,
            "image": self.image,
            "reason": self.reason,
        }

    @property
    def redacted(self) -> dict[str, Any]:
        return self.report


def probe_nvidia(
    *,
    runner: CommandRunner | Any | None = None,
    nvidia_smi: Callable[..., Any] | None = None,
    runtime_probe: Callable[..., Any] | None = None,
    image: str = DEFAULT_NVIDIA_PROBE_IMAGE,
    timeout: float = DEFAULT_GPU_PROBE_TIMEOUT,
) -> GpuProbe:
    """Require both host ``nvidia-smi`` and a Docker GPU runtime probe."""

    if not isinstance(image, str) or not image.strip():
        raise InvalidInputError("NVIDIA probe image is required")
    timeout = _timeout(timeout)
    command_runner = runner if runner is not None else CommandRunner()
    checks: dict[str, Any] = {"nvidia_smi": False, "container_runtime": False}
    try:
        smi_result = (
            _call(nvidia_smi, timeout=timeout)
            if nvidia_smi is not None
            else _run(command_runner, ("nvidia-smi",), timeout=timeout)
        )
        checks["nvidia_smi"] = _success(smi_result)
    except (CommandExecutionError, OSError, TimeoutError, subprocess.SubprocessError):
        return GpuProbe("nvidia", "unavailable", False, checks, image=image, reason="nvidia-smi unavailable")
    if not checks["nvidia_smi"]:
        return GpuProbe("nvidia", "unavailable", False, checks, image=image, reason="nvidia-smi unavailable")

    try:
        runtime_result = (
            _call(runtime_probe, image=image, timeout=timeout)
            if runtime_probe is not None
            else _run(
                command_runner,
                (
                    "docker", "run", "--rm", "--pull=never", "--gpus", "all",
                    image.strip(), "nvidia-smi",
                ),
                timeout=timeout,
            )
        )
        checks["container_runtime"] = _success(runtime_result)
    except (CommandExecutionError, OSError, TimeoutError, subprocess.SubprocessError):
        checks["container_runtime"] = False
    if not checks["container_runtime"]:
        return GpuProbe(
            "nvidia", "unavailable", False, checks, image=image,
            reason="NVIDIA container runtime unavailable",
        )
    return GpuProbe("nvidia", "available", True, checks, image=image)


def _numeric_gid(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise InvalidInputError(f"{name} must be a numeric group ID")
    text = str(value).strip()
    if not _GPU_ID.fullmatch(text):
        raise InvalidInputError(f"{name} must be a numeric group ID")
    try:
        return int(text, 10)
    except ValueError as exc:
        raise InvalidInputError(f"{name} must be a numeric group ID") from exc


def _device_path(root: Path, prefix: str, *, device_exists: Callable[[Path], bool]) -> Path | None:
    direct = root / prefix
    if device_exists(direct):
        return direct
    try:
        for candidate in sorted(root.iterdir(), key=lambda path: path.name):
            if candidate.name.startswith(prefix.rstrip("0123456789")) and device_exists(candidate):
                return candidate
    except OSError:
        return None
    return None


def probe_vaapi(
    *,
    runner: CommandRunner | Any | None = None,
    device_root: str | os.PathLike[str] = "/dev/dri",
    device_exists: Callable[[Path], bool] | None = None,
    device_stat: Callable[[Path], Any] | None = None,
    render_gid: Any | None = None,
    video_gid: Any | None = None,
    architecture: str | None = None,
    manifest_probe: Callable[..., Any] | None = None,
    manifest_architectures: Sequence[str] | None = None,
    ffmpeg_probe: Callable[..., Any] | None = None,
    ffmpeg_capabilities: Sequence[str] | str | None = None,
    image: str = DEFAULT_JELLYFIN_IMAGE,
    timeout: float = DEFAULT_GPU_PROBE_TIMEOUT,
) -> GpuProbe:
    """Validate VA-API devices, groups, image architecture, and ffmpeg."""

    if not isinstance(image, str) or not image.strip():
        raise InvalidInputError("Jellyfin image is required for VA-API probing")
    timeout = _timeout(timeout)
    root = Path(device_root)
    exists = device_exists or (lambda path: path.exists())
    checks: dict[str, Any] = {
        "device": False,
        "groups": False,
        "architecture": False,
        "ffmpeg": False,
    }
    try:
        if not exists(root) or not root.is_dir():
            return GpuProbe("vaapi", "unavailable", False, checks, image=image, reason="/dev/dri unavailable")
    except OSError:
        return GpuProbe("vaapi", "unavailable", False, checks, image=image, reason="/dev/dri unavailable")

    render_path = _device_path(root, "renderD128", device_exists=exists)
    video_path = _device_path(root, "card0", device_exists=exists)
    stat_reader = device_stat or os.stat
    if render_gid is None:
        if render_path is None:
            return GpuProbe("vaapi", "unavailable", False, checks, image=image, reason="render group unavailable")
        try:
            render_gid = getattr(stat_reader(render_path), "st_gid")
        except (AttributeError, OSError, TypeError):
            return GpuProbe("vaapi", "unavailable", False, checks, image=image, reason="render group unavailable")
    if video_gid is None:
        if video_path is None:
            return GpuProbe("vaapi", "unavailable", False, checks, image=image, reason="video group unavailable")
        try:
            video_gid = getattr(stat_reader(video_path), "st_gid")
        except (AttributeError, OSError, TypeError):
            return GpuProbe("vaapi", "unavailable", False, checks, image=image, reason="video group unavailable")
    render_id = _numeric_gid(render_gid, "render GID")
    video_id = _numeric_gid(video_gid, "video GID")
    checks["device"] = True
    checks["groups"] = True

    host_arch = str(architecture or "").strip().lower()
    target_arch = _ARCHITECTURES.get(host_arch)
    if target_arch is None:
        return GpuProbe("vaapi", "unavailable", False, checks, render_id, video_id, image, "unsupported host architecture")
    if manifest_architectures is not None:
        manifest = {"status": "supported", "architectures": tuple(manifest_architectures)}
    else:
        try:
            manifest = (
                _call(manifest_probe, image.strip(), runner=runner)
                if manifest_probe is not None
                else inspect_manifest_architectures(image.strip(), runner=runner)
            )
        except (CommandExecutionError, OSError, TimeoutError, subprocess.SubprocessError):
            manifest = None
    architectures = tuple(getattr(manifest, "architectures", ()))
    if isinstance(manifest, Mapping):
        architectures = tuple(manifest.get("architectures", ()))
    manifest_status = str(
        getattr(manifest, "status", manifest.get("status", ""))
        if isinstance(manifest, Mapping)
        else getattr(manifest, "status", "")
    ).strip().lower()
    manifest_supported = (
        (manifest_status == "supported" or bool(manifest.get("supported")))
        if isinstance(manifest, Mapping)
        else (manifest_status == "supported" or bool(getattr(manifest, "supported", False)))
    )
    normalized_architectures = {
        str(item).strip().lower().rsplit("/", 1)[-1]
        for item in architectures
    }
    if not manifest_supported or target_arch not in normalized_architectures:
        return GpuProbe("vaapi", "unavailable", False, checks, render_id, video_id, image, "Jellyfin image architecture unavailable")
    checks["architecture"] = True

    command_runner = runner if runner is not None else CommandRunner()
    try:
        ffmpeg_result = (
            ffmpeg_capabilities
            if ffmpeg_capabilities is not None
            else _call(
                ffmpeg_probe,
                image=image.strip(),
                device_root=root,
                render_gid=render_id,
                video_gid=video_id,
                timeout=timeout,
            )
            if ffmpeg_probe is not None
            else _run(
                command_runner,
                (
                    "docker", "run", "--rm", "--pull=never",
                    "--device", f"{root}:{root}",
                    "--group-add", str(render_id), "--group-add", str(video_id),
                    image.strip(), "ffmpeg", "-hide_banner", "-hwaccels",
                ),
                timeout=timeout,
            )
        )
        checks["ffmpeg"] = _success(ffmpeg_result, require_vaapi=True)
    except (CommandExecutionError, OSError, TimeoutError, subprocess.SubprocessError):
        checks["ffmpeg"] = False
    if not checks["ffmpeg"]:
        return GpuProbe("vaapi", "unavailable", False, checks, render_id, video_id, image, "Jellyfin ffmpeg lacks VA-API")
    return GpuProbe("vaapi", "available", True, checks, render_id, video_id, image)


def detect_gpu(
    mode: str = "auto",
    *,
    runner: CommandRunner | Any | None = None,
    nvidia_probe: Callable[..., GpuProbe] | None = None,
    vaapi_probe: Callable[..., GpuProbe] | None = None,
    **kwargs: Any,
) -> GpuProbe:
    """Detect a requested mode without changing state or enabling Compose."""

    requested = validate_gpu_mode(mode)
    if requested == "none":
        return GpuProbe("none", "disabled", False, {})
    if requested in {"nvidia", "auto"}:
        try:
            nvidia = (
                _call(nvidia_probe, runner=runner, **kwargs)
                if nvidia_probe is not None
                else probe_nvidia(runner=runner, **{key: value for key, value in kwargs.items() if key in {"image", "timeout"}})
            )
        except (CommandExecutionError, OSError, TimeoutError, subprocess.SubprocessError):
            nvidia = GpuProbe("nvidia", "unavailable", False, {}, reason="NVIDIA probe failed")
        if nvidia.mode != "nvidia":
            raise InvalidInputError("NVIDIA detector returned a non-NVIDIA result")
        if requested == "nvidia" or nvidia.available:
            return nvidia
    if requested in {"vaapi", "auto"}:
        try:
            vaapi = (
                _call(vaapi_probe, runner=runner, **kwargs)
                if vaapi_probe is not None
                else probe_vaapi(runner=runner, **kwargs)
            )
        except (CommandExecutionError, OSError, TimeoutError, subprocess.SubprocessError):
            vaapi = GpuProbe("vaapi", "unavailable", False, {}, reason="VA-API probe failed")
        if vaapi.mode != "vaapi":
            raise InvalidInputError("VA-API detector returned a non-VA-API result")
        return vaapi
    return nvidia


def _confirmation(value: bool | Callable[..., Any] | None, candidate: GpuProbe) -> bool:
    if callable(value):
        return bool(_call(value, candidate=candidate, mode=candidate.mode))
    return bool(value)


def resolve_gpu(
    mode: str = "none",
    *,
    detector: Callable[..., GpuProbe] | None = None,
    confirm: bool | Callable[..., Any] | None = None,
    noninteractive: bool = False,
    **kwargs: Any,
) -> GpuDetection:
    """Resolve activation mode; auto requires an explicit confirmation."""

    requested = validate_gpu_mode(mode)
    detect = detector or detect_gpu
    candidate = _call(detect, requested, **kwargs)
    if not isinstance(candidate, GpuProbe):
        raise InvalidInputError("GPU detector returned an invalid result")
    if requested == "none":
        return GpuDetection("none", "none", "disabled", False, candidate.checks)
    if not candidate.available:
        if requested == "auto":
            return GpuDetection("auto", "none", candidate.status, False, candidate.checks, reason=candidate.reason)
        raise GpuCapabilityError(candidate.reason or f"{requested} GPU capability is unavailable")
    if requested == "auto" and not _confirmation(confirm, candidate):
        raise DriftError(
            f"detected {candidate.mode} GPU support requires explicit confirmation before activation"
        )
    return GpuDetection(
        requested, candidate.mode, "available", True, candidate.checks,
        candidate.render_gid, candidate.video_gid, candidate.image,
        candidate.mode, candidate.reason,
    )


def gpu_environment(result: GpuProbe | GpuDetection) -> dict[str, str]:
    """Return non-secret Compose values needed by the VA-API overlay."""

    mode = result.mode
    if mode != "vaapi":
        return {}
    if result.render_gid is None or result.video_gid is None:
        raise InvalidInputError("VA-API group IDs are required")
    return {
        "RENDER_GID": str(_numeric_gid(result.render_gid, "render GID")),
        "VIDEO_GID": str(_numeric_gid(result.video_gid, "video GID")),
    }


def overlay_for_mode(mode: str) -> str | None:
    normalized = validate_gpu_mode(mode)
    return {
        "none": None,
        "auto": None,
        "nvidia": "docker-compose.gpu.yml",
        "vaapi": "docker-compose.vaapi.yml",
    }[normalized]


def gpu_diagnostics(
    mode: str = "none",
    *,
    detector: Callable[..., GpuProbe] | None = None,
    runner: CommandRunner | Any | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build a safe doctor detail without activating any detected mode."""

    requested = validate_gpu_mode(mode)
    if requested == "none":
        return {"mode": "none", "status": "disabled", "available": False, "overlay": None}
    result = _call(detector or detect_gpu, requested, runner=runner, **kwargs)
    if not isinstance(result, GpuProbe):
        raise InvalidInputError("GPU detector returned an invalid result")
    return {
        **result.report,
        "requested_mode": requested,
        # A doctor probe is never an activation decision.  In particular an
        # auto candidate must not make its overlay appear selected.
        "overlay": overlay_for_mode(result.mode) if requested != "auto" else None,
    }


# Friendly aliases used by lifecycle/doctor callers and external integrations.
probe_gpu = detect_gpu
check_gpu = detect_gpu
plan_gpu = resolve_gpu
GPUProbe = GpuProbe
GPUDetection = GpuDetection


__all__ = [
    "DEFAULT_GPU_PROBE_TIMEOUT",
    "DEFAULT_JELLYFIN_IMAGE",
    "DEFAULT_NVIDIA_PROBE_IMAGE",
    "GPU_MODE_SET",
    "GPU_MODES",
    "GPUDetection",
    "GPUProbe",
    "GpuCapabilityError",
    "GpuDetection",
    "GpuError",
    "GpuProbe",
    "check_gpu",
    "detect_gpu",
    "gpu_diagnostics",
    "gpu_environment",
    "overlay_for_mode",
    "plan_gpu",
    "probe_gpu",
    "probe_nvidia",
    "probe_vaapi",
    "resolve_gpu",
    "validate_gpu_mode",
]
