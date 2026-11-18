import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.compose import ComposeOptions, derive_pull_services, down, redeploy_dashboard, up
from lumen_installer.errors import InvalidInputError


class ComposeOptionsTests(unittest.TestCase):
    def test_builds_safe_ordered_vectors_for_overlays_profiles_and_action(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            options = ComposeOptions(profiles=("subtitles", "requests"), gpu=False, dev=True)
            vector = options.argv(root, root / ".env", "up", "-d")

        self.assertEqual(
            vector,
            (
                "docker", "compose", "--env-file", str(root / ".env"),
                "-f", str(root / "docker-compose.yml"),
                "-f", str(root / "docker-compose.dev.yml"),
                "--profile", "subtitles", "--profile", "requests",
                "up", "-d",
            ),
        )

    def test_uses_recorded_compose_files_instead_of_reconstructing_overlays(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "docker-compose.custom-base.yml"
            override = root / "docker-compose.custom-override.yml"
            options = ComposeOptions(
                compose_files=(base, override),
                profiles=("requests",),
                gpu="vaapi",
                dev=True,
            )

        self.assertEqual(
            options.argv(root, root / ".env", "up", "-d"),
            (
                "docker", "compose", "--env-file", str(root / ".env"),
                "-f", str(base), "-f", str(override),
                "--profile", "requests", "up", "-d",
            ),
        )

    def test_rejects_malformed_profiles_and_accepts_gpu_modes(self):
        with self.assertRaises(InvalidInputError):
            ComposeOptions(profiles=("requests; echo bad",))
        with self.assertRaises(InvalidInputError):
            ComposeOptions(profiles=("unknown",))
        self.assertEqual(ComposeOptions(gpu="nvidia").gpu_mode, "nvidia")
        self.assertEqual(ComposeOptions(gpu="vaapi").gpu_mode, "vaapi")
        with self.assertRaises(InvalidInputError):
            ComposeOptions(gpu="yes")

    def test_up_never_adds_remove_orphans(self):
        class Runner:
            def __init__(self):
                self.argv = None

            def run(self, argv, **kwargs):
                self.argv = tuple(argv)
                return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        runner = Runner()
        up(runner, "/srv/lumen", "/srv/lumen/.env", ComposeOptions(), services=("dashboard",))
        self.assertNotIn("--remove-orphans", runner.argv)

    def test_down_and_dashboard_redeploy_never_remove_unrelated_containers(self):
        class Runner:
            def __init__(self):
                self.argvs = []

            def run(self, argv, **kwargs):
                self.argvs.append(tuple(argv))
                return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        runner = Runner()
        down(runner, "/srv/lumen", "/srv/lumen/.env", ComposeOptions())
        redeploy_dashboard(runner, "/srv/lumen", "/srv/lumen/.env", ComposeOptions())
        self.assertTrue(all("--remove-orphans" not in argv for argv in runner.argvs))

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
        saved = ComposeOptions(profiles=("requests",), gpu=False)
        inherited = ComposeOptions().resolved(saved_profiles=saved.selected_profiles, saved_gpu="nvidia")
        overridden = ComposeOptions(profiles=(), gpu=False).resolved(
            saved_profiles=saved.selected_profiles, saved_gpu=saved.gpu
        )
        self.assertEqual(inherited.selected_profiles, ("requests",))
        self.assertTrue(inherited.gpu_enabled)
        self.assertEqual(overridden.selected_profiles, ())
        self.assertFalse(overridden.gpu_enabled)

    def test_default_file_selection_includes_existing_local_override_before_gpu_and_dev(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
            (root / "docker-compose.override.yml").write_text("services: {}\n", encoding="utf-8")
            (root / "docker-compose.gpu.yml").write_text("services: {}\n", encoding="utf-8")
            (root / "docker-compose.dev.yml").write_text("services: {}\n", encoding="utf-8")
            options = ComposeOptions(gpu="nvidia", dev=True)
            argv = options.global_argv(root, root / ".env")
            files = [argv[i] for i in range(5, len(argv), 2)]
            self.assertEqual(files, [
                str(root / "docker-compose.yml"),
                str(root / "docker-compose.override.yml"),
                str(root / "docker-compose.gpu.yml"),
                str(root / "docker-compose.dev.yml"),
            ])

    def test_default_file_selection_without_override_is_base_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
            (root / "docker-compose.dev.yml").write_text("services: {}\n", encoding="utf-8")
            options = ComposeOptions(gpu=False, dev=True)
            argv = options.global_argv(root, root / ".env")
            files = [argv[i] for i in range(5, len(argv), 2)]
            self.assertEqual(files, [
                str(root / "docker-compose.yml"),
                str(root / "docker-compose.dev.yml"),
            ])

    def test_explicit_file_lists_are_not_silently_extended(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "docker-compose.custom-base.yml"
            override = root / "docker-compose.custom-override.yml"
            (base).write_text("services: {}\n", encoding="utf-8")
            (override).write_text("services: {}\n", encoding="utf-8")
            (root / "docker-compose.override.yml").write_text("services: {}\n", encoding="utf-8")
            options = ComposeOptions(
                compose_files=(base, override),
                profiles=("requests",),
                gpu="vaapi",
                dev=True,
            )
            self.assertEqual(
                options.argv(root, root / ".env", "up", "-d"),
                (
                    "docker",
                    "compose",
                    "--env-file",
                    str(root / ".env"),
                    "-f",
                    str(base),
                    "-f",
                    str(override),
                    "--profile",
                    "requests",
                    "up",
                    "-d",
                ),
            )

    def test_default_file_selection_ordering_base_then_override_then_gpu_then_dev(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
            (root / "docker-compose.override.yml").write_text("services: {}\n", encoding="utf-8")
            options = ComposeOptions(gpu="vaapi", dev=True)
            argv = options.global_argv(root, root / ".env")
            self.assertEqual(argv[4], "-f")
            self.assertEqual(argv[5], str(root / "docker-compose.yml"))
            self.assertEqual(argv[6], "-f")
            self.assertEqual(argv[7], str(root / "docker-compose.override.yml"))
            self.assertEqual(argv[8], "-f")
            self.assertEqual(argv[9], str(root / "docker-compose.vaapi.yml"))
            self.assertEqual(argv[10], "-f")
            self.assertEqual(argv[11], str(root / "docker-compose.dev.yml"))

    def test_default_selection_includes_override_but_preserves_explicit_file_lists(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
            (root / "docker-compose.override.yml").write_text("services: {}\n", encoding="utf-8")
            explicit_a = root / "docker-compose.explicit-a.yml"
            explicit_b = root / "docker-compose.explicit-b.yml"
            explicit_a.write_text("services: {}\n", encoding="utf-8")
            explicit_b.write_text("services: {}\n", encoding="utf-8")
            options = ComposeOptions(compose_files=(explicit_a, explicit_b))
            vector = options.global_argv(root, root / ".env")
            self.assertEqual(vector.count("-f"), 2)
            self.assertEqual(vector[4], "-f")
            self.assertEqual(vector[5], str(explicit_a))

    def test_no_override_file_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
            vector = ComposeOptions(dev=True).global_argv(root, root / ".env")
            self.assertIn(str(root / "docker-compose.yml"), vector)
            self.assertIn(str(root / "docker-compose.dev.yml"), vector)


if __name__ == "__main__":
    unittest.main()
