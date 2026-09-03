import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.commands import CommandResult
from lumen_installer.compose import ComposeOptions
from lumen_installer.docker import DockerPreflight
from lumen_installer.errors import DriftError, InvalidInputError
from lumen_installer.gpu import (
    DEFAULT_JELLYFIN_IMAGE,
    GpuProbe,
    detect_gpu,
    gpu_environment,
    probe_nvidia,
    probe_vaapi,
    resolve_gpu,
)
from lumen_installer.platform import HostFacts


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


HOST = HostFacts(
    uid=os.getuid(),
    gid=os.getgid(),
    timezone="UTC",
    distro_id="ubuntu",
    distro_like=("debian",),
    arch="x86_64",
    euid=os.geteuid(),
    sudo_uid=None,
    sudo_gid=None,
    codename="jammy",
)


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
            ("docker", "run", "--rm", "--pull=missing", "--gpus", "all", "nvidia/cuda:12.4.1-base-ubuntu22.04", "nvidia-smi"):
                CommandResult((), 0, "GPU 0"),
        })

        result = probe_nvidia(runner=runner)

        self.assertTrue(result.available)
        self.assertEqual(result.status, "available")
        self.assertEqual([call[0] for call in runner.calls], [
            ("nvidia-smi",),
            ("docker", "run", "--rm", "--pull=missing", "--gpus", "all", "nvidia/cuda:12.4.1-base-ubuntu22.04", "nvidia-smi"),
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

    def test_doctor_reports_explicit_unavailable_mode_as_attention(self):
        from lumen_installer.setup import doctor_diagnostics

        with tempfile.TemporaryDirectory() as temporary:
            report = doctor_diagnostics(
                Path(temporary),
                host_report={"status": "ok", "exit_code": 0},
                gpu_mode="nvidia",
                gpu_detector=lambda mode, **kwargs: GpuProbe("nvidia", "unavailable", False, {}),
            )

        self.assertEqual(report["gpu"]["status"], "unavailable")
        self.assertNotEqual(report["exit_code"], 0)
        self.assertEqual(report["status"], "needs-attention")
        self.assertIn("GPU diagnostics need attention", report["errors"])

    def test_doctor_reports_healthy_explicit_gpu_without_attention(self):
        from lumen_installer.setup import doctor_diagnostics
        from lumen_installer.state import InstallerState

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            media = root / "media"
            downloads = root / "downloads"
            media.mkdir()
            downloads.mkdir()
            (repo / ".env").write_text(
                f"ROOT_PATH={media}\nDOWNLOADS_PATH={downloads}\n"
                "ACTIONS_TOKEN=present\nJELLYFIN_BIND_ADDRESS=127.0.0.1\n",
                encoding="utf-8",
            )
            InstallerState.new(
                repo,
                gpu_mode="nvidia",
                completed_stages=("host", "environment", "network", "storage", "preflight", "compose"),
            ).save()
            with mock.patch(
                "lumen_installer.setup.validate_storage",
                return_value=SimpleNamespace(report={"status": "ok"}),
            ):
                report = doctor_diagnostics(
                    repo,
                    host_report={"status": "ok", "exit_code": 0},
                    gpu_mode="nvidia",
                    gpu_detector=lambda mode, **kwargs: GpuProbe(
                        "nvidia", "available", True, {"nvidia_smi": True, "container_runtime": True}
                    ),
                )

        self.assertEqual(report["gpu"]["status"], "available")
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["exit_code"], 0)

    def test_vaapi_probe_container_uses_bounded_pull_when_image_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            dri = Path(temporary) / "dri"
            dri.mkdir()
            (dri / "renderD128").touch()
            (dri / "card0").touch()
            runner = Runner({
                ("docker", "run", "--rm", "--pull=missing", "--device", f"{dri}:{dri}",
                 "--group-add", "107", "--group-add", "44", DEFAULT_JELLYFIN_IMAGE,
                 "ffmpeg", "-hide_banner", "-hwaccels"): CommandResult((), 0, "Hardware acceleration methods: vaapi"),
            })
            result = probe_vaapi(
                runner=runner,
                device_root=dri,
                render_gid=107,
                video_gid=44,
                architecture="x86_64",
                manifest_architectures=("amd64",),
            )

        self.assertTrue(result.available)
        self.assertEqual(len(runner.calls), 1)

    def test_up_validates_requested_gpu_before_starting_compose(self):
        from lumen_installer.setup import run_up
        from lumen_installer.state import InstallerState

        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            InstallerState.new(repo).save()
            runner = Runner()
            with self.assertRaises(InvalidInputError):
                run_up(
                    repo,
                    runner=runner,
                    options=ComposeOptions(gpu="nvidia"),
                    gpu_detector=lambda mode, **kwargs: GpuProbe("nvidia", "unavailable", False, {}),
                    stale_finder=lambda: (),
                )

        self.assertFalse(any(call[-2:] == ("up", "-d") for call, _ in runner.calls))

    def test_up_dry_run_does_not_execute_gpu_probe_or_pull_images(self):
        from lumen_installer.setup import run_up
        from lumen_installer.state import InstallerState

        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            InstallerState.new(repo).save()
            runner = Runner()
            result = run_up(
                repo,
                runner=runner,
                options=ComposeOptions(gpu="nvidia"),
                dry_run=True,
                stale_finder=lambda: (),
            )

        probed = [call for call, _ in runner.calls if call and (call[0] == "nvidia-smi" or call[0:2] == ("docker", "run"))]
        self.assertEqual(probed, [])
        self.assertEqual(result.status, "dry-run")
        self.assertEqual(result.gpu["status"], "unverified")
        self.assertEqual(result.gpu["mode"], "nvidia")
        self.assertEqual(result.gpu["overlay"], "docker-compose.gpu.yml")

    def test_up_vaapi_persists_numeric_groups_before_compose_and_saves_override(self):
        from lumen_installer.setup import run_up
        from lumen_installer.state import InstallerState

        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            env_path = repo / ".env"
            env_path.write_text("ROOT_PATH=/srv/media\nDOWNLOADS_PATH=/srv/downloads\n", encoding="utf-8")
            InstallerState.new(repo).save()
            runner = Runner()
            result = run_up(
                repo,
                runner=runner,
                options=ComposeOptions(gpu="vaapi"),
                gpu_detector=lambda mode, **kwargs: GpuProbe(
                    "vaapi", "available", True, {}, render_gid=107, video_gid=44
                ),
                stale_finder=lambda: (),
            )
            rendered_env = env_path.read_text(encoding="utf-8")
            saved_state = InstallerState.load(repo)

        self.assertIn("RENDER_GID=107", rendered_env)
        self.assertIn("VIDEO_GID=44", rendered_env)
        self.assertEqual(saved_state.gpu_mode, "vaapi")
        self.assertEqual(result.gpu["environment"], {"RENDER_GID": "107", "VIDEO_GID": "44"})
        self.assertTrue(any(call[-2:] == ("up", "-d") for call, _ in runner.calls))

    def test_up_vaapi_dry_run_reports_groups_without_writing_env_or_state(self):
        from lumen_installer.setup import run_up
        from lumen_installer.state import InstallerState

        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            env_path = repo / ".env"
            env_path.write_text("ROOT_PATH=/srv/media\nDOWNLOADS_PATH=/srv/downloads\n", encoding="utf-8")
            InstallerState.new(repo).save()
            before_env = env_path.read_text(encoding="utf-8")
            runner = Runner()
            result = run_up(
                repo,
                runner=runner,
                options=ComposeOptions(gpu="vaapi"),
                gpu_detector=lambda mode, **kwargs: GpuProbe(
                    "vaapi", "available", True, {}, render_gid=107, video_gid=44
                ),
                dry_run=True,
                stale_finder=lambda: (),
            )
            after_env = env_path.read_text(encoding="utf-8")
            after_state = InstallerState.load(repo)

        self.assertEqual(after_env, before_env)
        self.assertEqual(after_state.gpu_mode, "none")
        self.assertEqual(result.gpu["status"], "unverified")
        self.assertEqual(result.gpu["environment"], {"RENDER_GID": "107", "VIDEO_GID": "44"})

    def test_foundation_gpu_dry_run_skips_real_probes_for_requested_modes(self):
        from lumen_installer.setup import run_foundation

        class FoundationRunner(Runner):
            def run(self, argv, **kwargs):
                key = tuple(argv)
                self.calls.append((key, kwargs))
                if key[-3:] == ("config", "--format", "json"):
                    return CommandResult(key, 0, '{"services":{"jellyfin":{"image":"x"}}}')
                return CommandResult(key, 0, "")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for mode in ("nvidia", "vaapi"):
                with self.subTest(mode=mode):
                    repo = root / mode
                    repo.mkdir()
                    media = root / f"{mode}-media"
                    downloads = root / f"{mode}-downloads"
                    runner = FoundationRunner()
                    result = run_foundation(
                        repo,
                        runner=runner,
                        host=HOST,
                        options=ComposeOptions(gpu=mode),
                        answers={"ROOT_PATH": str(media), "DOWNLOADS_PATH": str(downloads)},
                        dry_run=True,
                        preflight_checker=lambda runner: DockerPreflight(status="ok"),
                        storage_validator=lambda *args, **kwargs: SimpleNamespace(report={}),
                        stale_finder=lambda: (),
                    )

                    probe_calls = [
                        call
                        for call, _ in runner.calls
                        if call and (call[0] == "nvidia-smi" or call[:2] == ("docker", "run"))
                    ]
                    self.assertEqual(probe_calls, [])
                    self.assertEqual(result.status, "dry-run")
                    self.assertEqual(result.gpu["status"], "unverified")
                    self.assertEqual(result.gpu["mode"], mode)

    def test_lifecycle_dry_run_injected_unavailable_or_unconfirmed_gpu_never_raises(self):
        from lumen_installer.setup import run_foundation, run_up
        from lumen_installer.state import InstallerState

        class FoundationRunner(Runner):
            def run(self, argv, **kwargs):
                key = tuple(argv)
                self.calls.append((key, kwargs))
                if key[-3:] == ("config", "--format", "json"):
                    return CommandResult(key, 0, '{"services":{"jellyfin":{"image":"x"}}}')
                return CommandResult(key, 0, "")

        candidates = {
            "nvidia": GpuProbe("nvidia", "unavailable", False, {}),
            "auto": GpuProbe("nvidia", "available", True, {}),
        }
        for lifecycle in (run_up, run_foundation):
            for mode, candidate in candidates.items():
                with self.subTest(lifecycle=lifecycle.__name__, mode=mode), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    repo = root / "repo"
                    repo.mkdir()
                    InstallerState.new(repo).save()
                    runner = FoundationRunner()
                    kwargs = {
                        "runner": runner,
                        "options": ComposeOptions(gpu=mode),
                        "gpu_detector": lambda requested, candidate=candidate, **extra: candidate,
                        "dry_run": True,
                        "stale_finder": lambda: (),
                    }
                    if lifecycle is run_foundation:
                        kwargs.update(
                            {
                                "host": HOST,
                                "answers": {
                                    "ROOT_PATH": str(root / "media"),
                                    "DOWNLOADS_PATH": str(root / "downloads"),
                                },
                                "preflight_checker": lambda runner: DockerPreflight(status="ok"),
                                "storage_validator": lambda *args, **extra: SimpleNamespace(report={}),
                            }
                        )
                    result = lifecycle(repo, **kwargs)

                    self.assertEqual(result.status, "dry-run")
                    self.assertEqual(result.gpu["status"], "unverified")
                    self.assertFalse(result.gpu["available"])
                    self.assertEqual(
                        [call for call, _ in runner.calls if call and (call[0] == "nvidia-smi" or call[:2] == ("docker", "run"))],
                        [],
                    )
                    self.assertFalse((repo / ".env").exists())

    def test_confirmed_auto_foundation_saves_resolved_gpu_mode_for_future_up(self):
        from lumen_installer.setup import run_foundation, run_up
        from lumen_installer.state import InstallerState

        class FoundationRunner(Runner):
            def run(self, argv, **kwargs):
                key = tuple(argv)
                self.calls.append((key, kwargs))
                if key[-3:] == ("config", "--format", "json"):
                    return CommandResult(key, 0, '{"services":{"jellyfin":{"image":"x"}}}')
                return CommandResult(key, 0, "")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            media = root / "media"
            downloads = root / "downloads"
            runner = FoundationRunner()
            detector = lambda mode, **kwargs: GpuProbe("nvidia", "available", True, {})
            run_foundation(
                repo,
                runner=runner,
                host=HOST,
                options=ComposeOptions(gpu="auto"),
                gpu_detector=detector,
                gpu_confirm=True,
                answers={"ROOT_PATH": str(media), "DOWNLOADS_PATH": str(downloads)},
                preflight_checker=lambda runner: DockerPreflight(status="ok"),
                storage_validator=lambda *args, **kwargs: SimpleNamespace(report={}),
                stale_finder=lambda: (),
                health_probe=lambda: True,
            )
            saved = InstallerState.load(repo)
            self.assertEqual(saved.gpu_mode, "nvidia")

            result = run_up(
                repo,
                runner=runner,
                gpu_detector=detector,
                stale_finder=lambda: (),
            )

        self.assertEqual(result.options.gpu_mode, "nvidia")
        self.assertEqual(result.gpu["status"], "available")

    def test_foundation_vaapi_dry_run_uses_temporary_planning_groups(self):
        from lumen_installer.setup import run_foundation

        class PlanningRunner(Runner):
            def run(self, argv, **kwargs):
                key = tuple(argv)
                self.calls.append((key, kwargs))
                if key[-3:] == ("config", "--format", "json"):
                    env_path = Path(key[key.index("--env-file") + 1])
                    content = env_path.read_text(encoding="utf-8")
                    if "RENDER_GID=107" not in content or "VIDEO_GID=44" not in content:
                        raise AssertionError("VA-API planning environment omitted discovered groups")
                    return CommandResult(key, 0, '{"services":{"jellyfin":{"image":"x"}}}')
                return CommandResult(key, 0, "")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            env_path = repo / ".env"
            env_path.write_text(
                "ROOT_PATH=/srv/media\nDOWNLOADS_PATH=/srv/downloads\n"
                "ACTIONS_TOKEN=present\nJELLYFIN_BIND_ADDRESS=127.0.0.1\n",
                encoding="utf-8",
            )
            before = env_path.read_text(encoding="utf-8")
            runner = PlanningRunner()
            result = run_foundation(
                repo,
                runner=runner,
                host=HOST,
                options=ComposeOptions(gpu="vaapi"),
                gpu_detector=lambda mode, **kwargs: GpuProbe(
                    "vaapi", "available", True, {}, render_gid=107, video_gid=44
                ),
                dry_run=True,
                preflight_checker=lambda runner: DockerPreflight(status="ok"),
                storage_validator=lambda *args, **kwargs: SimpleNamespace(report={}),
                stale_finder=lambda: (),
            )
            after = env_path.read_text(encoding="utf-8")

        self.assertEqual(result.status, "dry-run")
        self.assertEqual(result.gpu["status"], "unverified")
        self.assertEqual(after, before)

    def test_foundation_vaapi_dry_run_without_detector_groups_uses_placeholders(self):
        from lumen_installer.setup import run_foundation

        class PlanningRunner(Runner):
            def run(self, argv, **kwargs):
                key = tuple(argv)
                self.calls.append((key, kwargs))
                if key[-3:] == ("config", "--format", "json"):
                    env_path = Path(key[key.index("--env-file") + 1])
                    content = env_path.read_text(encoding="utf-8")
                    if "RENDER_GID=0" not in content or "VIDEO_GID=0" not in content:
                        raise AssertionError("VA-API dry-run omitted disposable group placeholders")
                    return CommandResult(key, 0, '{"services":{"jellyfin":{"image":"x"}}}')
                return CommandResult(key, 0, "")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            env_path = repo / ".env"
            env_path.write_text(
                "ROOT_PATH=/srv/media\nDOWNLOADS_PATH=/srv/downloads\n"
                "ACTIONS_TOKEN=present\nJELLYFIN_BIND_ADDRESS=127.0.0.1\n",
                encoding="utf-8",
            )
            before = env_path.read_text(encoding="utf-8")
            runner = PlanningRunner()
            result = run_foundation(
                repo,
                runner=runner,
                host=HOST,
                options=ComposeOptions(gpu="vaapi"),
                gpu_detector=lambda mode, **kwargs: GpuProbe("vaapi", "available", True, {}),
                dry_run=True,
                preflight_checker=lambda runner: DockerPreflight(status="ok"),
                storage_validator=lambda *args, **kwargs: SimpleNamespace(report={}),
                stale_finder=lambda: (),
            )
            after = env_path.read_text(encoding="utf-8")

        self.assertEqual(result.status, "dry-run")
        self.assertEqual(result.gpu["status"], "unverified")
        self.assertFalse(result.gpu["available"])
        self.assertEqual(after, before)

    def test_saved_auto_up_vaapi_persists_concrete_mode_and_group_ids(self):
        from lumen_installer.setup import run_up
        from lumen_installer.state import InstallerState

        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            env_path = repo / ".env"
            env_path.write_text(
                "ROOT_PATH=/srv/media\nDOWNLOADS_PATH=/srv/downloads\n",
                encoding="utf-8",
            )
            InstallerState.new(repo, gpu_mode="auto").save()
            runner = Runner()
            detector = lambda mode, **kwargs: GpuProbe(
                "vaapi", "available", True, {}, render_gid=107, video_gid=44
            )

            result = run_up(
                repo,
                runner=runner,
                gpu_detector=detector,
                gpu_confirm=True,
                stale_finder=lambda: (),
            )
            saved = InstallerState.load(repo)
            rendered = env_path.read_text(encoding="utf-8")

        self.assertEqual(result.options.gpu_mode, "vaapi")
        self.assertEqual(saved.gpu_mode, "vaapi")
        self.assertIn("RENDER_GID=107", rendered)
        self.assertIn("VIDEO_GID=44", rendered)
        self.assertEqual(result.gpu["environment"], {"RENDER_GID": "107", "VIDEO_GID": "44"})

    def test_saved_auto_up_persists_resolved_mode_and_avoids_reconfirmation(self):
        from lumen_installer.setup import run_up
        from lumen_installer.state import InstallerState

        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            InstallerState.new(repo, gpu_mode="auto").save()
            runner = Runner()
            detector = lambda mode, **kwargs: GpuProbe("nvidia", "available", True, {})

            first = run_up(
                repo,
                runner=runner,
                gpu_detector=detector,
                gpu_confirm=True,
                stale_finder=lambda: (),
            )
            self.assertEqual(InstallerState.load(repo).gpu_mode, "nvidia")

            second = run_up(
                repo,
                runner=runner,
                gpu_detector=detector,
                stale_finder=lambda: (),
            )

        self.assertEqual(first.options.gpu_mode, "nvidia")
        self.assertEqual(second.options.gpu_mode, "nvidia")
        self.assertEqual(second.gpu["status"], "available")



if __name__ == "__main__":
    unittest.main()
