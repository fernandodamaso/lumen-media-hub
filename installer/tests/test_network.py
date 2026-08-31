import json
import socket
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

    def test_lan_public_host_rejects_loopback_localhost_multicast_and_broadcast(self):
        for host in (
            "127.0.0.1",
            "::1",
            "localhost",
            "jellyfin.localhost",
            "224.0.0.1",
            "255.255.255.255",
            "192.0.2.255",
        ):
            with self.subTest(host=host):
                with self.assertRaises(InvalidInputError):
                    plan_network({}, "lan", host, interactive=False)

    def test_lan_public_host_rejects_disguised_loopback_names_and_numeric_forms(self):
        for host in (
            "localhost.localdomain",
            "localhost6",
            "127.0.0.1.nip.io",
            "127.1",
            "0",
            "2130706433",
            "127.000.000.001",
        ):
            with self.subTest(host=host):
                with self.assertRaises(InvalidInputError):
                    plan_network({}, "lan", host, interactive=False)

    def test_lan_public_host_rejects_injected_loopback_dns_result(self):
        calls = []

        def resolve(host):
            calls.append(host)
            return ["127.0.0.1"]

        with self.assertRaisesRegex(InvalidInputError, "loopback"):
            plan_network(
                {}, "lan", "media.example.test", interactive=False, resolver=resolve
            )
        self.assertEqual(calls, ["media.example.test"])

    def test_lan_public_host_accepts_safe_injected_dns_result(self):
        plan = plan_network(
            {},
            "lan",
            "media.example.test",
            interactive=False,
            resolver=lambda host: ["192.168.1.20"],
        )
        self.assertEqual(plan.values["PUBLIC_HOST"], "media.example.test")

    def test_lan_public_host_accepts_syntactically_valid_name_when_dns_fails(self):
        def resolve(host):
            raise socket.gaierror("temporary DNS failure")

        plan = plan_network(
            {},
            "lan",
            "media.example.test",
            interactive=False,
            resolver=resolve,
        )
        self.assertEqual(plan.values["PUBLIC_HOST"], "media.example.test")

    def test_local_mode_does_not_resolve_public_host(self):
        def resolve(host):
            raise AssertionError(f"local mode unexpectedly resolved {host}")

        plan = plan_network(
            {}, "local", "localhost", interactive=False, resolver=resolve
        )
        self.assertEqual(plan.values["PUBLIC_HOST"], "localhost")

    def test_adopted_interactive_implicit_preserve_rejects_loopback_public_host(self):
        for host in ("127.0.0.1", "localhost"):
            with self.subTest(host=host):
                with self.assertRaises(InvalidInputError):
                    plan_network(
                        {"ROOT_PATH": "/srv/media"},
                        None,
                        host,
                        interactive=True,
                    )

    def test_injected_dns_rejects_unsafe_addresses(self):
        for address in (
            "0.0.0.0",
            "169.254.1.1",
            "224.0.0.1",
            "240.0.0.1",
            "255.255.255.255",
        ):
            with self.subTest(address=address):
                with self.assertRaises(InvalidInputError):
                    plan_network(
                        {},
                        "lan",
                        "media.example.test",
                        interactive=False,
                        resolver=lambda host, address=address: [address],
                    )

    def test_local_mode_accepts_loopback_public_host_but_lan_rejects_existing_loopback(self):
        local = plan_network(
            {"JELLYFIN_BIND_ADDRESS": "127.0.0.1", "PUBLIC_HOST": "127.0.0.1"},
            "local",
            None,
            interactive=False,
        )
        self.assertEqual(local.values["PUBLIC_HOST"], "127.0.0.1")

        with self.assertRaises(InvalidInputError):
            plan_network(
                {"JELLYFIN_BIND_ADDRESS": "127.0.0.1", "PUBLIC_HOST": "127.0.0.1"},
                "lan",
                None,
                interactive=False,
            )

    def test_v1_rejects_ipv6_public_hosts_until_compose_urls_support_brackets(self):
        with self.assertRaisesRegex(InvalidInputError, "IPv6"):
            plan_network({}, "lan", "2001:db8::20", interactive=False)

    def test_bind_addresses_are_compose_ip_literals_not_hostnames(self):
        for key, value in (
            ("JELLYFIN_BIND_ADDRESS", "media.example.test"),
            ("MANAGEMENT_BIND_ADDRESS", "localhost"),
            ("JELLYFIN_BIND_ADDRESS", "2001:db8::20"),
        ):
            with self.subTest(key=key, value=value):
                with self.assertRaises(InvalidInputError):
                    plan_network({key: value}, None, None, interactive=False)

    def test_legacy_missing_binds_preserve_all_interface_exposure_with_warning(self):
        plan = plan_network({"ROOT_PATH": "/srv/media"}, None, None, interactive=True)

        self.assertEqual(plan.values["JELLYFIN_BIND_ADDRESS"], "0.0.0.0")
        self.assertEqual(plan.values["MANAGEMENT_BIND_ADDRESS"], "0.0.0.0")
        self.assertTrue(any(record["key"] == "MANAGEMENT_BIND_ADDRESS" for record in plan.drift))
        self.assertIn("management", (plan.warning or "").lower())


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
    def _compose_config(self, *profiles: str, dev: bool = False, gpu: bool = False) -> dict:
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
            if gpu:
                command.extend(("-f", str(WORKTREE_ROOT / "docker-compose.gpu.yml")))
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

    def test_gpu_overlay_keeps_all_published_bindings_explicit(self):
        services = self._compose_config(
            "subtitles", "requests", "maintenance", "indexer-tools", "ai", gpu=True
        )

        self.assertEqual(services["jellyfin"]["ports"][0]["host_ip"], "0.0.0.0")
        self.assertEqual(services["jellyfin"]["deploy"]["resources"]["reservations"]["devices"][0]["driver"], "nvidia")
        for name, service in services.items():
            for port in service.get("ports", []):
                if name == "qbittorrent" and port in service["ports"][1:]:
                    self.assertNotIn("host_ip", port)
                elif name == "homepage-actions":
                    self.assertEqual(port["host_ip"], "127.0.0.1")
                elif name == "jellyfin":
                    self.assertEqual(port["host_ip"], "0.0.0.0")
                else:
                    self.assertEqual(port["host_ip"], "127.0.0.1")

    def test_combined_dev_gpu_keeps_dashboard_loopback_and_gpu_jellyfin(self):
        services = self._compose_config(dev=True, gpu=True)

        dashboard_port = services["dashboard"]["ports"][0]
        self.assertEqual(dashboard_port["host_ip"], "127.0.0.1")
        self.assertEqual(str(dashboard_port["target"]), "4200")
        self.assertEqual(services["jellyfin"]["ports"][0]["host_ip"], "0.0.0.0")


class WindowsNetworkMigrationSourceTests(unittest.TestCase):
    def test_windows_existing_env_migration_preserves_legacy_network_before_compose(self):
        source = (WORKTREE_ROOT / "install.ps1").read_text(encoding="utf-8")
        merge_start = source.index("function Merge-MissingEnvKeys")
        merge_end = source.index("function Initialize-EnvFile")
        merge = source[merge_start:merge_end]

        self.assertIn("JELLYFIN_BIND_ADDRESS", merge)
        self.assertIn("MANAGEMENT_BIND_ADDRESS", merge)
        self.assertIn("PUBLIC_HOST", merge)
        self.assertIn("JELLYFIN_REMOTE_ACCESS", merge)
        self.assertIn("Write-Warning", merge)

        for function_name in ("Invoke-RedeployDashboard", "Invoke-Stack", "Invoke-StackUp"):
            function_start = source.index(f"function {function_name}")
            next_function = source.find("function ", function_start + 1)
            body = source[function_start:] if next_function < 0 else source[function_start:next_function]
            self.assertLess(body.index("Initialize-EnvFile"), body.index("docker compose"))

    def test_windows_migration_does_not_overwrite_explicit_network_values(self):
        source = (WORKTREE_ROOT / "install.ps1").read_text(encoding="utf-8")
        merge_start = source.index("function Merge-MissingEnvKeys")
        merge_end = source.index("function Initialize-EnvFile")
        merge = source[merge_start:merge_end]

        self.assertIn("Test-NonEmptyEnvValue $map 'JELLYFIN_BIND_ADDRESS'", merge)
        self.assertIn("Test-NonEmptyEnvValue $map 'MANAGEMENT_BIND_ADDRESS'", merge)
        self.assertIn("Test-NonEmptyEnvValue $map 'PUBLIC_HOST'", merge)
        self.assertIn("Test-NonEmptyEnvValue $map 'JELLYFIN_REMOTE_ACCESS'", merge)
        self.assertIn("0.0.0.0", merge)
        self.assertIn("127.0.0.1", merge)

    def test_windows_migration_treats_blank_network_values_as_unset(self):
        source = (WORKTREE_ROOT / "install.ps1").read_text(encoding="utf-8")
        merge_start = source.index("function Merge-MissingEnvKeys")
        merge_end = source.index("function Initialize-EnvFile")
        merge = source[merge_start:merge_end]

        self.assertIn("function Test-NonEmptyEnvValue", source)
        self.assertIn("IsNullOrWhiteSpace", source)
        for key in (
            "JELLYFIN_BIND_ADDRESS",
            "MANAGEMENT_BIND_ADDRESS",
            "PUBLIC_HOST",
            "JELLYFIN_REMOTE_ACCESS",
        ):
            self.assertIn(f"Test-NonEmptyEnvValue $map '{key}'", merge)

    def test_windows_migration_derives_remote_intent_from_effective_bind(self):
        source = (WORKTREE_ROOT / "install.ps1").read_text(encoding="utf-8")
        merge_start = source.index("function Merge-MissingEnvKeys")
        merge_end = source.index("function Initialize-EnvFile")
        merge = source[merge_start:merge_end]

        self.assertIn("$effectiveJellyfinBind", merge)
        self.assertIn("-match '^127\\.'", merge)
        self.assertIn("{ 'false' }", merge)
        self.assertIn("{ 'true' }", merge)
        self.assertIn("JELLYFIN_REMOTE_ACCESS=$remoteAccess", merge)
        self.assertNotIn("JELLYFIN_REMOTE_ACCESS=true'", merge)


if __name__ == "__main__":
    unittest.main()
