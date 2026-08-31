import os
import sys
import unittest
from pathlib import Path


WORKTREE_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_ROOT = WORKTREE_ROOT / "installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.dotenv import DotEnvDocument
from lumen_installer.environment import plan_environment
from lumen_installer.platform import HostFacts


HOST = HostFacts(
    uid=1001,
    gid=1002,
    timezone="America/Sao_Paulo",
    distro_id="ubuntu",
    distro_like=("debian",),
    arch="x86_64",
    euid=1001,
    sudo_uid=None,
    sudo_gid=None,
)


class EnvironmentPlanTests(unittest.TestCase):
    def test_fresh_plan_uses_detected_owner_facts_absolute_paths_and_aligned_password_alias(self):
        plan = plan_environment(
            DotEnvDocument.parse(""),
            HOST,
            {
                "ROOT_PATH": "./media",
                "DOWNLOADS_PATH": "~/downloads",
                "QBT_PASSWORD": "fresh-secret",
            },
        )

        values = plan.values
        self.assertEqual(values["PUID"], "1001")
        self.assertEqual(values["PGID"], "1002")
        self.assertEqual(values["TZ"], "America/Sao_Paulo")
        self.assertTrue(Path(values["ROOT_PATH"]).is_absolute())
        self.assertTrue(Path(values["DOWNLOADS_PATH"]).is_absolute())
        self.assertEqual(values["QBT_PASSWORD"], "fresh-secret")
        self.assertEqual(values["STACK_PASSWORD"], "fresh-secret")

    def test_adopted_plan_preserves_owner_and_timezone_drift_and_redacts_secrets_in_display(self):
        old_secret = "old-actions-token"
        document = DotEnvDocument.parse(
            "PUID=2001\n"
            "PGID=2002\n"
            "TZ=UTC\n"
            "ROOT_PATH=./library\n"
            f"ACTIONS_TOKEN={old_secret}\n"
            "STACK_PASSWORD=old-password\n"
        )

        plan = plan_environment(
            document,
            HOST,
            {"ROOT_PATH": "./new-library", "STACK_PASSWORD": "new-password"},
        )

        self.assertEqual(plan.values["PUID"], "2001")
        self.assertEqual(plan.values["PGID"], "2002")
        self.assertEqual(plan.values["TZ"], "UTC")
        self.assertTrue(Path(plan.values["ROOT_PATH"]).is_absolute())
        self.assertEqual(plan.values["STACK_PASSWORD"], "old-password")
        self.assertTrue(plan.drift)
        drift_keys = {record["key"] for record in plan.drift}
        self.assertEqual(drift_keys, {"PUID", "PGID", "TZ"})

        display_text = repr(plan.display)
        self.assertNotIn(old_secret, display_text)
        self.assertNotIn("old-password", display_text)
        self.assertNotIn("new-password", display_text)
        self.assertEqual(plan.display["values"]["ACTIONS_TOKEN"], "<redacted>")
        self.assertEqual(plan.display["values"]["STACK_PASSWORD"], "<redacted>")


if __name__ == "__main__":
    unittest.main()
