import json
import sys
import unittest
from pathlib import Path


WORKTREE_ROOT = Path(__file__).resolve().parents[2]
INSTALLER_ROOT = WORKTREE_ROOT / "installer"
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.errors import InvalidInputError, PartialError
from lumen_installer.dotenv import DotEnvDocument
from lumen_installer.http import HttpConnectionError, HttpResponse, HttpStatusError, HttpTimeoutError
from lumen_installer.services.qbittorrent import (
    QbittorrentAdapter,
    QbittorrentAuthenticationError,
    QbittorrentCategoryReconciliationError,
    QbittorrentPasswordVerificationError,
    QbittorrentResult,
    QbittorrentEnvironmentUpdate,
    QbittorrentSchemaError,
    parse_temporary_password,
)


BASE_URL = "http://qbittorrent.test:8081"
CURRENT_PASSWORD = "current-env-secret"
NEW_COOKIE = "new-session-cookie"
TEMPORARY_PASSWORD = "temporary-log-secret"
SELECTED_PASSWORD = "selected-secret"


def response(payload, status=200, headers=None):
    if payload is None:
        body = b""
    elif isinstance(payload, bytes):
        body = payload
    elif isinstance(payload, str):
        body = payload.encode("utf-8")
    else:
        body = json.dumps(payload).encode("utf-8")
    return HttpResponse(status, headers or {"Content-Type": "application/json"}, body)


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


class QbittorrentAdapterTests(unittest.TestCase):
    def test_environment_update_is_redacted_in_result_report(self):
        result = QbittorrentResult(
            service="qbittorrent",
            status="ok",
            environment_update=QbittorrentEnvironmentUpdate(
                {"QBT_PASSWORD": SELECTED_PASSWORD, "STACK_PASSWORD": SELECTED_PASSWORD}
            ),
        )

        self.assertEqual(
            result.report["environment_update"],
            {"QBT_PASSWORD": "<redacted>", "STACK_PASSWORD": "<redacted>"},
        )
        self.assertNotIn(SELECTED_PASSWORD, repr(result.report))

    def _configured_responses(self, *, save_path="/downloads", categories=None):
        return [
            response("Ok.", headers={"Set-Cookie": "SID=initial-session; Path=/"}),
            response({"save_path": save_path, "listen_port": 6881}),
            response(categories or {}),
            response(""),
            response("Ok.", headers={"Set-Cookie": f"SID={NEW_COOKIE}; Path=/"}),
        ]

    def test_current_env_password_is_verified_reconfigured_and_reauthenticated(self):
        transport = DeterministicTransport(
            [
                response("Ok.", headers={"Set-Cookie": "SID=initial-session; Path=/"}),
                response(
                    {
                        "save_path": "/downloads",
                    }
                ),
                response(
                    {
                        "sonarr": {"savePath": "/downloads/sonarr"},
                        "radarr": {"savePath": "/downloads/radarr"},
                        "unrelated": {"savePath": "/downloads/unrelated"},
                    }
                ),
                response(""),
                response("Ok.", headers={"Set-Cookie": f"SID={NEW_COOKIE}; Path=/"}),
            ]
        )
        adapter = QbittorrentAdapter(
            BASE_URL,
            transport,
            env={"QBT_PASSWORD": CURRENT_PASSWORD, "STACK_PASSWORD": "legacy-secret"},
        )

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/api/v2/auth/login"),
                ("GET", f"{BASE_URL}/api/v2/app/preferences"),
                ("GET", f"{BASE_URL}/api/v2/torrents/categories"),
                ("POST", f"{BASE_URL}/api/v2/app/setPreferences"),
                ("POST", f"{BASE_URL}/api/v2/auth/login"),
            ],
        )
        self.assertEqual(
            transport.requests[0][2]["form"],
            {"username": "admin", "password": CURRENT_PASSWORD},
        )
        self.assertEqual(
            json.loads(transport.requests[3][2]["form"]["json"]),
            {"web_ui_password": CURRENT_PASSWORD},
        )
        self.assertEqual(result.environment_update["QBT_PASSWORD"], CURRENT_PASSWORD)
        self.assertEqual(result.environment_update["STACK_PASSWORD"], CURRENT_PASSWORD)
        self.assertNotIn(CURRENT_PASSWORD, repr(result))
        self.assertNotIn(CURRENT_PASSWORD, repr(result.report))
        self.assertNotIn(CURRENT_PASSWORD, repr(result.environment_update))

    def test_temporary_log_credential_is_attempted_after_current_env_and_replaced_by_selected_password(self):
        transport = DeterministicTransport(
            [
                response("Fails."),
                response("Ok.", headers={"Set-Cookie": "SID=temp-session; Path=/"}),
                response({"save_path": "/downloads"}),
                response({"sonarr": {"savePath": "/downloads/sonarr"}, "radarr": {"savePath": "/downloads/radarr"}}),
                response(""),
                response("Ok.", headers={"Set-Cookie": "SID=selected-session; Path=/"}),
            ]
        )
        adapter = QbittorrentAdapter(
            BASE_URL,
            transport,
            env={"QBT_PASSWORD": "stale-env-secret"},
            logs=(
                "The WebUI administrator password was not set. "
                f"A temporary password is provided for this session: {TEMPORARY_PASSWORD}\n"
            ),
            selected_password=SELECTED_PASSWORD,
        )

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            [request[2].get("form") for request in transport.requests[:2]],
            [
                {"username": "admin", "password": "stale-env-secret"},
                {"username": "admin", "password": TEMPORARY_PASSWORD},
            ],
        )
        self.assertEqual(
            json.loads(transport.requests[4][2]["form"]["json"]),
            {"web_ui_password": SELECTED_PASSWORD},
        )
        self.assertEqual(result.environment_update["QBT_PASSWORD"], SELECTED_PASSWORD)
        self.assertEqual(result.environment_update["STACK_PASSWORD"], SELECTED_PASSWORD)
        for value in (result, result.report, repr(result), repr(result.report), repr(result.error)):
            self.assertNotIn(TEMPORARY_PASSWORD, repr(value))
            self.assertNotIn(SELECTED_PASSWORD, repr(value))

    def test_stack_password_is_the_current_secret_fallback_when_qbt_password_is_absent(self):
        transport = DeterministicTransport(self._configured_responses(
            categories={
                "sonarr": {"savePath": "/downloads/sonarr"},
                "radarr": {"savePath": "/downloads/radarr"},
            }
        ))
        adapter = QbittorrentAdapter(
            BASE_URL,
            transport,
            env={"STACK_PASSWORD": SELECTED_PASSWORD},
            interactive=False,
        )

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        self.assertEqual(transport.requests[0][2]["form"], {"username": "admin", "password": SELECTED_PASSWORD})
        self.assertEqual(result.environment_update["QBT_PASSWORD"], SELECTED_PASSWORD)

    def test_dotenv_document_is_accepted_as_the_current_env_source(self):
        transport = DeterministicTransport(self._configured_responses(
            categories={
                "sonarr": {"savePath": "/downloads/sonarr"},
                "radarr": {"savePath": "/downloads/radarr"},
            }
        ))
        adapter = QbittorrentAdapter(
            BASE_URL,
            transport,
            environment=DotEnvDocument.parse(f"QBT_PASSWORD={CURRENT_PASSWORD}\n"),
            interactive=False,
        )

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.environment_update["QBT_PASSWORD"], CURRENT_PASSWORD)

    def test_interactive_password_callback_is_last_credential_source(self):
        transport = DeterministicTransport(self._configured_responses(
            categories={
                "sonarr": {"savePath": "/downloads/sonarr"},
                "radarr": {"savePath": "/downloads/radarr"},
            }
        ))
        prompts = []
        adapter = QbittorrentAdapter(
            BASE_URL,
            transport,
            prompt=lambda: prompts.append("asked") or SELECTED_PASSWORD,
            interactive=True,
        )

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        self.assertEqual(prompts, ["asked"])
        self.assertEqual(result.environment_update["QBT_PASSWORD"], SELECTED_PASSWORD)

    def test_interactive_password_callback_is_not_read_when_current_env_authenticates(self):
        transport = DeterministicTransport(self._configured_responses(
            categories={
                "sonarr": {"savePath": "/downloads/sonarr"},
                "radarr": {"savePath": "/downloads/radarr"},
            }
        ))
        prompts = []
        adapter = QbittorrentAdapter(
            BASE_URL,
            transport,
            env={"QBT_PASSWORD": CURRENT_PASSWORD},
            prompt=lambda: prompts.append("asked") or SELECTED_PASSWORD,
            interactive=True,
        )

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        self.assertEqual(prompts, [])
        self.assertEqual(result.environment_update["QBT_PASSWORD"], CURRENT_PASSWORD)

    def test_unknown_adopted_credentials_return_guided_exit_four_without_http_or_env_update(self):
        transport = DeterministicTransport([])
        adapter = QbittorrentAdapter(BASE_URL, transport, interactive=False)

        result = adapter.configure(adopt=True)

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.exit_code, 4)
        self.assertEqual(result.checkpoints[0].code, "qbittorrent-credentials")
        self.assertIsInstance(result.error, PartialError)
        self.assertEqual(dict(result.environment_update), {})
        self.assertEqual(transport.requests, [])

    def test_temporary_password_parser_is_bounded_by_bytes_and_lines_and_ignores_other_log_text(self):
        line = (
            "The WebUI administrator password was not set. "
            f"A temporary password is provided for this session: {TEMPORARY_PASSWORD}\n"
        )

        self.assertIsNone(parse_temporary_password(line, max_lines=0))
        self.assertIsNone(parse_temporary_password("noise\n" + line, max_lines=1))
        self.assertIsNone(parse_temporary_password(line, max_bytes=len(line.encode()) - 1))
        self.assertIsNone(parse_temporary_password("unrelated secret text\n"))
        self.assertEqual(parse_temporary_password(line), TEMPORARY_PASSWORD)

        adapter = QbittorrentAdapter(BASE_URL, DeterministicTransport([]), logs="unrelated secret text\n", interactive=False)
        self.assertNotIn("unrelated secret text", repr(adapter))

    def test_temporary_password_parser_stops_before_oversized_or_unencodable_lines(self):
        line = (
            "The WebUI administrator password was not set. "
            f"A temporary password is provided for this session: {TEMPORARY_PASSWORD}\n"
        )

        self.assertIsNone(parse_temporary_password("x" * 65 + "\n" + line, max_bytes=64))
        self.assertIsNone(parse_temporary_password("\ud800\n" + line, max_bytes=1024))
        self.assertIsNone(parse_temporary_password(b"\xff\n" + line.encode(), max_bytes=1024))

    def test_banned_authentication_is_typed_redacted_and_has_no_exception_context(self):
        transport = DeterministicTransport([response("banned", status=403)])
        adapter = QbittorrentAdapter(BASE_URL, transport, interactive=False)

        with self.assertRaises(QbittorrentAuthenticationError) as raised:
            adapter.authenticate(password=SELECTED_PASSWORD)

        self.assertEqual(raised.exception.status, 403)
        self.assertTrue(raised.exception.banned)
        self.assertIsInstance(raised.exception, PartialError)
        self.assertNotIn(SELECTED_PASSWORD, str(raised.exception))
        self.assertNotIn("banned", str(raised.exception))
        self.assertIsNone(raised.exception.__context__)

    def test_http_403_ban_stops_all_credential_retries(self):
        temporary_line = (
            "The WebUI administrator password was not set. "
            f"A temporary password is provided for this session: {TEMPORARY_PASSWORD}\n"
        )
        transport = DeterministicTransport(
            [
                response("banned", status=403),
                response("Ok.", headers={"Set-Cookie": "SID=unexpected-retry; Path=/"}),
            ]
        )
        adapter = QbittorrentAdapter(
            BASE_URL,
            transport,
            env={"QBT_PASSWORD": CURRENT_PASSWORD},
            logs=temporary_line,
            prompt=lambda: SELECTED_PASSWORD,
        )

        with self.assertRaises(QbittorrentAuthenticationError) as raised:
            adapter.authenticate()

        self.assertTrue(raised.exception.banned)
        self.assertEqual(len(transport.requests), 1)
        self.assertIsNone(raised.exception.__context__)

    def test_fails_login_body_is_typed_without_echoing_body_or_password(self):
        transport = DeterministicTransport([response("Fails.")])
        adapter = QbittorrentAdapter(BASE_URL, transport, interactive=False)

        with self.assertRaises(QbittorrentAuthenticationError) as raised:
            adapter.authenticate(password=SELECTED_PASSWORD)

        self.assertIsNone(raised.exception.status)
        self.assertNotIn(SELECTED_PASSWORD, repr(raised.exception))
        self.assertNotIn("Fails.", str(raised.exception))
        self.assertIsNone(raised.exception.__context__)

    def test_successful_login_requires_a_valid_sid_cookie(self):
        transport = DeterministicTransport([response("Ok.")])
        adapter = QbittorrentAdapter(BASE_URL, transport, interactive=False)

        with self.assertRaises(QbittorrentAuthenticationError) as raised:
            adapter.authenticate(password=SELECTED_PASSWORD)

        self.assertEqual(len(transport.requests), 1)
        self.assertIsNone(adapter.session)
        self.assertIsNone(raised.exception.__context__)

    def test_malformed_preferences_are_invalid_typed_and_redacted(self):
        transport = DeterministicTransport(
            [
                response("Ok.", headers={"Set-Cookie": "SID=initial-session; Path=/"}),
                response(f'{{"save_path":"{SELECTED_PASSWORD}"'),
            ]
        )
        adapter = QbittorrentAdapter(BASE_URL, transport, env={"QBT_PASSWORD": CURRENT_PASSWORD})

        with self.assertRaises(QbittorrentSchemaError) as raised:
            adapter.configure()

        self.assertIsInstance(raised.exception, InvalidInputError)
        self.assertNotIn(SELECTED_PASSWORD, str(raised.exception))
        self.assertIsNone(raised.exception.__context__)

    def test_failed_selected_password_verification_returns_no_environment_update(self):
        transport = DeterministicTransport(
            [
                response("Ok.", headers={"Set-Cookie": "SID=initial-session; Path=/"}),
                response({"save_path": "/downloads"}),
                response({"sonarr": {"savePath": "/downloads/sonarr"}, "radarr": {"savePath": "/downloads/radarr"}}),
                response(""),
                response("Fails.", status=403),
            ]
        )
        adapter = QbittorrentAdapter(BASE_URL, transport, env={"QBT_PASSWORD": CURRENT_PASSWORD}, selected_password=SELECTED_PASSWORD)

        result = adapter.configure()

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.checkpoints[0].code, "qbittorrent-password-verification")
        self.assertIsInstance(result.error, QbittorrentPasswordVerificationError)
        self.assertEqual(result.exit_code, 4)
        self.assertEqual(dict(result.environment_update), {})
        self.assertNotIn(SELECTED_PASSWORD, repr(result))

    def test_category_drift_changes_only_managed_category_save_path_and_default_path(self):
        transport = DeterministicTransport(
            [
                response("Ok.", headers={"Set-Cookie": "SID=initial-session; Path=/"}),
                response({"save_path": "/old-downloads", "listen_port": 16881, "max_active": 9}),
                response(
                    {
                        "sonarr": {"savePath": "/old-downloads/series", "downloadPath": "keep-me"},
                        "radarr": {"savePath": "/downloads/radarr", "downloadPath": "keep-radarr"},
                        "unrelated": {"savePath": "/keep/unrelated", "downloadPath": "keep-this"},
                    }
                ),
                response(""),
                response(""),
                response("Ok.", headers={"Set-Cookie": "SID=selected-session; Path=/"}),
            ]
        )
        adapter = QbittorrentAdapter(BASE_URL, transport, env={"QBT_PASSWORD": CURRENT_PASSWORD})

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            json.loads(transport.requests[3][2]["form"]["json"]),
            {"web_ui_password": CURRENT_PASSWORD, "save_path": "/downloads"},
        )
        self.assertEqual(
            transport.requests[4][2]["form"],
            {"category": "sonarr", "savePath": "/downloads/sonarr"},
        )
        self.assertNotIn("unrelated", repr(transport.requests[4]))
        self.assertNotIn("listen_port", json.loads(transport.requests[3][2]["form"]["json"]))

    def test_category_failure_after_mutation_is_sanitized_partial_without_env_handoff(self):
        transport = DeterministicTransport(
            [
                response("Ok.", headers={"Set-Cookie": "SID=initial-session; Path=/"}),
                response({"save_path": "/old-downloads"}),
                response({"sonarr": {"savePath": "/old-downloads/series"}}),
                response(""),
                response("category-upstream-secret", status=500),
            ]
        )
        adapter = QbittorrentAdapter(BASE_URL, transport, env={"QBT_PASSWORD": CURRENT_PASSWORD})

        result = adapter.configure()

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.exit_code, 4)
        self.assertEqual(result.checkpoints[0].code, "qbittorrent-category-reconciliation")
        self.assertIsInstance(result.error, QbittorrentCategoryReconciliationError)
        self.assertEqual(dict(result.environment_update), {})
        self.assertEqual(
            [request[0:2] for request in transport.requests],
            [
                ("POST", f"{BASE_URL}/api/v2/auth/login"),
                ("GET", f"{BASE_URL}/api/v2/app/preferences"),
                ("GET", f"{BASE_URL}/api/v2/torrents/categories"),
                ("POST", f"{BASE_URL}/api/v2/app/setPreferences"),
                ("POST", f"{BASE_URL}/api/v2/torrents/editCategory"),
            ],
        )
        self.assertNotIn("category-upstream-secret", repr(result))
        self.assertIsNone(result.error.__context__)

    def test_missing_categories_are_created_without_touching_unrelated_category(self):
        transport = DeterministicTransport(
            [
                response("Ok.", headers={"Set-Cookie": "SID=initial-session; Path=/"}),
                response({"save_path": "/downloads"}),
                response({"unrelated": {"savePath": "/keep/unrelated"}}),
                response(""),
                response(""),
                response(""),
                response("Ok.", headers={"Set-Cookie": "SID=selected-session; Path=/"}),
            ]
        )
        adapter = QbittorrentAdapter(BASE_URL, transport, env={"QBT_PASSWORD": CURRENT_PASSWORD})

        result = adapter.configure()

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            [request[2]["form"] for request in transport.requests[4:6]],
            [
                {"category": "sonarr", "savePath": "/downloads/sonarr"},
                {"category": "radarr", "savePath": "/downloads/radarr"},
            ],
        )
        self.assertNotIn("unrelated", repr(transport.requests[4][2]["form"]))

    def test_dry_run_makes_no_http_request_or_environment_update(self):
        transport = DeterministicTransport([])
        adapter = QbittorrentAdapter(BASE_URL, transport, env={"QBT_PASSWORD": CURRENT_PASSWORD})

        result = adapter.configure(dry_run=True)

        self.assertTrue(result.dry_run)
        self.assertEqual(result.status, "dry-run")
        self.assertEqual(dict(result.environment_update), {})
        self.assertEqual(transport.requests, [])


if __name__ == "__main__":
    unittest.main()
