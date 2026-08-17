"""Tests for GET /cron/logs current/history contract and report parsers."""
import json
import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch

import config
import routes.reports as reports


class _CaptureHandler:
    def __init__(self, path="/cron/logs"):
        self.path = path
        self.headers = {}
        self.status = None
        self.wfile = BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers[name] = value

    def end_headers(self):
        pass


class GroupCurrentHistoryTests(unittest.TestCase):
    def test_empty_returns_none_and_empty_history(self):
        self.assertEqual(reports._group_current_history([]), (None, []))

    def test_single_run_is_current(self):
        runs = [{"status": "ok", "detail": "first"}]
        current, history = reports._group_current_history(runs)
        self.assertEqual(current, runs[0])
        self.assertEqual(history, [])

    def test_last_run_is_current_and_history_oldest_first(self):
        runs = [
            {"status": "fatal", "detail": "old"},
            {"status": "ok", "detail": "mid"},
            {"status": "ok", "detail": "newest"},
        ]
        current, history = reports._group_current_history(runs)
        self.assertEqual(current["detail"], "newest")
        self.assertEqual([r["detail"] for r in history], ["old", "mid"])

    def test_equal_timestamps_keep_source_order_in_history(self):
        runs = [
            {"status": "fatal", "timestamp": "2026-07-12T10:00:00Z", "detail": "a"},
            {"status": "ok", "timestamp": "2026-07-12T10:00:00Z", "detail": "b"},
            {"status": "warn", "timestamp": "2026-07-12T10:00:00Z", "detail": "c"},
        ]
        current, history = reports._group_current_history(runs)
        self.assertEqual(current["detail"], "c")
        self.assertEqual([r["detail"] for r in history], ["a", "b"])


class MissingRunTests(unittest.TestCase):
    def test_missing_run_carries_status_and_detail(self):
        run = reports._missing_run("No log file yet")
        self.assertEqual(run["status"], "missing")
        self.assertEqual(run["detail"], "No log file yet")


class ParserTests(unittest.TestCase):
    def test_ndjson_statuses(self):
        lines = [
            json.dumps({"timestamp": "2026-07-12T10:00:00Z", "exitCode": 1, "fatal": "boom"}),
            json.dumps({"timestamp": "2026-07-12T11:00:00Z", "exitCode": 0, "summary": {"applied": 2, "evaluated": 2}}),
            json.dumps({"timestamp": "2026-07-12T12:00:00Z", "exitCode": 0, "summary": {"applied": 0, "evaluated": 0}}),
        ]
        runs = reports._summarize_watchdog_lines(lines)
        self.assertEqual([r["status"] for r in runs], ["fatal", "applied", "ok"])

    def test_ndjson_malformed_line_is_unparsed_and_last(self):
        lines = [
            json.dumps({"timestamp": "2026-07-12T10:00:00Z", "exitCode": 0, "summary": {"applied": 0, "evaluated": 0}}),
            "this is not json {{{",
        ]
        runs = reports._summarize_watchdog_lines(lines)
        self.assertEqual(len(runs), 2)
        current, history = reports._group_current_history(runs)
        self.assertEqual(current["status"], "unparsed")
        self.assertEqual(history[0]["status"], "ok")

    def test_text_job_fatal_and_history_order(self):
        text = [
            "====",
            "timestamp=2026-07-09T10:00:00Z job=j returncode=1",
            "--- stdout ---",
            "some failing output",
        ]
        runs = reports._summarize_text_job_lines(text)
        self.assertEqual(runs[-1]["status"], "fatal")

    def test_successful_weekly_block_is_ok_with_phase_completed_detail(self):
        text = [
            "====",
            "timestamp=2026-08-16T14:35:54Z job=weekly-validate-final returncode=0",
            "--- stdout ---",
            "19. D: free space >= 75 GiB: PASS",
            "Blockers:",
            "- (none)",
            "Manual steps required:",
            "- (none)",
            "Phase completed: 6 (Tasks 19-20)",
        ]
        runs = reports._summarize_text_job_lines(text)
        current, history = reports._group_current_history(runs)
        self.assertEqual(current["status"], "ok")
        self.assertEqual(current["detail"], "Phase completed: 6 (Tasks 19-20)")

    def test_retains_up_to_50_runs(self):
        lines = []
        for i in range(60):
            lines.append(json.dumps({"timestamp": f"2026-07-12T{i:02d}:00:00Z", "exitCode": 0, "summary": {}}))
        runs = reports._summarize_watchdog_lines(lines)
        self.assertEqual(len(runs), 50)


class HandleCronLogsTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self._tmp_path = os.path.join(self._dir.name, "tmp")
        os.makedirs(self._tmp_path, exist_ok=True)

    def _patch(self):
        return patch.multiple(
            config,
            TMP_DIR=self._tmp_path,
            CRON_LOG_FILES=(
                {
                    "id": "watchdog",
                    "title": "Media Download Watchdog",
                    "file": "watch-downloads.log",
                    "format": "ndjson",
                    "schedule": "every 15m",
                },
                {
                    "id": "stale-metadata",
                    "title": "Stale Metadata Cleanup",
                    "file": "stale-metadata-cleanup.log",
                    "format": "text",
                    "schedule": "every 30m",
                },
            ),
        )

    def _get(self, handler):
        with self._patch():
            reports.handle_cron_logs(handler)
        return json.loads(handler.wfile.getvalue().decode("utf-8"))

    def test_absent_log_is_missing_current(self):
        handler = _CaptureHandler()
        body = self._get(handler)
        entries = {e["id"]: e for e in body["logs"]}
        self.assertEqual(entries["watchdog"]["current"], {"status": "missing", "detail": "No log file yet"})
        self.assertEqual(entries["watchdog"]["history"], [])
        self.assertEqual(entries["watchdog"]["exists"], False)

    def test_empty_log_is_missing_current(self):
        with open(os.path.join(self._tmp_path, "watch-downloads.log"), "w", encoding="utf-8") as f:
            f.write("")
        handler = _CaptureHandler()
        entries = {e["id"]: e for e in self._get(handler)["logs"]}
        self.assertEqual(entries["watchdog"]["current"], {"status": "missing", "detail": "Log is empty"})

    def test_fatal_then_success_current_and_history(self):
        lines = [
            json.dumps({"timestamp": "2026-07-08T20:30:00Z", "exitCode": 1, "fatal": "old failure"}),
            json.dumps({"timestamp": "2026-07-16T09:00:00Z", "exitCode": 0, "summary": {"applied": 0, "evaluated": 0}}),
        ]
        with open(os.path.join(self._tmp_path, "watch-downloads.log"), "w", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
        handler = _CaptureHandler()
        entries = {e["id"]: e for e in self._get(handler)["logs"]}
        self.assertEqual(entries["watchdog"]["current"]["status"], "ok")
        self.assertEqual(len(entries["watchdog"]["history"]), 1)
        self.assertEqual(entries["watchdog"]["history"][0]["status"], "fatal")

    def test_no_recent_runs_when_scanned_lines_produce_nothing(self):
        # Text-format log with no "====" run separator yields no parsed run.
        with open(os.path.join(self._tmp_path, "stale-metadata-cleanup.log"), "w", encoding="utf-8") as f:
            f.write("random launcher chatter without a run block\n")
        handler = _CaptureHandler()
        entries = {e["id"]: e for e in self._get(handler)["logs"]}
        self.assertEqual(entries["stale-metadata"]["current"]["status"], "missing")
        self.assertEqual(entries["stale-metadata"]["current"]["detail"], "No recent runs")

    def test_wanted_id_filters_logs(self):
        handler = _CaptureHandler(path="/cron/logs?id=stale-metadata")
        with self._patch():
            reports.handle_cron_logs(handler)
        body = json.loads(handler.wfile.getvalue().decode("utf-8"))
        self.assertEqual([e["id"] for e in body["logs"]], ["stale-metadata"])


class ScheduleMetadataTests(unittest.TestCase):
    def test_intended_schedules_are_locked(self):
        by_id = {spec["id"]: spec for spec in config.CRON_LOG_FILES}
        self.assertEqual(by_id["watchdog"]["schedule"], "every 15m")
        self.assertEqual(by_id["stale-metadata"]["schedule"], "every 30m")


if __name__ == "__main__":
    unittest.main()