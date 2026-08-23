import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import config
import queue_hygiene
from server import ActionsHandler


TOKEN = "task-five-token"
ORIGIN = "http://localhost:3000"


class QueueHygieneApiTests(unittest.TestCase):
    def setUp(self):
        self.old_token = config.ACTIONS_TOKEN
        self.old_origins = config.CORS_ORIGINS
        config.ACTIONS_TOKEN = TOKEN
        config.CORS_ORIGINS = [ORIGIN]
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ActionsHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.restore)

    def restore(self):
        config.ACTIONS_TOKEN = self.old_token
        config.CORS_ORIGINS = self.old_origins

    def request(self, method, path, body=None, token=None, origin=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        headers = {}
        if token is not None:
            headers["X-Actions-Token"] = token
        if origin is not None:
            headers["Origin"] = origin
        if body is not None or raw is not None:
            headers["Content-Type"] = "application/json"
        payload = raw if raw is not None else (json.dumps(body) if body is not None else None)
        conn.request(method, path, payload, headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, json.loads(data.decode("utf-8")) if data else None

    def test_get_is_read_only(self):
        with patch("routes.queue_hygiene._read_state", return_value={"mode": "observe"}):
            status, body = self.request("GET", "/automation/queue-hygiene")
        self.assertEqual(status, 200)
        self.assertEqual(body["mode"], "observe")

    def test_get_normalizes_missing_state(self):
        with patch("routes.queue_hygiene._read_state", return_value={}):
            status, body = self.request("GET", "/automation/queue-hygiene")
        self.assertEqual(status, 200)
        self.assertEqual(body, {
            "ok": True,
            "mode": "observe",
            "circuitOpen": False,
            "eligibleCount": 0,
            "blockedCount": 0,
            "eligibleItems": [],
            "blockedItems": [],
            "lastCycleAt": None,
            "lastCleanup": None,
            "verification": None,
        })

    def test_post_requires_token_and_origin(self):
        status, body = self.request("POST", "/automation/queue-hygiene/run", {"mode": "observe"})
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "Unauthorized")

    def test_post_rejects_invalid_body(self):
        for payload in ({}, {"mode": "invalid"}, {"mode": "observe", "extra": True}):
            status, _body = self.request("POST", "/automation/queue-hygiene/run", payload, TOKEN, ORIGIN)
            self.assertEqual(status, 400)
        status, _body = self.request("POST", "/automation/queue-hygiene/run", raw="not-json", token=TOKEN, origin=ORIGIN)
        self.assertEqual(status, 400)

    def test_post_runs_observe_cycle(self):
        with patch(
            "routes.queue_hygiene.run_queue_hygiene_cycle",
            return_value={"status": "observed", "mode": "observe"},
        ) as run_cycle:
            status, body = self.request("POST", "/automation/queue-hygiene/run", {"mode": "observe"}, TOKEN, ORIGIN)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        run_cycle.assert_called_once_with(mode="observe")

    def test_reset_requires_exact_confirmation_and_preserves_audit(self):
        for payload in ({}, {"confirm": "wrong"}, {"confirm": "reset-circuit", "extra": True}):
            status, _body = self.request("POST", "/automation/queue-hygiene/reset", payload, TOKEN, ORIGIN)
            self.assertEqual(status, 400)
        state = {
            "mode": "auto",
            "circuitOpen": True,
            "error": "paused",
            "lastCleanup": {"at": "2026-08-23T12:00:00Z"},
        }
        with patch("routes.queue_hygiene._read_state", return_value=state), patch(
            "routes.queue_hygiene._write_state"
        ) as write_state:
            status, body = self.request(
                "POST", "/automation/queue-hygiene/reset", {"confirm": "reset-circuit"}, TOKEN, ORIGIN
            )
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        write_state.assert_called_once()
        self.assertFalse(write_state.call_args.args[0]["circuitOpen"])
        self.assertNotIn("error", write_state.call_args.args[0])
        self.assertEqual(write_state.call_args.args[0]["lastCleanup"], state["lastCleanup"])


class QueueHygieneSchedulerTests(unittest.TestCase):
    def test_scheduler_loop_runs_startup_then_intervals(self):
        calls = []
        waits = iter([False, True])

        def wait(_event, timeout):
            calls.append(timeout)
            return next(waits)

        queue_hygiene._queue_hygiene_scheduler_loop(3, threading.Event(), lambda: calls.append("run"), wait)
        self.assertEqual(calls, ["run", 3, "run", 3])

    def test_start_is_idempotent_and_stop_joins(self):
        with patch.object(queue_hygiene, "run_queue_hygiene_cycle") as run_cycle:
            self.assertTrue(queue_hygiene.start_queue_hygiene_scheduler(0.01))
            self.assertFalse(queue_hygiene.start_queue_hygiene_scheduler(0.01))
            self.assertTrue(queue_hygiene.stop_queue_hygiene_scheduler())
            self.assertTrue(run_cycle.called)


if __name__ == "__main__":
    unittest.main()
