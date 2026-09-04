import sys
import unittest
from pathlib import Path

INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.services.prowlarr import ProwlarrAdapter


class _Transport:
    def request(self, method, url, **kwargs):
        return {"status": 200, "body": {}}


class ProwlarrCredentialRegressionTests(unittest.TestCase):
    def test_omitted_existing_password_is_retested_and_updated(self):
        adapter = ProwlarrAdapter(
            "http://127.0.0.1:9696",
            _Transport(),
            api_key="prowlarr-key",
            qbit_password="new-password",
        )
        fields = [
            {"name": "host", "value": "qbittorrent"},
            {"name": "port", "value": 8081},
            {"name": "username", "value": "admin"},
            {"name": "password", "value": ""},
        ]

        plan = adapter._qbit_plan({"fields": fields}, {"id": 9, "fields": fields})

        self.assertEqual(plan.action, "update-download-client")


if __name__ == "__main__":
    unittest.main()
