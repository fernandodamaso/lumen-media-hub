import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.commands import CommandResult
from lumen_installer.compose import ComposeOptions
from lumen_installer.errors import DriftError, InvalidInputError
from lumen_installer.gpu import (
    GpuProbe,
    detect_gpu,
    gpu_environment,
    probe_nvidia,
    probe_vaapi,
    resolve_gpu,
)


class Runner:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def run(self, argv, **kwargs):
        key = tuple(argv)
        self.calls.append((key, kwargs))
        value = self.responses.get(key, CommandResult(key, 1, "", "not configured"))
        if isinstance(value, BaseException):
            raise value
        return value


class GpuProbeTests(unittest.TestCase):
    def test_compose_selects_distinct_nvidia_and_vaapi_overlays(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nvidia = ComposeOptions(gpu="nvidia").argv(root, root / ".env", "config")
            vaapi = ComposeOptions(gpu="vaapi").argv(root, root / ".env", "config")

        self.assertTrue(any("docker-compose.gpu.yml" in item for item in nvidia))
        self.assertFalse(any("docker-compose.vaapi.yml" in item for item in nvidia))
        self.assertTrue(any("docker-compose.vaapi.yml" in item for item in vaapi))
        self.assertFalse(any("docker-compose.gpu.yml" in item for item in vaapi))

    def test_none_mode_is_disabled_without_running_host_probes(self):
        runner = Runner()

        result = detect_gpu("none", runner=runner)

        self.assertEqual(result.mode, "none")
        self.assertEqual(result.status, "disabled")
        self.assertFalse(result.available)
        self.assertEqual(runner.calls, [])

    def test_nvidia_requires_host_smi_and_container_runtime_probe(self):
        runner = Runner({
            ("nvidia-smi",): CommandResult(("nvidia-smi",), 0, "GPU 0"),
            ("docker", "run", "--rm", "--pull=never", "--gpus", "all", "nvidia/cuda:12.4.1-base-ubuntu22.04", "nvidia-smi"):
                CommandResult((), 0, "GPU 0"),
        })

        result = probe_nvidia(runner=runner)

        self.assertTrue(result.available)
        self.assertEqual(result.status, "available")
        self.assertEqual([call[0] for call in runner.calls], [
            ("nvidia-smi",),
            ("docker", "run", "--rm", "--pull=never", "--gpus", "all", "nvidia/cuda:12.4.1-base-ubuntu22.04", "nvidia-smi"),
        ])
        self.assertTrue(all(kwargs.get("timeout", 0) <= 30 for _, kwargs in runner.calls))

    def test_nvidia_smi_failure_does_not_probe_container_runtime(self):
        runner = Runner({("nvidia-smi",): CommandResult(("nvidia-smi",), 1, "")})

        result = probe_nvidia(runner=runner)

        self.assertFalse(result.available)
        self.assertEqual(result.status, "unavailable")
        self.assertEqual(len(runner.calls), 1)

    def test_vaapi_requires_device_groups_architecture_manifest_and_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temporary:
            dri = Path(temporary) / "dri"
            dri.mkdir()
            (dri / "renderD128").touch()
            (dri / "card0").touch()
            stats = {
                dri / "renderD128": SimpleNamespace(st_gid=107),
                dri / "card0": SimpleNamespace(st_gid=44),
            }
            runner = Runner()

            result = probe_vaapi(
                runner=runner,
                device_root=dri,
                device_stat=stats.__getitem__,
                architecture="x86_64",
                manifest_probe=lambda image, **kwargs: SimpleNamespace(
                    status="supported", architectures=("amd64",), report={}
                ),
                ffmpeg_probe=lambda **kwargs: True,
            )

            self.assertTrue(result.available)
            self.assertEqual(result.render_gid, 107)
            self.assertEqual(result.video_gid, 44)
            self.assertEqual(result.status, "available")
            self.assertEqual(gpu_environment(result), {"RENDER_GID": "107", "VIDEO_GID": "44"})

    def test_vaapi_rejects_non_numeric_group_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            dri = Path(temporary) / "dri"
            dri.mkdir()
            (dri / "renderD128").touch()
            (dri / "card0").touch()
            with self.assertRaises(InvalidInputError):
                probe_vaapi(
                    device_root=dri,
                    render_gid="render",
                    video_gid="44",
                )

    def test_auto_detects_candidate_but_requires_confirmation_before_activation(self):
        candidate = GpuProbe("nvidia", "available", True, {})
        with self.assertRaises(DriftError):
            resolve_gpu("auto", detector=lambda mode, **kwargs: candidate, confirm=False)

        result = resolve_gpu("auto", detector=lambda mode, **kwargs: candidate, confirm=True)

        self.assertEqual(result.mode, "nvidia")
        self.assertEqual(result.requested_mode, "auto")
        self.assertTrue(result.available)

    def test_auto_without_a_candidate_remains_disabled(self):
        unavailable = GpuProbe("none", "unavailable", False, {})

        result = resolve_gpu("auto", detector=lambda mode, **kwargs: unavailable)

        self.assertEqual(result.mode, "none")
        self.assertEqual(result.status, "unavailable")

    def test_vaapi_capability_probe_can_use_explicit_injected_facts(self):
        with tempfile.TemporaryDirectory() as temporary:
            dri = Path(temporary) / "dri"
            dri.mkdir()
            (dri / "renderD128").touch()
            (dri / "card0").touch()
            result = probe_vaapi(
                device_root=dri,
                render_gid="107",
                video_gid=44,
                architecture="aarch64",
                manifest_architectures=("arm64",),
                ffmpeg_capabilities=("h264", "vaapi"),
            )

        self.assertTrue(result.available)
        self.assertEqual(gpu_environment(result), {"RENDER_GID": "107", "VIDEO_GID": "44"})


if __name__ == "__main__":
    unittest.main()
