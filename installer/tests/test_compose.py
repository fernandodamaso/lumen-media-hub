import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.compose import ComposeOptions, derive_pull_services
from lumen_installer.errors import InvalidInputError


class ComposeOptionsTests(unittest.TestCase):
    def test_builds_safe_ordered_vectors_for_overlays_profiles_and_action(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            options = ComposeOptions(profiles=("subtitles", "requests"), gpu=True, dev=True)
            vector = options.argv(root, root / ".env", "up", "-d", "--remove-orphans")

        self.assertEqual(
            vector,
            (
                "docker", "compose", "--env-file", str(root / ".env"),
                "-f", str(root / "docker-compose.yml"),
                "-f", str(root / "docker-compose.gpu.yml"),
                "-f", str(root / "docker-compose.dev.yml"),
                "--profile", "subtitles", "--profile", "requests",
                "up", "-d", "--remove-orphans",
            ),
        )

    def test_rejects_malformed_profiles_and_options(self):
        with self.assertRaises(InvalidInputError):
            ComposeOptions(profiles=("requests; echo bad",))
        with self.assertRaises(InvalidInputError):
            ComposeOptions(profiles=("unknown",))
        with self.assertRaises(InvalidInputError):
            ComposeOptions(gpu="yes")

    def test_derives_only_enabled_non_build_services(self):
        payload = {
            "services": {
                "jellyfin": {"image": "example"},
                "dashboard": {"build": {"context": "dashboard-app"}, "image": "local"},
                "ai-recommendations": {"build": {"context": "config/ai-recommendations"}},
            }
        }
        self.assertEqual(derive_pull_services(payload), ("jellyfin",))

    def test_saved_choices_are_used_unless_an_explicit_override_is_given(self):
        saved = ComposeOptions(profiles=("requests",), gpu=True)
        inherited = ComposeOptions().resolved(saved_profiles=saved.selected_profiles, saved_gpu=saved.gpu)
        overridden = ComposeOptions(profiles=(), gpu=False).resolved(
            saved_profiles=saved.selected_profiles, saved_gpu=saved.gpu
        )
        self.assertEqual(inherited.selected_profiles, ("requests",))
        self.assertTrue(inherited.gpu_enabled)
        self.assertEqual(overridden.selected_profiles, ())
        self.assertFalse(overridden.gpu_enabled)


if __name__ == "__main__":
    unittest.main()
