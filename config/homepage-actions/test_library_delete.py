#!/usr/bin/env python3
"""Tests for library deletion matching, preview store, and HTTP routes."""

import http.client
import json
import shutil
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

import config
import library_delete as ld
from library_delete import (
    MatchError,
    PreviewStore,
    UpstreamError,
    _history_download_ids,
    _intersect_hashes,
    execute_library_delete,
    resolve_library_target,
)
from server import ActionsHandler

TOKEN = "test-actions-token"
ALLOWED_ORIGIN = "http://localhost:3000"
ITEM_ID = "jf-movie-1"
HASH_A = "a" * 40
HASH_B = "b" * 40
HASH_C = "c" * 40


HASH40 = "d" * 40
HASH64 = "e" * 64


class LibraryDeleteUnitTests(unittest.TestCase):
    def test_movie_exact_tmdb_match(self):
        with mock.patch("library_delete._jellyfin_user_id_for_queries", return_value="user-1"), mock.patch(
            "library_delete.jellyfin_get"
        ) as mock_get, mock.patch(
            "library_delete.find_radarr_movies_by_tmdb", return_value=[{"id": 7, "tmdbId": 123}]
        ), mock.patch(
            "library_delete.fetch_arr_history",
            return_value={"totalRecords": 1, "records": [{"downloadId": HASH_A}]},
        ), mock.patch(
            "library_delete._current_qbit_hashes", return_value={HASH_A}
        ):
            mock_get.return_value = {
                "Type": "Movie",
                "Name": "Dune",
                "ProviderIds": {"Tmdb": "123"},
            }
            target = resolve_library_target(ITEM_ID)
        self.assertEqual(target["manager"], "Radarr")
        self.assertEqual(target["arr_id"], 7)
        self.assertEqual(target["hashes"], (HASH_A,))

    def test_movie_zero_matches_raises(self):
        with mock.patch("library_delete._jellyfin_user_id_for_queries", return_value="user-1"), mock.patch(
            "library_delete.jellyfin_get"
        ) as mock_get, mock.patch(
            "library_delete.find_radarr_movies_by_tmdb", return_value=[]
        ):
            mock_get.return_value = {
                "Type": "Movie",
                "Name": "Dune",
                "ProviderIds": {"Tmdb": "123"},
            }
            with self.assertRaises(MatchError):
                resolve_library_target(ITEM_ID)

    def test_movie_two_matches_raises(self):
        with mock.patch("library_delete._jellyfin_user_id_for_queries", return_value="user-1"), mock.patch(
            "library_delete.jellyfin_get"
        ) as mock_get, mock.patch(
            "library_delete.find_radarr_movies_by_tmdb",
            return_value=[{"id": 1}, {"id": 2}],
        ):
            mock_get.return_value = {
                "Type": "Movie",
                "Name": "Dune",
                "ProviderIds": {"Tmdb": "123"},
            }
            with self.assertRaises(MatchError):
                resolve_library_target(ITEM_ID)

    def test_series_tvdb_and_tmdb_agree(self):
        with mock.patch("library_delete._jellyfin_user_id_for_queries", return_value="user-1"), mock.patch(
            "library_delete.jellyfin_get"
        ) as mock_get, mock.patch(
            "library_delete.find_sonarr_series_by_tvdb", return_value=[{"id": 9, "tvdbId": 55}]
        ), mock.patch(
            "library_delete.find_sonarr_series_by_tmdb", return_value=[{"id": 9, "tmdbId": 66}]
        ), mock.patch(
            "library_delete._series_episode_count", return_value=10
        ), mock.patch(
            "library_delete.fetch_arr_history",
            return_value={"totalRecords": 0, "records": []},
        ), mock.patch("library_delete._current_qbit_hashes", return_value=set()):
            mock_get.return_value = {
                "Type": "Series",
                "Name": "Show",
                "ProviderIds": {"Tvdb": "55", "Tmdb": "66"},
            }
            target = resolve_library_target("jf-series-1")
        self.assertEqual(target["manager"], "Sonarr")
        self.assertEqual(target["arr_id"], 9)
        self.assertEqual(target["episode_count"], 10)

    def test_series_tvdb_tmdb_disagree_raises(self):
        with mock.patch("library_delete._jellyfin_user_id_for_queries", return_value="user-1"), mock.patch(
            "library_delete.jellyfin_get"
        ) as mock_get, mock.patch(
            "library_delete.find_sonarr_series_by_tvdb", return_value=[{"id": 1}]
        ), mock.patch(
            "library_delete.find_sonarr_series_by_tmdb", return_value=[{"id": 2}]
        ):
            mock_get.return_value = {
                "Type": "Series",
                "Name": "Show",
                "ProviderIds": {"Tvdb": "55", "Tmdb": "66"},
            }
            with self.assertRaises(MatchError):
                resolve_library_target("jf-series-1")

    def test_title_not_used_for_matching(self):
        with mock.patch("library_delete._jellyfin_user_id_for_queries", return_value="user-1"), mock.patch(
            "library_delete.jellyfin_get"
        ) as mock_get, mock.patch(
            "library_delete.find_radarr_movies_by_tmdb", return_value=[]
        ):
            mock_get.return_value = {
                "Type": "Movie",
                "Name": "Same Title",
                "ProviderIds": {},
            }
            with self.assertRaises(MatchError):
                resolve_library_target(ITEM_ID)

    def test_history_total_over_cap_raises(self):
        with self.assertRaises(MatchError):
            _history_download_ids({"totalRecords": 1001, "records": []})

    def test_history_malformed_download_ids_ignored(self):
        ids = _history_download_ids(
            {
                "totalRecords": 2,
                "records": [
                    {"downloadId": "bad"},
                    {"downloadId": HASH40},
                    {"downloadId": HASH64},
                ],
            }
        )
        self.assertEqual(ids, [HASH40.lower(), HASH64.lower()])

    def test_qbit_exception_is_upstream_error(self):
        with mock.patch("library_delete.qbt_login", side_effect=RuntimeError("down")):
            with self.assertRaises(UpstreamError):
                ld._current_qbit_hashes()

    def test_intersect_hashes(self):
        self.assertEqual(
            _intersect_hashes([HASH_A, HASH_B], {HASH_B, HASH_C}),
            (HASH_B,),
        )

    def test_preview_store_expires(self):
        clock = {"now": 1000.0}

        def monotonic():
            return clock["now"]

        store = PreviewStore(monotonic=monotonic, ttl=120)
        target = {
            "jellyfin_id": ITEM_ID,
            "kind": "movie",
            "title": "Dune",
            "episode_count": None,
            "manager": "Radarr",
            "arr_id": 1,
            "hashes": (),
        }
        preview = store.put(target)
        self.assertIsNotNone(store.get(preview["previewId"]))
        clock["now"] = 1121.0
        self.assertIsNone(store.get(preview["previewId"]))

    def test_preview_store_drops_oldest_at_limit(self):
        store = PreviewStore(limit=2)
        t = {
            "jellyfin_id": ITEM_ID,
            "kind": "movie",
            "title": "A",
            "episode_count": None,
            "manager": "Radarr",
            "arr_id": 1,
            "hashes": (),
        }
        first = store.put(t)["previewId"]
        second = store.put({**t, "title": "B"})["previewId"]
        third = store.put({**t, "title": "C"})["previewId"]
        self.assertIsNone(store.get(first))
        self.assertIsNotNone(store.get(second))
        self.assertIsNotNone(store.get(third))

    def test_preview_pop_consumes(self):
        store = PreviewStore()
        target = {
            "jellyfin_id": ITEM_ID,
            "kind": "movie",
            "title": "Dune",
            "episode_count": None,
            "manager": "Radarr",
            "arr_id": 1,
            "hashes": (),
        }
        preview_id = store.put(target)["previewId"]
        popped = store.pop(preview_id)
        self.assertEqual(popped["jellyfin_id"], ITEM_ID)
        self.assertIsNone(store.get(preview_id))


class LibraryDeleteHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="library-delete-http-")
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self._old_token = config.ACTIONS_TOKEN
        self._old_cors = config.CORS_ORIGINS
        self._old_jellyfin_key = config.JELLYFIN_API_KEY
        config.ACTIONS_TOKEN = TOKEN
        config.CORS_ORIGINS = [ALLOWED_ORIGIN]
        config.JELLYFIN_API_KEY = "test-jellyfin-key"
        self.addCleanup(self._restore_config)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ActionsHandler)
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _restore_config(self):
        config.ACTIONS_TOKEN = self._old_token
        config.CORS_ORIGINS = self._old_cors
        config.JELLYFIN_API_KEY = self._old_jellyfin_key

    def _request(self, method, path, body=None, token=TOKEN, origin=ALLOWED_ORIGIN):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token is not None:
            headers["X-Actions-Token"] = token
        if origin is not None:
            headers["Origin"] = origin
        payload = json.dumps(body) if body is not None else None
        conn.request(method, path, body=payload, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        parsed = json.loads(data.decode("utf-8")) if data else None
        return resp.status, parsed, dict(resp.getheaders())

    def test_options_includes_delete(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("OPTIONS", "/library/items/x/delete-preview", headers={"Origin": ALLOWED_ORIGIN})
        resp = conn.getresponse()
        methods = resp.getheader("Access-Control-Allow-Methods")
        resp.read()
        conn.close()
        self.assertIn("DELETE", methods)

    def test_preview_requires_auth(self):
        status, body, _headers = self._request(
            "GET", f"/library/items/{ITEM_ID}/delete-preview", token=None
        )
        self.assertEqual(status, 401)
        self.assertEqual(body["error"], "Unauthorized")

    @mock.patch("routes.library.resolve_library_target")
    def test_preview_success_has_no_secrets(self, mock_resolve):
        mock_resolve.return_value = {
            "jellyfin_id": ITEM_ID,
            "kind": "movie",
            "title": "Dune",
            "episode_count": None,
            "manager": "Radarr",
            "arr_id": 99,
            "hashes": (HASH_A,),
        }
        status, body, _headers = self._request(
            "GET", f"/library/items/{ITEM_ID}/delete-preview"
        )
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertIn("previewId", body)
        self.assertEqual(body["torrentCount"], 1)
        raw = json.dumps(body)
        for secret in ("hash", "tmdb", "tvdb", "arr_id", "/data/"):
            self.assertNotIn(secret, raw.lower())

    @mock.patch("routes.library.resolve_library_target", side_effect=MatchError())
    def test_preview_match_failure_409(self, _mock_resolve):
        status, body, _headers = self._request(
            "GET", f"/library/items/{ITEM_ID}/delete-preview"
        )
        self.assertEqual(status, 409)
        self.assertEqual(body["error"], "Unable to prepare deletion")

    @mock.patch("routes.library.resolve_library_target", side_effect=UpstreamError("qbit"))
    def test_preview_qbit_down_502(self, _mock_resolve):
        status, body, _headers = self._request(
            "GET", f"/library/items/{ITEM_ID}/delete-preview"
        )
        self.assertEqual(status, 502)
        self.assertEqual(body["error"], "Unable to prepare deletion")

    def test_delete_missing_preview_400(self):
        status, body, _headers = self._request(
            "DELETE", f"/library/items/{ITEM_ID}"
        )
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "Invalid preview")

    @mock.patch("routes.library.execute_library_delete", side_effect=ld.ConflictError())
    def test_delete_conflict_409(self, _mock_execute):
        status, body, _headers = self._request(
            "DELETE", f"/library/items/{ITEM_ID}?previewId=abc"
        )
        self.assertEqual(status, 409)
        self.assertEqual(body["error"], "Library changed. Request a new preview.")

    @mock.patch("library_delete.jellyfin_post")
    @mock.patch("routes.discover.invalidate_discover_library_caches")
    @mock.patch("library_delete.delete_radarr_movie")
    @mock.patch("library_delete._delete_qbit_hashes")
    @mock.patch("library_delete.resolve_library_target")
    def test_delete_order_qbit_before_arr(
        self, mock_resolve, mock_qbit, mock_arr_delete, _mock_discover, _mock_scan
    ):
        store = PreviewStore()
        target = {
            "jellyfin_id": ITEM_ID,
            "kind": "movie",
            "title": "Dune",
            "episode_count": None,
            "manager": "Radarr",
            "arr_id": 7,
            "hashes": (HASH_A,),
        }
        preview_id = store.put(target)["previewId"]
        mock_resolve.return_value = dict(target)
        calls = []

        def track_qbit(_hashes):
            calls.append("qbit")

        def track_arr(_arr_id):
            calls.append("arr")

        mock_qbit.side_effect = track_qbit
        mock_arr_delete.side_effect = track_arr
        with mock.patch("library_delete.PREVIEW_STORE", store):
            status, body, _headers = self._request(
                "DELETE", f"/library/items/{ITEM_ID}?previewId={preview_id}"
            )
        self.assertEqual(status, 200)
        self.assertTrue(body["removed"])
        self.assertEqual(calls, ["qbit", "arr"])
        self.assertEqual(
            body["steps"],
            {"torrents": "ok", "library": "ok", "jellyfin": "ok"},
        )

    @mock.patch("library_delete.delete_radarr_movie")
    @mock.patch("library_delete._delete_qbit_hashes", side_effect=UpstreamError("qbit"))
    @mock.patch("library_delete.resolve_library_target")
    def test_delete_qbit_failure_skips_arr(
        self, mock_resolve, _mock_qbit, mock_arr_delete
    ):
        store = PreviewStore()
        target = {
            "jellyfin_id": ITEM_ID,
            "kind": "movie",
            "title": "Dune",
            "episode_count": None,
            "manager": "Radarr",
            "arr_id": 7,
            "hashes": (HASH_A,),
        }
        preview_id = store.put(target)["previewId"]
        mock_resolve.return_value = dict(target)
        with mock.patch("library_delete.PREVIEW_STORE", store):
            status, body, _headers = self._request(
                "DELETE", f"/library/items/{ITEM_ID}?previewId={preview_id}"
            )
        self.assertEqual(status, 502)
        mock_arr_delete.assert_not_called()
        self.assertEqual(
            body["steps"],
            {"torrents": "failed", "library": "skipped", "jellyfin": "skipped"},
        )

    @mock.patch("library_delete.jellyfin_post", side_effect=RuntimeError("scan fail"))
    @mock.patch("routes.discover.invalidate_discover_library_caches")
    @mock.patch("library_delete.delete_radarr_movie")
    @mock.patch("library_delete._delete_qbit_hashes")
    @mock.patch("library_delete.resolve_library_target")
    def test_delete_scan_failure_warning(
        self, mock_resolve, _mock_qbit, _mock_arr, _mock_discover, _mock_scan
    ):
        store = PreviewStore()
        target = {
            "jellyfin_id": ITEM_ID,
            "kind": "movie",
            "title": "Dune",
            "episode_count": None,
            "manager": "Radarr",
            "arr_id": 7,
            "hashes": (),
        }
        preview_id = store.put(target)["previewId"]
        mock_resolve.return_value = dict(target)
        with mock.patch("library_delete.PREVIEW_STORE", store):
            status, body, _headers = self._request(
                "DELETE", f"/library/items/{ITEM_ID}?previewId={preview_id}"
            )
        self.assertEqual(status, 200)
        self.assertEqual(body["warning"], "Removed; Jellyfin refresh pending")
        self.assertEqual(body["steps"]["jellyfin"], "pending")
        self.assertEqual(body["steps"]["library"], "ok")

    @mock.patch("library_delete.delete_radarr_movie", side_effect=RuntimeError("/data/media secret"))
    @mock.patch("library_delete._delete_qbit_hashes")
    @mock.patch("library_delete.resolve_library_target")
    def test_delete_partial_no_upstream_leak(
        self, mock_resolve, _mock_qbit, _mock_arr
    ):
        store = PreviewStore()
        target = {
            "jellyfin_id": ITEM_ID,
            "kind": "movie",
            "title": "Dune",
            "episode_count": None,
            "manager": "Radarr",
            "arr_id": 7,
            "hashes": (HASH_A,),
        }
        preview_id = store.put(target)["previewId"]
        mock_resolve.return_value = dict(target)
        with mock.patch("library_delete.PREVIEW_STORE", store):
            status, body, _headers = self._request(
                "DELETE", f"/library/items/{ITEM_ID}?previewId={preview_id}"
            )
        self.assertEqual(status, 200)
        self.assertTrue(body["partial"])
        self.assertEqual(body["steps"]["library"], "failed")
        self.assertEqual(body["steps"]["torrents"], "ok")
        self.assertNotIn("/data/", json.dumps(body))


if __name__ == "__main__":
    unittest.main()
