import os
import json
import subprocess
import stat
import sys
import tempfile
import time
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
from lumen_installer.errors import DriftError, InvalidInputError, PartialError
from lumen_installer.platform import HostFacts
from lumen_installer.setup import (
    doctor_diagnostics,
    node_satisfies,
    run_down,
    run_foundation,
    run_redeploy_dashboard,
    run_up,
)
from lumen_installer.setup import _compose_project_name, _lifecycle_lock
from lumen_installer.state import InstallerState, StageJournal


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
                storage_validator=lambda *args, **kwargs: {},
            )
            content = (repo / ".env").read_text(encoding="utf-8")
            self.assertIn("# required compose value", content)
            self.assertIn("# local note", content)
            self.assertIn("JELLYFIN_BIND_ADDRESS=127.0.0.1", content)
            self.assertIn("UNKNOWN=keep", content)

    def test_fresh_seeded_template_uses_detected_owner_facts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            (repo / ".env.example").write_text(
                "PUID=1000\nPGID=1000\nTZ=America/Sao_Paulo\n"
                "JELLYFIN_BIND_ADDRESS=127.0.0.1\n",
                encoding="utf-8",
            )
            (repo / ".env").write_text("# preserve this note\n", encoding="utf-8")
            media = root / "media"; downloads = root / "downloads"
            detected = HostFacts(
                uid=4321, gid=5432, timezone="Europe/London", distro_id="ubuntu",
                distro_like=("debian",), arch="x86_64", euid=4321,
                sudo_uid=None, sudo_gid=None, codename="jammy",
            )

            class Runner:
                def run(self, argv, **kwargs):
                    if tuple(argv[-3:]) == ("config", "--format", "json"):
                        return CommandResult(tuple(argv), 0, '{"services":{"jellyfin":{"image":"x"}}}')
                    return CommandResult(tuple(argv), 0, "")

            result = run_foundation(
                repo, runner=Runner(), host=detected,
                answers={"ROOT_PATH": str(media), "DOWNLOADS_PATH": str(downloads)},
                preflight_checker=lambda runner: DockerPreflight(status="ok"),
                stale_finder=lambda: (), health_probe=lambda: True,
                storage_validator=lambda *args, **kwargs: {},
            )
            values = result.environment["values"]
            self.assertEqual(values["PUID"], "4321")
            self.assertEqual(values["PGID"], "5432")
            self.assertEqual(values["TZ"], "Europe/London")

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

    def test_completed_setup_direct_answers_revalidate_changed_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            old_media = root / "old-media"; old_downloads = root / "old-downloads"
            new_downloads = root / "new-downloads"
            (repo / ".env").write_text(
                f"ROOT_PATH={old_media}\nDOWNLOADS_PATH={old_downloads}\n"
                "JELLYFIN_BIND_ADDRESS=127.0.0.1\nMANAGEMENT_BIND_ADDRESS=127.0.0.1\n"
                "PUBLIC_HOST=127.0.0.1\n",
                encoding="utf-8",
            )
            os.chmod(repo / ".env", 0o600)
            InstallerState.new(
                repo,
                completed_stages=("host", "environment", "network", "storage", "preflight", "compose"),
            ).save()

            class Runner:
                def run(self, argv, **kwargs):
                    if tuple(argv[-3:]) == ("config", "--format", "json"):
                        return CommandResult(tuple(argv), 0, '{"services":{"jellyfin":{"image":"x"}}}')
                    return CommandResult(tuple(argv), 0, "")

            with self.assertRaises(InvalidInputError):
                run_foundation(
                    repo, runner=Runner(), host=HOST,
                    answers={"ROOT_PATH": "/", "DOWNLOADS_PATH": str(new_downloads)},
                    preflight_checker=lambda runner: DockerPreflight(status="ok"),
                    stale_finder=lambda: (), health_probe=lambda: True,
                )

    def test_completed_setup_same_answers_file_is_a_noop_but_changed_file_revalidates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            media = root / "media"; downloads = root / "downloads"
            answers_path = root / "answers.json"
            answers_path.write_text(
                json.dumps({"schema_version": 1, "answers": {
                    "ROOT_PATH": str(media), "DOWNLOADS_PATH": str(downloads),
                }}),
                encoding="utf-8",
            )
            calls = []

            class Runner:
                def run(self, argv, **kwargs):
                    calls.append(tuple(argv))
                    if tuple(argv[-3:]) == ("config", "--format", "json"):
                        return CommandResult(tuple(argv), 0, '{"services":{"jellyfin":{"image":"x"}}}')
                    return CommandResult(tuple(argv), 0, "")

            kwargs = dict(
                runner=Runner(), host=HOST, answers_path=answers_path,
                preflight_checker=lambda runner: DockerPreflight(status="ok"),
                stale_finder=lambda: (), health_probe=lambda: True,
                storage_validator=lambda *args, **kwargs: {},
            )
            run_foundation(repo, **kwargs)
            first_calls = len(calls)
            result = run_foundation(repo, **kwargs)
            self.assertEqual(result.health, "already-complete")
            self.assertEqual(len(calls), first_calls)

            answers_path.write_text(
                json.dumps({"schema_version": 1, "answers": {
                    "ROOT_PATH": "/", "DOWNLOADS_PATH": str(downloads),
                }}),
                encoding="utf-8",
            )
            with self.assertRaises(InvalidInputError):
                run_foundation(repo, **kwargs)

    def test_supplied_journal_reconciles_changed_answers_and_storage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            old_media = root / "old-media"; old_downloads = root / "old-downloads"
            new_downloads = root / "new-downloads"
            (repo / ".env").write_text(
                f"ROOT_PATH={old_media}\nDOWNLOADS_PATH={old_downloads}\n"
                "JELLYFIN_BIND_ADDRESS=127.0.0.1\nMANAGEMENT_BIND_ADDRESS=127.0.0.1\n"
                "PUBLIC_HOST=127.0.0.1\n",
                encoding="utf-8",
            )
            os.chmod(repo / ".env", 0o600)
            InstallerState.new(
                repo,
                completed_stages=("host", "environment", "network", "storage", "preflight", "compose"),
            ).save()
            journal = StageJournal(InstallerState.load(repo), stages=("host", "environment", "network", "storage", "preflight", "compose"))
            validated = []

            class Runner:
                def run(self, argv, **kwargs):
                    if tuple(argv[-3:]) == ("config", "--format", "json"):
                        return CommandResult(tuple(argv), 0, '{"services":{"jellyfin":{"image":"x"}}}')
                    return CommandResult(tuple(argv), 0, "")

            result = run_foundation(
                repo, runner=Runner(), host=HOST, stage_journal=journal,
                answers={"ROOT_PATH": str(old_media), "DOWNLOADS_PATH": str(new_downloads)},
                storage_validator=lambda media, downloads, **kwargs: validated.append((media, downloads)) or {},
                preflight_checker=lambda runner: DockerPreflight(status="ok"),
                stale_finder=lambda: (), health_probe=lambda: True,
            )
            self.assertEqual(result.status, "ok")
            self.assertEqual(validated, [(str(old_media), str(new_downloads))])

    def test_supplied_journal_persists_explicit_profile_override(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            media = root / "media"; downloads = root / "downloads"
            (repo / ".env").write_text(
                f"ROOT_PATH={media}\nDOWNLOADS_PATH={downloads}\n"
                "JELLYFIN_BIND_ADDRESS=127.0.0.1\nMANAGEMENT_BIND_ADDRESS=127.0.0.1\n"
                "PUBLIC_HOST=127.0.0.1\n",
                encoding="utf-8",
            )
            os.chmod(repo / ".env", 0o600)
            InstallerState.new(
                repo, profiles=("subtitles",),
                completed_stages=("host", "environment", "network", "storage", "preflight", "compose"),
            ).save()
            journal = StageJournal(InstallerState.load(repo), stages=("host", "environment", "network", "storage", "preflight", "compose"))

            class Runner:
                def run(self, argv, **kwargs):
                    if tuple(argv[-3:]) == ("config", "--format", "json"):
                        return CommandResult(tuple(argv), 0, '{"services":{"jellyfin":{"image":"x"}}}')
                    return CommandResult(tuple(argv), 0, "")

            run_foundation(
                repo, runner=Runner(), host=HOST, stage_journal=journal,
                options=ComposeOptions(profiles=("requests",)),
                storage_validator=lambda *args, **kwargs: {},
                preflight_checker=lambda runner: DockerPreflight(status="ok"),
                stale_finder=lambda: (), health_probe=lambda: True,
            )
            self.assertEqual(InstallerState.load(repo).profiles, ("requests",))

    def test_supplied_journal_unchanged_completed_state_is_a_noop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            media = root / "media"; downloads = root / "downloads"
            (repo / ".env").write_text(
                f"ROOT_PATH={media}\nDOWNLOADS_PATH={downloads}\n"
                "ACTIONS_TOKEN=actions\nJELLYFIN_BIND_ADDRESS=127.0.0.1\n"
                "MANAGEMENT_BIND_ADDRESS=127.0.0.1\nPUBLIC_HOST=127.0.0.1\n",
                encoding="utf-8",
            )
            os.chmod(repo / ".env", 0o600)
            InstallerState.new(
                repo,
                completed_stages=("host", "environment", "network", "storage", "preflight", "compose"),
            ).save()
            journal = StageJournal(InstallerState.load(repo), stages=("host", "environment", "network", "storage", "preflight", "compose"))
            result = run_foundation(repo, host=HOST, stage_journal=journal)
            self.assertEqual(result.health, "already-complete")

    def test_lifecycle_dry_run_preserves_existing_state_modes(self):
        for lifecycle in (run_up, run_down, run_redeploy_dashboard):
            with self.subTest(lifecycle=lifecycle.__name__), tempfile.TemporaryDirectory() as temporary:
                repo = Path(temporary) / "repo"; repo.mkdir(); (repo / ".git").mkdir()
                installer = repo / ".state" / "installer"; installer.mkdir(parents=True)
                state_path = installer / "state.json"
                state_path.write_text(
                    json.dumps({
                        "completed_stages": [], "gpu_mode": "none", "owned_resources": {},
                        "profiles": [], "schema_version": 1,
                    }),
                    encoding="utf-8",
                )
                os.chmod(repo / ".state", 0o755)
                os.chmod(installer, 0o755)
                os.chmod(state_path, 0o644)
                lifecycle(repo, dry_run=True, stale_finder=lambda: ()) if lifecycle is run_up else lifecycle(repo, dry_run=True)
                self.assertEqual(stat.S_IMODE((repo / ".state").stat().st_mode), 0o755)
                self.assertEqual(stat.S_IMODE(installer.stat().st_mode), 0o755)
                self.assertEqual(stat.S_IMODE(state_path.stat().st_mode), 0o644)

    def test_saved_gpu_mode_activates_validated_overlay(self):
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
            self.assertTrue(any(any("docker-compose.gpu.yml" in item for item in call) for call in runner.calls))
            self.assertTrue(result.options.gpu_enabled)

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

    def test_doctor_aggregates_nested_exit_codes_and_incomplete_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            (repo / ".env").write_text(
                "ROOT_PATH=/srv/media\nDOWNLOADS_PATH=/srv/downloads\n"
                "JELLYFIN_BIND_ADDRESS=127.0.0.1\nPUBLIC_HOST=127.0.0.1\n",
                encoding="utf-8",
            )
            os.chmod(repo / ".env", 0o600)
            InstallerState.new(repo, completed_stages=("host",)).save()
            with mock.patch(
                "lumen_installer.setup.plan_network",
                return_value=SimpleNamespace(report={"status": "ok", "drift": [{"key": "PUBLIC_HOST"}]}),
            ), mock.patch(
                "lumen_installer.setup.validate_storage",
                return_value=SimpleNamespace(report={"status": "ok", "exit_code": 4}),
            ):
                report = doctor_diagnostics(repo, host_report={"status": "ok", "exit_code": 3})
            self.assertEqual(report["status"], "needs-attention")
            self.assertEqual(report["exit_code"], 4)
            self.assertEqual(report["state"]["status"], "incomplete")

    def test_doctor_missing_environment_and_storage_is_invalid(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            report = doctor_diagnostics(repo, host_report={"status": "ok", "exit_code": 0})
            self.assertEqual(report["status"], "needs-attention")
            self.assertEqual(report["exit_code"], 2)

    def test_doctor_cli_maps_nested_host_attention(self):
        from lumen_installer import cli
        with mock.patch.object(cli, "run_host_doctor", return_value={"status": "ok", "exit_code": 3}), \
             mock.patch.object(cli, "doctor_diagnostics", return_value={"status": "needs-attention", "exit_code": 4}):
            self.assertEqual(cli._doctor(mock.Mock()), 4)

    def test_stale_project_uses_compose_environment_before_dotenv(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "_worktree"; repo.mkdir(); (repo / ".git").mkdir()
            (repo / ".env").write_text("COMPOSE_PROJECT_NAME=from-file\n", encoding="utf-8")
            observed = []

            def finder(*, project_name=None):
                observed.append(project_name)
                return ()

            with mock.patch.dict(os.environ, {"COMPOSE_PROJECT_NAME": "from-process"}):
                run_up(repo, dry_run=True, stale_finder=finder)
            self.assertEqual(observed, ["from-process"])

            run_up(repo, dry_run=True, compose_project="explicit", stale_finder=finder)
            self.assertEqual(observed[-1], "explicit")

    def test_fresh_stale_project_uses_seeded_compose_project_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); repo = root / "repo"; repo.mkdir(); (repo / ".git").mkdir()
            (repo / ".env.example").write_text(
                "COMPOSE_PROJECT_NAME=template-project\nJELLYFIN_BIND_ADDRESS=127.0.0.1\n",
                encoding="utf-8",
            )
            (repo / ".env").write_text("# empty local env\n", encoding="utf-8")
            observed = []
            media = root / "media"; downloads = root / "downloads"

            def finder(*, project_name=None):
                observed.append(project_name)
                return ()

            class Runner:
                def run(self, argv, **kwargs):
                    if tuple(argv[-3:]) == ("config", "--format", "json"):
                        return CommandResult(tuple(argv), 0, '{"services":{"jellyfin":{"image":"x"}}}')
                    return CommandResult(tuple(argv), 0, "")

            run_foundation(
                repo, runner=Runner(), host=HOST,
                answers={"ROOT_PATH": str(media), "DOWNLOADS_PATH": str(downloads)},
                storage_validator=lambda *args, **kwargs: {},
                preflight_checker=lambda runner: DockerPreflight(status="ok"),
                stale_finder=finder, health_probe=lambda: True,
            )
            self.assertEqual(observed, ["template-project"])

    def test_compose_project_name_strips_leading_separators(self):
        self.assertEqual(_compose_project_name(Path("/tmp/_foo")), "foo")
        self.assertEqual(_compose_project_name(Path("/tmp/-foo")), "foo")
        self.assertEqual(_compose_project_name(Path("/tmp/___")), "media")

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
