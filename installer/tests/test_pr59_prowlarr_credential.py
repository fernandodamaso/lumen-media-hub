import sys
import unittest
from pathlib import Path

INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.services.prowlarr import ProwlarrAdapter


class _Transport:
    def __init__(self):
        self.calls = []
        self.tests = 0

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if method == "POST" and url.endswith("/downloadclient/test"):
            self.tests += 1
            if self.tests == 1:
                return {"status": 400, "body": {}}
        return {"status": 200, "body": {}}


class ProwlarrCredentialRegressionTests(unittest.TestCase):
    def test_omitted_existing_password_is_retested_and_updated(self):
        transport = _Transport()
        adapter = ProwlarrAdapter(
            "http://127.0.0.1:9696",
            transport,
            api_key="prowlarr-key",
            qbit_password="new-password",
            verify_qbit_client=True,
        )
        fields = [
            {"name": "host", "value": "qbittorrent"},
            {"name": "port", "value": 8081},
            {"name": "username", "value": "admin"},
            {"name": "password", "value": ""},
        ]

        plan = adapter._qbit_plan({"fields": fields}, {"id": 9, "fields": fields})
        result = adapter._apply_plans((plan,), confirm=False)

        self.assertIn("update-download-client", result.actions)
        self.assertEqual([call[0] for call in transport.calls], ["POST", "POST", "PUT"])


if __name__ == "__main__":
    unittest.main()
