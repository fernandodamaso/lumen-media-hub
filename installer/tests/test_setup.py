import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.commands import CommandResult
from lumen_installer.docker import DockerPreflight
from lumen_installer.errors import PartialError
from lumen_installer.platform import HostFacts
from lumen_installer.setup import run_foundation


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
            up_index = next(i for i, value in enumerate(rendered) if value.endswith("up -d --remove-orphans"))
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


if __name__ == "__main__":
    unittest.main()
