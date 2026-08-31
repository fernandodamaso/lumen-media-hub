import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


WORKTREE_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_ROOT = WORKTREE_ROOT / "installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.errors import DriftError, ExitCode, InvalidInputError
from lumen_installer.network import plan_network


class NetworkPlanTests(unittest.TestCase):
    def test_fresh_local_defaults_all_user_facing_network_values_to_loopback(self):
        plan = plan_network({}, "local", None, interactive=False)

        self.assertEqual(
            plan.values,
            {
                "JELLYFIN_BIND_ADDRESS": "127.0.0.1",
                "MANAGEMENT_BIND_ADDRESS": "127.0.0.1",
                "PUBLIC_HOST": "127.0.0.1",
                "JELLYFIN_REMOTE_ACCESS": "false",
            },
        )
        self.assertFalse(plan.drift)
        self.assertIsNone(plan.decision)

    def test_explicit_lan_exposes_jellyfin_and_enables_remote_access(self):
        plan = plan_network({}, "lan", "media.example.test", interactive=False)

        self.assertEqual(plan.values["JELLYFIN_BIND_ADDRESS"], "0.0.0.0")
        self.assertEqual(plan.values["MANAGEMENT_BIND_ADDRESS"], "127.0.0.1")
        self.assertEqual(plan.values["PUBLIC_HOST"], "media.example.test")
        self.assertEqual(plan.values["JELLYFIN_REMOTE_ACCESS"], "true")

    def test_legacy_adoption_interactive_records_preserve_lan_and_local_choices(self):
        plan = plan_network(
            {"ROOT_PATH": "/srv/media", "MANAGEMENT_BIND_ADDRESS": "127.0.0.1"},
            None,
            "media.example.test",
            interactive=True,
        )

        self.assertEqual(plan.values["JELLYFIN_BIND_ADDRESS"], "0.0.0.0")
        self.assertEqual(plan.values["JELLYFIN_REMOTE_ACCESS"], "true")
        self.assertIsNotNone(plan.decision)
        self.assertEqual(plan.decision["code"], "legacy-jellyfin-binding")
        self.assertIn("preserve-lan", plan.decision["options"])
        self.assertIn("local", plan.decision["options"])
        self.assertIn("JELLYFIN", plan.decision["message"])
        self.assertTrue(any(record["key"] == "JELLYFIN_BIND_ADDRESS" for record in plan.drift))
        self.assertNotIn("ROOT_PATH", plan.values)

    def test_legacy_adoption_can_choose_local_or_preserve_lan(self):
        existing = {"MANAGEMENT_BIND_ADDRESS": "127.0.0.1"}

        local = plan_network(existing, "local", None, interactive=True)
        self.assertEqual(local.values["JELLYFIN_BIND_ADDRESS"], "127.0.0.1")
        self.assertEqual(local.values["JELLYFIN_REMOTE_ACCESS"], "false")
        self.assertEqual(local.decision["selected"], "local")

        preserve = plan_network(existing, "preserve-lan", "media.example.test", interactive=True)
        self.assertEqual(preserve.values["JELLYFIN_BIND_ADDRESS"], "0.0.0.0")
        self.assertEqual(preserve.values["JELLYFIN_REMOTE_ACCESS"], "true")
        self.assertEqual(preserve.decision["selected"], "preserve-lan")

    def test_legacy_adoption_noninteractive_is_exit_three_before_any_values_are_applied(self):
        with self.assertRaises(DriftError) as raised:
            plan_network({"ROOT_PATH": "/srv/media"}, None, None, interactive=False)

        self.assertEqual(raised.exception.exit_code, ExitCode.DRIFT)
        self.assertIn("JELLYFIN_BIND_ADDRESS", str(raised.exception))

    def test_invalid_lan_public_hosts_are_rejected(self):
        for host in (
            "http://media.example.test",
            "media.example.test/path",
            "media.example.test:3000",
            "media example.test",
            "0.0.0.0",
            "*",
            "",
        ):
            with self.subTest(host=host):
                with self.assertRaises(InvalidInputError):
                    plan_network({}, "lan", host, interactive=False)

    def test_existing_explicit_values_are_preserved_without_reconciliation(self):
        plan = plan_network(
            {
                "JELLYFIN_BIND_ADDRESS": "192.168.1.20",
                "MANAGEMENT_BIND_ADDRESS": "192.168.1.21",
                "PUBLIC_HOST": "old.example.test",
                "JELLYFIN_REMOTE_ACCESS": "true",
            },
            None,
            None,
            interactive=False,
        )

        self.assertEqual(plan.values["JELLYFIN_BIND_ADDRESS"], "192.168.1.20")
        self.assertEqual(plan.values["MANAGEMENT_BIND_ADDRESS"], "192.168.1.21")
        self.assertEqual(plan.values["PUBLIC_HOST"], "old.example.test")
        self.assertEqual(plan.values["JELLYFIN_REMOTE_ACCESS"], "true")
        self.assertFalse(plan.drift)

    def test_network_display_never_includes_unrelated_secret_values(self):
        plan = plan_network(
            {"ACTIONS_TOKEN": "do-not-report", "QBT_PASSWORD": "also-secret"},
            "local",
            None,
            interactive=False,
        )

        rendered = repr(plan.display)
        self.assertNotIn("do-not-report", rendered)
        self.assertNotIn("also-secret", rendered)


@unittest.skipUnless(shutil.which("docker"), "Docker is not installed")
class ComposeNetworkBindingTests(unittest.TestCase):
    def _compose_config(self, *profiles: str, dev: bool = False) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            env_path = Path(temporary) / ".env"
            env_path.write_text(
                "\n".join(
                    (
                        "TZ=UTC",
                        "PUID=1000",
                        "PGID=1000",
                        "UMASK=002",
                        "ROOT_PATH=/srv/media",
                        "DOWNLOADS_PATH=/srv/downloads",
                        "JELLYFIN_BIND_ADDRESS=0.0.0.0",
                        "MANAGEMENT_BIND_ADDRESS=127.0.0.1",
                        "PUBLIC_HOST=media.example.test",
                        "JELLYFIN_REMOTE_ACCESS=true",
                        "JELLYFIN_PORT=18096",
                        "QBITTORRENT_WEBUI_PORT=18081",
                        "QBITTORRENT_PEER_PORT=16881",
                        "RADARR_PORT=17878",
                        "SONARR_PORT=18989",
                        "PROWLARR_PORT=19696",
                        "BAZARR_PORT=16767",
                        "JELLYSEERR_PORT=15055",
                        "MAINTAINERR_PORT=16246",
                        "QBT_PASSWORD=redacted-test-password",
                        "ACTIONS_TOKEN=redacted-test-actions-token",
                        "BAZARR_ENABLED=false",
                        "JELLYSEERR_ENABLED=false",
                        "JELLYFIN_API_KEY=placeholder",
                        "SONARR_API_KEY=placeholder",
                        "RADARR_API_KEY=placeholder",
                        "PROWLARR_API_KEY=placeholder",
                        "BAZARR_API_KEY=placeholder",
                        "JELLYSEERR_API_KEY=placeholder",
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            command = [
                "docker",
                "compose",
                "--env-file",
                str(env_path),
                "-f",
                str(WORKTREE_ROOT / "docker-compose.yml"),
            ]
            if dev:
                command.extend(("-f", str(WORKTREE_ROOT / "docker-compose.dev.yml")))
            for profile in profiles:
                command.extend(("--profile", profile))
            command.extend(("config", "--format", "json"))
            completed = subprocess.run(
                command,
                cwd=WORKTREE_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                msg=f"Compose config failed:\n{completed.stdout}\n{completed.stderr}",
            )
            return json.loads(completed.stdout)["services"]

    def test_core_and_all_profile_bindings_use_the_network_contract(self):
        services = self._compose_config(
            "subtitles", "requests", "maintenance", "indexer-tools", "ai"
        )

        self.assertEqual(services["jellyfin"]["ports"][0]["host_ip"], "0.0.0.0")
        management_services = {
            "qbittorrent",
            "radarr",
            "sonarr",
            "prowlarr",
            "flaresolverr",
            "bazarr",
            "jellyseerr",
            "maintainerr",
            "dashboard",
        }
        for service in management_services:
            with self.subTest(service=service):
                self.assertEqual(services[service]["ports"][0]["host_ip"], "127.0.0.1")

        self.assertEqual(services["homepage-actions"]["ports"][0]["host_ip"], "127.0.0.1")
        peer_ports = services["qbittorrent"]["ports"][1:]
        self.assertTrue(all("host_ip" not in port for port in peer_ports), peer_ports)

        environment = services["homepage-actions"]["environment"]
        self.assertEqual(environment["JELLYFIN_EXTERNAL_URL"], "http://media.example.test:18096")
        self.assertEqual(environment["QBITTORRENT_EXTERNAL_URL"], "http://media.example.test:18081")

    def test_dev_override_keeps_dashboard_loopback_and_retargets_container_port(self):
        services = self._compose_config(dev=True)
        dashboard_port = services["dashboard"]["ports"][0]
        self.assertEqual(dashboard_port["host_ip"], "127.0.0.1")
        self.assertEqual(str(dashboard_port["published"]), "3000")
        self.assertEqual(str(dashboard_port["target"]), "4200")


if __name__ == "__main__":
    unittest.main()
