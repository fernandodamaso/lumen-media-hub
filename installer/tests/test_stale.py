import sys
import tempfile
import unittest
from pathlib import Path


INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.storage import KNOWN_STACK_CONTAINER_NAMES, find_stale_containers


def inspect_row(name, working_dir, *, identifier="id", project="media", service=None):
    return {
        "Id": identifier,
        "Name": "/" + name,
        "Config": {
            "Labels": {
                "com.docker.compose.project": project,
                "com.docker.compose.service": service or name,
                "com.docker.compose.project.working_dir": working_dir,
            }
        },
    }


class StaleContainerTests(unittest.TestCase):
    def test_only_exact_known_stack_container_with_missing_checkout_is_stale(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            (repo / ".git").mkdir()
            rows = [
                inspect_row("jellyfin", str(repo), identifier="live"),
                inspect_row("qbittorrent", str(repo / "gone"), identifier="stale"),
                inspect_row("jellyfin-old", str(repo / "gone"), identifier="substring"),
                inspect_row("foreign", str(repo / "gone"), identifier="foreign-name"),
            ]
            result = find_stale_containers(rows, repo_root=repo, project_name="media")
            self.assertEqual([entry.identifier for entry in result], ["stale"])
            self.assertEqual(result[0].remove_argv, ("docker", "rm", "-f", "stale"))

    def test_foreign_project_and_malformed_or_missing_metadata_are_safe(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            rows = [
                inspect_row("jellyfin", str(repo / "gone"), identifier="foreign", project="other"),
                {"Id": "missing-labels", "Name": "/jellyfin", "Config": {"Labels": {}}},
                {"Id": "bad", "Name": "/jellyfin", "Config": {"Labels": None}},
                {"Id": "name-only", "Name": "/jellyfin"},
            ]
            self.assertEqual(find_stale_containers(rows, repo_root=repo, project_name="media"), ())

    def test_json_inspect_input_and_exact_name_catalog_are_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            self.assertIn("homepage-actions", KNOWN_STACK_CONTAINER_NAMES)
            row = inspect_row("dashboard", str(repo / "gone"), identifier="json-id")
            result = find_stale_containers("[" + __import__("json").dumps(row) + "]", repo_root=repo, project_name="media")
            self.assertEqual(result[0].identifier, "json-id")


if __name__ == "__main__":
    unittest.main()
