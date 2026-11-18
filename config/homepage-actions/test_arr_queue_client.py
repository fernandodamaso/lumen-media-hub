#!/usr/bin/env python3
"""Tests for data-safe Sonarr queue mutations."""

import json
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import clients.arr as arr_client
from verified_cleanup import mapping_for_torrent

HASH = "a" * 40
OTHER_HASH = "b" * 40


def _pages_getter(pages):
    def _get(base, api_key, path):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
        return pages[int(query["page"][0])]

    return _get


class _CaptureRequestHandler(BaseHTTPRequestHandler):
    request_data = None
    request_ready = threading.Event()

    def do_DELETE(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        type(self).request_data = {
            "command": self.command,
            "path": self.path,
            "body": json.loads(body.decode("utf-8")),
        }
        type(self).request_ready.set()
        self.send_response(204)
        self.end_headers()

    def log_message(self, format, *args):
        pass


class SonarrQueueClientTestCase(unittest.TestCase):
    def setUp(self):
        _CaptureRequestHandler.request_data = None
        _CaptureRequestHandler.request_ready.clear()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _CaptureRequestHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_ignore_queue_items_uses_safe_sonarr_bulk_delete_contract(self):
        base = f"http://127.0.0.1:{self.server.server_address[1]}"
        with mock.patch.object(arr_client.settings, "SONARR_URL", base), mock.patch.object(
            arr_client.settings, "SONARR_API_KEY", "test-sonarr-key"
        ):
            arr_client.ignore_sonarr_queue_items([22, 11, 22])

        self.assertTrue(_CaptureRequestHandler.request_ready.wait(timeout=5))
        request = _CaptureRequestHandler.request_data
        parsed = urllib.parse.urlparse(request["path"])
        self.assertEqual(request["command"], "DELETE")
        self.assertEqual(parsed.path, "/api/v3/queue/bulk")
        self.assertEqual(
            urllib.parse.parse_qs(parsed.query),
            {
                "removeFromClient": ["false"],
                "blocklist": ["false"],
                "skipRedownload": ["false"],
                "changeCategory": ["false"],
            },
        )
        self.assertEqual(request["body"], {"ids": [11, 22]})

    def test_ignore_queue_items_rejects_invalid_ids_without_request(self):
        invalid_queue_ids = ([True], [False], ["1"], [0], [-1], [])

        for queue_ids in invalid_queue_ids:
            with self.subTest(queue_ids=queue_ids):
                with self.assertRaises(ValueError):
                    arr_client.ignore_sonarr_queue_items(queue_ids)

        self.assertFalse(_CaptureRequestHandler.request_ready.is_set())
        self.assertIsNone(_CaptureRequestHandler.request_data)

    def test_fetch_arr_history_all_reads_every_page_and_marks_complete(self):
        pages = [
            {"records": [{"id": 1}], "totalRecords": 3},
            {"records": [{"id": 2}, {"id": 3}], "totalRecords": 3},
        ]
        with mock.patch.object(arr_client, "fetch_arr_history", side_effect=pages) as fetch:
            result = arr_client.fetch_arr_history_all("http://sonarr", "key", "seriesIds", 42, page_size=2)

        self.assertEqual(result, {"records": [{"id": 1}, {"id": 2}, {"id": 3}], "totalRecords": 3, "complete": True})
        self.assertEqual(
            [call.kwargs for call in fetch.call_args_list],
            [{"page": 1, "page_size": 2}, {"page": 2, "page_size": 2}],
        )

    def test_fetch_arr_history_all_fails_closed_when_snapshot_changes_or_stalls(self):
        with mock.patch.object(
            arr_client,
            "fetch_arr_history",
            side_effect=[
                {"records": [{"id": 1}], "totalRecords": 2},
                {"records": [{"id": 2}], "totalRecords": 3},
            ],
        ):
            with self.assertRaisesRegex(ValueError, "changed"):
                arr_client.fetch_arr_history_all("http://sonarr", "key", "seriesIds", 42, page_size=1)

        with mock.patch.object(
            arr_client,
            "fetch_arr_history",
            return_value={"records": [], "totalRecords": 1},
        ):
            with self.assertRaisesRegex(ValueError, "incomplete"):
                arr_client.fetch_arr_history_all("http://sonarr", "key", "seriesIds", 42, page_size=1)


class DownloadHistoryTransportTestCase(unittest.TestCase):
    def test_one_page_transport_preserves_download_id_case(self):
        for download_id in (HASH.upper(), HASH):
            with self.subTest(download_id=download_id), mock.patch.object(
                arr_client, "_arr_get", return_value={"records": [], "totalRecords": 0}
            ) as get:
                payload = arr_client.fetch_arr_history_for_download(
                    "http://sonarr", "key", download_id
                )

            self.assertEqual(payload, {"records": [], "totalRecords": 0})
            path = get.call_args.args[2]
            self.assertIn(f"downloadId={download_id}", path)
            self.assertIn("page=1", path)
            self.assertIn("pageSize=1000", path)

    def test_complete_snapshot_aggregates_pages_in_order(self):
        pages = {
            1: {"records": [{"id": 1}], "totalRecords": 2},
            2: {"records": [{"id": 2}], "totalRecords": 2},
        }
        with mock.patch.object(arr_client, "_arr_get", side_effect=_pages_getter(pages)) as get:
            result = arr_client.fetch_arr_history_for_download_all(
                "http://sonarr", "key", HASH, page_size=1
            )

        self.assertEqual(
            result,
            {"records": [{"id": 1}, {"id": 2}], "totalRecords": 2, "complete": True},
        )
        self.assertEqual(get.call_count, 2)
        for call in get.call_args_list:
            self.assertIn(f"downloadId={HASH}", call.args[2])

    def test_complete_snapshot_rejects_changing_total(self):
        pages = {
            1: {"records": [{"id": 1}], "totalRecords": 2},
            2: {"records": [{"id": 2}], "totalRecords": 3},
        }
        with mock.patch.object(arr_client, "_arr_get", side_effect=_pages_getter(pages)):
            with self.assertRaisesRegex(ValueError, "changed"):
                arr_client.fetch_arr_history_for_download_all(
                    "http://sonarr", "key", HASH, page_size=1
                )

    def test_complete_snapshot_rejects_duplicate_record_ids(self):
        pages = {
            1: {"records": [{"id": 1}], "totalRecords": 2},
            2: {"records": [{"id": 1}], "totalRecords": 2},
        }
        with mock.patch.object(arr_client, "_arr_get", side_effect=_pages_getter(pages)):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                arr_client.fetch_arr_history_for_download_all(
                    "http://sonarr", "key", HASH, page_size=1
                )

    def test_complete_snapshot_rejects_malformed_records(self):
        cases = (
            {1: {"records": [{"id": "not-an-int"}], "totalRecords": 1}},
            {1: {"records": ["not-a-record"], "totalRecords": 1}},
            {1: {"records": [{"downloadId": HASH}], "totalRecords": 1}},
            {1: {"totalRecords": 1}},
        )
        for pages in cases:
            with self.subTest(pages=pages), mock.patch.object(
                arr_client, "_arr_get", side_effect=_pages_getter(pages)
            ):
                with self.assertRaises(ValueError):
                    arr_client.fetch_arr_history_for_download_all(
                        "http://sonarr", "key", HASH, page_size=1
                    )

    def test_complete_snapshot_rejects_empty_page_before_total_is_met(self):
        pages = {1: {"records": [], "totalRecords": 1}}
        with mock.patch.object(arr_client, "_arr_get", side_effect=_pages_getter(pages)):
            with self.assertRaisesRegex(ValueError, "incomplete"):
                arr_client.fetch_arr_history_for_download_all(
                    "http://sonarr", "key", HASH, page_size=1
                )

    def test_complete_snapshot_empty_history_is_complete(self):
        pages = {1: {"records": [], "totalRecords": 0}}
        with mock.patch.object(arr_client, "_arr_get", side_effect=_pages_getter(pages)) as get:
            result = arr_client.fetch_arr_history_for_download_all(
                "http://sonarr", "key", HASH, page_size=1
            )

        self.assertEqual(result, {"records": [], "totalRecords": 0, "complete": True})
        self.assertEqual(get.call_count, 1)

    def test_both_case_variant_queries_contribute_matching_evidence(self):
        def fake_get(base, api_key, path):
            if f"downloadId={HASH.upper()}" in path:
                return {
                    "records": [
                        {
                            "id": 1,
                            "downloadId": OTHER_HASH,
                            "eventType": "downloadFolderImported",
                            "seriesId": 7,
                        }
                    ],
                    "totalRecords": 1,
                }
            return {
                "records": [
                    {
                        "id": 2,
                        "downloadId": HASH,
                        "eventType": "downloadFolderImported",
                        "seriesId": 42,
                    }
                ],
                "totalRecords": 1,
            }

        class TransportArr:
            def __init__(self):
                self.queries = []

            def configured_services(self):
                return ("sonarr", "radarr")

            def history_for_download(self, service, download_id):
                self.queries.append((service, download_id))
                return arr_client.fetch_arr_history_for_download_all(
                    "http://sonarr", "key", download_id
                )

        arr = TransportArr()
        with mock.patch.object(arr_client, "_arr_get", side_effect=fake_get):
            mapping = mapping_for_torrent(arr, HASH)

        self.assertEqual(mapping, {"service": "sonarr", "id": 42})
        self.assertIn(("sonarr", HASH.upper()), arr.queries)
        self.assertIn(("sonarr", HASH), arr.queries)


if __name__ == "__main__":
    unittest.main()
