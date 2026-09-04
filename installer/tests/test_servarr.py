import sys
import tempfile
import unittest
import json
from pathlib import Path


WORKTREE_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_ROOT = WORKTREE_ROOT / "installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.services.servarr import (  # noqa: E402
    RADARR_CONFIG_PATH,
    RadarrAdapter,
    SONARR_CONFIG_PATH,
    SonarrAdapter,
    ServarrCapabilityError,
    ServarrConfigError,
    ServarrConflictError,
    ServarrSchemaError,
    ServarrResult,
    read_servarr_api_key,
)
from lumen_installer.http import HttpResponse  # noqa: E402


SONARR_KEY = "sonarr-generated-api-key-must-not-escape"
RADARR_KEY = "radarr-generated-api-key-must-not-escape"
QBT_PASSWORD = "qbit-password-must-not-escape"
BASE_URL = "http://sonarr.test:8989"


def response(payload, status=200):
    if isinstance(payload, bytes):
        body = payload
    elif isinstance(payload, str):
        body = payload.encode("utf-8")
    else:
        body = json.dumps(payload).encode("utf-8")
    return HttpResponse(status, {"Content-Type": "application/json"}, body)


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


def qbit_schema(*, fields=None):
    return {
        "name": "qBittorrent",
        "implementation": "QBittorrent",
        "implementationName": "qBittorrent",
        "configContract": "QBittorrentSettings",
        "protocol": "torrent",
        "fields": fields
        or [
            {"name": "host", "value": "old-qbt"},
            {"name": "port", "value": 1234},
            {"name": "username", "value": "old-user"},
            {"name": "password", "value": ""},
            {"name": "tvCategory", "value": "old-tv"},
            {"name": "movieCategory", "value": "old-movie"},
            {"name": "unrelated", "value": "preserve-me"},
        ],
    }


def qbit_client(schema, *, client_id=None, field_values=None):
    fields = []
    schema_fields = schema["fields"].values() if isinstance(schema["fields"], dict) else schema["fields"]
    for field in schema_fields:
        name = field["name"]
        value = (field_values or {}).get(name, field.get("value"))
        fields.append({**field, "value": value})
    client = {
        "name": "qBittorrent",
        "implementation": "QBittorrent",
        "configContract": "QBittorrentSettings",
        "enable": True,
        "protocol": "torrent",
        "priority": 1,
        "fields": fields,
    }
    if client_id is not None:
        client["id"] = client_id
    return client


class ServarrApiKeyParsingTests(unittest.TestCase):
    def test_exact_config_paths_parse_keys_and_public_surfaces_redact_them(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            sonarr_path = root / SONARR_CONFIG_PATH
            radarr_path = root / RADARR_CONFIG_PATH
            sonarr_path.parent.mkdir(parents=True)
            radarr_path.parent.mkdir(parents=True)
            sonarr_path.write_text(f"<Config><ApiKey>{SONARR_KEY}</ApiKey></Config>", encoding="utf-8")
            radarr_path.write_text(f"<Config><ApiKey>{RADARR_KEY}</ApiKey></Config>", encoding="utf-8")

            self.assertEqual(read_servarr_api_key("sonarr", root), SONARR_KEY)
            self.assertEqual(read_servarr_api_key("radarr", root), RADARR_KEY)

            result = ServarrResult(
                service="sonarr",
                status="ok",
                api_key=SONARR_KEY,
            )
            error = ServarrConfigError(f"unable to read {SONARR_KEY}")
            for surface in (result, repr(result), result.report, result.redacted, error, repr(error), error.report):
                self.assertNotIn(SONARR_KEY, repr(surface))


class ServarrAdapterTests(unittest.TestCase):
    def adapter(self, responses, adapter_class=SonarrAdapter, **kwargs):
        transport = DeterministicTransport(responses)
        adapter = adapter_class(
            BASE_URL,
            transport,
            api_key=SONARR_KEY,
            qbit_password=QBT_PASSWORD,
            **kwargs,
        )
        return adapter, transport

    def test_fresh_sonarr_config_creates_tv_root_and_schema_driven_qbittorrent_client(self):
        schema = qbit_schema()
        adapter, transport = self.adapter(
            [
                response({"version": "4.0.0", "instanceName": "private-sonarr"}),
                response([]),
                response([schema]),
                response([]),
                response({"status": "ok"}),
                response({"id": 17}),
                response({"id": 23}),
            ]
        )

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("GET", f"{BASE_URL}/api/v3/system/status"),
                ("GET", f"{BASE_URL}/api/v3/rootfolder"),
                ("GET", f"{BASE_URL}/api/v3/downloadclient/schema"),
                ("GET", f"{BASE_URL}/api/v3/downloadclient"),
                ("POST", f"{BASE_URL}/api/v3/downloadclient/test"),
                ("POST", f"{BASE_URL}/api/v3/rootfolder"),
                ("POST", f"{BASE_URL}/api/v3/downloadclient"),
            ],
        )
        self.assertEqual(transport.requests[0][2]["headers"]["X-Api-Key"], SONARR_KEY)
        self.assertEqual(transport.requests[5][2]["json_body"], {"path": "/data/media/tv"})
        client_payload = transport.requests[6][2]["json_body"]
        self.assertEqual(client_payload["implementation"], "QBittorrent")
        self.assertEqual(client_payload["configContract"], "QBittorrentSettings")
        fields = {field["name"]: field["value"] for field in client_payload["fields"]}
        self.assertEqual(fields["host"], "qbittorrent")
        self.assertEqual(fields["port"], 8081)
        self.assertEqual(fields["username"], "admin")
        self.assertEqual(fields["password"], QBT_PASSWORD)
        self.assertEqual(fields["tvCategory"], "sonarr")
        self.assertEqual(fields["movieCategory"], "old-movie")
        self.assertEqual(fields["unrelated"], "preserve-me")
        self.assertNotIn(QBT_PASSWORD, repr(result))

    def test_schema_variants_and_matching_existing_configuration_are_a_noop(self):
        schema = qbit_schema(
            fields={
                "host": {"name": "host", "value": "schema-host"},
                "port": {"name": "port", "value": 1},
                "username": {"name": "username", "value": "schema-user"},
                "password": {"name": "password", "value": ""},
                "tvCategory": {"name": "tvCategory", "value": "schema-category"},
                "unrelated": {"name": "unrelated", "value": "keep"},
            }
        )
        existing_fields = {
            "host": "qbittorrent",
            "port": 8081,
            "username": "admin",
            "tvCategory": "sonarr",
            "unrelated": "keep",
        }
        adapter, transport = self.adapter(
            [
                response({"version": "4.0.0"}),
                response({"items": [{"id": 1, "path": "/data/media/tv", "name": "keep-name"}]}),
                response({"schemas": [schema]}),
                response({"items": [qbit_client(schema, client_id=9, field_values=existing_fields)]}),
            ]
        )

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        self.assertIn("reuse-root-folder", result.actions)
        self.assertIn("reuse-download-client", result.actions)
        self.assertEqual([request[0] for request in transport.requests], ["GET"] * 4)

    def test_managed_field_conflict_requires_confirmation_and_preserves_unrelated_resources(self):
        schema = qbit_schema()
        existing = qbit_client(
            schema,
            client_id=9,
            field_values={"host": "wrong-qbt", "tvCategory": "sonarr", "unrelated": "keep"},
        )
        adapter, transport = self.adapter(
            [response({"version": "4.0.0"}), response([{"id": 1, "path": "/data/media/tv"}, {"id": 2, "path": "/data/other"}]), response([schema]), response([existing])]
        )

        result = adapter.configure(confirm=False)

        self.assertEqual(result.status, "drift")
        self.assertIsInstance(result.error, ServarrConflictError)
        self.assertEqual(result.drift[0].field, "host")
        self.assertEqual([request[0] for request in transport.requests], ["GET"] * 4)
        self.assertNotIn("wrong-qbt", repr(result))

    def test_confirmed_conflict_tests_before_updating_only_the_managed_client(self):
        schema = qbit_schema()
        existing = qbit_client(schema, client_id=9, field_values={"host": "wrong-qbt", "tvCategory": "sonarr"})
        adapter, transport = self.adapter(
            [
                response({"version": "4.0.0"}),
                response([{"id": 1, "path": "/data/media/tv"}, {"id": 2, "path": "/data/other"}]),
                response([schema]),
                response([existing]),
                response({"status": "ok"}),
                response({"id": 9}),
            ]
        )

        result = adapter.configure(confirm=True)

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            [request[0:2] for request in transport.requests[-2:]],
            [
                ("POST", f"{BASE_URL}/api/v3/downloadclient/test"),
                ("PUT", f"{BASE_URL}/api/v3/downloadclient/9"),
            ],
        )
        self.assertEqual(len(transport.requests), 6)

    def test_download_client_test_failure_prevents_create_or_update(self):
        schema = qbit_schema()
        adapter, transport = self.adapter(
            [response({"version": "4.0.0"}), response([]), response([schema]), response([]), response({"error": "private-test-secret"}, status=400)]
        )

        result = adapter.configure()

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.checkpoints[0].code, "servarr-download-client-test")
        self.assertNotIn(QBT_PASSWORD, repr(result))
        self.assertNotIn("private-test-secret", repr(result))
        self.assertEqual(len(transport.requests), 5)

    def test_unsupported_api_and_unsupported_runtime_schema_fail_closed(self):
        adapter, transport = self.adapter([response({"instanceName": "private"})])
        with self.assertRaises(ServarrCapabilityError) as raised:
            adapter.configure()
        self.assertIsNone(raised.exception.__context__)
        self.assertNotIn(SONARR_KEY, repr(raised.exception))
        self.assertEqual(len(transport.requests), 1)

        schema_adapter, schema_transport = self.adapter(
            [response({"version": "4.0.0"}), response([]), response({"schemas": [{"name": "other"}]})]
        )
        with self.assertRaises(ServarrSchemaError) as raised:
            schema_adapter.configure()
        self.assertIsNone(raised.exception.__context__)
        self.assertNotIn(SONARR_KEY, repr(raised.exception))
        self.assertEqual(len(schema_transport.requests), 3)

    def test_malformed_api_v3_response_fails_closed_without_response_text(self):
        adapter, transport = self.adapter([response(f"malformed {SONARR_KEY}")])

        with self.assertRaises(ServarrSchemaError) as raised:
            adapter.configure()

        self.assertIsNone(raised.exception.__context__)
        self.assertNotIn(SONARR_KEY, repr(raised.exception))
        self.assertEqual(len(transport.requests), 1)

    def test_radarr_does_not_reuse_sonarr_root_path(self):
        schema = qbit_schema()
        transport = DeterministicTransport(
            [
                response({"version": "5.0.0"}),
                response([{"id": 1, "path": "/data/media/tv"}]),
                response([schema]),
                response([]),
                response({}),
                response({"id": 1}),
                response({"id": 2}),
            ]
        )
        adapter = RadarrAdapter(
            "http://radarr.test:7878",
            transport,
            api_key=RADARR_KEY,
            qbit_password=QBT_PASSWORD,
        )

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        self.assertEqual(transport.requests[5][2]["json_body"], {"path": "/data/media/movies"})
        fields = {field["name"]: field["value"] for field in transport.requests[6][2]["json_body"]["fields"]}
        self.assertEqual(fields["movieCategory"], "radarr")

    def test_confirmed_conflict_preserves_unrelated_client_fields(self):
        schema = qbit_schema()
        existing = qbit_client(
            schema,
            client_id=9,
            field_values={"host": "wrong-qbt", "tvCategory": "sonarr", "unrelated": "preserve"},
        )
        adapter, transport = self.adapter(
            [
                response({"version": "4.0.0"}),
                response([{"id": 1, "path": "/data/media/tv"}]),
                response([schema]),
                response([existing]),
                response({"status": "ok"}),
                response({"id": 9}),
            ]
        )

        result = adapter.configure(confirm=True)

        self.assertEqual(result.status, "ok")
        updated_fields = {
            field["name"]: field["value"]
            for field in transport.requests[-1][2]["json_body"]["fields"]
        }
        self.assertEqual(updated_fields["unrelated"], "preserve")
        self.assertEqual(len(transport.requests), 6)

    def test_dry_run_makes_no_api_v3_request_and_redacts_credentials(self):
        adapter, transport = self.adapter([])

        result = adapter.configure(dry_run=True)

        self.assertEqual(result.status, "dry-run")
        self.assertTrue(result.dry_run)
        self.assertEqual(transport.requests, [])
        for surface in (result, repr(result), result.report, result.redacted):
            self.assertNotIn(SONARR_KEY, repr(surface))
            self.assertNotIn(QBT_PASSWORD, repr(surface))

    def test_transport_error_is_sanitized(self):
        adapter, transport = self.adapter([RuntimeError(f"private {SONARR_KEY} {QBT_PASSWORD}")])

        with self.assertRaises(Exception) as raised:
            adapter.configure()

        self.assertIsNone(raised.exception.__context__)
        self.assertNotIn(SONARR_KEY, repr(raised.exception))
        self.assertNotIn(QBT_PASSWORD, repr(raised.exception))
        self.assertEqual(len(transport.requests), 1)

    def test_radarr_uses_movie_root_and_movie_category(self):
        schema = qbit_schema()
        transport = DeterministicTransport(
            [response({"version": "5.0.0"}), response([]), response([schema]), response([]), response({}), response({"id": 1}), response({"id": 2})]
        )
        adapter = RadarrAdapter(
            "http://radarr.test:7878",
            transport,
            api_key=RADARR_KEY,
            qbit_password=QBT_PASSWORD,
        )

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        self.assertEqual(transport.requests[5][2]["json_body"], {"path": "/data/media/movies"})
        fields = {field["name"]: field["value"] for field in transport.requests[6][2]["json_body"]["fields"]}
        self.assertEqual(fields["movieCategory"], "radarr")
        self.assertEqual(fields["tvCategory"], "old-tv")
        self.assertNotIn(RADARR_KEY, repr(result))


if __name__ == "__main__":
    unittest.main()
