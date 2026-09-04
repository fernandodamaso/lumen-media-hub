import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


WORKTREE_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_ROOT = WORKTREE_ROOT / "installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.dotenv import DotEnvDocument, write_atomic


class DotEnvDocumentTests(unittest.TestCase):
    def test_round_trip_preserves_comments_order_unknown_lines_and_quoting(self):
        source = (
            "# keep this comment\n"
            "FIRST=one\n"
            "export SECOND='two words' # keep inline comment\n"
            "UNKNOWN syntax that must survive\n"
            "THIRD=\"three\\\"value\"\n"
            "\n"
            "LAST=plain#hash\n"
        )

        document = DotEnvDocument.parse(source)

        self.assertEqual(document.get("FIRST"), "one")
        self.assertEqual(document.get("SECOND"), "two words")
        self.assertEqual(document.get("THIRD"), 'three"value')
        self.assertEqual(document.get("LAST"), "plain#hash")
        self.assertEqual(document.render(), source)

    def test_set_existing_key_keeps_its_quote_style_and_inline_comment(self):
        document = DotEnvDocument.parse(
            "# header\nVALUE='old value' # explanation\nOTHER=keep\n"
        )

        document.set("VALUE", "new value")

        self.assertEqual(
            document.render(),
            "# header\nVALUE='new value' # explanation\nOTHER=keep\n",
        )

    def test_set_new_key_appends_without_destroying_existing_document(self):
        document = DotEnvDocument.parse("# header\nUNKNOWN=keep")

        document.set("NEW_VALUE", "needs quoting")

        self.assertEqual(
            document.render(),
            "# header\nUNKNOWN=keep\nNEW_VALUE=\"needs quoting\"\n",
        )

    def test_appending_after_editing_unterminated_assignment_inserts_line_break(self):
        document = DotEnvDocument.parse("A=old")

        document.set("A", "new")
        document.set("B", "value")

        self.assertEqual(document.render(), "A=new\nB=value\n")

    def test_unknown_double_quote_escapes_are_preserved(self):
        document = DotEnvDocument.parse(
            'PASSWORD="p\\q"\nWINDOWS_PATH="C:\\\\media\\\\downloads"\n'
        )

        self.assertEqual(document.get("PASSWORD"), r"p\q")
        self.assertEqual(document.get("WINDOWS_PATH"), r"C:\media\downloads")

    def test_write_atomic_sets_restrictive_mode_and_preserves_original_on_replace_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text("ORIGINAL=keep\n", encoding="utf-8")
            path.chmod(0o644)

            write_atomic(path, "NEW=value\n")

            self.assertEqual(path.read_text(encoding="utf-8"), "NEW=value\n")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

            with mock.patch("lumen_installer.dotenv.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    write_atomic(path, "MUST-NOT-REPLACE\n")

            self.assertEqual(path.read_text(encoding="utf-8"), "NEW=value\n")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(
                [child.name for child in Path(temporary).iterdir()],
                [".env"],
            )

    def test_post_replace_parent_fsync_failure_does_not_report_failed_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text("ORIGINAL=keep\n", encoding="utf-8")

            with mock.patch(
                "lumen_installer.dotenv._fsync_parent",
                side_effect=[None, OSError("post-rename fsync failed")],
            ) as sync_parent:
                write_atomic(path, "NEW=value\n")

            self.assertEqual(path.read_text(encoding="utf-8"), "NEW=value\n")
            self.assertEqual(sync_parent.call_count, 2)


if __name__ == "__main__":
    unittest.main()
