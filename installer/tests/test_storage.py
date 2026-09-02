import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.errors import InvalidInputError
from lumen_installer.errors import ExitCode
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
            self.assertEqual(raised.exception.exit_code, ExitCode.PARTIAL)

    def test_uid_only_and_gid_only_chown_preserve_the_other_owner_axis(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            uid = os.getuid() + 1000
            gid = os.getgid() + 1000
            OwnerStat = type("OwnerStat", (), {
                "st_uid": uid,
                "st_gid": gid,
                "st_mode": stat.S_IFDIR | 0o755,
            })

            calls = []
            chown = lambda path, requested_uid, requested_gid: calls.append(
                (Path(path), requested_uid, requested_gid)
            )
            validate_storage(
                base / "uid-library",
                base / "uid-downloads",
                repo_root=repo,
                uid=uid,
                chown_probe=chown,
                stat_probe=lambda path: OwnerStat(),
                access_probe=lambda path, mode: True,
            )
            validate_storage(
                base / "gid-library",
                base / "gid-downloads",
                repo_root=repo,
                gid=gid,
                chown_probe=chown,
                stat_probe=lambda path: OwnerStat(),
                access_probe=lambda path, mode: True,
            )
            self.assertTrue(calls)
            uid_calls = [call for call in calls if call[0] == base / "uid-library"]
            gid_calls = [call for call in calls if call[0] == base / "gid-library"]
            self.assertTrue(uid_calls)
            self.assertTrue(gid_calls)
            self.assertTrue(all(call[1:] == (uid, -1) for call in uid_calls))
            self.assertTrue(all(call[1:] == (-1, gid) for call in gid_calls))

    def test_storage_inode_swap_does_not_chown_outside_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            root = base / "library"
            downloads = base / "downloads"
            outside = base / "outside"
            outside.mkdir()
            sentinel = outside / "sentinel"
            sentinel.write_text("untouched", encoding="utf-8")
            moved = base / "library-real"

            def swap_root(path, mode):
                path = Path(path)
                if path == root:
                    path.rename(moved)
                    path.symlink_to(outside, target_is_directory=True)
                else:
                    os.chmod(path, mode)

            class OwnerStat:
                st_uid = os.getuid() + 1000
                st_gid = os.getgid() + 1000
                st_mode = stat.S_IFDIR | 0o755

            def unsafe_chown(*args):
                sentinel.write_text("outside-was-touched", encoding="utf-8")

            with mock.patch("lumen_installer.storage.os.chown", side_effect=unsafe_chown):
                with self.assertRaises(StorageMutationError):
                    validate_storage(
                        root,
                        downloads,
                        repo_root=repo,
                        uid=OwnerStat.st_uid,
                        gid=OwnerStat.st_gid,
                        stat_probe=lambda path: OwnerStat(),
                        access_probe=lambda path, mode: True,
                        chmod_probe=swap_root,
                        chown_probe=lambda path, requested_uid, requested_gid: None,
                    )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "untouched")

    def test_ordinary_root_replacement_between_preflight_and_apply_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            root = base / "library"
            root.mkdir()
            downloads = base / "downloads"
            replacement = base / "replacement"
            replacement.mkdir()
            sentinel = replacement / "outside-sentinel"
            sentinel.write_text("untouched", encoding="utf-8")
            moved = base / "library-original"
            swapped = False

            def stat_probe(path):
                nonlocal swapped
                metadata = path.stat()
                if path == root and not swapped:
                    swapped = True
                    root.rename(moved)
                    replacement.rename(root)
                return metadata

            with self.assertRaises(InvalidInputError):
                validate_storage(
                    root,
                    downloads,
                    repo_root=repo,
                    stat_probe=stat_probe,
                    access_probe=lambda path, mode: True,
                )
            self.assertEqual((root / sentinel.name).read_text(encoding="utf-8"), "untouched")
            self.assertFalse((root / "media").exists())

    def test_symlink_replacement_during_preflight_is_rejected_before_capacity_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            root = base / "library"
            root.mkdir()
            downloads = base / "downloads"
            outside = base / "outside"
            outside.mkdir()
            sentinel = outside / "sentinel"
            sentinel.write_text("untouched", encoding="utf-8")
            moved = base / "library-original"
            swapped = False

            def access_probe(path, mode):
                nonlocal swapped
                if path == root and not swapped:
                    swapped = True
                    root.rename(moved)
                    root.symlink_to(outside, target_is_directory=True)
                return True

            def statvfs_probe(path):
                if path == root or path == outside:
                    sentinel.write_text("capacity-probe-followed-symlink", encoding="utf-8")
                return type("Vfs", (), {"f_bavail": 1024, "f_frsize": 1024**3})()

            with self.assertRaises(InvalidInputError):
                validate_storage(
                    root,
                    downloads,
                    repo_root=repo,
                    access_probe=access_probe,
                    statvfs_probe=statvfs_probe,
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "untouched")

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
