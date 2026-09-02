import json
import os
import stat
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock


INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.errors import InvalidInputError
from lumen_installer.state import InstallerState, StageJournal


class InstallerStateTests(unittest.TestCase):
    def test_new_state_persists_deterministic_schema_and_restrictive_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            state = InstallerState(
                repo_root=repo,
                profiles=("requests", "ai"),
                gpu_mode="none",
                owned_resources={"dashboard": "dashboard"},
            )

            state.save()

            state_dir = repo / ".state" / "installer"
            state_path = state_dir / "state.json"
            self.assertEqual(stat.S_IMODE(state_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(state_path.stat().st_mode), 0o600)
            self.assertEqual(
                state_path.read_text(encoding="utf-8"),
                '{"completed_stages":[],"gpu_mode":"none","owned_resources":{"dashboard":"dashboard"},"profiles":["ai","requests"],"schema_version":1}\n',
            )
            loaded = InstallerState.load(repo)
            self.assertEqual(loaded.profiles, ("ai", "requests"))
            self.assertEqual(loaded.owned_resources, {"dashboard": "dashboard"})

    def test_corrupt_or_unknown_schema_fails_without_resetting_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            state_path = repo / ".state" / "installer" / "state.json"
            state_path.parent.mkdir(parents=True)
            original = '{"schema_version":999,"profiles":[]}'
            state_path.write_text(original, encoding="utf-8")
            with self.assertRaises(InvalidInputError):
                InstallerState.load(repo)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)

            state_path.write_text("not json", encoding="utf-8")
            with self.assertRaises(InvalidInputError):
                InstallerState.load(repo)
            self.assertEqual(state_path.read_text(encoding="utf-8"), "not json")

    def test_schema_version_must_be_integer_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            path = repo / ".state" / "installer" / "state.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps({
                    "schema_version": 1.0,
                    "profiles": [],
                    "gpu_mode": "none",
                    "owned_resources": {},
                    "completed_stages": [],
                }),
                encoding="utf-8",
            )
            with self.assertRaises(InvalidInputError):
                InstallerState.load(repo)
            with self.assertRaises(InvalidInputError):
                InstallerState(schema_version=1.0)

    def test_schema_requires_all_fields_exact_types_and_allowed_stage_set(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            path = repo / ".state" / "installer" / "state.json"
            path.parent.mkdir(parents=True)
            canonical = {
                "schema_version": 1,
                "profiles": [],
                "gpu_mode": "none",
                "owned_resources": {},
                "completed_stages": [],
            }
            for field_name in canonical:
                malformed = dict(canonical)
                malformed.pop(field_name)
                path.write_text(json.dumps(malformed), encoding="utf-8")
                with self.subTest(kind="missing", field=field_name):
                    with self.assertRaises(InvalidInputError):
                        InstallerState.load(repo)
            for field_name in ("profiles", "gpu_mode", "owned_resources", "completed_stages"):
                malformed = dict(canonical)
                malformed[field_name] = None
                path.write_text(json.dumps(malformed), encoding="utf-8")
                with self.subTest(kind="null", field=field_name):
                    with self.assertRaises(InvalidInputError):
                        InstallerState.load(repo)
            malformed = dict(canonical)
            malformed["unexpected"] = "value"
            path.write_text(json.dumps(malformed), encoding="utf-8")
            with self.assertRaises(InvalidInputError):
                InstallerState.load(repo)
            malformed = dict(canonical)
            malformed["completed_stages"] = ["future-stage"]
            path.write_text(json.dumps(malformed), encoding="utf-8")
            with self.assertRaises(InvalidInputError):
                InstallerState.load(repo, allowed_stages=("host",))
            for field_name in ("profiles", "gpu_mode", "owned_resources", "completed_stages"):
                with self.subTest(kind="constructor-null", field=field_name):
                    with self.assertRaises(InvalidInputError):
                        InstallerState(**{field_name: None})

    def test_direct_load_rejects_unknown_stage_without_an_explicit_stage_registry(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            path = repo / ".state" / "installer" / "state.json"
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps({
                    "schema_version": 1,
                    "profiles": [],
                    "gpu_mode": "none",
                    "owned_resources": {},
                    "completed_stages": ["bogus"],
                }),
                encoding="utf-8",
            )
            with self.assertRaises(InvalidInputError):
                InstallerState.load(repo)

    def test_invalid_state_directory_is_not_treated_as_a_missing_fresh_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            state_parent = repo / ".state"
            state_parent.mkdir()
            (state_parent / "installer").write_text("not a directory", encoding="utf-8")
            with self.assertRaises(InvalidInputError):
                InstallerState.load(repo)

    def test_direct_state_file_outside_required_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            direct = Path(temporary) / "state.json"
            direct.write_text("{}", encoding="utf-8")
            with self.assertRaises(InvalidInputError):
                InstallerState.load(direct)

    def test_repr_does_not_include_opaque_resource_identifier_values(self):
        state = InstallerState(owned_resources={"resource": "opaque-identifier"})
        self.assertNotIn("opaque-identifier", repr(state))

    def test_failed_atomic_replace_keeps_previous_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            state = InstallerState(repo_root=repo, profiles=("requests",))
            state.save()
            path = repo / ".state" / "installer" / "state.json"
            original = path.read_bytes()
            changed = InstallerState(repo_root=repo, profiles=("subtitles",))
            with mock.patch("lumen_installer.state.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    changed.save()
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual({child.name for child in path.parent.iterdir()}, {"state.json"})

    def test_state_mode_is_set_before_replace_and_final_chmod_is_never_needed(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            state = InstallerState(repo_root=repo, profiles=("requests",))
            state_path = repo / ".state" / "installer" / "state.json"
            replace_seen = []
            real_replace = os.replace
            real_chmod = os.chmod

            def replace(source, destination, **kwargs):
                replace_seen.append((Path(source), Path(destination)))
                return real_replace(source, destination, **kwargs)

            def chmod(path, mode):
                if Path(path) == state_path:
                    raise OSError("final chmod must not run")
                return real_chmod(path, mode)

            with mock.patch("lumen_installer.state.os.replace", side_effect=replace):
                with mock.patch("lumen_installer.state.os.chmod", side_effect=chmod):
                    state.save()
            self.assertEqual(len(replace_seen), 1)
            self.assertTrue(state_path.exists())

            old = state_path.read_bytes()
            def fail_temp(fd, mode):
                raise OSError("temporary chmod failed")

            with mock.patch("lumen_installer.state.os.fchmod", side_effect=fail_temp):
                with self.assertRaises(OSError):
                    InstallerState(repo_root=repo, profiles=("ai",)).save()
            self.assertEqual(state_path.read_bytes(), old)

            with mock.patch("lumen_installer.state.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    InstallerState(repo_root=repo, profiles=("ai",)).save()
            self.assertEqual(state_path.read_bytes(), old)

            real_fsync = os.fsync
            fsync_calls = 0

            def fail_pre_rename_fsync(fd):
                nonlocal fsync_calls
                fsync_calls += 1
                if fsync_calls == 2:
                    raise OSError("pre-rename directory fsync failed")
                return real_fsync(fd)

            with mock.patch("lumen_installer.state.os.fsync", side_effect=fail_pre_rename_fsync):
                with self.assertRaises(OSError):
                    InstallerState(repo_root=repo, profiles=("ai",)).save()
            self.assertEqual(state_path.read_bytes(), old)

            fsync_calls = 0

            def fail_post_rename_fsync(fd):
                nonlocal fsync_calls
                fsync_calls += 1
                if fsync_calls == 3:
                    raise OSError("post-rename directory fsync failed")
                return real_fsync(fd)

            with mock.patch("lumen_installer.state.os.fsync", side_effect=fail_post_rename_fsync):
                InstallerState(repo_root=repo, profiles=("ai",)).save()
            self.assertEqual(InstallerState.load(repo).profiles, ("ai",))

    def test_state_replace_cannot_follow_an_installer_directory_swap(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            InstallerState(repo_root=repo, profiles=("requests",)).save()
            installer = repo / ".state" / "installer"
            outside = base / "outside"
            outside.mkdir()
            outside_state = outside / "state.json"
            outside_state.write_text("outside-sentinel", encoding="utf-8")
            moved = repo / ".state" / "installer-real"
            real_replace = os.replace

            def swap_then_replace(source, destination, **kwargs):
                installer.rename(moved)
                installer.symlink_to(outside, target_is_directory=True)
                return real_replace(source, destination, **kwargs)

            with mock.patch("lumen_installer.state.os.replace", side_effect=swap_then_replace):
                with self.assertRaises(InvalidInputError):
                    InstallerState(repo_root=repo, profiles=("ai",)).save()
            self.assertEqual(outside_state.read_text(encoding="utf-8"), "outside-sentinel")

    def test_journal_rejects_ordinary_state_parent_replacement_after_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            (repo / ".state").mkdir()
            (repo / ".state" / "installer").mkdir()
            journal = StageJournal(InstallerState(repo_root=repo), stages=("host",))
            journal.state.save()

            replacement = base / "replacement-state"
            replacement_installer = replacement / "installer"
            replacement_installer.mkdir(parents=True)
            external_state = replacement_installer / "state.json"
            external_state.write_text(
                json.dumps({
                    "schema_version": 1,
                    "profiles": [],
                    "gpu_mode": "none",
                    "owned_resources": {},
                    "completed_stages": [],
                }),
                encoding="utf-8",
            )
            state_parent = repo / ".state"
            moved = repo / ".state-original"
            swapped = False
            real_assert = __import__("lumen_installer.state", fromlist=["_assert_state_identity"])._assert_state_identity

            def assert_identity(path, fd, *, description):
                nonlocal swapped
                result = real_assert(path, fd, description=description)
                if description == "installer state directory" and not swapped:
                    swapped = True
                    state_parent.rename(moved)
                    replacement.rename(state_parent)
                return result

            with mock.patch("lumen_installer.state._assert_state_identity", side_effect=assert_identity):
                with self.assertRaises(InvalidInputError):
                    journal.complete("host")
            self.assertEqual((state_parent / "installer" / "state.json").read_text(encoding="utf-8"), json.dumps({
                "schema_version": 1,
                "profiles": [],
                "gpu_mode": "none",
                "owned_resources": {},
                "completed_stages": [],
            }))

    def test_state_creation_rejects_ordinary_state_directory_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            replacement = base / "replacement-state"
            replacement_installer = replacement / "installer"
            replacement_installer.mkdir(parents=True)
            external_state = replacement_installer / "state.json"
            external_state.write_text("outside-sentinel", encoding="utf-8")
            moved = base / "state-original"
            real_open = os.open
            swapped = False
            missing_seen = False

            def open_and_replace(name, flags, mode=0o777, *, dir_fd=None):
                nonlocal missing_seen, swapped
                if name == ".state" and dir_fd is not None and not missing_seen:
                    try:
                        return real_open(name, flags, mode, dir_fd=dir_fd)
                    except FileNotFoundError:
                        missing_seen = True
                        raise
                if name == ".state" and dir_fd is not None and missing_seen and not swapped:
                    state_parent = repo / ".state"
                    state_parent.rename(moved)
                    replacement.rename(state_parent)
                    swapped = True
                return real_open(name, flags, mode, dir_fd=dir_fd)

            with mock.patch("lumen_installer.state.os.open", side_effect=open_and_replace):
                with self.assertRaises(InvalidInputError):
                    InstallerState(repo_root=repo).save()
            self.assertEqual((repo / ".state" / "installer" / "state.json").read_text(encoding="utf-8"), "outside-sentinel")

    def test_state_reports_and_string_forms_never_include_resource_identifier_values(self):
        sentinel = "0123456789abcdef0123456789abcdef"
        state = InstallerState(owned_resources={"resource": sentinel})
        self.assertNotIn(sentinel, str(state))
        self.assertNotIn(sentinel, repr(state))
        self.assertNotIn(sentinel, repr(state.report))
        self.assertNotIn(sentinel, repr(state.redacted))
        malformed = state.as_dict()
        malformed["owned_resources"] = {"resource": sentinel + "!"}
        with self.assertRaises(InvalidInputError) as raised:
            InstallerState.from_dict(malformed)
        self.assertNotIn(sentinel, str(raised.exception))

    def test_state_path_symlinks_are_rejected_and_existing_modes_are_corrected_without_repo_chmod(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repo = base / "checkout"
            repo.mkdir()
            outside = base / "outside"
            outside.mkdir()

            (repo / ".state").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(InvalidInputError):
                InstallerState.load(repo)

            (repo / ".state").unlink()
            installer = repo / ".state" / "installer"
            installer.mkdir(parents=True)
            state_path = installer / "state.json"
            state_path.write_text(
                json.dumps({
                    "schema_version": 1,
                    "profiles": [],
                    "gpu_mode": "none",
                    "owned_resources": {},
                    "completed_stages": [],
                }),
                encoding="utf-8",
            )
            (repo / ".state").chmod(0o755)
            installer.chmod(0o755)
            state_path.chmod(0o644)
            original_repo_mode = stat.S_IMODE(repo.stat().st_mode)
            loaded = InstallerState.load(repo)
            self.assertEqual(loaded.profiles, ())
            self.assertEqual(stat.S_IMODE(repo.stat().st_mode), original_repo_mode)
            self.assertEqual(stat.S_IMODE(installer.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(state_path.stat().st_mode), 0o600)


class StageJournalTests(unittest.TestCase):
    def test_first_completion_persists_initial_state_choices(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            journal = StageJournal(
                InstallerState(
                    repo_root=repo,
                    profiles=("ai",),
                    gpu_mode="nvidia",
                    owned_resources={"dashboard": "dashboard"},
                ),
                stages=("host",),
            )
            self.assertTrue(journal.complete("host"))
            persisted = InstallerState.load(repo, allowed_stages=("host",))
            self.assertEqual(persisted.profiles, ("ai",))
            self.assertEqual(persisted.gpu_mode, "nvidia")
            self.assertEqual(persisted.owned_resources, {"dashboard": "dashboard"})
            self.assertEqual(persisted.completed_stages, ("host",))

    def test_journal_is_ordered_idempotent_and_resumable(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            state = InstallerState(repo_root=repo)
            journal = StageJournal(state, stages=("host", "storage", "compose"))

            with self.assertRaises(InvalidInputError):
                journal.complete("compose")
            self.assertTrue(journal.complete("host"))
            self.assertFalse(journal.complete("host"))
            self.assertEqual(journal.pending, ("storage", "compose"))
            resumed = StageJournal(
                InstallerState.load(repo, allowed_stages=("host", "storage", "compose")),
                stages=("host", "storage", "compose"),
            )
            self.assertTrue(resumed.is_complete("host"))
            self.assertTrue(resumed.complete("storage"))
            self.assertEqual(
                InstallerState.load(repo, allowed_stages=("host", "storage", "compose")).completed_stages,
                ("host", "storage"),
            )
            self.assertTrue(resumed.complete("compose"))

    def test_journal_lock_merges_concurrent_state_choices_and_only_one_same_stage_wins(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            first = StageJournal(
                InstallerState(repo_root=repo, profiles=("requests",)),
                stages=("host", "storage"),
            )
            second = StageJournal(InstallerState.load(repo), stages=("host", "storage"))
            outcomes = []
            barrier = threading.Barrier(2)

            def finish(journal):
                barrier.wait()
                outcomes.append(journal.complete("host"))

            threads = [threading.Thread(target=finish, args=(journal,)) for journal in (first, second)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(sorted(outcomes), [False, True])
            path = repo / ".state" / "installer" / "state.lock"
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

            current = InstallerState.load(repo)
            current = replace(current, profiles=("ai",), gpu_mode="nvidia", owned_resources={"dashboard": "dashboard"})
            current.save()
            self.assertTrue(first.complete("storage"))
            merged = InstallerState.load(repo, allowed_stages=("host", "storage"))
            self.assertEqual(merged.profiles, ("ai",))
            self.assertEqual(merged.gpu_mode, "nvidia")
            self.assertEqual(merged.owned_resources, {"dashboard": "dashboard"})

    def test_journal_lock_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            outside = Path(temporary) / "outside"
            outside.write_text("not a lock", encoding="utf-8")
            journal = StageJournal(InstallerState(repo_root=repo), stages=("host",))
            journal.state.save()
            lock = repo / ".state" / "installer" / "state.lock"
            lock.symlink_to(outside)
            with self.assertRaises(InvalidInputError):
                journal.complete("host")

    def test_journal_rejects_unknown_duplicate_and_out_of_order_persisted_stages(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "checkout"
            repo.mkdir()
            bad = InstallerState(repo_root=repo, completed_stages=("compose",))
            with self.assertRaises(InvalidInputError):
                StageJournal(bad, stages=("host", "compose"))
            journal = StageJournal(InstallerState(repo_root=repo), stages=("host", "compose"))
            with self.assertRaises(InvalidInputError):
                journal.complete("unknown")
            with self.assertRaises(InvalidInputError):
                journal.complete("compose")


if __name__ == "__main__":
    unittest.main()
