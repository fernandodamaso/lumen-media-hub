import importlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


WORKTREE_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_ROOT = WORKTREE_ROOT / "installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer import cli
from lumen_installer.commands import CommandResult
from lumen_installer.compose import ComposeOptions, pull as compose_pull
from lumen_installer.configure import build_adapter_factory
from lumen_installer.docker import DockerPreflight
from lumen_installer.errors import InvalidInputError
from lumen_installer.platform import HostFacts
from lumen_installer.services.prowlarr import ProwlarrAdapter
from lumen_installer.services.servarr import SonarrAdapter
from lumen_installer.setup import FOUNDATION_STAGES, doctor_diagnostics, run_foundation, run_frontend_dev
from lumen_installer.update import RollbackValidationError, run_rollback


SETUP_MODULE = importlib.import_module("lumen_installer.setup")
CONFIGURE_MODULE = importlib.import_module("lumen_installer.configure")
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


class _Transport:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return {"status": 200, "body": {}}


class _ComposeRunner:
    def __init__(self):
        self.calls = []

    def run(self, argv, **kwargs):
        command = tuple(argv)
        self.calls.append((command, kwargs))
        if command[-3:] == ("config", "--format", "json"):
            return CommandResult(command, 0, '{"services":{"jellyfin":{"image":"x"}}}')
        return CommandResult(command, 0, "")


class InteractiveSetupRegressionTests(unittest.TestCase):
    def test_setup_passes_a_real_prompt_to_both_lifecycle_phases(self):
        args = cli.build_parser().parse_args(["setup"])
        foundation = SimpleNamespace(options=ComposeOptions(), report={"status": "ok"})
        configured = SimpleNamespace(report={"status": "ok"}, exit_code=0)

        with mock.patch.object(cli, "terminal_prompt", create=True) as prompt:
            prompt.side_effect = lambda name, default=None: default or "secret"
            with mock.patch.object(cli, "run_foundation", return_value=foundation) as foundation_call:
                with mock.patch.object(cli, "run_configure", return_value=configured) as configure_call:
                    self.assertEqual(cli._setup(args), 0)

        self.assertIs(foundation_call.call_args.kwargs.get("prompt"), prompt)
        self.assertIs(configure_call.call_args.kwargs.get("prompt"), prompt)

    def test_jellyfin_factory_securely_prompts_for_missing_admin_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = {
                "JELLYFIN_BIND_ADDRESS": "127.0.0.1",
                "JELLYFIN_REMOTE_ACCESS": "false",
                "JELLYFIN_PORT": "8096",
            }
            values = {
                "JELLYFIN_ADMIN_NAME": "admin",
                "JELLYFIN_ADMIN_PASSWORD": "super-secret",
            }
            seen = []

            def prompt(name, default=None):
                seen.append(name)
                return values.get(name, default)

            factory = build_adapter_factory(
                root,
                environment=env,
                transport=_Transport(),
                interactive=True,
                prompt=prompt,
            )
            wrapped = factory("jellyfin", environment=env, dry_run=False)

        self.assertEqual(wrapped.adapter._admin_name, "admin")
        self.assertEqual(wrapped.adapter._admin_password, "super-secret")
        self.assertEqual(seen, ["JELLYFIN_ADMIN_NAME", "JELLYFIN_ADMIN_PASSWORD"])

    def test_interactive_legacy_network_choice_is_resolved_before_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            media = root / "media"
            downloads = root / "downloads"
            (repo / ".env").write_text(
                "\n".join(
                    (
                        f"ROOT_PATH={media}",
                        f"DOWNLOADS_PATH={downloads}",
                        f"PUID={HOST.uid}",
                        f"PGID={HOST.gid}",
                        "TZ=UTC",
                        "QBT_PASSWORD=secret",
                        "ACTIONS_TOKEN=token",
                        "MANAGEMENT_BIND_ADDRESS=127.0.0.1",
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            def prompt(name, default=None):
                if name == "NETWORK_MODE":
                    return "local"
                return default

            result = run_foundation(
                repo,
                runner=_ComposeRunner(),
                host=HOST,
                interactive=True,
                prompt=prompt,
                storage_validator=lambda *args, **kwargs: {},
                preflight_checker=lambda runner: DockerPreflight(status="ok"),
                stale_finder=lambda: (),
                health_probe=lambda: True,
            )

        self.assertEqual(result.network["values"]["JELLYFIN_BIND_ADDRESS"], "127.0.0.1")
        self.assertEqual(result.network["values"]["JELLYFIN_REMOTE_ACCESS"], "false")


class StorageThresholdRegressionTests(unittest.TestCase):
    def test_setup_passes_configured_minimum_free_space_to_storage_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            (repo / ".env.example").write_text("MIN_FREE_SPACE_GIB=75\n", encoding="utf-8")
            captured = {}

            def storage_validator(*args, **kwargs):
                captured.update(kwargs)
                return {}

            run_foundation(
                repo,
                runner=_ComposeRunner(),
                host=HOST,
                answers={
                    "ROOT_PATH": str(root / "media"),
                    "DOWNLOADS_PATH": str(root / "downloads"),
                    "QBT_PASSWORD": "secret",
                },
                storage_validator=storage_validator,
                preflight_checker=lambda runner: DockerPreflight(status="ok"),
                stale_finder=lambda: (),
                health_probe=lambda: True,
            )

        self.assertEqual(float(captured.get("required_free_gib", -1)), 75.0)

    def test_doctor_uses_the_same_minimum_free_space_threshold(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".env").write_text(
                "\n".join(
                    (
                        "ROOT_PATH=/srv/lumen-media",
                        "DOWNLOADS_PATH=/srv/lumen-downloads",
                        "ACTIONS_TOKEN=token",
                        "MIN_FREE_SPACE_GIB=75",
                        "JELLYFIN_BIND_ADDRESS=127.0.0.1",
                        "MANAGEMENT_BIND_ADDRESS=127.0.0.1",
                        "PUBLIC_HOST=127.0.0.1",
                        "JELLYFIN_REMOTE_ACCESS=false",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            captured = {}

            def validate(*args, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(report={"status": "ok"})

            state = SimpleNamespace(
                gpu_mode="none",
                completed_stages=FOUNDATION_STAGES,
                report={"status": "ok"},
            )
            with mock.patch.object(SETUP_MODULE, "validate_storage", side_effect=validate):
                with mock.patch.object(SETUP_MODULE.InstallerState, "load", return_value=state):
                    with mock.patch.object(SETUP_MODULE, "gpu_diagnostics", return_value={"status": "disabled"}):
                        doctor_diagnostics(root, host_report={"status": "ok"}, gpu_mode="none")

        self.assertEqual(float(captured.get("required_free_gib", -1)), 75.0)


class TimeoutRegressionTests(unittest.TestCase):
    def test_compose_pull_gets_a_long_operation_timeout(self):
        class Runner:
            def __init__(self):
                self.kwargs = None

            def run(self, argv, **kwargs):
                self.kwargs = kwargs
                return CommandResult(tuple(argv), 0, "")

        runner = Runner()
        compose_pull(
            runner,
            "/repo",
            "/repo/.env",
            ComposeOptions(),
            ("jellyfin",),
        )
        self.assertGreaterEqual(float((runner.kwargs or {}).get("timeout", 0)), 300.0)

    def test_frontend_npm_ci_gets_a_long_operation_timeout(self):
        class Runner:
            def __init__(self):
                self.calls = []

            def run(self, argv, **kwargs):
                command = tuple(argv)
                self.calls.append((command, kwargs))
                if command == ("node", "--version"):
                    return CommandResult(command, 0, "v22.0.0")
                if command[:2] == ("node", "-p"):
                    return CommandResult(command, 0, ">=22.0.0")
                return CommandResult(command, 0, "")

        runner = Runner()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "dashboard-app").mkdir()
            run_frontend_dev(root, runner=runner)
        npm_kwargs = next(kwargs for command, kwargs in runner.calls if command == ("npm", "ci"))
        self.assertGreaterEqual(float(npm_kwargs.get("timeout", 0)), 300.0)


class QbittorrentClientRegressionTests(unittest.TestCase):
    def test_configure_factory_propagates_custom_qbittorrent_webui_port(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = {
                "QBT_PASSWORD": "secret",
                "QBITTORRENT_WEBUI_PORT": "18081",
                "SONARR_PORT": "8989",
                "PROWLARR_PORT": "9696",
            }
            with mock.patch.object(CONFIGURE_MODULE, "read_servarr_api_key", return_value="sonarr-key"):
                with mock.patch.object(CONFIGURE_MODULE, "read_prowlarr_api_key", return_value="prowlarr-key"):
                    factory = build_adapter_factory(root, environment=env, transport=_Transport())
                    sonarr = factory("sonarr", environment=env)
                    prowlarr = factory("prowlarr", environment=env)

        self.assertEqual(getattr(sonarr, "_qbit_port", None), 18081)
        self.assertEqual(getattr(prowlarr.adapter, "_qbit_port", None), 18081)

    def test_servarr_updates_a_masked_existing_qbittorrent_credential(self):
        class CredentialTransport(_Transport):
            def __init__(self):
                super().__init__()
                self.tests = 0

            def request(self, method, url, **kwargs):
                self.calls.append((method, url, kwargs))
                if method == "POST" and url.endswith("/downloadclient/test"):
                    self.tests += 1
                    if self.tests == 1:
                        return {"status": 400, "body": {}}
                return {"status": 200, "body": {}}

        transport = CredentialTransport()
        adapter = SonarrAdapter(
            "http://127.0.0.1:8989",
            transport,
            api_key="sonarr-key",
            qbit_password="new-password",
            verify_qbit_client=True,
        )
        fields = [
            {"name": "host", "value": "qbittorrent"},
            {"name": "port", "value": 8081},
            {"name": "username", "value": "admin"},
            {"name": "password", "value": "********"},
            {"name": "tvCategory", "value": "sonarr"},
        ]
        schema = {"fields": fields}
        existing = {"id": 7, "implementation": "QBittorrent", "fields": fields}

        result = adapter._configure_from_state(
            [{"path": "/data/media/tv"}],
            schema,
            [existing],
            confirm=False,
        )

        self.assertIn("update-download-client", result.actions)
        self.assertTrue(any(method == "POST" and url.endswith("/downloadclient/test") for method, url, _ in transport.calls))
        self.assertTrue(any(method == "PUT" and url.endswith("/downloadclient/7") for method, url, _ in transport.calls))

    def test_prowlarr_updates_a_masked_existing_qbittorrent_credential(self):
        class CredentialTransport(_Transport):
            def __init__(self):
                super().__init__()
                self.tests = 0

            def request(self, method, url, **kwargs):
                self.calls.append((method, url, kwargs))
                if method == "POST" and url.endswith("/downloadclient/test"):
                    self.tests += 1
                    if self.tests == 1:
                        return {"status": 400, "body": {}}
                return {"status": 200, "body": {}}

        transport = CredentialTransport()
        adapter = ProwlarrAdapter(
            "http://127.0.0.1:9696",
            transport,
            api_key="prowlarr-key",
            qbit_password="new-password",
            verify_qbit_client=True,
        )
        fields = [
            {"name": "host", "value": "qbittorrent"},
            {"name": "port", "value": 8081},
            {"name": "username", "value": "admin"},
            {"name": "password", "value": "********"},
        ]
        plan = adapter._qbit_plan({"fields": fields}, {"id": 9, "fields": fields})
        result = adapter._apply_plans((plan,), confirm=False)
        self.assertIn("update-download-client", result.actions)
        self.assertEqual(
            [call[0] for call in transport.calls], ["POST", "POST", "PUT"]
        )


class NetworkLinkRegressionTests(unittest.TestCase):
    def test_management_deep_links_remain_loopback_when_jellyfin_public_host_is_lan(self):
        compose = (WORKTREE_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        for key in (
            "SONARR_EXTERNAL_URL",
            "RADARR_EXTERNAL_URL",
            "PROWLARR_EXTERNAL_URL",
            "BAZARR_EXTERNAL_URL",
            "QBITTORRENT_EXTERNAL_URL",
        ):
            line = next(line for line in compose.splitlines() if f"- {key}=" in line)
            self.assertIn("http://127.0.0.1:", line, key)
            self.assertNotIn("PUBLIC_HOST", line, key)


class UpdateHealthRegressionTests(unittest.TestCase):
    def test_update_recreate_uses_the_stack_service_health_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env_path = root / ".env"
            env_path.write_text("JELLYFIN_PORT=8096\n", encoding="utf-8")
            compose_path = root / "docker-compose.yml"
            compose_path.write_text("services:\n  jellyfin:\n    image: x\n", encoding="utf-8")
            manifest = SimpleNamespace(
                env_path=str(env_path),
                profiles=[],
                gpu_mode="none",
                gpu_environment={},
                compose_files=[str(compose_path)],
                local_image_ids={},
                image_refs={"jellyfin": "x"},
            )
            runner = cli.CommandRunner(executor=lambda argv, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""))
            with mock.patch.object(cli, "compose_config", return_value={"services": {"jellyfin": {"image": "x"}}}):
                with mock.patch.object(cli, "compose_up"):
                    with mock.patch.object(cli, "wait_for_health") as legacy_health:
                        with mock.patch.object(cli, "wait_for_stack_health", create=True) as stack_health:
                            _tag, _pull, recreate = cli._update_callbacks(
                                root,
                                manifest,
                                SimpleNamespace(dev=False),
                                runner,
                            )
                            recreate("run-1")

        stack_health.assert_called_once()
        legacy_health.assert_not_called()

    def test_stack_health_gate_checks_each_published_service_and_container_health(self):
        spec = importlib.util.find_spec("lumen_installer.health")
        self.assertIsNotNone(spec)
        if spec is None:
            return
        health_module = importlib.import_module("lumen_installer.health")
        calls = []

        class Runner:
            def run(self, argv, **kwargs):
                command = tuple(argv)
                payload = [
                    {"Service": "jellyfin", "State": "running", "Health": ""},
                    {"Service": "sonarr", "State": "running", "Health": ""},
                    {"Service": "ai-recommendations", "State": "running", "Health": "healthy"},
                ]
                return CommandResult(command, 0, json.dumps(payload))

        def connect(host, port, timeout):
            calls.append((host, port))
            return True

        result = health_module.wait_for_stack_health(
            Runner(),
            "/repo",
            "/repo/.env",
            ComposeOptions(),
            services=("jellyfin", "sonarr", "ai-recommendations"),
            environment={"JELLYFIN_PORT": "8096", "SONARR_PORT": "18989"},
            connect=connect,
            timeout=0,
        )
        self.assertTrue(result)
        self.assertEqual(calls, [("127.0.0.1", 8096), ("127.0.0.1", 18989)])


class RollbackDryRunRegressionTests(unittest.TestCase):
    def test_rollback_dry_run_validates_the_record_instead_of_false_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(RollbackValidationError):
                run_rollback(root, "missing-run", confirm=False, dry_run=True)


if __name__ == "__main__":
    unittest.main()
