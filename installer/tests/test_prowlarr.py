import json
import sys
import tempfile
import unittest
from pathlib import Path


WORKTREE_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_ROOT = WORKTREE_ROOT / "installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.http import HttpResponse  # noqa: E402
from lumen_installer.services.prowlarr import (  # noqa: E402
    ProwlarrAdapter,
    ProwlarrCapabilityError,
    ProwlarrConfigError,
    ProwlarrConflictError,
    ProwlarrResult,
    ProwlarrSchemaError,
    read_prowlarr_api_key,
)


BASE_URL = "http://prowlarr.test:9696"
PROWLARR_KEY = "prowlarr-api-key-must-not-escape"
QBT_PASSWORD = "qbit-password-must-not-escape"
SONARR_KEY = "sonarr-api-key-must-not-escape"
RADARR_KEY = "radarr-api-key-must-not-escape"
TORZNAB_KEY = "torznab-api-key-must-not-escape"
TORZNAB_URL = "https://indexer.example.test/torznab"


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
            {"name": "unrelated", "value": "preserve-me"},
        ],
    }


def application_schema(service, *, fields=None):
    return {
        "name": service.title(),
        "implementation": service.title(),
        "implementationName": service.title(),
        "configContract": f"{service.title()}Settings",
        "fields": fields
        or [
            {"name": "baseUrl", "value": "http://old-service"},
            {"name": "apiKey", "value": ""},
            {"name": "syncLevel", "value": "addOnly"},
            {"name": "unrelated", "value": "preserve-me"},
        ],
    }


def torznab_schema(*, fields=None):
    return {
        "name": "Generic Torznab",
        "implementation": "Torznab",
        "implementationName": "Generic Torznab",
        "configContract": "TorznabSettings",
        "protocol": "torrent",
        "fields": fields
        or [
            {"name": "baseUrl", "value": "https://old.example.test"},
            {"name": "apiKey", "value": ""},
            {"name": "categories", "value": "5000"},
        ],
    }


def fields_by_name(payload):
    fields = payload["fields"]
    values = fields.values() if isinstance(fields, dict) else fields
    return {field["name"]: field.get("value") for field in values}


def fresh_responses(
    *,
    qbit=None,
    qbit_existing=None,
    applications=None,
    applications_existing=None,
    indexer_schemas=None,
    indexers=None,
):
    return [
        response({"version": "1.0.0", "instanceName": "private-prowlarr"}),
        response([qbit or qbit_schema()]),
        response([qbit_existing] if isinstance(qbit_existing, dict) else qbit_existing or []),
        response(applications or [application_schema("sonarr"), application_schema("radarr")]),
        response(applications_existing or []),
        response(indexer_schemas or [torznab_schema()]),
        response(indexers or []),
        response({"status": "ok"}),
        response({"id": 11}),
        response({"status": "ok"}),
        response({"id": 12}),
        response({"status": "ok"}),
        response({"id": 13}),
        response({"status": "ok"}),
        response({"id": 14}),
    ]


class ProwlarrKeyTests(unittest.TestCase):
    def test_exact_config_path_is_read_and_public_surfaces_redact_the_key(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_path = root / "config" / "prowlarr" / "config.xml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(f"<Config><ApiKey>{PROWLARR_KEY}</ApiKey></Config>", encoding="utf-8")

            self.assertEqual(read_prowlarr_api_key(root), PROWLARR_KEY)

            result = ProwlarrResult(service="prowlarr", status="ok", api_key=PROWLARR_KEY)
            error = ProwlarrConfigError(f"unable to read {PROWLARR_KEY}")
            for surface in (result, repr(result), result.report, result.redacted, error, repr(error), error.report):
                self.assertNotIn(PROWLARR_KEY, repr(surface))

    def test_missing_or_malformed_config_key_is_typed_and_redacted(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "config" / "prowlarr" / "config.xml"
            path.parent.mkdir(parents=True)
            path.write_text("<Config><ApiKey></ApiKey></Config>", encoding="utf-8")

            with self.assertRaises(ProwlarrConfigError):
                read_prowlarr_api_key(root)


class ProwlarrAdapterTests(unittest.TestCase):
    def adapter(self, responses, **kwargs):
        transport = DeterministicTransport(responses)
        adapter = ProwlarrAdapter(
            BASE_URL,
            transport,
            api_key=PROWLARR_KEY,
            qbit_password=QBT_PASSWORD,
            sonarr_api_key=SONARR_KEY,
            radarr_api_key=RADARR_KEY,
            generic_torznab_url=TORZNAB_URL,
            generic_torznab_api_key=TORZNAB_KEY,
            **kwargs,
        )
        return adapter, transport

    def test_fresh_setup_reads_runtime_schemas_tests_before_creating_all_core_resources(self):
        adapter, transport = self.adapter(fresh_responses())

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            [(request[0], request[1]) for request in transport.requests],
            [
                ("GET", f"{BASE_URL}/api/v1/system/status"),
                ("GET", f"{BASE_URL}/api/v1/downloadclient/schema"),
                ("GET", f"{BASE_URL}/api/v1/downloadclient"),
                ("GET", f"{BASE_URL}/api/v1/applications/schema"),
                ("GET", f"{BASE_URL}/api/v1/applications"),
                ("GET", f"{BASE_URL}/api/v1/indexer/schema"),
                ("GET", f"{BASE_URL}/api/v1/indexer"),
                ("POST", f"{BASE_URL}/api/v1/downloadclient/test"),
                ("POST", f"{BASE_URL}/api/v1/downloadclient"),
                ("POST", f"{BASE_URL}/api/v1/applications/test"),
                ("POST", f"{BASE_URL}/api/v1/applications"),
                ("POST", f"{BASE_URL}/api/v1/applications/test"),
                ("POST", f"{BASE_URL}/api/v1/applications"),
                ("POST", f"{BASE_URL}/api/v1/indexer/test"),
                ("POST", f"{BASE_URL}/api/v1/indexer"),
            ],
        )
        self.assertEqual(transport.requests[0][2]["headers"]["X-Api-Key"], PROWLARR_KEY)

        qbit_payload = transport.requests[7][2]["json_body"]
        qbit_values = fields_by_name(qbit_payload)
        self.assertEqual(qbit_values["host"], "qbittorrent")
        self.assertEqual(qbit_values["port"], 8081)
        self.assertEqual(qbit_values["username"], "admin")
        self.assertEqual(qbit_values["password"], QBT_PASSWORD)
        self.assertEqual(qbit_values["unrelated"], "preserve-me")

        sonarr_payload = transport.requests[9][2]["json_body"]
        self.assertEqual(fields_by_name(sonarr_payload)["baseUrl"], "http://sonarr:8989")
        self.assertEqual(fields_by_name(sonarr_payload)["apiKey"], SONARR_KEY)
        self.assertEqual(fields_by_name(sonarr_payload)["syncLevel"], "fullSync")

        torznab_payload = transport.requests[13][2]["json_body"]
        self.assertEqual(fields_by_name(torznab_payload)["baseUrl"], TORZNAB_URL)
        self.assertEqual(fields_by_name(torznab_payload)["apiKey"], TORZNAB_KEY)
        self.assertNotIn(QBT_PASSWORD, repr(result))
        self.assertNotIn(SONARR_KEY, repr(result))
        self.assertNotIn(RADARR_KEY, repr(result))
        self.assertNotIn(TORZNAB_KEY, repr(result))
        self.assertNotIn(PROWLARR_KEY, repr(result))

    def test_matching_managed_resources_are_a_read_only_noop_and_unrelated_indexer_is_preserved(self):
        qbit = qbit_schema(
            fields=[
                {"name": "host", "value": "qbittorrent"},
                {"name": "port", "value": 8081},
                {"name": "username", "value": "admin"},
                {"name": "password", "value": ""},
                {"name": "unrelated", "value": "preserve-me"},
            ]
        )
        applications = [
            application_schema(
                "sonarr",
                fields=[
                    {"name": "baseUrl", "value": "http://sonarr:8989"},
                    {"name": "apiKey", "value": SONARR_KEY},
                    {"name": "syncLevel", "value": "fullSync"},
                ],
            ),
            application_schema(
                "radarr",
                fields=[
                    {"name": "baseUrl", "value": "http://radarr:7878"},
                    {"name": "apiKey", "value": RADARR_KEY},
                    {"name": "syncLevel", "value": "fullSync"},
                ],
            ),
        ]
        managed_indexer = torznab_schema()
        managed_indexer.update({"id": 14, "name": "Lumen Generic Torznab"})
        managed_indexer["fields"] = [
            {"name": "baseUrl", "value": TORZNAB_URL},
            {"name": "apiKey", "value": TORZNAB_KEY},
            {"name": "categories", "value": "5000"},
        ]
        unrelated_indexer = {"id": 99, "name": "Unrelated Indexer", "implementation": "Other"}
        adapter, transport = self.adapter(
            fresh_responses(
                qbit=qbit,
                qbit_existing={
                    "id": 7,
                    "name": "qBittorrent",
                    "implementation": "QBittorrent",
                    "fields": qbit["fields"],
                },
                applications=applications,
                applications_existing=applications,
                indexers=[unrelated_indexer, managed_indexer],
            )
        )

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        self.assertTrue(all(request[0] == "GET" for request in transport.requests))
        self.assertEqual(len(transport.requests), 7)
        self.assertIn("reuse-download-client", result.actions)
        self.assertIn("reuse-sonarr-application", result.actions)
        self.assertIn("reuse-radarr-application", result.actions)
        self.assertIn("reuse-generic-torznab", result.actions)

    def test_exact_managed_torznab_name_with_endpoint_drift_is_tested_then_updated(self):
        qbit = qbit_schema(
            fields=[
                {"name": "host", "value": "qbittorrent"},
                {"name": "port", "value": 8081},
                {"name": "username", "value": "admin"},
                {"name": "password", "value": ""},
            ]
        )
        applications = [
            application_schema(
                "sonarr",
                fields=[
                    {"name": "baseUrl", "value": "http://sonarr:8989"},
                    {"name": "apiKey", "value": SONARR_KEY},
                    {"name": "syncLevel", "value": "fullSync"},
                ],
            ),
            application_schema(
                "radarr",
                fields=[
                    {"name": "baseUrl", "value": "http://radarr:7878"},
                    {"name": "apiKey", "value": RADARR_KEY},
                    {"name": "syncLevel", "value": "fullSync"},
                ],
            ),
        ]
        managed_indexer = torznab_schema(
            fields=[
                {"name": "baseUrl", "value": "https://old.example.test/torznab"},
                {"name": "apiKey", "value": ""},
                {"name": "categories", "value": "5000"},
            ]
        )
        managed_indexer.update({"id": 314, "name": "Lumen Generic Torznab"})
        adapter, transport = self.adapter(
            fresh_responses(
                qbit=qbit,
                qbit_existing={"id": 7, "name": "qBittorrent", "implementation": "QBittorrent", "fields": qbit["fields"]},
                applications=applications,
                applications_existing=applications,
                indexers=[managed_indexer],
            )
        )

        result = adapter.configure(confirm=True)

        self.assertEqual(result.status, "ok")
        self.assertIn("update-generic-torznab", result.actions)
        self.assertEqual(
            [(request[0], request[1]) for request in transport.requests[7:]],
            [
                ("POST", f"{BASE_URL}/api/v1/indexer/test"),
                ("PUT", f"{BASE_URL}/api/v1/indexer/314"),
            ],
        )
        self.assertEqual(fields_by_name(transport.requests[8][2]["json_body"])["baseUrl"], TORZNAB_URL)


    def test_similarly_named_unrelated_clients_and_applications_are_not_adopted_or_updated(self):
        unrelated_qbit = {
            "id": 101,
            "name": "qBittorrent backup",
            "implementation": "OtherTorrentClient",
            "implementationName": "OtherTorrentClient",
            "configContract": "OtherTorrentClientSettings",
            "fields": [
                {"name": "host", "value": "backup-qbittorrent"},
                {"name": "port", "value": 8081},
                {"name": "username", "value": "backup-user"},
                {"name": "password", "value": ""},
            ],
        }
        unrelated_applications = [
            {
                "id": 102,
                "name": "Sonarr backup",
                "implementation": "OtherApplication",
                "implementationName": "OtherApplication",
                "configContract": "OtherApplicationSettings",
                "fields": [
                    {"name": "baseUrl", "value": "http://backup-sonarr:8989"},
                    {"name": "apiKey", "value": ""},
                    {"name": "syncLevel", "value": "addOnly"},
                ],
            },
            {
                "id": 103,
                "name": "Radarr backup",
                "implementation": "OtherApplication",
                "implementationName": "OtherApplication",
                "configContract": "OtherApplicationSettings",
                "fields": [
                    {"name": "baseUrl", "value": "http://backup-radarr:7878"},
                    {"name": "apiKey", "value": ""},
                    {"name": "syncLevel", "value": "addOnly"},
                ],
            },
        ]
        adapter, transport = self.adapter(
            fresh_responses(
                qbit_existing=unrelated_qbit,
                applications_existing=unrelated_applications,
            )
        )

        result = adapter.configure(confirm=True)

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            [(request[0], request[1]) for request in transport.requests[7:]],
            [
                ("POST", f"{BASE_URL}/api/v1/downloadclient/test"),
                ("POST", f"{BASE_URL}/api/v1/downloadclient"),
                ("POST", f"{BASE_URL}/api/v1/applications/test"),
                ("POST", f"{BASE_URL}/api/v1/applications"),
                ("POST", f"{BASE_URL}/api/v1/applications/test"),
                ("POST", f"{BASE_URL}/api/v1/applications"),
                ("POST", f"{BASE_URL}/api/v1/indexer/test"),
                ("POST", f"{BASE_URL}/api/v1/indexer"),
            ],
        )
        self.assertEqual(
            result.actions,
            (
                "create-download-client",
                "create-sonarr-application",
                "create-radarr-application",
                "create-generic-torznab",
            ),
        )

    def test_generic_name_with_wrong_implementation_is_preserved_and_not_adopted(self):
        wrong_generic = torznab_schema(
            fields=[
                {"name": "baseUrl", "value": "https://unrelated.example.test"},
                {"name": "apiKey", "value": ""},
                {"name": "categories", "value": "5000"},
            ]
        )
        wrong_generic.update(
            {
                "id": 88,
                "name": "Lumen Generic Torznab",
                "implementation": "OtherIndexer",
                "implementationName": "OtherIndexer",
                "configContract": "OtherIndexerSettings",
            }
        )
        adapter, transport = self.adapter(fresh_responses(indexers=[wrong_generic]))

        result = adapter.configure(confirm=True)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.actions[-1], "create-generic-torznab")
        self.assertEqual(
            [(request[0], request[1]) for request in transport.requests[-2:]],
            [
                ("POST", f"{BASE_URL}/api/v1/indexer/test"),
                ("POST", f"{BASE_URL}/api/v1/indexer"),
            ],
        )
        self.assertNotIn("/api/v1/indexer/88", [request[1] for request in transport.requests])

    def test_substring_matching_generic_schema_falls_back_without_mutation(self):
        unsupported_schema = torznab_schema()
        unsupported_schema.update(
            {
                "name": "Generic Torznab legacy",
                "implementation": "Custom Generic Torznab",
                "implementationName": "Custom Generic Torznab",
                "configContract": "CustomGenericTorznabSettings",
            }
        )
        adapter, transport = self.adapter(
            fresh_responses(indexer_schemas=[unsupported_schema], indexers=[])
        )

        result = adapter.configure()

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.checkpoints[0].code, "prowlarr-indexer-guided")
        self.assertEqual(result.checkpoints[0].action, "open-prowlarr-ui")
        self.assertEqual(len(transport.requests), 7)
        self.assertTrue(all(request[0] == "GET" for request in transport.requests))
        self.assertNotIn(TORZNAB_KEY, repr(result))

    def test_indexer_definition_accepts_minimal_exact_type_but_guides_substring_name(self):
        exact_adapter, exact_transport = self.adapter(
            fresh_responses(),
            indexer_definitions=[{"name": "Generic Torznab", "implementation": "Torznab"}],
        )

        exact_result = exact_adapter.configure()

        self.assertEqual(exact_result.status, "ok")
        self.assertEqual(
            [(request[0], request[1]) for request in exact_transport.requests[-2:]],
            [
                ("POST", f"{BASE_URL}/api/v1/indexer/test"),
                ("POST", f"{BASE_URL}/api/v1/indexer"),
            ],
        )

        substring_adapter, substring_transport = self.adapter(
            fresh_responses(),
            indexer_definitions=[{"name": "Generic Torznab legacy", "implementation": "Torznab"}],
        )

        substring_result = substring_adapter.configure()

        self.assertEqual(substring_result.status, "guided")
        self.assertEqual(substring_result.checkpoints[0].code, "prowlarr-indexer-guided")
        self.assertEqual(len(substring_transport.requests), 7)

    def test_managed_conflict_requires_confirmation_before_any_mutation(self):
        qbit = qbit_schema(
            fields=[
                {"name": "host", "value": "wrong-qbt"},
                {"name": "port", "value": 8081},
                {"name": "username", "value": "admin"},
                {"name": "password", "value": ""},
                {"name": "unrelated", "value": "keep"},
            ]
        )
        adapter, transport = self.adapter(
            fresh_responses(
                qbit=qbit,
                qbit_existing={
                    "id": 7,
                    "name": "qBittorrent",
                    "implementation": "QBittorrent",
                    "fields": qbit["fields"],
                },
            )
        )

        result = adapter.configure(confirm=False)

        self.assertEqual(result.status, "drift")
        self.assertIsInstance(result.error, ProwlarrConflictError)
        self.assertTrue(result.drift)
        self.assertEqual(len(transport.requests), 7)
        self.assertNotIn("wrong-qbt", repr(result))

    def test_confirmed_managed_conflict_tests_then_updates_only_the_owned_resource(self):
        qbit = qbit_schema(
            fields=[
                {"name": "host", "value": "wrong-qbt"},
                {"name": "port", "value": 8081},
                {"name": "username", "value": "admin"},
                {"name": "password", "value": ""},
                {"name": "unrelated", "value": "keep"},
            ]
        )
        existing = {
            "id": 7,
            "name": "qBittorrent",
            "implementation": "QBittorrent",
            "fields": qbit["fields"],
        }
        responses = fresh_responses(qbit=qbit)
        responses[2] = response([existing])
        adapter, transport = self.adapter(responses)

        result = adapter.configure(confirm=True)

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            [(request[0], request[1]) for request in transport.requests[7:9]],
            [
                ("POST", f"{BASE_URL}/api/v1/downloadclient/test"),
                ("PUT", f"{BASE_URL}/api/v1/downloadclient/7"),
            ],
        )
        updated_fields = fields_by_name(transport.requests[8][2]["json_body"])
        self.assertEqual(updated_fields["unrelated"], "keep")

    def test_download_client_test_failure_prevents_create(self):
        responses = fresh_responses()
        responses[7] = response({"error": "private-qbit-test-response"}, status=400)
        adapter, transport = self.adapter(responses)

        result = adapter.configure()

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.checkpoints[0].code, "prowlarr-download-client-test")
        self.assertEqual(len(transport.requests), 8)
        self.assertNotIn("private-qbit-test-response", repr(result))
        self.assertNotIn(QBT_PASSWORD, repr(result))

    def test_application_test_failure_prevents_that_application_create(self):
        applications = [application_schema("sonarr"), application_schema("radarr")]
        existing_qbit = {
            "id": 7,
            "name": "qBittorrent",
            "implementation": "QBittorrent",
            "fields": qbit_schema(
                fields=[
                    {"name": "host", "value": "qbittorrent"},
                    {"name": "port", "value": 8081},
                    {"name": "username", "value": "admin"},
                    {"name": "password", "value": ""},
                    {"name": "unrelated", "value": "keep"},
                ]
            )["fields"],
        }
        responses = fresh_responses(applications=applications, qbit_existing=existing_qbit)
        responses[7] = response({"error": "private-sonarr-test-response"}, status=400)
        adapter, transport = self.adapter(responses)

        result = adapter.configure()

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.checkpoints[0].code, "prowlarr-sonarr-application-test")
        self.assertEqual(len(transport.requests), 8)
        self.assertNotIn("private-sonarr-test-response", repr(result))
        self.assertNotIn(SONARR_KEY, repr(result))

    def test_schema_variants_map_required_fields_by_name_without_dropping_unrelated_fields(self):
        qbit = qbit_schema(
            fields={
                "hostField": {"name": "host", "value": "old"},
                "portField": {"name": "port", "value": 1},
                "userField": {"name": "username", "value": "old"},
                "passwordField": {"name": "password", "value": ""},
                "keepField": {"name": "unrelated", "value": "keep"},
            }
        )
        applications = [
            application_schema(
                "sonarr",
                fields={
                    "urlField": {"name": "url", "value": "http://old"},
                    "keyField": {"name": "apikey", "value": ""},
                    "syncField": {"name": "syncLevel", "value": "addOnly"},
                },
            ),
            application_schema("radarr"),
        ]
        torznab = torznab_schema(
            fields={
                "urlField": {"name": "url", "value": "https://old"},
                "keyField": {"name": "apikey", "value": ""},
                "categoryField": {"name": "categories", "value": "5000"},
            }
        )
        adapter, transport = self.adapter(
            fresh_responses(
                qbit=qbit,
                applications=applications,
                indexer_schemas=[torznab],
                indexers=[],
            )
        )

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        qbit_payload = transport.requests[7][2]["json_body"]
        self.assertEqual(qbit_payload["fields"]["keepField"]["value"], "keep")
        sonarr_payload = transport.requests[9][2]["json_body"]
        self.assertEqual(sonarr_payload["fields"]["urlField"]["value"], "http://sonarr:8989")
        self.assertEqual(sonarr_payload["fields"]["keyField"]["value"], SONARR_KEY)
        torznab_payload = transport.requests[13][2]["json_body"]
        self.assertEqual(torznab_payload["fields"]["urlField"]["value"], TORZNAB_URL)
        self.assertEqual(torznab_payload["fields"]["keyField"]["value"], TORZNAB_KEY)

    def test_unsupported_indexer_definition_returns_guided_ui_checkpoint_without_generic_mutation(self):
        adapter, transport = self.adapter(
            fresh_responses(indexers=[]),
            indexer_definitions=[{"name": "Private Custom", "implementation": "UnsupportedIndexer"}],
        )

        result = adapter.configure()

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.checkpoints[0].code, "prowlarr-indexer-guided")
        self.assertEqual(result.checkpoints[0].action, "open-prowlarr-ui")
        self.assertEqual(len(transport.requests), 7)
        self.assertNotIn(TORZNAB_KEY, repr(result))

    def test_missing_generic_schema_returns_guided_checkpoint_without_mutating_other_indexers(self):
        adapter, transport = self.adapter(
            fresh_responses(
                indexer_schemas=[{"name": "Custom", "implementation": "Unsupported"}],
                indexers=[{"id": 42, "name": "Unrelated", "implementation": "Other"}],
            ),
            indexer_definitions=None,
        )

        result = adapter.configure()

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.checkpoints[0].code, "prowlarr-indexer-guided")
        self.assertEqual(len(transport.requests), 7)

    def test_unsupported_runtime_api_and_schema_fail_closed_without_response_text(self):
        adapter, transport = self.adapter([response({"instanceName": "private"})])

        with self.assertRaises(ProwlarrCapabilityError) as raised:
            adapter.configure()

        self.assertIsNone(raised.exception.__context__)
        self.assertNotIn(PROWLARR_KEY, repr(raised.exception))
        self.assertEqual(len(transport.requests), 1)

        schema_adapter, schema_transport = self.adapter(
            [response({"version": "1.0.0"}), response([{"name": "other"}])]
        )
        with self.assertRaises(ProwlarrSchemaError) as raised:
            schema_adapter.configure()
        self.assertIsNone(raised.exception.__context__)
        self.assertNotIn(PROWLARR_KEY, repr(raised.exception))
        self.assertEqual(len(schema_transport.requests), 2)

    def test_dry_run_is_read_only_and_all_credentials_remain_private(self):
        adapter, transport = self.adapter([])

        result = adapter.configure(dry_run=True)

        self.assertEqual(result.status, "dry-run")
        self.assertTrue(result.dry_run)
        self.assertEqual(transport.requests, [])
        for surface in (adapter, result, repr(result), result.report, result.redacted):
            rendered = repr(surface)
            self.assertNotIn(PROWLARR_KEY, rendered)
            self.assertNotIn(QBT_PASSWORD, rendered)
            self.assertNotIn(SONARR_KEY, rendered)
            self.assertNotIn(RADARR_KEY, rendered)
            self.assertNotIn(TORZNAB_KEY, rendered)

    def test_transport_failure_is_sanitized(self):
        adapter, transport = self.adapter([RuntimeError(f"private {PROWLARR_KEY} {TORZNAB_KEY}")])

        with self.assertRaises(Exception) as raised:
            adapter.configure()

        self.assertIsNone(raised.exception.__context__)
        self.assertNotIn(PROWLARR_KEY, repr(raised.exception))
        self.assertNotIn(TORZNAB_KEY, repr(raised.exception))
        self.assertEqual(len(transport.requests), 1)


if __name__ == "__main__":
    unittest.main()
