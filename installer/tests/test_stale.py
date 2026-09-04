import sys
import tempfile
import unittest
from pathlib import Path


INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.storage import KNOWN_STACK_CONTAINER_NAMES, find_stale_containers


def inspect_row(name, working_dir, *, identifier="a" * 12, project="media", service=None):
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
                inspect_row("jellyfin", str(repo), identifier="a" * 12),
                inspect_row("qbittorrent", str(repo / "gone"), identifier="b" * 12),
                inspect_row("jellyfin-old", str(repo / "gone"), identifier="c" * 12),
                inspect_row("foreign", str(repo / "gone"), identifier="d" * 12),
            ]
            result = find_stale_containers(rows, repo)
            self.assertEqual([entry.execution_identifier for entry in result], ["b" * 12])
            self.assertEqual(result[0].execution_argv, ("docker", "rm", "-f", "b" * 12))
            self.assertNotIn("b" * 12, repr(result[0]))
            self.assertNotIn("b" * 12, str(result[0]))
            self.assertNotIn("b" * 12, repr(result[0].plan))
            self.assertNotIn("b" * 12, repr(result[0].report))

    def test_foreign_project_and_malformed_or_missing_metadata_are_safe(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            (repo / ".git").mkdir()
            rows = [
                inspect_row("jellyfin", str(repo / "gone"), identifier="a" * 12, project="other", service="foreign-service"),
                {"Id": "missing-labels", "Name": "/jellyfin", "Config": {"Labels": {}}},
                {"Id": "bad", "Name": "/jellyfin", "Config": {"Labels": None}},
                {"Id": "name-only", "Name": "/jellyfin"},
            ]
            self.assertEqual(find_stale_containers(rows, repo), ())

    def test_json_inspect_input_and_exact_name_catalog_are_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            (repo / ".git").mkdir()
            self.assertIn("homepage-actions", KNOWN_STACK_CONTAINER_NAMES)
            row = inspect_row("dashboard", str(repo / "gone"), identifier="e" * 12, project="worktree-project")
            result = find_stale_containers("[" + __import__("json").dumps(row) + "]", repo, project_name="media")
            self.assertEqual(result, ())
            result = find_stale_containers("[" + __import__("json").dumps(row) + "]", repo)
            self.assertEqual(result[0].execution_identifier, "e" * 12)

    def test_current_repo_without_git_is_not_a_live_checkout_and_canonical_root_is_skipped(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            row = inspect_row("dashboard", str(repo), identifier="f" * 12, project="worktree-project")
            self.assertEqual(find_stale_containers([row], repo), ())
            (repo / ".git").mkdir()
            self.assertEqual(find_stale_containers([row], repo), ())

    def test_invalid_docker_ids_are_not_returned_as_removal_options(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            (repo / ".git").mkdir()
            gone = repo / "gone"
            cases = ("id", "-" + "a" * 12, "a" * 11, "a" * 65, "a" * 11 + " ")
            rows = [inspect_row("dashboard", str(gone), identifier=value, project="worktree-project") for value in cases]
            self.assertEqual(find_stale_containers(rows, repo), ())


if __name__ == "__main__":
    unittest.main()
