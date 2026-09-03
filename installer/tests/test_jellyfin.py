import json
import sys
import unittest
from collections.abc import Mapping
from pathlib import Path


WORKTREE_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_ROOT = WORKTREE_ROOT / "installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.errors import InvalidInputError, PartialError
from lumen_installer.http import (
    HttpConnectionError,
    HttpResponse,
    HttpTimeoutError,
    MalformedJsonError,
)
from lumen_installer.services.base import ServicePlan, ServiceResult
from lumen_installer.services.jellyfin import (
    JellyfinAdapter,
    JellyfinAuthenticationError,
    JellyfinCapabilityError,
    JellyfinLibrarySchemaError,
    JellyfinResult,
    JellyfinSessionError,
)


BASE_URL = "http://jellyfin.test:8096"
ADMIN = "lumen-admin"
PASSWORD = "correct horse battery staple"
TOKEN = "auth-token-must-not-escape"
SERVER_ID = "server-id-must-not-escape"


class DeterministicTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class SecretBearingMapping(Mapping):
    def __init__(self, secret):
        self.secret = secret

    def __getitem__(self, key):
        raise RuntimeError(f"malformed response contains {self.secret}")

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0


class SecretBearingSchemaMapping(Mapping):
    def __init__(self, secret):
        self.secret = secret

    def __contains__(self, key):
        return key != "body"

    def __getitem__(self, key):
        return None

    def get(self, key, default=None):
        if key == "Items":
            raise RuntimeError(f"malformed schema contains {self.secret}")
        return default

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0


def response(payload, status=200):
    if payload is None:
        body = b""
    elif isinstance(payload, bytes):
        body = payload
    else:
        body = json.dumps(payload).encode("utf-8")
    return HttpResponse(status, {"Content-Type": "application/json"}, body)


def system_info(initialized):
    return {
        "Id": SERVER_ID,
        "ServerName": "private-server-name",
        "Version": "10.11.0",
        "ProductName": "Jellyfin Server",
        "StartupWizardCompleted": initialized,
    }


def api_keys(items):
    return response({"Items": items, "TotalRecordCount": len(items), "StartIndex": 0})


class SharedServiceTypeTests(unittest.TestCase):
    def test_shared_public_types_are_immutable_and_have_no_credential_fields(self):
        plan = ServicePlan(service="jellyfin", actions=("authenticate",))
        result = ServiceResult(service="jellyfin", status="ok", actions=("authenticate",))

        with self.assertRaises(AttributeError):
            plan.actions = ()
        with self.assertRaises(AttributeError):
            result.status = "bad"
        for value in (plan, result, repr(plan), repr(result), plan.report, result.report):
            self.assertNotIn("password", repr(value).lower())
            self.assertNotIn("token", repr(value).lower())
        self.assertFalse(any("token" in field.name.lower() or "password" in field.name.lower() for field in plan.__dataclass_fields__.values()))
        self.assertFalse(any("token" in field.name.lower() or "password" in field.name.lower() for field in result.__dataclass_fields__.values()))


class JellyfinAdapterTests(unittest.TestCase):
    def adapter(self, responses, **kwargs):
        transport = DeterministicTransport(responses)
        adapter = JellyfinAdapter(BASE_URL, transport, **kwargs)
        return adapter, transport

    def authenticated_adapter(self, responses, **kwargs):
        adapter, transport = self.adapter([response({"AccessToken": TOKEN}), *responses], **kwargs)
        adapter.authenticate()
        return adapter, transport

    def test_authenticated_empty_library_inventory_plans_only_managed_libraries(self):
        adapter, transport = self.authenticated_adapter(
            [response([])],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        plan = adapter.plan_libraries()

        self.assertIsInstance(plan, ServicePlan)
        self.assertEqual(plan.status, "planned")
        self.assertEqual(
            plan.actions,
            ("create-library-movies", "create-library-shows"),
        )
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
            ],
        )
        for value in (plan, plan.report, repr(plan)):
            self.assertNotIn(ADMIN, repr(value))
            self.assertNotIn(PASSWORD, repr(value))
            self.assertNotIn(TOKEN, repr(value))

    def test_missing_managed_libraries_are_created_and_exact_readback_is_required(self):
        adapter, transport = self.authenticated_adapter(
            [
                response([]),
                response(None, status=204),
                response(None, status=204),
                response([
                    {
                        "Name": "Movies",
                        "CollectionType": "movies",
                        "Locations": ["/data/media/movies"],
                    },
                    {
                        "Name": "Shows",
                        "CollectionType": "tvshows",
                        "Locations": ["/data/media/tv"],
                    },
                ]),
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.reconcile_libraries()

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            result.actions,
            ("create-library-movies", "create-library-shows"),
        )
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
                (
                    "POST",
                    f"{BASE_URL}/Library/VirtualFolders?name=Movies&collectionType=movies&paths=%2Fdata%2Fmedia%2Fmovies",
                ),
                (
                    "POST",
                    f"{BASE_URL}/Library/VirtualFolders?name=Shows&collectionType=tvshows&paths=%2Fdata%2Fmedia%2Ftv",
                ),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
            ],
        )
        for request in transport.requests[1:]:
            self.assertEqual(
                request[2]["headers"]["Authorization"],
                adapter.session.headers["Authorization"],
            )
            self.assertNotIn("X-Emby-Authorization", request[2]["headers"])
        for value in (result, result.report, repr(result)):
            self.assertNotIn(ADMIN, repr(value))
            self.assertNotIn(PASSWORD, repr(value))
            self.assertNotIn(TOKEN, repr(value))

    def test_exact_managed_libraries_are_adopted_without_mutation_or_unrelated_changes(self):
        adapter, transport = self.authenticated_adapter(
            [
                response([
                    {
                        "Name": "Movies",
                        "CollectionType": "movies",
                        "Locations": ["/data/media/movies"],
                    },
                    {
                        "Name": "Shows",
                        "CollectionType": "tvshows",
                        "Locations": ["/data/media/tv"],
                    },
                    {
                        "Name": "Sonarr Imports",
                        "CollectionType": "mixed",
                        "Locations": ["/data/other"],
                    },
                ])
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.reconcile_libraries()

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            result.actions,
            ("adopt-library-movies", "adopt-library-shows"),
        )
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
            ],
        )
        self.assertNotIn("Sonarr Imports", repr(result))

    def test_duplicate_managed_library_matches_are_guided_without_mutation(self):
        adapter, transport = self.authenticated_adapter(
            [
                response([
                    {
                        "Name": "Movies",
                        "CollectionType": "movies",
                        "Locations": ["/data/media/movies"],
                    },
                    {
                        "Name": "Movies",
                        "CollectionType": "movies",
                        "Locations": ["/data/alternate-movies"],
                    },
                    {
                        "Name": "Shows",
                        "CollectionType": "tvshows",
                        "Locations": ["/data/media/tv"],
                    },
                ])
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.reconcile_libraries()

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.checkpoints[0].code, "jellyfin-library-conflict")
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
            ],
        )
        self.assertNotIn("alternate-movies", repr(result))

    def test_noninteractive_managed_drift_requires_confirmation_without_mutation(self):
        adapter, transport = self.authenticated_adapter(
            [
                response([
                    {
                        "Name": "Movies",
                        "CollectionType": "movies",
                        "Locations": ["/data/other-movies"],
                    }
                ])
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
            interactive=False,
        )

        result = adapter.reconcile_libraries(confirm_drift=True)

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.checkpoints[0].code, "jellyfin-library-drift")
        self.assertEqual(result.checkpoints[0].action, "confirm")
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
            ],
        )
        self.assertNotIn("other-movies", repr(result))

    def test_unauthorized_library_inventory_is_guided_without_mutation_or_response_leak(self):
        response_secret = "private-library-response"
        adapter, transport = self.authenticated_adapter(
            [response({"error": response_secret}, status=401)],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.reconcile_libraries()

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.checkpoints[0].code, "jellyfin-authentication")
        self.assertIsInstance(result.error, JellyfinAuthenticationError)
        self.assertNotIn(response_secret, repr(result))
        self.assertNotIn(TOKEN, repr(result))
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
            ],
        )

    def test_confirmed_managed_drift_remains_guided_without_delete_or_update(self):
        adapter, transport = self.authenticated_adapter(
            [
                response([
                    {
                        "Name": "Movies",
                        "CollectionType": "movies",
                        "Locations": ["/data/other-movies"],
                    }
                ])
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.reconcile_libraries(confirm_drift=True)

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.checkpoints[0].code, "jellyfin-library-drift")
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
            ],
        )

    def test_unauthorized_library_readback_after_create_is_guided(self):
        adapter, transport = self.authenticated_adapter(
            [
                response([]),
                response(None, status=204),
                response(None, status=204),
                response({"error": "private-readback"}, status=401),
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.reconcile_libraries()

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.checkpoints[0].code, "jellyfin-authentication")
        self.assertIsInstance(result.error, JellyfinAuthenticationError)
        self.assertNotIn("private-readback", repr(result))
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
                (
                    "POST",
                    f"{BASE_URL}/Library/VirtualFolders?name=Movies&collectionType=movies&paths=%2Fdata%2Fmedia%2Fmovies",
                ),
                (
                    "POST",
                    f"{BASE_URL}/Library/VirtualFolders?name=Shows&collectionType=tvshows&paths=%2Fdata%2Fmedia%2Ftv",
                ),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
            ],
        )

    def test_post_create_readback_rejects_case_or_whitespace_normalized_duplicates(self):
        for duplicate_name in ("movies", " Movies "):
            with self.subTest(duplicate_name=duplicate_name):
                adapter, transport = self.authenticated_adapter(
                    [
                        response([]),
                        response(None, status=204),
                        response(None, status=204),
                        response([
                            {
                                "Name": "Movies",
                                "CollectionType": "movies",
                                "Locations": ["/data/media/movies"],
                            },
                            {
                                "Name": duplicate_name,
                                "CollectionType": "movies",
                                "Locations": ["/data/media/movies"],
                            },
                            {
                                "Name": "Shows",
                                "CollectionType": "tvshows",
                                "Locations": ["/data/media/tv"],
                            },
                        ]),
                    ],
                    admin_name=ADMIN,
                    admin_password=PASSWORD,
                )

                result = adapter.reconcile_libraries()

                self.assertEqual(result.status, "guided")
                self.assertEqual(
                    result.checkpoints[0].code,
                    "jellyfin-library-readback-conflict",
                )
                self.assertEqual(
                    [request[0:2] for request in transport.requests],
                    [
                        ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                        ("GET", f"{BASE_URL}/Library/VirtualFolders"),
                        (
                            "POST",
                            f"{BASE_URL}/Library/VirtualFolders?name=Movies&collectionType=movies&paths=%2Fdata%2Fmedia%2Fmovies",
                        ),
                        (
                            "POST",
                            f"{BASE_URL}/Library/VirtualFolders?name=Shows&collectionType=tvshows&paths=%2Fdata%2Fmedia%2Ftv",
                        ),
                        ("GET", f"{BASE_URL}/Library/VirtualFolders"),
                    ],
                )

    def test_library_creation_unauthorized_is_typed_without_follow_up_mutation(self):
        for status in (401, 403):
            response_secret = f"private-create-response-{status}"
            with self.subTest(status=status):
                adapter, transport = self.authenticated_adapter(
                    [
                        response([]),
                        response({"error": response_secret}, status=status),
                    ],
                    admin_name=ADMIN,
                    admin_password=PASSWORD,
                )

                result = adapter.reconcile_libraries()

                self.assertEqual(result.status, "guided")
                self.assertEqual(result.checkpoints[0].code, "jellyfin-authentication")
                self.assertIsInstance(result.error, JellyfinAuthenticationError)
                self.assertEqual(result.error.status, status)
                self.assertIsNone(result.error.__context__)
                self.assertNotIn(response_secret, repr(result))
                self.assertNotIn(PASSWORD, repr(result))
                self.assertNotIn(TOKEN, repr(result))
                self.assertEqual(
                    [request[0:2] for request in transport.requests],
                    [
                        ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                        ("GET", f"{BASE_URL}/Library/VirtualFolders"),
                        (
                            "POST",
                            f"{BASE_URL}/Library/VirtualFolders?name=Movies&collectionType=movies&paths=%2Fdata%2Fmedia%2Fmovies",
                        ),
                    ],
                )

    def test_dry_run_library_plan_has_no_mutation_or_handoff_changes(self):
        adapter, transport = self.authenticated_adapter(
            [response([])],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.reconcile_libraries(dry_run=True)

        self.assertEqual(result.status, "dry-run")
        self.assertTrue(result.dry_run)
        self.assertEqual(
            result.actions,
            ("create-library-movies", "create-library-shows"),
        )
        self.assertIsNone(adapter.api_key_handoff)
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
            ],
        )
        for value in (result, result.report, repr(result)):
            self.assertNotIn(PASSWORD, repr(value))
            self.assertNotIn(TOKEN, repr(value))

    def test_case_variant_managed_name_is_drift_not_a_missing_library(self):
        adapter, transport = self.authenticated_adapter(
            [
                response([
                    {
                        "Name": "movies",
                        "CollectionType": "movies",
                        "Locations": ["/data/media/movies"],
                    }
                ])
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.reconcile_libraries()

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.checkpoints[0].code, "jellyfin-library-drift")
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
            ],
        )

    def test_whitespace_variant_managed_name_is_drift_not_a_missing_library(self):
        adapter, transport = self.authenticated_adapter(
            [
                response([
                    {
                        "Name": " Movies ",
                        "CollectionType": "movies",
                        "Locations": ["/data/media/movies"],
                    }
                ])
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.reconcile_libraries()

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.checkpoints[0].code, "jellyfin-library-drift")
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
            ],
        )

    def test_malformed_library_inventory_fails_closed_before_mutation(self):
        malformed_payloads = [
            {"Items": []},
            [{"CollectionType": "movies", "Locations": ["/data/media/movies"]}],
            [{"Name": "Movies", "Locations": ["/data/media/movies"]}],
            [{
                "Name": "Movies",
                "CollectionType": "movies",
                "Locations": "/data/media/movies",
            }],
            [{
                "Name": "Movies",
                "CollectionType": "movies",
                "Locations": ["/data/media/movies", 17],
            }],
        ]

        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                adapter, transport = self.authenticated_adapter(
                    [response(payload)],
                    admin_name=ADMIN,
                    admin_password=PASSWORD,
                )

                with self.assertRaises(InvalidInputError) as raised:
                    adapter.reconcile_libraries()

                self.assertIsInstance(raised.exception, JellyfinLibrarySchemaError)
                self.assertIsNone(raised.exception.__context__)
                self.assertEqual(
                    [request[0:2] for request in transport.requests],
                    [
                        ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                        ("GET", f"{BASE_URL}/Library/VirtualFolders"),
                    ],
                )

    def test_library_create_requires_both_exact_managed_definitions_in_readback(self):
        for readback in (
            [],
            [{
                "Name": "Movies",
                "CollectionType": "movies",
                "Locations": ["/data/media/movies"],
            }],
            [
                {
                    "Name": "Movies",
                    "CollectionType": "movies",
                    "Locations": ["/data/media/movies"],
                },
                {
                    "Name": "Movies",
                    "CollectionType": "movies",
                    "Locations": ["/data/media/movies"],
                },
                {
                    "Name": "Shows",
                    "CollectionType": "tvshows",
                    "Locations": ["/data/media/tv"],
                },
            ],
        ):
            with self.subTest(readback=readback):
                adapter, transport = self.authenticated_adapter(
                    [
                        response([]),
                        response(None, status=204),
                        response(None, status=204),
                        response(readback),
                    ],
                    admin_name=ADMIN,
                    admin_password=PASSWORD,
                )

                result = adapter.reconcile_libraries()

                self.assertEqual(result.status, "guided")
                self.assertEqual(
                    result.checkpoints[0].code,
                    "jellyfin-library-readback-conflict",
                )
                self.assertEqual(
                    [request[0:2] for request in transport.requests],
                    [
                        ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                        ("GET", f"{BASE_URL}/Library/VirtualFolders"),
                        (
                            "POST",
                            f"{BASE_URL}/Library/VirtualFolders?name=Movies&collectionType=movies&paths=%2Fdata%2Fmedia%2Fmovies",
                        ),
                        (
                            "POST",
                            f"{BASE_URL}/Library/VirtualFolders?name=Shows&collectionType=tvshows&paths=%2Fdata%2Fmedia%2Ftv",
                        ),
                        ("GET", f"{BASE_URL}/Library/VirtualFolders"),
                    ],
                )

    def test_library_dry_run_preserves_an_existing_private_api_key_handoff(self):
        existing_key = "existing-key-must-stay-private"
        adapter, transport = self.authenticated_adapter(
            [
                api_keys([{"AppName": "Lumen", "AccessToken": existing_key}]),
                response([]),
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        adapter.reconcile_api_key()
        handoff = adapter.api_key_handoff
        result = adapter.reconcile_libraries(dry_run=True)

        self.assertEqual(result.status, "dry-run")
        self.assertIs(adapter.api_key_handoff, handoff)
        self.assertEqual(handoff.consume(), existing_key)
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                ("GET", f"{BASE_URL}/Auth/Keys"),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
            ],
        )
        self.assertNotIn(existing_key, repr(result))

    def test_unbound_library_plan_is_reinventoried_before_any_mutation(self):
        adapter, transport = self.authenticated_adapter(
            [
                response([]),
                response(None, status=204),
                response(None, status=204),
                response([
                    {
                        "Name": "Movies",
                        "CollectionType": "movies",
                        "Locations": ["/data/media/movies"],
                    },
                    {
                        "Name": "Shows",
                        "CollectionType": "tvshows",
                        "Locations": ["/data/media/tv"],
                    },
                ]),
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )
        plan = ServicePlan(
            service="jellyfin",
            actions=("create-library-movies",),
            mode="libraries",
        )

        result = adapter.apply_libraries(plan)

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
                (
                    "POST",
                    f"{BASE_URL}/Library/VirtualFolders?name=Movies&collectionType=movies&paths=%2Fdata%2Fmedia%2Fmovies",
                ),
                (
                    "POST",
                    f"{BASE_URL}/Library/VirtualFolders?name=Shows&collectionType=tvshows&paths=%2Fdata%2Fmedia%2Ftv",
                ),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
            ],
        )

    def test_malformed_library_json_is_typed_and_secret_free(self):
        response_secret = "library-json-secret"
        payload = json.dumps({"Items": response_secret}).encode("utf-8")
        adapter, transport = self.authenticated_adapter(
            [response(payload)],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        with self.assertRaises(InvalidInputError) as raised:
            adapter.reconcile_libraries()

        self.assertIsInstance(raised.exception, JellyfinLibrarySchemaError)
        self.assertNotIn(response_secret, str(raised.exception))
        self.assertNotIn(response_secret, repr(raised.exception))
        self.assertIsNone(raised.exception.__context__)
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
            ],
        )

    def test_library_transport_failure_is_typed_and_secret_free(self):
        transport_secret = "library-transport-secret"
        adapter, transport = self.authenticated_adapter(
            [RuntimeError(f"socket failed: {transport_secret}")],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        with self.assertRaises(HttpConnectionError) as raised:
            adapter.reconcile_libraries()

        self.assertNotIn(transport_secret, str(raised.exception))
        self.assertNotIn(transport_secret, repr(raised.exception))
        self.assertIsNone(raised.exception.__context__)
        self.assertIsNone(raised.exception.__cause__)
        self.assertEqual(len(transport.requests), 2)

    def test_stale_library_plan_rechecks_inventory_before_creating(self):
        adapter, transport = self.authenticated_adapter(
            [
                response([]),
                response([]),
                response(None, status=204),
                response(None, status=204),
                response([
                    {
                        "Name": "Movies",
                        "CollectionType": "movies",
                        "Locations": ["/data/media/movies"],
                    },
                    {
                        "Name": "Shows",
                        "CollectionType": "tvshows",
                        "Locations": ["/data/media/tv"],
                    },
                ]),
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )
        plan = adapter.plan_libraries()

        result = adapter.apply_libraries(plan)

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
                (
                    "POST",
                    f"{BASE_URL}/Library/VirtualFolders?name=Movies&collectionType=movies&paths=%2Fdata%2Fmedia%2Fmovies",
                ),
                (
                    "POST",
                    f"{BASE_URL}/Library/VirtualFolders?name=Shows&collectionType=tvshows&paths=%2Fdata%2Fmedia%2Ftv",
                ),
                ("GET", f"{BASE_URL}/Library/VirtualFolders"),
            ],
        )

    def test_existing_lumen_key_is_reused_without_auth_key_mutation(self):
        existing_key = "existing-lumen-api-key"
        unrelated_key = "unrelated-api-key"
        adapter, transport = self.authenticated_adapter(
            [api_keys([
                {"AppName": "Lumen", "AccessToken": existing_key},
                {"AppName": "Sonarr", "AccessToken": unrelated_key},
            ])],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.reconcile_api_key()

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.actions, ("reuse-api-key",))
        self.assertEqual([request[0:2] for request in transport.requests], [
            ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
            ("GET", f"{BASE_URL}/Auth/Keys"),
        ])
        handoff = adapter.api_key_handoff
        self.assertEqual(type(handoff).__name__, "JellyfinApiKeyHandoff")
        self.assertEqual(handoff.env_key_name, "JELLYFIN_API_KEY")
        self.assertEqual(handoff.consume(), existing_key)
        for value in (result, result.report, repr(result), handoff, repr(handoff), handoff.report):
            self.assertNotIn(existing_key, repr(value))
            self.assertNotIn(unrelated_key, repr(value))

    def test_inactive_or_revoked_lumen_keys_are_guided_without_reuse_or_creation(self):
        for item, checkpoint_code in (
            (
                {"AppName": "Lumen", "AccessToken": "inactive-lumen-key", "IsActive": False},
                "jellyfin-api-key-inactive",
            ),
            (
                {
                    "AppName": "Lumen",
                    "AccessToken": "revoked-lumen-key",
                    "DateRevoked": "2026-09-03T00:00:00Z",
                },
                "jellyfin-api-key-revoked",
            ),
        ):
            with self.subTest(checkpoint_code=checkpoint_code):
                adapter, transport = self.authenticated_adapter(
                    [api_keys([item])],
                    admin_name=ADMIN,
                    admin_password=PASSWORD,
                )

                result = adapter.reconcile_api_key()

                self.assertEqual(result.status, "guided")
                self.assertEqual(result.checkpoints[0].code, checkpoint_code)
                self.assertIsNone(adapter.api_key_handoff)
                self.assertEqual([request[0:2] for request in transport.requests], [
                    ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                    ("GET", f"{BASE_URL}/Auth/Keys"),
                ])
                self.assertNotIn(item["AccessToken"], repr(result))

    def test_missing_lumen_key_is_created_once_and_exact_readback_is_required(self):
        generated_key = "generated-lumen-api-key"
        adapter, transport = self.authenticated_adapter(
            [
                api_keys([]),
                response(None, status=204),
                api_keys([{"AppName": "Lumen", "AccessToken": generated_key}]),
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.reconcile_api_key()

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.actions, ("create-api-key",))
        self.assertEqual([request[0:2] for request in transport.requests], [
            ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
            ("GET", f"{BASE_URL}/Auth/Keys"),
            ("POST", f"{BASE_URL}/Auth/Keys?app=Lumen"),
            ("GET", f"{BASE_URL}/Auth/Keys"),
        ])
        self.assertNotIn("json_body", transport.requests[2][2])
        self.assertEqual(adapter.api_key_handoff.consume(), generated_key)

        for request in transport.requests[1:]:
            authorization = request[2]["headers"].get("Authorization")
            self.assertTrue(authorization.startswith("MediaBrowser Token="))
            self.assertNotIn("X-Emby-Authorization", request[2]["headers"])

    def test_post_create_inactive_or_revoked_lumen_readback_is_guided_without_handoff(self):
        for item, checkpoint_code in (
            (
                {
                    "AppName": "Lumen",
                    "AccessToken": "inactive-created-lumen-key",
                    "IsActive": False,
                },
                "jellyfin-api-key-inactive",
            ),
            (
                {
                    "AppName": "Lumen",
                    "AccessToken": "revoked-created-lumen-key",
                    "DateRevoked": "2026-09-03T00:00:00Z",
                },
                "jellyfin-api-key-revoked",
            ),
        ):
            with self.subTest(checkpoint_code=checkpoint_code):
                adapter, transport = self.authenticated_adapter(
                    [
                        api_keys([]),
                        response(None, status=204),
                        api_keys([item]),
                    ],
                    admin_name=ADMIN,
                    admin_password=PASSWORD,
                )

                result = adapter.reconcile_api_key()

                self.assertEqual(result.status, "guided")
                self.assertEqual(result.checkpoints[0].code, checkpoint_code)
                self.assertIsNone(adapter.api_key_handoff)
                self.assertEqual(
                    [request[0:2] for request in transport.requests],
                    [
                        ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                        ("GET", f"{BASE_URL}/Auth/Keys"),
                        ("POST", f"{BASE_URL}/Auth/Keys?app=Lumen"),
                        ("GET", f"{BASE_URL}/Auth/Keys"),
                    ],
                )
                self.assertNotIn(item["AccessToken"], repr(result))

    def test_duplicate_lumen_keys_are_guided_without_mutation_or_handoff(self):
        adapter, transport = self.authenticated_adapter(
            [api_keys([
                {"AppName": "Lumen", "AccessToken": "first-lumen-key"},
                {"AppName": "Lumen", "AccessToken": "second-lumen-key"},
            ])],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.reconcile_api_key()

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.checkpoints[0].code, "jellyfin-api-key-conflict")
        self.assertIsNone(adapter.api_key_handoff)
        self.assertEqual([request[0:2] for request in transport.requests], [
            ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
            ("GET", f"{BASE_URL}/Auth/Keys"),
        ])
        self.assertNotIn("first-lumen-key", repr(result))
        self.assertNotIn("second-lumen-key", repr(result))

    def test_post_create_missing_or_ambiguous_readback_is_guided_partial(self):
        for readback in ([], [
            {"AppName": "Lumen", "AccessToken": "first-lumen-key"},
            {"AppName": "Lumen", "AccessToken": "second-lumen-key"},
        ]):
            with self.subTest(readback=readback):
                adapter, transport = self.authenticated_adapter(
                    [api_keys([]), response(None, status=204), api_keys(readback)],
                    admin_name=ADMIN,
                    admin_password=PASSWORD,
                )

                result = adapter.reconcile_api_key()

                self.assertEqual(result.status, "guided")
                self.assertIn(result.checkpoints[0].code, {
                    "jellyfin-api-key-readback-missing",
                    "jellyfin-api-key-readback-ambiguous",
                })
                self.assertIsNone(adapter.api_key_handoff)
                self.assertEqual(
                    [request[0:2] for request in transport.requests],
                    [
                        ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                        ("GET", f"{BASE_URL}/Auth/Keys"),
                        ("POST", f"{BASE_URL}/Auth/Keys?app=Lumen"),
                        ("GET", f"{BASE_URL}/Auth/Keys"),
                    ],
                )

    def test_malformed_key_collection_and_item_fail_closed_before_creation(self):
        malformed_payloads = [
            {"Items": "not-a-list"},
            {"Items": [{"AccessToken": "orphan-key"}]},
            {"Items": [{"AppName": "Lumen"}]},
            {"Items": [{"AppName": "Lumen", "AccessToken": []}]},
            {"Items": ["not-an-object"]},
        ]
        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                adapter, transport = self.authenticated_adapter(
                    [response(payload)],
                    admin_name=ADMIN,
                    admin_password=PASSWORD,
                )

                with self.assertRaises(InvalidInputError) as raised:
                    adapter.reconcile_api_key()

                self.assertEqual(type(raised.exception).__name__, "JellyfinApiKeySchemaError")
                self.assertIsNone(raised.exception.__context__)
                self.assertNotIn("not-a-list", repr(raised.exception))
                self.assertEqual(len(transport.requests), 2)

    def test_incomplete_or_malformed_key_pagination_fails_before_creation(self):
        pagination_payloads = [
            {"Items": [], "TotalRecordCount": 1, "StartIndex": 0},
            {
                "Items": [{"AppName": "Sonarr", "AccessToken": "unrelated-key"}],
                "TotalRecordCount": 2,
                "StartIndex": 1,
            },
            {"Items": [], "TotalRecordCount": "0", "StartIndex": 0},
            {"Items": [], "TotalRecordCount": 0},
        ]
        for payload in pagination_payloads:
            with self.subTest(payload=payload):
                adapter, transport = self.authenticated_adapter(
                    [
                        response(payload),
                        response(None, status=204),
                        api_keys([{"AppName": "Lumen", "AccessToken": "generated-key"}]),
                    ],
                    admin_name=ADMIN,
                    admin_password=PASSWORD,
                )

                with self.assertRaises(InvalidInputError) as raised:
                    adapter.reconcile_api_key()

                self.assertEqual(type(raised.exception).__name__, "JellyfinApiKeySchemaError")
                self.assertIsNone(raised.exception.__context__)
                self.assertEqual([request[0:2] for request in transport.requests], [
                    ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
                    ("GET", f"{BASE_URL}/Auth/Keys"),
                ])

    def test_malformed_injected_mapping_detaches_secret_exception_context(self):
        secret = "mapping-secret-response"
        adapter, transport = self.authenticated_adapter(
            [SecretBearingMapping(secret)],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        with self.assertRaises(InvalidInputError) as raised:
            adapter.reconcile_api_key()

        self.assertEqual(type(raised.exception).__name__, "JellyfinSchemaError")
        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn(secret, repr(raised.exception))
        self.assertIsNone(raised.exception.__context__)
        self.assertIsNone(raised.exception.__cause__)
        self.assertEqual(len(transport.requests), 2)

    def test_malformed_injected_api_key_mapping_detaches_secret_exception_context(self):
        secret = "mapping-secret-api-key-schema"
        adapter, transport = self.authenticated_adapter(
            [SecretBearingSchemaMapping(secret)],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        with self.assertRaises(InvalidInputError) as raised:
            adapter.reconcile_api_key()

        self.assertEqual(type(raised.exception).__name__, "JellyfinApiKeySchemaError")
        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn(secret, repr(raised.exception))
        self.assertIsNone(raised.exception.__context__)
        self.assertIsNone(raised.exception.__cause__)
        self.assertEqual(len(transport.requests), 2)

    def test_unauthorized_key_request_is_guided_and_sanitized(self):
        response_secret = "private-response-body"
        adapter, transport = self.authenticated_adapter(
            [response({"error": response_secret}, status=401)],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.reconcile_api_key()

        self.assertEqual(result.status, "guided")
        self.assertIsInstance(result.error, JellyfinAuthenticationError)
        self.assertEqual(result.error.status, 401)
        self.assertNotIn(response_secret, repr(result))
        self.assertNotIn(TOKEN, repr(result))
        self.assertIsNone(result.error.__context__)
        self.assertEqual(len(transport.requests), 2)

    def test_untyped_transport_failure_is_reduced_without_secret_context(self):
        transport_secret = "transport-secret"
        adapter, transport = self.authenticated_adapter(
            [RuntimeError(f"socket failed: {transport_secret}")],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        with self.assertRaises(HttpConnectionError) as raised:
            adapter.reconcile_api_key()

        self.assertNotIn(transport_secret, str(raised.exception))
        self.assertNotIn(transport_secret, repr(raised.exception))
        self.assertIsNone(raised.exception.__context__)
        self.assertIsNone(raised.exception.__cause__)
        self.assertEqual(len(transport.requests), 2)

    def test_dry_run_plans_missing_key_without_post_or_fabricated_secret(self):
        adapter, transport = self.authenticated_adapter(
            [api_keys([])],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.reconcile_api_key(dry_run=True)

        self.assertEqual(result.status, "dry-run")
        self.assertTrue(result.dry_run)
        self.assertEqual(result.actions, ("create-api-key",))
        self.assertIsNone(adapter.api_key_handoff)
        self.assertEqual([request[0:2] for request in transport.requests], [
            ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
            ("GET", f"{BASE_URL}/Auth/Keys"),
        ])
        self.assertNotIn("fabricated", repr(result).lower())

    def test_dry_run_existing_key_never_exposes_consumable_handoff(self):
        existing_key = "existing-lumen-key-dry-run"
        adapter, transport = self.authenticated_adapter(
            [api_keys([{"AppName": "Lumen", "AccessToken": existing_key}])],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.reconcile_api_key(dry_run=True)

        self.assertEqual(result.status, "dry-run")
        self.assertTrue(result.dry_run)
        self.assertEqual(result.actions, ("reuse-api-key",))
        self.assertIsNone(adapter.api_key_handoff)
        self.assertEqual([request[0:2] for request in transport.requests], [
            ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
            ("GET", f"{BASE_URL}/Auth/Keys"),
        ])
        self.assertNotIn(existing_key, repr(result))

    def test_handoff_is_explicitly_consumable_but_all_normal_surfaces_are_redacted(self):
        api_key = "secret-key-for-private-handoff"
        adapter, _ = self.authenticated_adapter(
            [api_keys([{"AppName": "Lumen", "AccessToken": api_key}])],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        adapter.reconcile_api_key()
        handoff = adapter.api_key_handoff

        self.assertEqual(handoff.report, {
            "env_key_name": "JELLYFIN_API_KEY",
            "available": True,
        })
        self.assertEqual(handoff.consume(), api_key)
        self.assertEqual(handoff, adapter.api_key_handoff)
        for value in (handoff, str(handoff), repr(handoff), handoff.report):
            self.assertNotIn(api_key, repr(value))

        other = type(handoff)(api_key)
        self.assertNotEqual(handoff, other)
        self.assertNotIn(api_key, repr(handoff == other))

    def test_api_key_reconciliation_requires_an_authenticated_session(self):
        adapter, transport = self.adapter(
            [], admin_name=ADMIN, admin_password=PASSWORD
        )

        with self.assertRaises(JellyfinSessionError) as raised:
            adapter.reconcile_api_key()

        self.assertIsNone(raised.exception.__context__)
        self.assertIsNone(raised.exception.__cause__)
        self.assertEqual(transport.requests, [])

    def test_malformed_post_create_readback_fails_closed_without_handoff(self):
        adapter, transport = self.authenticated_adapter(
            [api_keys([]), response(None, status=204), response({"Items": [{"AppName": "Lumen"}]})],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        with self.assertRaises(InvalidInputError) as raised:
            adapter.reconcile_api_key()

        self.assertEqual(type(raised.exception).__name__, "JellyfinApiKeySchemaError")
        self.assertIsNone(raised.exception.__context__)
        self.assertIsNone(adapter.api_key_handoff)
        self.assertEqual(len(transport.requests), 4)

    def test_supported_fresh_startup_sequence_and_authentication(self):
        adapter, transport = self.adapter(
            [
                response(system_info(False)),
                response({"ServerName": "private-old-name"}),
                response(system_info(False)),
                response({"ServerName": "private-old-name"}),
                response(None),
                response({"Name": "bootstrap-user"}),
                response(None),
                response(None),
                response({"AccessToken": TOKEN, "User": {"Id": SERVER_ID}}),
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
            server_name="private-new-name",
        )

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.actions, ("configure-startup", "create-administrator", "complete-startup", "authenticate"))
        self.assertEqual([request[0:2] for request in transport.requests], [
            ("GET", f"{BASE_URL}/System/Info/Public"),
            ("GET", f"{BASE_URL}/Startup/Configuration"),
            ("GET", f"{BASE_URL}/System/Info/Public"),
            ("GET", f"{BASE_URL}/Startup/Configuration"),
            ("POST", f"{BASE_URL}/Startup/Configuration"),
            ("GET", f"{BASE_URL}/Startup/User"),
            ("POST", f"{BASE_URL}/Startup/User"),
            ("POST", f"{BASE_URL}/Startup/Complete"),
            ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
        ])
        self.assertEqual(transport.requests[4][2]["json_body"], {
            "ServerName": "private-new-name",
            "UICulture": "",
            "MetadataCountryCode": "",
            "PreferredMetadataLanguage": "",
        })
        self.assertEqual(transport.requests[6][2]["json_body"], {"Name": ADMIN, "Password": PASSWORD})
        self.assertEqual(transport.requests[8][2]["json_body"], {"Username": ADMIN, "Pw": PASSWORD})
        self.assertEqual(adapter.session.token, TOKEN)
        for value in (result, result.report, repr(result), repr(result.report), repr(result.error)):
            self.assertNotIn(ADMIN, repr(value))
            self.assertNotIn(PASSWORD, repr(value))
            self.assertNotIn(TOKEN, repr(value))
            self.assertNotIn(SERVER_ID, repr(value))

    def test_adopted_authentication_has_zero_startup_mutation(self):
        adapter, transport = self.adapter(
            [response(system_info(True)), response({"AccessToken": TOKEN, "User": {"Id": SERVER_ID}})],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.configure(adopt=True)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.actions, ("authenticate",))
        self.assertEqual([request[0:2] for request in transport.requests], [
            ("GET", f"{BASE_URL}/System/Info/Public"),
            ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
        ])
        self.assertEqual(adapter.session.token, TOKEN)

    def test_initialized_server_is_startup_noop_even_when_fresh_is_requested(self):
        adapter, transport = self.adapter(
            [response(system_info(True)), response({"AccessToken": TOKEN})],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        plan = adapter.plan(fresh=True)
        result = adapter.apply(plan)

        self.assertEqual(plan.actions, ("authenticate",))
        self.assertEqual(result.actions, ("authenticate",))
        self.assertEqual([request[0:2] for request in transport.requests], [
            ("GET", f"{BASE_URL}/System/Info/Public"),
            ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
        ])

    def test_unauthorized_credentials_return_guided_partial_result_and_typed_direct_error(self):
        adapter, transport = self.adapter(
            [response(system_info(True)), response({"no": "body"}, status=401)],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.configure(adopt=True)

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.checkpoints[0].code, "jellyfin-authentication")
        self.assertIsInstance(result.error, JellyfinAuthenticationError)
        self.assertIsInstance(result.error, PartialError)
        self.assertNotIn(PASSWORD, repr(result))
        self.assertNotIn(TOKEN, repr(result))
        self.assertEqual(len(transport.requests), 2)

        adapter2, _ = self.adapter([response({}, status=401)], admin_name=ADMIN, admin_password=PASSWORD)
        with self.assertRaises(JellyfinAuthenticationError):
            adapter2.authenticate()

    def test_unsupported_system_and_startup_shapes_fail_closed(self):
        for responses in (
            [response({"Version": "10.11.0"})],
            [response(system_info(False)), response([])],
            [response(system_info(False)), response({"ServerName": []})],
        ):
            with self.subTest(responses=responses):
                adapter, transport = self.adapter(responses, admin_name=ADMIN, admin_password=PASSWORD)
                with self.assertRaises(JellyfinCapabilityError) as raised:
                    adapter.plan()
                self.assertNotIn(PASSWORD, str(raised.exception))
                self.assertNotIn(SERVER_ID, str(raised.exception))
                self.assertEqual([request[0] for request in transport.requests], ["GET"] * len(responses))

    def test_malformed_json_is_typed_and_sanitized(self):
        adapter, _ = self.adapter(
            [response(b'{"StartupWizardCompleted":false,"Id":"' + SERVER_ID.encode() + b'"')],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        with self.assertRaises(JellyfinCapabilityError) as raised:
            adapter.plan()
        self.assertNotIn(SERVER_ID, str(raised.exception))
        self.assertNotIn(PASSWORD, repr(raised.exception))
        self.assertIsNone(raised.exception.__context__)

    def test_timeout_and_connection_failures_remain_typed_and_sanitized(self):
        for error in (
            HttpTimeoutError(method="GET", url=f"{BASE_URL}/System/Info/Public", timeout=1),
            HttpConnectionError(method="GET", url=f"{BASE_URL}/System/Info/Public"),
        ):
            with self.subTest(error=type(error).__name__):
                adapter, _ = self.adapter([error], admin_name=ADMIN, admin_password=PASSWORD)
                with self.assertRaises(type(error)) as raised:
                    adapter.plan()
                self.assertNotIn(PASSWORD, str(raised.exception))
                self.assertNotIn(SERVER_ID, repr(raised.exception))

    def test_dry_run_plans_actions_but_sends_no_mutation_requests(self):
        adapter, transport = self.adapter(
            [response(system_info(False)), response({})],
            admin_name=ADMIN,
            admin_password=PASSWORD,
            server_name="private-name",
        )

        result = adapter.configure(dry_run=True)

        self.assertTrue(result.dry_run)
        self.assertEqual(result.actions, ("configure-startup", "create-administrator", "complete-startup", "authenticate"))
        self.assertEqual([request[0] for request in transport.requests], ["GET", "GET"])

    def test_missing_noninteractive_decisions_fail_before_mutation(self):
        adapter, transport = self.adapter([response(system_info(False)), response({})], interactive=False)

        with self.assertRaises(InvalidInputError):
            adapter.configure()
        self.assertEqual(transport.requests, [])

    def test_apply_capability_checks_before_mutating_an_unbound_plan(self):
        adapter, transport = self.adapter(
            [
                response(system_info(False)),
                response({}),
                response(None),
                response({"Name": "bootstrap-user"}),
                response(None),
                response(None),
                response({"AccessToken": TOKEN}),
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )
        plan = ServicePlan(
            service="jellyfin",
            actions=("configure-startup", "create-administrator", "complete-startup", "authenticate"),
            mode="fresh",
        )

        result = adapter.apply(plan)

        self.assertEqual(result.status, "ok")
        self.assertEqual([request[0:2] for request in transport.requests], [
            ("GET", f"{BASE_URL}/System/Info/Public"),
            ("GET", f"{BASE_URL}/Startup/Configuration"),
            ("POST", f"{BASE_URL}/Startup/Configuration"),
            ("GET", f"{BASE_URL}/Startup/User"),
            ("POST", f"{BASE_URL}/Startup/User"),
            ("POST", f"{BASE_URL}/Startup/Complete"),
            ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
        ])

    def test_apply_rejects_missing_credentials_before_external_plan_mutation(self):
        adapter, transport = self.adapter(
            [response(system_info(False)), response({}), response(None), response(None), response(None)]
        )
        plan = ServicePlan(
            service="jellyfin",
            actions=("configure-startup", "create-administrator", "complete-startup"),
            mode="fresh",
        )

        with self.assertRaises(InvalidInputError):
            adapter.apply(plan)
        self.assertEqual(transport.requests, [])

    def test_fresh_startup_gets_initial_user_before_posting_it(self):
        adapter, transport = self.adapter(
            [
                response(system_info(False)),
                response({
                    "ServerName": "old-server",
                    "UICulture": "en-US",
                    "MetadataCountryCode": "US",
                    "PreferredMetadataLanguage": "en",
                }),
                response(system_info(False)),
                response({
                    "ServerName": "old-server",
                    "UICulture": "en-US",
                    "MetadataCountryCode": "US",
                    "PreferredMetadataLanguage": "en",
                }),
                response(None),
                response({"Name": "bootstrap-user", "Password": "must-not-be-used"}),
                response(None),
                response(None),
                response({"AccessToken": TOKEN}),
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        self.assertEqual([request[0:2] for request in transport.requests], [
            ("GET", f"{BASE_URL}/System/Info/Public"),
            ("GET", f"{BASE_URL}/Startup/Configuration"),
            ("GET", f"{BASE_URL}/System/Info/Public"),
            ("GET", f"{BASE_URL}/Startup/Configuration"),
            ("POST", f"{BASE_URL}/Startup/Configuration"),
            ("GET", f"{BASE_URL}/Startup/User"),
            ("POST", f"{BASE_URL}/Startup/User"),
            ("POST", f"{BASE_URL}/Startup/Complete"),
            ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
        ])
        self.assertNotIn("bootstrap-user", repr(result))
        self.assertNotIn("must-not-be-used", repr(result))

    def test_malformed_initial_user_response_fails_before_user_mutation(self):
        adapter, transport = self.adapter(
            [
                response(system_info(False)),
                response({"ServerName": "old-server"}),
                response(system_info(False)),
                response({"ServerName": "old-server"}),
                response(None),
                response({"Password": "response-secret"}),
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        with self.assertRaises(JellyfinCapabilityError) as raised:
            adapter.configure()

        self.assertNotIn("response-secret", str(raised.exception))
        self.assertEqual([request[0:2] for request in transport.requests], [
            ("GET", f"{BASE_URL}/System/Info/Public"),
            ("GET", f"{BASE_URL}/Startup/Configuration"),
            ("GET", f"{BASE_URL}/System/Info/Public"),
            ("GET", f"{BASE_URL}/Startup/Configuration"),
            ("POST", f"{BASE_URL}/Startup/Configuration"),
            ("GET", f"{BASE_URL}/Startup/User"),
        ])

    def test_authenticated_requests_use_quoted_modern_authorization_header(self):
        token = 'auth-"token"\\must-not-escape'
        adapter, transport = self.adapter(
            [response({"AccessToken": token, "User": {"Id": SERVER_ID}})],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        session = adapter.authenticate()

        headers = session.headers
        escaped_token = token.replace("\\", "\\\\").replace('"', '\\"')
        self.assertEqual(
            headers["Authorization"],
            f'MediaBrowser Token="{escaped_token}", '
            'Client="Lumen Installer", Device="installer", '
            'DeviceId="lumen-installer", Version="1.0"',
        )
        self.assertNotIn("X-Emby-Authorization", headers)
        guided = JellyfinResult(
            service="jellyfin",
            status="guided",
            error=JellyfinAuthenticationError(401),
        )
        for value in (session, adapter, guided, guided.report, guided.error):
            self.assertNotIn(token, repr(value))

    def test_startup_configuration_preserves_existing_fields_when_changing_server_name(self):
        adapter, transport = self.adapter(
            [
                response(system_info(False)),
                response({
                    "ServerName": "private-old-name",
                    "UICulture": "pt-BR",
                    "MetadataCountryCode": "BR",
                    "PreferredMetadataLanguage": "pt",
                }),
                response(system_info(False)),
                response({
                    "ServerName": "private-old-name",
                    "UICulture": "pt-BR",
                    "MetadataCountryCode": "BR",
                    "PreferredMetadataLanguage": "pt",
                }),
                response(None),
                response({"Name": "bootstrap-user"}),
                response(None),
                response(None),
                response({"AccessToken": TOKEN}),
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
            server_name="Lumen Media Hub",
        )

        adapter.configure()

        self.assertEqual(
            transport.requests[4][2]["json_body"],
            {
                "ServerName": "Lumen Media Hub",
                "UICulture": "pt-BR",
                "MetadataCountryCode": "BR",
                "PreferredMetadataLanguage": "pt",
            },
        )

    def test_stale_fresh_plan_rechecks_server_before_startup_mutation(self):
        adapter, transport = self.adapter(
            [
                response(system_info(False)),
                response({"ServerName": "old-server"}),
                response(system_info(True)),
                response({"AccessToken": TOKEN}),
            ],
            admin_name=ADMIN,
            admin_password=PASSWORD,
        )

        plan = adapter.plan()
        result = adapter.apply(plan)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.actions, ("authenticate",))
        self.assertEqual([request[0:2] for request in transport.requests], [
            ("GET", f"{BASE_URL}/System/Info/Public"),
            ("GET", f"{BASE_URL}/Startup/Configuration"),
            ("GET", f"{BASE_URL}/System/Info/Public"),
            ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
        ])


if __name__ == "__main__":
    unittest.main()
