import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path


INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.errors import InvalidInputError
from lumen_installer.storage import StorageMutationError, validate_storage


class StorageValidationTests(unittest.TestCase):
    def test_valid_storage_creates_only_approved_layout_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            root = base / "library"
            downloads = base / "downloads"
            repo.mkdir()

            result = validate_storage(root, downloads, repo_root=repo, uid=os.getuid(), gid=os.getgid())
            expected = {
                root,
                downloads,
                root / "media",
                root / "media" / "movies",
                root / "media" / "tv",
            }
            self.assertEqual(set(result.created_paths), expected)
            self.assertEqual(set(p for p in result.approved_paths), expected)
            self.assertTrue((root / "media" / "movies").is_dir())
            self.assertFalse((root / "music").exists())
            before = {path: path.stat().st_mtime_ns for path in expected}
            again = validate_storage(root, downloads, repo_root=repo, uid=os.getuid(), gid=os.getgid())
            self.assertEqual(again.created_paths, ())
            self.assertEqual(before, {path: path.stat().st_mtime_ns for path in expected})

    def test_dry_run_reports_layout_without_creating_or_mutating(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            root = base / "library"
            downloads = base / "downloads"
            result = validate_storage(root, downloads, repo_root=repo, dry_run=True)
            self.assertFalse(root.exists())
            self.assertFalse(downloads.exists())
            self.assertEqual(len(result.approved_paths), 5)
            self.assertTrue(result.report["dry_run"])

    def test_creation_failure_rolls_back_only_empty_directories_created_by_this_call(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            root = base / "library"
            downloads = base / "downloads"
            preexisting = root / "media"
            preexisting.mkdir(parents=True)
            (preexisting / "keep.txt").write_text("keep", encoding="utf-8")

            def mkdir_probe(path, mode):
                if Path(path).name == "tv":
                    raise OSError("injected mkdir failure")
                Path(path).mkdir(mode=mode)

            with self.assertRaises(InvalidInputError):
                validate_storage(root, downloads, repo_root=repo, mkdir_probe=mkdir_probe)
            self.assertTrue(preexisting.is_dir())
            self.assertTrue((preexisting / "keep.txt").exists())
            self.assertFalse(downloads.exists())
            self.assertFalse((root / "media" / "movies").exists())

    def test_failed_rollback_reports_only_unremoved_created_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            root = base / "library"
            downloads = base / "downloads"

            def mkdir_probe(path, mode):
                if Path(path).name == "tv":
                    raise OSError("injected mkdir failure")
                Path(path).mkdir(mode=mode)

            def remove_probe(path):
                if Path(path).name == "media":
                    raise OSError("injected rollback failure")
                Path(path).rmdir()

            with self.assertRaises(StorageMutationError) as raised:
                validate_storage(root, downloads, repo_root=repo, mkdir_probe=mkdir_probe, remove_probe=remove_probe)
            self.assertIn(str(root / "media"), raised.exception.partial_created_paths)
            self.assertIn(str(root / "media"), raised.exception.report["partial_created_paths"])
            self.assertEqual(raised.exception.redacted, raised.exception.report)

    def test_mkdir_failure_after_creation_is_rolled_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            root = base / "library"
            downloads = base / "downloads"

            def mkdir_probe(path, mode):
                path.mkdir(mode=mode)
                if path == root / "media" / "movies":
                    raise OSError("mkdir reported failure after creating path")

            with self.assertRaises(InvalidInputError):
                validate_storage(root, downloads, repo_root=repo, mkdir_probe=mkdir_probe)
            self.assertFalse(root.exists())
            self.assertFalse(downloads.exists())

    def test_ownership_is_checked_on_existing_parent_for_missing_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            foreign = type("ForeignStat", (), {
                "st_uid": 4242,
                "st_gid": 4343,
                "st_mode": stat.S_IFDIR | 0o755,
            })()
            with self.assertRaises(InvalidInputError):
                validate_storage(
                    base / "library",
                    base / "downloads",
                    repo_root=repo,
                    uid=1000,
                    gid=1000,
                    stat_probe=lambda path: foreign,
                    dry_run=True,
                )

    def test_rejects_empty_relative_root_repo_root_inside_repo_and_overlap(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            bad_paths = (
                ("", base / "downloads"),
                ("relative", base / "downloads"),
                (Path("/"), base / "downloads"),
                (repo, base / "downloads"),
                (repo / "media", base / "downloads"),
                (base / "same", base / "same"),
                (base / "same", base / "same" / "child"),
            )
            for root, downloads in bad_paths:
                with self.subTest(root=root, downloads=downloads):
                    with self.assertRaises(InvalidInputError):
                        validate_storage(root, downloads, repo_root=repo, dry_run=True)

    def test_rejects_storage_parent_that_would_contain_the_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "library" / "checkout"
            repo.mkdir(parents=True)
            with self.assertRaises(InvalidInputError):
                validate_storage(base / "library", base / "downloads", repo_root=repo, dry_run=True)

    def test_rejects_symlink_target_that_aliases_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            link = base / "library"
            link.symlink_to(repo, target_is_directory=True)
            with self.assertRaises(InvalidInputError):
                validate_storage(link, base / "downloads", repo_root=repo, dry_run=True)

    def test_rejects_symlink_target_even_when_it_points_outside_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            outside = base / "outside"
            outside.mkdir()
            link = base / "library"
            link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(InvalidInputError):
                validate_storage(link, base / "downloads", repo_root=repo, dry_run=True)

    def test_rejects_existing_target_without_any_write_permission(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            root = base / "library"
            downloads = base / "downloads"
            root.mkdir(mode=0o555)
            downloads.mkdir()
            with self.assertRaises(InvalidInputError):
                validate_storage(root, downloads, repo_root=repo, dry_run=True)

    def test_capacity_writeability_and_ownership_are_injected_and_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            root = base / "library"
            downloads = base / "downloads"
            low_space = type("Vfs", (), {"f_bavail": 1, "f_frsize": 1024})()
            with self.assertRaises(InvalidInputError):
                validate_storage(
                    root,
                    downloads,
                    repo_root=repo,
                    required_free_gib=1,
                    statvfs_probe=lambda path: low_space,
                    dry_run=True,
                )

            with self.assertRaises(InvalidInputError):
                validate_storage(
                    root,
                    downloads,
                    repo_root=repo,
                    access_probe=lambda path, mode: False,
                    dry_run=True,
                )

            class ForeignStat:
                st_uid = 4242
                st_gid = 4343
                st_mode = stat.S_IFDIR | 0o755

            root.mkdir()
            downloads.mkdir()
            with self.assertRaises(InvalidInputError):
                validate_storage(
                    root,
                    downloads,
                    repo_root=repo,
                    uid=1000,
                    gid=1000,
                    stat_probe=lambda path: ForeignStat(),
                    dry_run=True,
                )


if __name__ == "__main__":
    unittest.main()
