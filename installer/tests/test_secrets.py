import re
import sys
import unittest
from pathlib import Path
from unittest import mock


WORKTREE_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_ROOT = WORKTREE_ROOT / "installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.secrets import ensure_actions_token


class ActionTokenTests(unittest.TestCase):
    def test_preserves_a_non_placeholder_token_verbatim(self):
        existing = "already-configured-token"

        self.assertEqual(ensure_actions_token(existing), existing)

    def test_replaces_placeholder_with_32_byte_hex_token_without_reporting_it(self):
        generated = "ab" * 32
        with mock.patch("lumen_installer.secrets.token_hex", return_value=generated) as token_hex:
            value = ensure_actions_token("your-actions-token")

        token_hex.assert_called_once_with(32)
        self.assertEqual(value, generated)
        self.assertRegex(value, re.compile(r"\A[0-9a-f]{64}\Z"))


if __name__ == "__main__":
    unittest.main()
