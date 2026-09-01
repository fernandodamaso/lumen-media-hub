import json
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
            self.assertEqual([child.name for child in path.parent.iterdir()], ["state.json"])


class StageJournalTests(unittest.TestCase):
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
            resumed = StageJournal(InstallerState.load(repo), stages=("host", "storage", "compose"))
            self.assertTrue(resumed.is_complete("host"))
            self.assertTrue(resumed.complete("storage"))
            self.assertEqual(InstallerState.load(repo).completed_stages, ("host", "storage"))
            self.assertTrue(resumed.complete("compose"))

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
