import json
import sys
import unittest
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

    def test_supported_fresh_startup_sequence_and_authentication(self):
        adapter, transport = self.adapter(
            [response(system_info(False)), response({"ServerName": "private-old-name"}), response(None), response(None), response(None), response({"AccessToken": TOKEN, "User": {"Id": SERVER_ID}})],
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
            ("POST", f"{BASE_URL}/Startup/Configuration"),
            ("POST", f"{BASE_URL}/Startup/User"),
            ("POST", f"{BASE_URL}/Startup/Complete"),
            ("POST", f"{BASE_URL}/Users/AuthenticateByName"),
        ])
        self.assertEqual(transport.requests[2][2]["json_body"], {"ServerName": "private-new-name"})
        self.assertEqual(transport.requests[3][2]["json_body"], {"Name": ADMIN, "Password": PASSWORD})
        self.assertEqual(transport.requests[5][2]["json_body"], {"Username": ADMIN, "Pw": PASSWORD})
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


if __name__ == "__main__":
    unittest.main()
