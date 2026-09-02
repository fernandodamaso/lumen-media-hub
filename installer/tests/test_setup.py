import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.commands import CommandResult
from lumen_installer.compose import ComposeOptions
from lumen_installer.docker import DockerPreflight
from lumen_installer.errors import DriftError, InvalidInputError, PartialError
from lumen_installer.platform import HostFacts
from lumen_installer.setup import doctor_diagnostics, node_satisfies, run_foundation
from lumen_installer.setup import _lifecycle_lock
from lumen_installer.state import InstallerState


HOST = HostFacts(
    uid=os.getuid(), gid=os.getgid(), timezone="UTC", distro_id="ubuntu", distro_like=("debian",),
    arch="x86_64", euid=os.geteuid(), sudo_uid=None, sudo_gid=None, codename="jammy",
)


class SetupFoundationTests(unittest.TestCase):
    def test_foundation_orders_stages_and_uses_pull_build_up_health(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            media = root / "media"
            downloads = root / "downloads"
            calls = []

            class Runner:
                def run(self, argv, **kwargs):
                    calls.append(tuple(argv))
                    if tuple(argv[-3:]) == ("config", "--format", "json"):
                        return CommandResult(tuple(argv), 0, '{"services":{"jellyfin":{"image":"x"},"dashboard":{"build":{}}}}')
                    return CommandResult(tuple(argv), 0, "")

            result = run_foundation(
                repo,
                runner=Runner(),
                host=HOST,
                answers={"ROOT_PATH": str(media), "DOWNLOADS_PATH": str(downloads), "QBT_PASSWORD": "secret"},
                health_probe=lambda: True,
                stale_finder=lambda: (),
                preflight_checker=lambda runner: DockerPreflight(status="ok"),
            )

            self.assertEqual(result.status, "ok")
            self.assertEqual([item for item in result.stages_completed], ["host", "environment", "network", "storage", "preflight", "compose"])
            rendered = [" ".join(call) for call in calls]
            pull_index = next(i for i, value in enumerate(rendered) if value.endswith("pull jellyfin"))
            build_index = next(i for i, value in enumerate(rendered) if value.endswith("build dashboard"))
            up_index = next(i for i, value in enumerate(rendered) if value.endswith("up -d"))
            self.assertLess(pull_index, build_index)
            self.assertLess(build_index, up_index)

    def test_health_timeout_is_typed_partial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir(); (repo / ".git").mkdir()
            media = root / "media"; downloads = root / "downloads"
            class Runner:
                def run(self, argv, **kwargs):
                    if tuple(argv[-3:]) == ("config", "--format", "json"):
                        return CommandResult(tuple(argv), 0, '{"services":{"jellyfin":{"image":"x"}}}')
                    return CommandResult(tuple(argv), 0, "")
            with self.assertRaises(PartialError):
                run_foundation(repo, runner=Runner(), host=HOST,
                               answers={"ROOT_PATH": str(media), "DOWNLOADS_PATH": str(downloads)},
                               health_probe=lambda: False, health_timeout=0, stale_finder=lambda: (),
                               preflight_checker=lambda runner: DockerPreflight(status="ok"))

    def test_dry_run_does_not_write_environment_state_or_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            media = root / "media"; downloads = root / "downloads"; calls = []
            class Runner:
                def run(self, argv, **kwargs):
                    calls.append(tuple(argv))
                    if tuple(argv[-3:]) == ("config", "--format", "json"):
                        return CommandResult(tuple(argv), 0, '{"services":{"jellyfin":{"image":"x"}}}')
                    return CommandResult(tuple(argv), 0, "")
            result = run_foundation(repo, runner=Runner(), host=HOST,
                                    answers={"ROOT_PATH": str(media), "DOWNLOADS_PATH": str(downloads)},
                                    dry_run=True, preflight_checker=lambda runner: DockerPreflight(status="ok"),
                                    stale_finder=lambda: ())
            self.assertEqual(result.status, "dry-run")
            self.assertFalse((repo / ".env").exists())
            self.assertFalse((repo / ".state").exists())
            self.assertFalse(media.exists())
            self.assertFalse(any(call[-1] in {"pull", "build", "up", "down"} for call in calls))

    def test_completed_setup_rerun_is_a_noop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            media = root / "media"; downloads = root / "downloads"; calls = []
            class Runner:
                def run(self, argv, **kwargs):
                    calls.append(tuple(argv))
                    if tuple(argv[-3:]) == ("config", "--format", "json"):
                        return CommandResult(tuple(argv), 0, '{"services":{"jellyfin":{"image":"x"},"dashboard":{"build":{}}}}')
                    return CommandResult(tuple(argv), 0, "")
            kwargs = dict(runner=Runner(), host=HOST,
                          answers={"ROOT_PATH": str(media), "DOWNLOADS_PATH": str(downloads)},
                          health_probe=lambda: True, stale_finder=lambda: (),
                          preflight_checker=lambda runner: DockerPreflight(status="ok"))
            run_foundation(repo, **kwargs)
            first = len(calls)
            second = run_foundation(repo, **kwargs)
            self.assertEqual(second.health, "already-complete")
            self.assertEqual(len(calls), first)

    def test_unchanged_environment_is_restricted_to_six_hundred(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            media = root / "media"; downloads = root / "downloads"
            class Runner:
                def run(self, argv, **kwargs):
                    if tuple(argv[-3:]) == ("config", "--format", "json"):
                        return CommandResult(tuple(argv), 0, '{"services":{"jellyfin":{"image":"x"}}}')
                    return CommandResult(tuple(argv), 0, "")
            kwargs = dict(runner=Runner(), host=HOST,
                          answers={"ROOT_PATH": str(media), "DOWNLOADS_PATH": str(downloads)},
                          health_probe=lambda: True, stale_finder=lambda: (),
                          preflight_checker=lambda runner: DockerPreflight(status="ok"))
            run_foundation(repo, **kwargs)
            os.chmod(repo / ".env", 0o644)
            run_foundation(repo, runner=Runner(), host=HOST,
                           preflight_checker=lambda runner: DockerPreflight(status="ok"),
                           stale_finder=lambda: (), health_probe=lambda: True)
            self.assertEqual((repo / ".env").stat().st_mode & 0o777, 0o600)

    def test_explicit_profile_and_gpu_choices_persist_after_reconciliation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            media = root / "media"; downloads = root / "downloads"
            class Runner:
                def run(self, argv, **kwargs):
                    if tuple(argv[-3:]) == ("config", "--format", "json"):
                        return CommandResult(tuple(argv), 0, '{"services":{"jellyfin":{"image":"x"}}}')
                    return CommandResult(tuple(argv), 0, "")
            run_foundation(repo, runner=Runner(), host=HOST,
                           options=ComposeOptions(profiles=("requests",), gpu=False),
                           answers={"ROOT_PATH": str(media), "DOWNLOADS_PATH": str(downloads)},
                           preflight_checker=lambda runner: DockerPreflight(status="ok"), stale_finder=lambda: (), health_probe=lambda: True)
            saved = InstallerState.load(repo)
            self.assertEqual(saved.profiles, ("requests",))
            self.assertEqual(saved.gpu_mode, "none")

    def test_changed_storage_answers_revalidate_and_reject_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            old_media = root / "old-media"; old_downloads = root / "old-downloads"
            new_media = root / "new-media"; new_downloads = root / "new-downloads"
            (repo / ".env").write_text(
                f"ROOT_PATH={old_media}\nDOWNLOADS_PATH={old_downloads}\nJELLYFIN_BIND_ADDRESS=127.0.0.1\n",
                encoding="utf-8",
            )
            InstallerState.new(repo, completed_stages=("host", "environment", "network", "storage", "preflight", "compose")).save()
            validated = []

            class Runner:
                def run(self, argv, **kwargs):
                    if tuple(argv[-3:]) == ("config", "--format", "json"):
                        return CommandResult(tuple(argv), 0, '{"services":{"jellyfin":{"image":"x"}}}')
                    return CommandResult(tuple(argv), 0, "")

            result = run_foundation(
                repo, runner=Runner(), host=HOST,
                root_path=new_media, downloads_path=new_downloads,
                storage_validator=lambda root_path, downloads_path, **kwargs: validated.append((root_path, downloads_path)) or {},
                preflight_checker=lambda runner: DockerPreflight(status="ok"),
                stale_finder=lambda: (), health_probe=lambda: True,
            )
            self.assertEqual(result.status, "ok")
            self.assertEqual(validated, [(str(new_media), str(new_downloads))])

            with self.assertRaises(InvalidInputError):
                run_foundation(
                    repo, runner=Runner(), host=HOST, root_path="/", downloads_path=new_downloads,
                    storage_validator=lambda *args, **kwargs: {},
                    preflight_checker=lambda runner: DockerPreflight(status="ok"),
                    stale_finder=lambda: (), health_probe=lambda: True,
                )

    def test_empty_env_is_seeded_from_example_before_compose(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            (repo / ".env.example").write_text(
                "# required compose value\nJELLYFIN_BIND_ADDRESS=127.0.0.1\nUNKNOWN=keep\n",
                encoding="utf-8",
            )
            (repo / ".env").write_text("# local note\n", encoding="utf-8")
            media = root / "media"; downloads = root / "downloads"
            class Runner:
                def run(self, argv, **kwargs):
                    if tuple(argv[-3:]) == ("config", "--format", "json"):
                        self.config_env = Path(argv[argv.index("--env-file") + 1]).read_text(encoding="utf-8")
                        return CommandResult(tuple(argv), 0, '{"services":{"jellyfin":{"image":"x"}}}')
                    return CommandResult(tuple(argv), 0, "")
            runner = Runner()
            run_foundation(
                repo, runner=runner, host=HOST,
                answers={"ROOT_PATH": str(media), "DOWNLOADS_PATH": str(downloads)},
                preflight_checker=lambda runner: DockerPreflight(status="ok"),
                stale_finder=lambda: (), health_probe=lambda: True,
            )
            content = (repo / ".env").read_text(encoding="utf-8")
            self.assertIn("# required compose value", content)
            self.assertIn("# local note", content)
            self.assertIn("JELLYFIN_BIND_ADDRESS=127.0.0.1", content)
            self.assertIn("UNKNOWN=keep", content)

    def test_interactive_resolver_fills_missing_paths_and_noninteractive_rejects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            media = root / "media"; downloads = root / "downloads"
            class Runner:
                def run(self, argv, **kwargs):
                    if tuple(argv[-3:]) == ("config", "--format", "json"):
                        return CommandResult(tuple(argv), 0, '{"services":{"jellyfin":{"image":"x"}}}')
                    return CommandResult(tuple(argv), 0, "")
            prompts = []
            run_foundation(
                repo, runner=Runner(), host=HOST, interactive=True,
                prompt=lambda name, default=None: prompts.append(name) or {"ROOT_PATH": str(media), "DOWNLOADS_PATH": str(downloads)}[name],
                preflight_checker=lambda runner: DockerPreflight(status="ok"), stale_finder=lambda: (), health_probe=lambda: True,
            )
            self.assertEqual(prompts[:2], ["ROOT_PATH", "DOWNLOADS_PATH"])
            missing_repo = root / "missing-repo"; missing_repo.mkdir(); (missing_repo / ".git").mkdir()
            with self.assertRaises(InvalidInputError):
                run_foundation(missing_repo, runner=Runner(), host=HOST, interactive=False, dry_run=True,
                               preflight_checker=lambda runner: DockerPreflight(status="ok"), stale_finder=lambda: ())

    def test_task7_gpu_modes_do_not_activate_overlay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            media = root / "media"; downloads = root / "downloads"
            state = InstallerState.new(repo, gpu_mode="nvidia")
            class Runner:
                def __init__(self): self.calls = []
                def run(self, argv, **kwargs):
                    self.calls.append(tuple(argv))
                    if tuple(argv[-3:]) == ("config", "--format", "json"):
                        return CommandResult(tuple(argv), 0, '{"services":{"jellyfin":{"image":"x"}}}')
                    return CommandResult(tuple(argv), 0, "")
            runner = Runner()
            result = run_foundation(repo, runner=runner, host=HOST, state=state,
                                    answers={"ROOT_PATH": str(media), "DOWNLOADS_PATH": str(downloads)},
                                    preflight_checker=lambda runner: DockerPreflight(status="ok"), stale_finder=lambda: (), health_probe=lambda: True)
            self.assertFalse(any("docker-compose.gpu.yml" in call for call in runner.calls))
            self.assertFalse(result.options.gpu_enabled)

    def test_semver_exact_and_spaced_ranges(self):
        self.assertFalse(node_satisfies("22.22.4", "=22.22.3"))
        self.assertTrue(node_satisfies("22.22.4", ">= 22.0.0"))

    def test_doctor_status_maps_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            with mock.patch("lumen_installer.setup.plan_network", side_effect=DriftError("choose exposure")):
                report = doctor_diagnostics(repo)
            self.assertEqual(report["status"], "needs-attention")
            self.assertEqual(report["exit_code"], 3)

    def test_lifecycle_lock_serializes_mutating_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            child_code = (
                "import sys,time\n"
                "from pathlib import Path\n"
                "from lumen_installer.setup import _lifecycle_lock\n"
                "with _lifecycle_lock(Path(sys.argv[1]), dry_run=False):\n"
                " print('ready', flush=True)\n"
                " time.sleep(.2)\n"
            )
            child = subprocess.Popen(
                [sys.executable, "-c", child_code, str(repo)],
                stdout=subprocess.PIPE,
                text=True,
                env={**os.environ, "PYTHONPATH": str(INSTALLER_ROOT)},
            )
            try:
                self.assertEqual(child.stdout.readline().strip(), "ready")
                started = time.monotonic()
                with _lifecycle_lock(repo, dry_run=False):
                    pass
                self.assertGreaterEqual(time.monotonic() - started, 0.15)
            finally:
                child.wait(timeout=5)
                if child.stdout is not None:
                    child.stdout.close()

    def test_failed_host_discovery_does_not_create_lifecycle_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            with self.assertRaises(InvalidInputError):
                run_foundation(
                    repo,
                    host_detector=lambda **kwargs: (_ for _ in ()).throw(InvalidInputError("host unavailable")),
                )
            self.assertFalse((repo / ".state").exists())


if __name__ == "__main__":
    unittest.main()
