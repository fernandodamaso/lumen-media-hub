"""Behavioral acceptance checks for the Linux installer delivery contract.

These tests intentionally exercise command builders and Compose itself.  They
do not search README/AGENTS prose for keywords, and Compose ``config`` is a
client-side render that does not contact or mutate a Docker daemon.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

INSTALLER_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = INSTALLER_ROOT.parent
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "command-contract.json"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer import cli
from lumen_installer.update import UpdateManifest, render_rollback_override


def _powershell_validate_set(script: str, parameter: str) -> tuple[str, ...]:
    """Read the executable ``ValidateSet`` attached to one PS parameter.

    The test does not grep documentation: it tokenizes the PowerShell source
    around the parameter declaration and extracts the quoted values from the
    actual validation expression used by ``install.ps1``.
    """

    parameter_marker = f"[string]${parameter}"
    parameter_start = script.find(parameter_marker)
    if parameter_start < 0:
        raise AssertionError(f"PowerShell parameter {parameter!r} is missing")
    validate_start = script.rfind("[ValidateSet(", 0, parameter_start)
    if validate_start < 0:
        raise AssertionError(f"PowerShell parameter {parameter!r} has no ValidateSet")
    open_paren = script.find("(", validate_start)
    if open_paren < 0:
        raise AssertionError("ValidateSet has no opening parenthesis")
    depth = 0
    quote: str | None = None
    close_paren = None
    for index in range(open_paren, len(script)):
        char = script[index]
        if quote is not None:
            if char == quote:
                # PowerShell escapes single quotes by doubling them.
                if index + 1 < len(script) and script[index + 1] == quote:
                    continue
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                close_paren = index
                break
    if close_paren is None:
        raise AssertionError("ValidateSet is not balanced")
    values = re.findall(r"'([^']*)'|\"([^\"]*)\"", script[open_paren + 1 : close_paren])
    return tuple(single or double for single, double in values)


class CommandContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_linux_command_surface_and_parity_fixture(self):
        expected_linux = tuple(self.fixture["linux_commands"])
        parser = cli.build_parser()
        actual_linux = tuple(parser._subparsers._group_actions[0].choices)
        self.assertEqual(actual_linux, expected_linux)
        for mapping in self.fixture["parity"].values():
            parsed = parser.parse_args([mapping["linux"]])
            self.assertEqual(parsed.command, mapping["linux"])

    def test_windows_mode_contract_and_parity_fixture(self):
        script = (REPOSITORY_ROOT / "install.ps1").read_text(encoding="utf-8")
        windows_modes = _powershell_validate_set(script, "Mode")
        self.assertEqual(tuple(self.fixture["windows_commands"]), windows_modes)
        for mapping in self.fixture["parity"].values():
            self.assertIn(mapping["windows_mode"], windows_modes)


class ComposeAcceptanceTests(unittest.TestCase):
    all_profiles = (
        "subtitles",
        "requests",
        "maintenance",
        "indexer-tools",
        "ai",
    )
    expected_core = {
        "jellyfin",
        "qbittorrent",
        "sonarr",
        "radarr",
        "prowlarr",
        "homepage-actions",
        "dashboard",
    }
    expected_all = expected_core | {
        "bazarr",
        "jellyseerr",
        "unpackerr",
        "recyclarr",
        "maintainerr",
        "flaresolverr",
        "ai-recommendations",
    }

    def _compose(self, env_file: Path, *files: str, profiles: tuple[str, ...] = ()) -> dict:
        docker = shutil.which("docker")
        if docker is None:
            self.fail("Docker CLI is required for Compose acceptance checks")
        command = [docker, "compose", "--env-file", str(env_file)]
        for profile in profiles:
            command.extend(("--profile", profile))
        for filename in files:
            command.extend(("-f", str(REPOSITORY_ROOT / filename)))
        command.extend(("config", "--format", "json"))
        completed = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if completed.returncode != 0:
            self.fail(
                f"Compose {files!r} render failed with exit {completed.returncode}: "
                f"{completed.stderr[-600:]}"
            )
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            self.fail(f"Compose {files!r} did not return JSON: {error}")
            raise AssertionError from error

    def test_core_all_dev_nvidia_and_vaapi_render_without_daemon(self):
        with tempfile.TemporaryDirectory(prefix="lumen-acceptance-") as temporary:
            env_file = Path(temporary) / ".env"
            env_file.write_text(
                (REPOSITORY_ROOT / ".env.example").read_text(encoding="utf-8")
                + "\nRENDER_GID=65534\nVIDEO_GID=65533\n",
                encoding="utf-8",
            )
            variants = {
                "core": self._compose(env_file, "docker-compose.yml"),
                "all": self._compose(
                    env_file,
                    "docker-compose.yml",
                    profiles=self.all_profiles,
                ),
                "dev": self._compose(
                    env_file,
                    "docker-compose.yml",
                    "docker-compose.dev.yml",
                ),
                "nvidia": self._compose(
                    env_file,
                    "docker-compose.yml",
                    "docker-compose.gpu.yml",
                ),
                "vaapi": self._compose(
                    env_file,
                    "docker-compose.yml",
                    "docker-compose.vaapi.yml",
                ),
            }

        self.assertEqual(set(variants["core"]["services"]), self.expected_core)
        self.assertEqual(set(variants["all"]["services"]), self.expected_all)

        dev_dashboard = variants["dev"]["services"]["dashboard"]
        self.assertEqual(dev_dashboard["image"], "node:22-alpine")
        self.assertNotIn("build", dev_dashboard)
        self.assertEqual(dev_dashboard["ports"][0]["target"], 4200)

        nvidia_device = variants["nvidia"]["services"]["jellyfin"][
            "deploy"
        ]["resources"]["reservations"]["devices"][0]
        self.assertEqual(nvidia_device["driver"], "nvidia")

        vaapi_jellyfin = variants["vaapi"]["services"]["jellyfin"]
        self.assertEqual(vaapi_jellyfin["devices"][0]["source"], "/dev/dri")
        self.assertEqual(vaapi_jellyfin["group_add"], ["65534", "65533"])


class RollbackAcceptanceTests(unittest.TestCase):
    def test_rollback_fixture_uses_immutable_registry_and_local_build_images(self):
        with tempfile.TemporaryDirectory(prefix="lumen-rollback-") as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            compose = root / "docker-compose.yml"
            compose.write_text(
                "services:\n"
                "  api:\n"
                "    image: registry.example/api:latest\n"
                "  dashboard:\n"
                "    build: ./dashboard-app\n",
                encoding="utf-8",
            )
            manifest = UpdateManifest.from_inputs(
                root / ".env",
                {"config": root / "config"},
                {"api": "registry.example/api:latest", "dashboard": "local/dashboard:local"},
                {"api": "sha256:" + "a" * 64},
                {"dashboard": "sha256:" + "b" * 64},
                (),
                "none",
                (compose,),
            )
            rendered = render_rollback_override(
                manifest,
                "run-17",
                {"dashboard"},
                {"dashboard": "lumen-rollback/dashboard:run-17"},
            )

        self.assertIn("registry.example/api@sha256:" + "a" * 64, rendered)
        self.assertIn("lumen-rollback/dashboard:run-17", rendered)
        self.assertEqual(rendered.count("pull_policy: never"), 2)
        self.assertEqual(rendered.count("build: !reset null"), 2)
        self.assertNotIn("/media", rendered)
        self.assertNotIn("/downloads", rendered)


if __name__ == "__main__":
    unittest.main()
