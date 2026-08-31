import json
import sys
import unittest
from pathlib import Path
from unittest import mock


WORKTREE_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_ROOT = WORKTREE_ROOT / "installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.docker import (
    COMPOSE_MINIMUM,
    DependencyPlan,
    DockerPreflight,
    ManifestInspection,
    dependency_plan,
    inspect_manifest_architectures,
    parse_compose_version,
    parse_docker_version,
    validate_compose_version,
)
from lumen_installer.errors import InvalidInputError, PreflightError, UnsupportedPlatformError
from lumen_installer.platform import HostFacts


UBUNTU = HostFacts(
    uid=1000,
    gid=1000,
    timezone="UTC",
    distro_id="ubuntu",
    distro_like=("debian",),
    arch="x86_64",
    euid=1000,
    sudo_uid=None,
    sudo_gid=None,
)
FEDORA = HostFacts(
    uid=1000,
    gid=1000,
    timezone="UTC",
    distro_id="fedora",
    distro_like=("fedora",),
    arch="x86_64",
    euid=1000,
    sudo_uid=None,
    sudo_gid=None,
)
ARCH = HostFacts(
    uid=1000,
    gid=1000,
    timezone="UTC",
    distro_id="arch",
    distro_like=("arch",),
    arch="aarch64",
    euid=1000,
    sudo_uid=None,
    sudo_gid=None,
)
UNSUPPORTED = HostFacts(
    uid=1000,
    gid=1000,
    timezone="UTC",
    distro_id="alpine",
    distro_like=("alpine",),
    arch="x86_64",
    euid=1000,
    sudo_uid=None,
    sudo_gid=None,
)


class DockerVersionTests(unittest.TestCase):
    def test_parses_common_docker_version_variants(self):
        for output in (
            "Docker version 26.1.4, build 123abc",
            "26.1.4",
            "Server: Docker Engine - Community\n Version: 26.1.4\n",
        ):
            with self.subTest(output=output):
                self.assertEqual(parse_docker_version(output), (26, 1, 4))

    def test_docker_full_server_output_ignores_nested_container_runtime_versions(self):
        output = (
            "Client: Docker Engine - Community\n"
            " Version: 26.1.4\n"
            "Server: Docker Engine - Community\n"
            " Engine:\n"
            "  Version: 26.1.4\n"
            "  containerd:\n"
            "   Version: 1.7.20\n"
            "  runc:\n"
            "   Version: 1.1.14\n"
        )

        self.assertEqual(parse_docker_version(output), (26, 1, 4))

    def test_parses_common_compose_version_variants(self):
        for output in (
            "Docker Compose version v2.24.4",
            "Docker Compose version 2.24.4-desktop.1",
            "2.25.0\n",
        ):
            with self.subTest(output=output):
                self.assertEqual(parse_compose_version(output), tuple(map(int, output.strip().split()[-1].lstrip("v").split("-")[0].split("."))))

    def test_compose_floor_is_inclusive_and_rejects_older_versions(self):
        self.assertEqual(COMPOSE_MINIMUM, (2, 24, 4))
        self.assertTrue(validate_compose_version((2, 24, 4)))
        with self.assertRaises(InvalidInputError):
            validate_compose_version((2, 24, 3))
        with self.assertRaises(InvalidInputError):
            validate_compose_version(None)

    def test_passing_docker_and_compose_versions_are_accepted_without_dependency_commands(self):
        runner = mock.Mock()
        runner.run.side_effect = [
            mock.Mock(stdout="Docker version 26.1.4, build abc", stderr="", returncode=0),
            mock.Mock(stdout="Docker Compose version v2.24.4", stderr="", returncode=0),
        ]

        result = __import__("lumen_installer.docker", fromlist=["docker_preflight"]).docker_preflight(runner)

        self.assertIsInstance(result, DockerPreflight)
        self.assertTrue(result.ok)
        self.assertEqual(result.compose_version, (2, 24, 4))
        self.assertEqual(
            [call.args[0] for call in runner.run.call_args_list],
            [
                ["docker", "version", "--format", "{{.Server.Version}}"],
                ["docker", "compose", "version", "--short"],
            ],
        )

    def test_compose_below_floor_is_an_explicit_typed_preflight_failure(self):
        runner = mock.Mock()
        runner.run.side_effect = [
            mock.Mock(stdout="26.1.4", stderr="", returncode=0),
            mock.Mock(stdout="Docker Compose version v2.24.3", stderr="", returncode=0),
        ]

        from lumen_installer.docker import docker_preflight

        result = docker_preflight(runner)

        self.assertEqual(result.status, "unsupported")
        self.assertIsInstance(result.error, InvalidInputError)
        self.assertIsInstance(result.error, PreflightError)
        self.assertIn("2.24.4", str(result.error))

    def test_missing_daemon_is_explicitly_offline_or_unavailable(self):
        runner = mock.Mock()
        runner.run.side_effect = OSError("Cannot connect to the Docker daemon")

        from lumen_installer.docker import docker_preflight

        result = docker_preflight(runner)

        self.assertIn(result.status, {"offline", "unavailable"})
        self.assertFalse(result.ok)
        self.assertIsInstance(result.error, InvalidInputError)


class DependencyPolicyTests(unittest.TestCase):
    def test_ubuntu_uses_official_docker_apt_repository_without_convenience_script(self):
        plan = dependency_plan(UBUNTU)

        self.assertIsInstance(plan, DependencyPlan)
        commands = [list(command) for command in plan.commands]
        rendered = repr(commands).lower()
        self.assertIn("download.docker.com/linux/ubuntu", rendered)
        self.assertIn("docker-ce", rendered)
        self.assertIn("docker-compose-plugin", rendered)
        self.assertNotIn("get.docker.com", rendered)
        self.assertNotIn("| sh", rendered)
        self.assertNotIn("| bash", rendered)
        self.assertTrue(any("apt-get" in part for command in commands for part in command))

    def test_debian_uses_official_docker_apt_repository(self):
        host = UBUNTU.__class__(**{**UBUNTU.__dict__, "distro_id": "debian"})
        plan = dependency_plan(host)
        self.assertIn("download.docker.com/linux/debian", repr(plan.commands).lower())

    def test_fedora_uses_official_dnf_repository(self):
        plan = dependency_plan(FEDORA)
        rendered = repr(plan.commands).lower()
        self.assertIn("download.docker.com/linux/fedora/docker-ce.repo", rendered)
        self.assertIn("dnf", rendered)
        self.assertIn("docker-ce", rendered)
        self.assertNotIn("get.docker.com", rendered)

    def test_arch_and_omarchy_use_distro_packages(self):
        for distro in ("arch", "omarchy"):
            with self.subTest(distro=distro):
                host = ARCH.__class__(**{**ARCH.__dict__, "distro_id": distro})
                plan = dependency_plan(host)
                rendered = repr(plan.commands).lower()
                self.assertIn("pacman", rendered)
                self.assertIn("docker-compose", rendered)
                self.assertNotIn("download.docker.com", rendered)

    def test_unsupported_distro_is_typed_and_has_no_mutation_commands(self):
        plan = dependency_plan(UNSUPPORTED)
        self.assertFalse(plan.supported)
        self.assertEqual(plan.status, "unsupported")
        self.assertEqual(plan.commands, ())
        self.assertTrue(any(record.code == "unsupported-distro" for record in plan.decisions))
        self.assertIsNotNone(plan.error)
        self.assertIsInstance(plan.error, UnsupportedPlatformError)

    def test_sudo_conflict_group_and_logout_are_decisions_not_actions(self):
        plan = dependency_plan(UBUNTU)
        codes = {record.code for record in plan.decisions}
        self.assertTrue({"sudo-required", "conflicting-packages", "docker-group-membership", "logout-required"} <= codes)
        for record in plan.decisions:
            if record.code in {"conflicting-packages", "docker-group-membership", "logout-required"}:
                self.assertNotEqual(record.action, "execute")
        commands = repr(plan.commands).lower()
        self.assertNotIn("apt-get remove", commands)
        self.assertNotIn("groupadd", commands)
        self.assertNotIn("usermod", commands)


class ManifestInspectionTests(unittest.TestCase):
    def test_parses_linux_architectures_without_using_a_pull_command(self):
        payload = {
            "manifests": [
                {"Descriptor": {"platform": {"architecture": "amd64", "os": "linux"}}},
                {"Descriptor": {"platform": {"architecture": "arm64", "os": "linux"}}},
                {"Descriptor": {"platform": {"architecture": "windows", "os": "windows"}}},
            ]
        }
        runner = mock.Mock()
        runner.run.return_value = mock.Mock(stdout=json.dumps(payload), stderr="", returncode=0)

        result = inspect_manifest_architectures("ghcr.io/example/media:latest", runner=runner)

        self.assertIsInstance(result, ManifestInspection)
        self.assertEqual(result.status, "supported")
        self.assertEqual(result.architectures, ("amd64", "arm64"))
        runner.run.assert_called_once()
        argv = runner.run.call_args.args[0]
        self.assertEqual(argv[:3], ["docker", "manifest", "inspect"])
        self.assertNotIn("pull", argv)

    def test_offline_result_is_explicit_and_does_not_claim_support(self):
        runner = mock.Mock()
        runner.run.side_effect = OSError("network is offline")

        result = inspect_manifest_architectures("image:tag", runner=runner)

        self.assertEqual(result.status, "offline")
        self.assertFalse(result.supported)
        self.assertEqual(result.architectures, ())

    def test_unknown_manifest_result_is_explicit(self):
        runner = mock.Mock()
        runner.run.return_value = mock.Mock(stdout='{"schemaVersion": 2}', stderr="", returncode=0)

        result = inspect_manifest_architectures("image:tag", runner=runner)

        self.assertEqual(result.status, "unknown")
        self.assertFalse(result.supported)


if __name__ == "__main__":
    unittest.main()
