import os
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


WORKTREE_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_ROOT = WORKTREE_ROOT / "installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.errors import InvalidInputError
from lumen_installer.platform import HostFacts, detect_host


class PlatformDetectionTests(unittest.TestCase):
    def test_host_facts_are_immutable(self):
        facts = HostFacts(
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

        with self.assertRaises(FrozenInstanceError):
            facts.uid = 2000

    def test_detects_ordinary_user_and_normalizes_host_facts(self):
        with tempfile.TemporaryDirectory() as temporary:
            localtime = Path(temporary) / "localtime"
            localtime.symlink_to("/usr/share/zoneinfo/America/Sao_Paulo")

            facts = detect_host(
                euid=1000,
                getuid=lambda: 1001,
                getgid=lambda: 1002,
                environment={},
                localtime_path=localtime,
                os_release_text='ID="ubuntu"\nID_LIKE="debian"\n',
                machine="amd64",
            )

        self.assertEqual(facts.uid, 1001)
        self.assertEqual(facts.gid, 1002)
        self.assertEqual(facts.timezone, "America/Sao_Paulo")
        self.assertEqual(facts.distro_id, "ubuntu")
        self.assertEqual(facts.distro_like, ("debian",))
        self.assertEqual(facts.arch, "x86_64")
        self.assertEqual(facts.euid, 1000)
        self.assertIsNone(facts.sudo_uid)
        self.assertIsNone(facts.sudo_gid)

    def test_sudo_invoker_uses_non_root_owner_ids(self):
        facts = detect_host(
            euid=0,
            getuid=lambda: 0,
            getgid=lambda: 0,
            environment={"SUDO_UID": "1100", "SUDO_GID": "1200"},
            timezone="UTC",
            os_release_text="ID=fedora\nID_LIKE=\"rhel fedora\"\n",
            machine="aarch64",
        )

        self.assertEqual((facts.uid, facts.gid), (1100, 1200))
        self.assertEqual((facts.sudo_uid, facts.sudo_gid), (1100, 1200))
        self.assertEqual(facts.arch, "aarch64")
        self.assertEqual(facts.distro_like, ("rhel", "fedora"))

    def test_genuine_root_requires_explicit_nonzero_owner_ids(self):
        with self.assertRaises(InvalidInputError):
            detect_host(
                euid=0,
                getuid=lambda: 0,
                getgid=lambda: 0,
                environment={},
                timezone="UTC",
                machine="x86_64",
            )

        facts = detect_host(
            euid=0,
            getuid=lambda: 0,
            getgid=lambda: 0,
            environment={},
            uid=1300,
            gid=1400,
            timezone="UTC",
            machine="x86_64",
        )
        self.assertEqual((facts.uid, facts.gid), (1300, 1400))

    def test_timezone_falls_back_to_timedatectl(self):
        with tempfile.TemporaryDirectory() as temporary:
            localtime = Path(temporary) / "localtime"
            localtime.write_bytes(b"not-a-zoneinfo-symlink")
            calls = []

            def timedatectl():
                calls.append(True)
                return "Europe/Lisbon\n"

            facts = detect_host(
                euid=1000,
                getuid=lambda: 1000,
                getgid=lambda: 1000,
                environment={},
                localtime_path=localtime,
                timedatectl=timedatectl,
                machine="x86_64",
            )

        self.assertEqual(facts.timezone, "Europe/Lisbon")
        self.assertEqual(calls, [True])

    def test_rejects_unsupported_architecture(self):
        with self.assertRaises(InvalidInputError):
            detect_host(
                euid=1000,
                getuid=lambda: 1000,
                getgid=lambda: 1000,
                environment={},
                timezone="UTC",
                machine="riscv64",
            )

    def test_detects_distribution_codename_for_dependency_repository_policy(self):
        facts = detect_host(
            euid=1000,
            getuid=lambda: 1000,
            getgid=lambda: 1000,
            environment={},
            timezone="UTC",
            os_release_text='ID=ubuntu\nVERSION_CODENAME=jammy\n',
            machine="x86_64",
        )

        self.assertEqual(facts.codename, "jammy")
        self.assertEqual(facts.distro_codename, "jammy")
        self.assertEqual(facts.version_codename, "jammy")


if __name__ == "__main__":
    unittest.main()
