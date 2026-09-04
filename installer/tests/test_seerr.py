import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.http import HttpResponse  # noqa: E402
from lumen_installer.services.seerr import (  # noqa: E402
    OwnershipInspection,
    SeerrAdapter,
    SeerrCapabilityError,
    SeerrConfigError,
    backup_config,
    inspect_config_ownership,
    prepare_seerr_config,
    seerr_service_urls,
)


SEERR_KEY = "seerr-key-must-not-escape"
SONARR_KEY = "sonarr-key-must-not-escape"
RADARR_KEY = "radarr-key-must-not-escape"


def response(payload, status=200):
    return HttpResponse(
        status,
        {"Content-Type": "application/json"},
        json.dumps(payload).encode("utf-8"),
    )


class DeterministicTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


class SeerrConfigMigrationTests(unittest.TestCase):
    def test_fresh_config_is_created_with_numeric_seerr_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "config" / "jellyseerr"
            backup = root / "backup" / "jellyseerr"

            with mock.patch("lumen_installer.services.seerr.os.chown") as chown:
                result = prepare_seerr_config(config, backup_path=backup)

            self.assertEqual(result.status, "ok")
            self.assertTrue(config.is_dir())
            self.assertFalse(backup.exists())
            chown.assert_called_once_with(config, 1000, 1000, follow_symlinks=False)
            ownership = inspect_config_ownership(config)
            self.assertIsInstance(ownership.uid, int)
            self.assertIsInstance(ownership.gid, int)

    def test_adopted_config_is_backed_up_before_confirmed_recursive_ownership_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "config" / "jellyseerr"
            config.mkdir(parents=True)
            (config / "settings.json").write_bytes(b"preserve-this-exactly")
            backup = root / "backup" / "jellyseerr"
            events = []
            real_backup = backup_config

            def record_backup(source, destination):
                events.append("backup")
                return real_backup(source, destination)

            def record_chown(path, uid, gid, *, follow_symlinks=False):
                events.append(("chown", Path(path).name, uid, gid, follow_symlinks))

            mismatched = OwnershipInspection(
                path=config,
                exists=True,
                uid=1234,
                gid=1234,
                entries=2,
                mismatched_entries=2,
            )
            with mock.patch(
                "lumen_installer.services.seerr.inspect_config_ownership",
                return_value=mismatched,
            ), mock.patch(
                "lumen_installer.services.seerr.backup_config",
                side_effect=record_backup,
            ), mock.patch(
                "lumen_installer.services.seerr.os.chown",
                side_effect=record_chown,
            ):
                result = prepare_seerr_config(config, backup_path=backup, confirm=True)

            self.assertEqual(result.status, "ok")
            self.assertEqual(events[0], "backup")
            self.assertTrue(any(event[0] == "chown" for event in events[1:]))
            self.assertEqual((backup / "settings.json").read_bytes(), b"preserve-this-exactly")
            self.assertEqual(result.backup_path, backup)

    def test_adopted_ownership_drift_requires_confirmation_without_chown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "config" / "jellyseerr"
            config.mkdir(parents=True)
            (config / "settings.json").write_text("user-config", encoding="utf-8")
            backup = root / "backup" / "jellyseerr"

            mismatched = OwnershipInspection(
                path=config,
                exists=True,
                uid=1234,
                gid=1234,
                entries=2,
                mismatched_entries=2,
            )
            with mock.patch(
                "lumen_installer.services.seerr.inspect_config_ownership",
                return_value=mismatched,
            ), mock.patch("lumen_installer.services.seerr.os.chown") as chown:
                result = prepare_seerr_config(config, backup_path=backup, confirm=False)

            self.assertEqual(result.status, "drift")
            self.assertTrue(result.requires_confirmation)
            self.assertTrue(backup.exists())
            chown.assert_not_called()
            self.assertNotIn("user-config", repr(result))


class SeerrAdapterTests(unittest.TestCase):
    def test_supported_integrations_use_compose_dns_names_and_ports(self):
        self.assertEqual(
            seerr_service_urls(),
            {
                "jellyfin": "http://jellyfin:8096",
                "sonarr": "http://sonarr:8989",
                "radarr": "http://radarr:7878",
            },
        )

    def adapter(self, responses):
        transport = DeterministicTransport(responses)
        adapter = SeerrAdapter(
            "http://jellyseerr.test:5055",
            transport,
            api_key=SEERR_KEY,
        )
        return adapter, transport

    def test_unsupported_runtime_capability_fails_closed_before_settings_mutation(self):
        adapter, transport = self.adapter([response({"status": "starting"})])

        result = adapter.configure_integrations(
            jellyfin_api_key="jellyfin-key",
            sonarr_api_key=SONARR_KEY,
            radarr_api_key=RADARR_KEY,
        )

        self.assertEqual(result.status, "unsupported")
        self.assertIsInstance(result.error, SeerrCapabilityError)
        self.assertEqual([request[0:2] for request in transport.requests], [("GET", "http://jellyseerr.test:5055/api/v1/status")])
        self.assertNotIn("key-must-not-escape", repr(result))

    def test_old_runtime_version_fails_closed_before_settings_mutation(self):
        adapter, transport = self.adapter([response({"version": "1.9.9"})])

        result = adapter.configure_integrations(
            jellyfin_api_key="jellyfin-key",
            sonarr_api_key=SONARR_KEY,
            radarr_api_key=RADARR_KEY,
        )

        self.assertEqual(result.status, "unsupported")
        self.assertIsInstance(result.error, SeerrCapabilityError)
        self.assertEqual(len(transport.requests), 1)

    def test_supported_runtime_preserves_unmanaged_settings_for_all_integrations(self):
        adapter, transport = self.adapter(
            [
                response({"version": "3.0.0"}),
                response({"hostname": "old-jellyfin", "port": 8096, "apiKey": "old", "userSetting": "keep"}),
                response({}),
                response({"hostname": "old-sonarr", "port": 8989, "apiKey": "old", "userSetting": "keep"}),
                response({}),
                response({"hostname": "old-radarr", "port": 7878, "apiKey": "old", "userSetting": "keep"}),
                response({}),
            ]
        )

        result = adapter.configure_integrations(
            jellyfin_api_key="jellyfin-key",
            sonarr_api_key=SONARR_KEY,
            radarr_api_key=RADARR_KEY,
        )

        self.assertEqual(result.status, "ok")
        writes = [request for request in transport.requests if request[0] == "PUT"]
        self.assertEqual(len(writes), 3)
        for _method, _url, kwargs in writes:
            self.assertEqual(kwargs["json_body"]["userSetting"], "keep")
        self.assertEqual(writes[1][2]["json_body"]["hostname"], "sonarr")
        self.assertEqual(writes[2][2]["json_body"]["hostname"], "radarr")
        self.assertNotIn(SONARR_KEY, repr(result))
        self.assertNotIn(RADARR_KEY, repr(result))

    def test_dry_run_does_not_probe_or_mutate_the_runtime(self):
        adapter, transport = self.adapter([])

        result = adapter.configure_integrations(
            jellyfin_api_key="jellyfin-key",
            sonarr_api_key=SONARR_KEY,
            radarr_api_key=RADARR_KEY,
            dry_run=True,
        )

        self.assertEqual(result.status, "dry-run")
        self.assertTrue(result.dry_run)
        self.assertEqual(transport.requests, [])


if __name__ == "__main__":
    unittest.main()
