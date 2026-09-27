import tempfile
import unittest
from unittest import mock

import config as settings
from routes import resources


class DiskStatsTests(unittest.TestCase):
    def test_measures_configured_data_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(settings, "DATA_PATH", temporary):
                stats = resources._disk_stats()
        self.assertEqual(stats["path"], temporary)
        self.assertGreater(stats["total"], 0)

    def test_missing_data_path_is_unknown_not_container_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = f"{temporary}/absent"
            with mock.patch.object(settings, "DATA_PATH", missing), mock.patch.object(
                resources.shutil, "disk_usage"
            ) as disk_usage:
                self.assertIsNone(resources._disk_stats())
        disk_usage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
