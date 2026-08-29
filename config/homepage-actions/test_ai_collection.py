#!/usr/bin/env python3
import io
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from recommendations_store import RecommendationStore
from routes import discover


class _Handler:
    def __init__(self, body):
        raw = json.dumps(body).encode("utf-8")
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.wfile = io.BytesIO()
        self.status = None

    def send_response(self, status):
        self.status = status

    def send_header(self, *_args):
        pass

    def end_headers(self):
        pass


class AiCollectionMigrationTests(unittest.TestCase):
    def test_renames_legacy_collection_by_reposting_complete_dto(self):
        legacy = {"Id": "legacy-id", "Name": "Hermes Picks", "Overview": "keep", "Genres": ["Drama"]}
        with mock.patch.object(discover, "_find_collection_id_named", side_effect=[None, "legacy-id"]), \
             mock.patch.object(discover, "jellyfin_get", return_value=legacy), \
             mock.patch.object(discover, "jellyfin_post_json") as post:
            collection_id = discover._ensure_ai_picks_collection_name()

        self.assertEqual(collection_id, "legacy-id")
        post.assert_called_once_with(
            "/Items/legacy-id",
            {"Id": "legacy-id", "Name": "AI Picks", "Overview": "keep", "Genres": ["Drama"]},
        )
        self.assertEqual(legacy["Name"], "Hermes Picks")

    def test_when_both_exist_prefers_ai_collection_without_delete_or_rename(self):
        with mock.patch.object(discover, "_find_collection_id_named", side_effect=["ai-id", "legacy-id"]), \
             mock.patch.object(discover, "jellyfin_post_json") as post:
            collection_id = discover._ensure_ai_picks_collection_name()

        self.assertEqual(collection_id, "ai-id")
        post.assert_not_called()

    def test_collection_sync_uses_one_library_snapshot_instead_of_per_item_lookups(self):
        data = {
            "items": [
                {"source": "ai", "type": "movie", "tmdb_id": 42, "feedback": None, "in_library": False},
                {"source": "ai", "type": "tv", "tmdb_id": 7, "feedback": None, "in_library": False},
            ]
        }
        snapshot = discover.LibraryExclusionSnapshot.from_maps(
            {42: "jf-movie"},
            {7: "jf-tv"},
            status="fresh",
            last_successful_refresh_at="2026-08-29T10:00:00Z",
        )
        posted = []

        with mock.patch.object(discover.settings, "JELLYFIN_API_KEY", "key"), \
             mock.patch.object(discover.settings, "RECOMMENDATIONS_STORE", SimpleNamespace(load=lambda: data)), \
             mock.patch.object(discover, "_library_exclusion_snapshot", return_value=snapshot), \
             mock.patch.object(discover, "_jellyfin_id_for_tmdb", side_effect=AssertionError("per-item lookup")), \
             mock.patch.object(discover, "_ensure_ai_picks_collection_name", return_value=None), \
             mock.patch.object(discover, "jellyfin_post", side_effect=lambda path, query: posted.append((path, query)) or {"Id": "collection"}):
            result = discover.sync_ai_picks_collection()

        self.assertEqual(result["total"], 2)
        self.assertEqual(posted, [
            ("/Collections", {"name": "AI Picks", "ids": "jf-movie,jf-tv"})
        ])

    def test_collection_sync_request_does_not_block_the_caller(self):
        started = threading.Event()
        release = threading.Event()

        def slow_sync():
            started.set()
            release.wait(1)
            return {"ok": True}

        try:
            with mock.patch.object(discover, "_sync_ai_picks_collection_best_effort", side_effect=slow_sync):
                before = time.monotonic()
                discover._request_ai_picks_collection_sync()
                elapsed = time.monotonic() - before
                self.assertTrue(started.wait(0.5))
                self.assertLess(elapsed, 0.1)
        finally:
            release.set()

    def test_negative_feedback_requests_collection_reconciliation(self):
        tmpdir = tempfile.mkdtemp(prefix="ai-collection-feedback-")
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        store = RecommendationStore(os.path.join(tmpdir, "recommendations.json"))
        store.update(lambda doc: (
            doc["presented_media_ids"].append("movie:42"),
            doc["items"].append({
                "id": "ai-movie-42", "identity": "movie:42", "source": "ai",
                "type": "movie", "title": "Fixture", "tmdb_id": 42,
                "reason": "Test", "active": True, "feedback": None,
                "feedback_at": None, "request_state": None, "request_provider": None,
                "requested_at": None,
                "jellyseerr_request_id": None, "added_at": "2026-08-29T10:00:00Z",
            }),
        ))
        handler = _Handler({"status": "disliked"})
        requested = threading.Event()

        with mock.patch.object(discover, "_reject_mutating", return_value=False), \
             mock.patch.object(discover.settings, "RECOMMENDATIONS_STORE", store), \
             mock.patch.object(discover, "_request_ai_picks_collection_sync", side_effect=requested.set):
            discover.handle_discover_ai_picks_patch(handler, "ai-movie-42")

        self.assertEqual(handler.status, 200)
        self.assertTrue(requested.is_set())


if __name__ == "__main__":
    unittest.main()
