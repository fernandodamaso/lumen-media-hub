#!/usr/bin/env python3
"""API-level tests for POST /discover/hermes/generations (PR 2).

Runs a real ThreadingHTTPServer on an ephemeral port with a store pointed at
a temporary recommendations.json, so routing, token auth, and the locked
commit path are exercised end to end. The live runtime file is never touched.

Run from inside config/homepage-actions:
    python -m unittest test_generations_api -v
"""

import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

import config
import reconciliation
import routes.discover as discover_routes
from server import ActionsHandler
import recommendations_store as rs

TOKEN = "test-actions-token"


def make_item(
    tmdb_id,
    title=None,
    active=True,
    feedback=None,
    request_state=None,
    media_type="movie",
):
    identity = f"{media_type}:{tmdb_id}"
    item = {
        "id": f"hermes-{media_type}-{tmdb_id}",
        "identity": identity,
        "source": "hermes",
        "type": media_type,
        "title": title or f"Title {tmdb_id}",
        "year": 2000,
        "tmdb_id": tmdb_id,
        "reason": "fixture",
        "active": active,
        "feedback": feedback,
        "feedback_at": "2026-01-01T00:00:00Z" if feedback else None,
        "request_state": request_state,
        "requested_at": "2026-01-01T00:00:00Z" if request_state else None,
        "jellyseerr_request_id": 555 if request_state else None,
        "added_at": "2026-01-01T00:00:00Z",
    }
    return item


class GenerationApiTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="genapi-test-")
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.path = os.path.join(self.tmpdir, "recommendations.json")
        self.store = rs.RecommendationStore(self.path)

        self._old_store = config.RECOMMENDATIONS_STORE
        self._old_token = config.ACTIONS_TOKEN
        self._old_jellyseerr_key = config.JELLYSEERR_API_KEY
        self._old_cors_origins = config.CORS_ORIGINS
        self._old_reconciliation_path = config.RECONCILIATION_PATH
        self._old_generation_request_path = config.GENERATION_REQUEST_PATH

        config.RECOMMENDATIONS_STORE = self.store
        config.ACTIONS_TOKEN = TOKEN
        config.CORS_ORIGINS = ["http://localhost:3000"]
        config.RECONCILIATION_PATH = os.path.join(self.tmpdir, "reconciliation.json")
        config.GENERATION_REQUEST_PATH = os.path.join(
            self.tmpdir, "generation-request.json"
        )
        discover_routes._tracked_media_cache["expires"] = 0.0
        discover_routes._tracked_media_cache["ids"] = []
        discover_routes._tracked_media_cache["errors"] = []
        discover_routes._tracked_media_cache["has_success"] = False
        self.addCleanup(self._restore_config)
        self.addCleanup(lambda: reconciliation.stop_reconciliation_scheduler(timeout=1.0))

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ActionsHandler)
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def _restore_config(self):
        config.RECOMMENDATIONS_STORE = self._old_store
        config.ACTIONS_TOKEN = self._old_token
        config.JELLYSEERR_API_KEY = self._old_jellyseerr_key
        config.CORS_ORIGINS = self._old_cors_origins
        config.RECONCILIATION_PATH = self._old_reconciliation_path
        config.GENERATION_REQUEST_PATH = self._old_generation_request_path

    # -- helpers ---------------------------------------------------------

    def seed(self, items, presented=None):
        def _apply(doc):
            doc["items"].extend(items)
            ids = (
                [item["identity"] for item in items]
                if presented is None
                else presented
            )
            doc["presented_media_ids"].extend(ids)

        return self.store.update(_apply)

    def request(self, method, path, body=None, token=TOKEN, origin=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["X-Actions-Token"] = token
        if origin is not None:
            headers["Origin"] = origin
        raw = json.dumps(body).encode("utf-8") if body is not None else None
        try:
            conn.request(method, path, body=raw, headers=headers)
            resp = conn.getresponse()
            payload = json.loads(resp.read().decode("utf-8") or b"{}")
            return resp.status, payload
        finally:
            conn.close()

    def post_generation(self, base_revision, candidates, token=TOKEN):
        return self.request(
            "POST",
            "/discover/hermes/generations",
            {"base_revision": base_revision, "candidates": candidates},
            token=token,
        )

    def candidate(self, tmdb_id, title=None, retain=False, media_type="movie", **extra):
        cand = {
            "type": media_type,
            "title": title or f"Title {tmdb_id}",
            "year": 2001,
            "tmdb_id": tmdb_id,
            "reason": "fixture reason",
        }
        if retain:
            cand["retain"] = True
        cand.update(extra)
        return cand

    def current_doc(self):
        return self.store.load()

    def item_by_tmdb(self, doc, tmdb_id, media_type=None):
        for item in doc["items"]:
            if item["tmdb_id"] == tmdb_id and (
                media_type is None or item["type"] == media_type
            ):
                return item
        return None


class AuthAndValidationTests(GenerationApiTestCase):
    def test_missing_token_rejected(self):
        status, payload = self.post_generation(0, [], token=None)
        self.assertEqual(status, 401)
        self.assertFalse(payload["ok"])

    def test_wrong_token_rejected(self):
        status, _ = self.post_generation(0, [], token="nope")
        self.assertEqual(status, 401)

    def test_invalid_json_body_rejected(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(
                "POST",
                "/discover/hermes/generations",
                body=b"{not json",
                headers={"Content-Type": "application/json", "X-Actions-Token": TOKEN},
            )
            resp = conn.getresponse()
            payload = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(resp.status, 400)
            self.assertFalse(payload["ok"])
        finally:
            conn.close()

    def test_missing_or_non_integer_base_revision_rejected(self):
        for body in (
            {"candidates": []},
            {"base_revision": "3", "candidates": []},
            {"base_revision": 1.5, "candidates": []},
            {"base_revision": True, "candidates": []},
        ):
            with self.subTest(body=body):
                status, payload = self.request(
                    "POST", "/discover/hermes/generations", body
                )
                self.assertEqual(status, 400)
                self.assertIn("base_revision", payload["error"])

    def test_candidates_must_be_a_list(self):
        status, payload = self.request(
            "POST",
            "/discover/hermes/generations",
            {"base_revision": 0, "candidates": {"tmdb_id": 1}},
        )
        self.assertEqual(status, 400)
        self.assertIn("candidates", payload["error"])

    def test_batch_size_capped_at_100(self):
        candidates = [self.candidate(1000 + i) for i in range(101)]
        status, payload = self.request(
            "POST",
            "/discover/hermes/generations",
            {"base_revision": 0, "candidates": candidates},
        )
        self.assertEqual(status, 400)
        self.assertIn("100", payload["error"])
        self.assertEqual(self.current_doc()["items"], [])
        # Exactly 100 is accepted.
        status, payload = self.post_generation(
            0, [self.candidate(1000 + i) for i in range(100)]
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["accepted"]), 100)

    def test_invalid_candidates_rejected_individually_with_reasons(self):
        status, payload = self.post_generation(
            0,
            [
                {"type": "anime", "title": "X", "tmdb_id": 10},  # bad type
                {"type": "movie", "title": "", "tmdb_id": 11},  # bad title
                {"type": "movie", "title": "Y", "tmdb_id": -3},  # bad id
                {"type": "movie", "title": "Z", "tmdb_id": 12, "year": "2001"},
                "not-an-object",
            ],
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["rejected"]), 5)
        for entry in payload["rejected"]:
            self.assertEqual(entry["reason"], "invalid_candidate")
            self.assertIn("detail", entry)
        self.assertEqual(payload["accepted"], [])
        # Nothing committed: an all-invalid batch still bumps revision once
        # (it is a successful, validated commit of an empty change set) but
        # adds no items and no presented IDs.
        doc = self.current_doc()
        self.assertEqual(doc["items"], [])
        self.assertEqual(doc["presented_media_ids"], [])

    def test_duplicate_tmdb_id_within_batch_rejected(self):
        status, payload = self.post_generation(
            0, [self.candidate(42), self.candidate(42, title="Copy")]
        )
        self.assertEqual(status, 200)
        self.assertEqual([a["tmdb_id"] for a in payload["accepted"]], [42])
        self.assertEqual(len(payload["rejected"]), 1)
        self.assertEqual(payload["rejected"][0]["reason"], "duplicate_in_batch")
        self.assertEqual(len(self.current_doc()["items"]), 1)

    def test_movie_and_tv_same_numeric_tmdb_id_are_distinct_but_each_repeats_once(self):
        status, payload = self.post_generation(
            0,
            [self.candidate(123), self.candidate(123, type="tv")],
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            [entry["identity"] for entry in payload["accepted"]],
            ["movie:123", "tv:123"],
        )
        doc = self.current_doc()
        self.assertEqual(
            {item["identity"] for item in doc["items"]}, {"movie:123", "tv:123"}
        )

        status, payload = self.post_generation(
            doc["revision"],
            [self.candidate(123), self.candidate(123, type="tv")],
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["accepted"], [])
        self.assertEqual(
            {entry["identity"] for entry in payload["rejected"]},
            {"movie:123", "tv:123"},
        )
        self.assertEqual(
            {entry["reason"] for entry in payload["rejected"]}, {"already_active"}
        )


class GenerationCommitTests(GenerationApiTestCase):
    def test_new_candidates_accepted_with_clean_fields_and_presented_appended(self):
        status, payload = self.post_generation(
            0, [self.candidate(101), self.candidate(102, type="tv")]
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["revision"], 1)
        self.assertEqual([a["identity"] for a in payload["accepted"]], ["movie:101", "tv:102"])
        self.assertEqual(payload["retained"], [])
        self.assertEqual(payload["rotated"], [])
        self.assertEqual(payload["rejected"], [])

        doc = self.current_doc()
        self.assertEqual(doc["presented_media_ids"], ["movie:101", "tv:102"])
        for tmdb_id in (101, 102):
            item = self.item_by_tmdb(doc, tmdb_id)
            self.assertTrue(item["active"])
            expected_type = "tv" if tmdb_id == 102 else "movie"
            self.assertEqual(item["id"], f"hermes-{expected_type}-{tmdb_id}")
            self.assertEqual(item["identity"], f"{expected_type}:{tmdb_id}")
            self.assertEqual(item["source"], "hermes")
            self.assertIsNone(item["feedback"])
            self.assertIsNone(item["feedback_at"])
            self.assertIsNone(item["request_state"])
            self.assertIsNone(item["requested_at"])
            self.assertIsNone(item["jellyseerr_request_id"])
            self.assertTrue(item["added_at"])
        self.assertTrue(rs.validate_v3(doc))

    def test_omitted_active_items_rotated_to_history_not_deleted(self):
        # Only non-keeper interacted actives may rotate when omitted.
        self.seed(
            [
                make_item(1, feedback="disliked"),
                make_item(2, feedback="skipped"),
                make_item(3, active=False),
            ],
            presented=["movie:1", "movie:2", "movie:3"],
        )
        rev = self.current_doc()["revision"]
        status, payload = self.post_generation(rev, [self.candidate(99)])
        self.assertEqual(status, 200)
        self.assertEqual(payload["rotated"], ["movie:1", "movie:2"])

        doc = self.current_doc()
        disliked = self.item_by_tmdb(doc, 1)
        self.assertFalse(disliked["active"])
        self.assertEqual(disliked["feedback"], "disliked")
        skipped = self.item_by_tmdb(doc, 2)
        self.assertFalse(skipped["active"])
        self.assertEqual(skipped["feedback"], "skipped")
        self.assertEqual(skipped["feedback_at"], "2026-01-01T00:00:00Z")
        # Already-inactive history item is untouched.
        self.assertFalse(self.item_by_tmdb(doc, 3)["active"])
        # Nothing deleted.
        self.assertEqual(len(doc["items"]), 4)

    def test_omitted_untouched_active_stays_active(self):
        self.seed(
            [
                make_item(1),
                make_item(2, feedback="skipped"),
                make_item(3, request_state="requested", active=True),
            ],
            presented=["movie:1", "movie:2", "movie:3"],
        )
        rev = self.current_doc()["revision"]
        status, payload = self.post_generation(rev, [self.candidate(99)])
        self.assertEqual(status, 200)
        self.assertIn("movie:1", payload["retained"])
        self.assertEqual(payload["rotated"], ["movie:2", "movie:3"])

        doc = self.current_doc()
        untouched = self.item_by_tmdb(doc, 1)
        self.assertTrue(untouched["active"])
        self.assertIsNone(untouched["feedback"])
        self.assertIsNone(untouched["request_state"])
        self.assertFalse(self.item_by_tmdb(doc, 2)["active"])
        self.assertFalse(self.item_by_tmdb(doc, 3)["active"])
        self.assertTrue(self.item_by_tmdb(doc, 99)["active"])

    def test_omitted_liked_active_rotates_to_history(self):
        self.seed(
            [
                make_item(1, feedback="liked"),
                make_item(2, feedback="watched"),
            ],
            presented=["movie:1", "movie:2"],
        )
        rev = self.current_doc()["revision"]
        status, payload = self.post_generation(rev, [self.candidate(99)])
        self.assertEqual(status, 200)
        self.assertEqual(payload["retained"], [])
        self.assertEqual(sorted(payload["rotated"]), ["movie:1", "movie:2"])

        doc = self.current_doc()
        liked = self.item_by_tmdb(doc, 1)
        self.assertFalse(liked["active"])
        self.assertEqual(liked["feedback"], "liked")
        self.assertFalse(self.item_by_tmdb(doc, 2)["active"])
        self.assertTrue(self.item_by_tmdb(doc, 99)["active"])

    def test_retained_active_keeps_feedback_and_request_fields(self):
        self.seed(
            [make_item(7, feedback="liked", request_state="requested")],
            presented=["movie:7"],
        )
        rev = self.current_doc()["revision"]
        status, payload = self.post_generation(
            rev,
            [
                self.candidate(7, title="Retitled", retain=True, reason="new reason"),
                self.candidate(8),
            ],
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["retained"], ["movie:7"])
        self.assertEqual(payload["rotated"], [])
        self.assertEqual([a["identity"] for a in payload["accepted"]], ["movie:8"])

        item = self.item_by_tmdb(self.current_doc(), 7)
        self.assertTrue(item["active"])
        self.assertEqual(item["title"], "Retitled")
        self.assertEqual(item["reason"], "new reason")
        self.assertEqual(item["feedback"], "liked")
        self.assertEqual(item["feedback_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(item["request_state"], "requested")
        self.assertEqual(item["requested_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(item["jellyseerr_request_id"], 555)
        self.assertEqual(item["added_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(len(self.current_doc()["items"]), 2)

    def test_active_candidate_without_retain_rejected(self):
        self.seed([make_item(7)], presented=["movie:7"])
        rev = self.current_doc()["revision"]
        status, payload = self.post_generation(rev, [self.candidate(7)])
        self.assertEqual(status, 200)
        self.assertEqual(payload["accepted"], [])
        self.assertEqual(
            payload["rejected"], [{"index": 0, "identity": "movie:7", "tmdb_id": 7, "reason": "already_active"}]
        )
        self.assertTrue(self.item_by_tmdb(self.current_doc(), 7)["active"])

    def test_replay_of_same_generation_creates_no_duplicates(self):
        candidates = [self.candidate(201), self.candidate(202)]
        status, payload = self.post_generation(0, candidates)
        self.assertEqual(status, 200)
        rev = payload["revision"]

        # Replay at the committed revision: both IDs are now active.
        status, payload = self.post_generation(rev, candidates)
        self.assertEqual(status, 200)
        self.assertEqual(payload["accepted"], [])
        self.assertEqual(
            sorted(r["reason"] for r in payload["rejected"]), ["already_active"] * 2
        )
        doc = self.current_doc()
        self.assertEqual(len(doc["items"]), 2)
        self.assertEqual(sum(1 for i in doc["items"] if i["tmdb_id"] == 201), 1)

        # Replay with retain flags: both retained, still no duplicates.
        status, payload = self.post_generation(
            doc["revision"], [self.candidate(201, retain=True), self.candidate(202, retain=True)]
        )
        self.assertEqual(status, 200)
        self.assertEqual(sorted(payload["retained"]), ["movie:201", "movie:202"])
        self.assertEqual(len(self.current_doc()["items"]), 2)

    def test_rotated_id_can_never_be_presented_as_new_again(self):
        # Give feedback so omission is allowed to rotate (untouched cannot rotate).
        self.seed([make_item(301, feedback="skipped")], presented=["movie:301"])
        rev = self.current_doc()["revision"]
        # Rotate 301 out by committing a generation that omits it.
        status, payload = self.post_generation(rev, [self.candidate(302)])
        self.assertEqual(status, 200)
        self.assertEqual(payload["rotated"], ["movie:301"])
        self.assertFalse(self.item_by_tmdb(self.current_doc(), 301)["active"])

        # Resubmit 301 as a new candidate: rejected by the deny list.
        rev = self.current_doc()["revision"]
        status, payload = self.post_generation(rev, [self.candidate(301)])
        self.assertEqual(status, 200)
        self.assertEqual(payload["accepted"], [])
        self.assertEqual(
            payload["rejected"],
            [{"index": 0, "identity": "movie:301", "tmdb_id": 301, "reason": "already_presented"}],
        )
        item = self.item_by_tmdb(self.current_doc(), 301)
        self.assertFalse(item["active"])
        self.assertEqual(sum(1 for i in self.current_doc()["items"] if i["tmdb_id"] == 301), 1)

    def test_retain_true_on_inactive_item_rejected_no_resurrection(self):
        self.seed([make_item(401, active=False)], presented=["movie:401"])
        rev = self.current_doc()["revision"]
        status, payload = self.post_generation(
            rev, [self.candidate(401, retain=True)]
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["accepted"], [])
        self.assertEqual(payload["retained"], [])
        self.assertEqual(
            payload["rejected"],
            [{"index": 0, "identity": "movie:401", "tmdb_id": 401, "reason": "already_presented"}],
        )
        doc = self.current_doc()
        item = self.item_by_tmdb(doc, 401)
        self.assertFalse(item["active"])
        self.assertEqual(sum(1 for i in doc["items"] if i["tmdb_id"] == 401), 1)

    def test_item_row_missing_from_presented_is_invalid_state(self):
        with self.assertRaises(rs.RecommendationValidationError):
            self.seed([make_item(402, active=False)], presented=[])


class RevisionConflictTests(GenerationApiTestCase):
    def test_stale_base_revision_returns_409_and_loses_no_feedback(self):
        self.seed([make_item(7)], presented=["movie:7"])
        stale_rev = self.current_doc()["revision"]

        # Feedback lands while "Hermes" holds the older snapshot.
        def _like(doc):
            for item in doc["items"]:
                if item["tmdb_id"] == 7:
                    rs.apply_feedback(item, "liked")

        self.store.update(_like)

        status, payload = self.post_generation(stale_rev, [self.candidate(900)])
        self.assertEqual(status, 409)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "stale_base_revision")
        self.assertEqual(payload["current_revision"], stale_rev + 1)

        doc = self.current_doc()
        self.assertEqual(doc["revision"], stale_rev + 1)
        self.assertEqual(self.item_by_tmdb(doc, 7)["feedback"], "liked")
        self.assertIsNone(self.item_by_tmdb(doc, 900))
        self.assertNotIn("movie:900", doc["presented_media_ids"])

    def test_fresh_retry_after_409_merges_and_preserves_metadata(self):
        self.seed([make_item(7)], presented=["movie:7"])
        stale_rev = self.current_doc()["revision"]

        def _request_item(doc):
            for item in doc["items"]:
                if item["tmdb_id"] == 7:
                    rs.apply_request(item, request_id=777)

        self.store.update(_request_item)
        status, _ = self.post_generation(stale_rev, [self.candidate(900)])
        self.assertEqual(status, 409)

        # Fresh snapshot, then retry: retain 7 (requested items are inactive,
        # so it cannot be retained; it stays in history) and accept 900.
        fresh_rev = self.current_doc()["revision"]
        status, payload = self.post_generation(fresh_rev, [self.candidate(900)])
        self.assertEqual(status, 200)
        self.assertEqual([a["identity"] for a in payload["accepted"]], ["movie:900"])
        item = self.item_by_tmdb(self.current_doc(), 7)
        self.assertEqual(item["request_state"], "requested")
        self.assertEqual(item["jellyseerr_request_id"], 777)

    def test_concurrent_generations_yield_one_commit_one_conflict(self):
        self.seed([make_item(1)], presented=["movie:1"])
        rev = self.current_doc()["revision"]
        outcomes = []

        def submit(tmdb_id):
            outcomes.append(self.post_generation(rev, [self.candidate(tmdb_id)]))

        threads = [threading.Thread(target=submit, args=(501,)),
                   threading.Thread(target=submit, args=(502,))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        statuses = sorted(status for status, _ in outcomes)
        self.assertEqual(statuses, [200, 409])
        doc = self.current_doc()
        # Exactly one generation committed: one item added, file is valid JSON.
        accepted = [i["tmdb_id"] for i in doc["items"] if i["tmdb_id"] in (501, 502)]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(doc["revision"], rev + 1)
        self.assertTrue(rs.validate_v3(doc))
        with open(self.path, encoding="utf-8") as fh:
            json.load(fh)


class GetAndRetiredRouteTests(GenerationApiTestCase):
    def test_get_exposes_only_dashboard_state_without_store_metadata(self):
        self.seed(
            [make_item(1), make_item(2, active=False), make_item(3, feedback="liked")],
            presented=["movie:1", "movie:2", "movie:3"],
        )
        status, payload = self.request("GET", "/discover/hermes")
        self.assertEqual(status, 200)
        for private_key in ("version", "revision", "updated_at", "presented_media_ids", "context"):
            self.assertNotIn(private_key, payload)
        by_tmdb = {item["tmdb_id"]: item for item in payload["items"]}
        self.assertTrue(by_tmdb[1]["active"])
        self.assertFalse(by_tmdb[2]["active"])
        self.assertEqual(by_tmdb[2]["feedback"], None)
        self.assertEqual(by_tmdb[3]["feedback"], "liked")
        self.assertFalse(by_tmdb[3]["active"])
        for item in payload["items"]:
            self.assertNotIn("status", item)

    def test_get_does_not_expose_generation_context(self):
        self.seed(
            [
                make_item(1),
                make_item(2, feedback="liked"),
                make_item(3, feedback="disliked", active=False),
                make_item(4, feedback="skipped", active=False),
                make_item(5, feedback="watched", active=True),
            ],
            presented=["movie:1", "movie:2", "movie:3", "movie:4", "movie:5"],
        )
        with mock.patch(
            "routes.discover._get_tracked_media_ids",
            return_value=(["movie:100", "tv:200"], []),
        ), mock.patch(
            "routes.discover._library_exclusion_snapshot",
            return_value=discover_routes.LibraryExclusionSnapshot.from_maps(
                {300: "movie-jf"}, {}, status="fresh", last_successful_refresh_at=None
            ),
        ):
            status, payload = self.request("GET", "/discover/hermes")
        self.assertEqual(status, 200)
        self.assertNotIn("context", payload)
        self.assertEqual(payload["library_exclusion"]["status"], "fresh")
        self.assertEqual(payload["watched_exclusion"]["status"], "unavailable")
        for item in payload["items"]:
            self.assertNotIn("identity", item)

    def test_get_projects_watched_hermes_items_without_writing_store(self):
        self.seed([make_item(7), make_item(8, active=False), make_item(9, feedback="liked")])
        watched = discover_routes.WatchedSnapshot(
            frozenset({"movie:7", "movie:8", "movie:9"}),
            "2026-08-11T12:00:00+00:00",
            "fresh",
        )
        with open(self.path, "rb") as handle:
            before = handle.read()
        with mock.patch.object(discover_routes, "_trakt_watched_snapshot", return_value=watched) as watched_snapshot, \
                mock.patch.object(
                    discover_routes,
                    "_library_exclusion_snapshot",
                    return_value=discover_routes.LibraryExclusionSnapshot.from_maps(
                        {}, {}, status="fresh", last_successful_refresh_at=None
                    ),
                ), \
                mock.patch.object(discover_routes, "_enrich_hermes_posters", side_effect=lambda values: values), \
                mock.patch.object(discover_routes, "_hermes_generation_context", return_value={}):
            status, payload = self.request("GET", "/discover/hermes")
        with open(self.path, "rb") as handle:
            after = handle.read()
        self.assertEqual(status, 200)
        watched_snapshot.assert_called_once_with()
        self.assertEqual(before, after)
        by_tmdb = {item["tmdb_id"]: item for item in payload["items"]}
        self.assertEqual(
            [(by_tmdb[tmdb_id]["active"], by_tmdb[tmdb_id]["excluded_reason"], by_tmdb[tmdb_id]["watched_on_trakt"])
             for tmdb_id in (7, 8, 9)],
            [(False, "watched_on_trakt", True)] * 3,
        )
        self.assertEqual(by_tmdb[9]["feedback"], "liked")

    def test_retired_upsert_route_returns_410(self):
        status, payload = self.request(
            "POST", "/discover/hermes", {"tmdb_id": 42, "title": "Heat"}
        )
        self.assertEqual(status, 410)
        self.assertFalse(payload["ok"])
        self.assertIn("generations", payload["use"])
        self.assertEqual(self.current_doc()["items"], [])


class InternalGenerationSnapshotTests(GenerationApiTestCase):
    def snapshot(self, token=TOKEN, origin="http://localhost:3000"):
        return self.request(
            "GET",
            "/internal/discover/hermes",
            token=token,
            origin=origin,
        )

    def test_missing_and_wrong_token_are_unauthorized(self):
        for token in (None, "wrong-token"):
            with self.subTest(token=token):
                status, payload = self.snapshot(token=token)
                self.assertEqual(status, 401)
                self.assertEqual(payload, {"ok": False, "error": "Unauthorized"})

    def test_disallowed_origin_is_forbidden(self):
        status, payload = self.snapshot(origin="https://attacker.example")
        self.assertEqual(status, 403)
        self.assertEqual(payload, {"ok": False, "error": "Origin not allowed"})

    def test_valid_snapshot_has_exact_keys_and_complete_retain_candidates(self):
        self.seed([make_item(7)], presented=["movie:7"])
        with mock.patch.object(
            discover_routes,
            "_get_tracked_media_ids",
            return_value=([], []),
        ), mock.patch.object(
            discover_routes,
            "_library_exclusion_snapshot",
            return_value=discover_routes.LibraryExclusionSnapshot.from_maps(
                {}, {}, status="fresh", last_successful_refresh_at=None
            ),
        ), mock.patch.object(
            discover_routes,
            "_trakt_watched_snapshot",
            return_value=discover_routes.WatchedSnapshot(frozenset(), None, "fresh"),
        ):
            status, payload = self.snapshot()

        self.assertEqual(status, 200)
        self.assertEqual(set(payload), {"ok", "revision", "presented_media_ids", "context"})
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["revision"], self.current_doc()["revision"])
        self.assertEqual(payload["presented_media_ids"], ["movie:7"])
        self.assertEqual(
            payload["context"]["required_retain"],
            [{
                "type": "movie",
                "title": "Title 7",
                "year": 2000,
                "tmdb_id": 7,
                "reason": "fixture",
                "retain": True,
            }],
        )

    def test_revision_and_presented_ids_are_same_document_and_snapshot_is_usable(self):
        self.seed([make_item(7)], presented=["movie:7"])
        patches = [
            mock.patch.object(discover_routes, "_get_tracked_media_ids", return_value=([], [])),
            mock.patch.object(
                discover_routes,
                "_library_exclusion_snapshot",
                return_value=discover_routes.LibraryExclusionSnapshot.from_maps(
                    {}, {}, status="fresh", last_successful_refresh_at=None
                ),
            ),
            mock.patch.object(
                discover_routes,
                "_trakt_watched_snapshot",
                return_value=discover_routes.WatchedSnapshot(frozenset(), None, "fresh"),
            ),
        ]
        with patches[0], patches[1], patches[2]:
            status, snapshot = self.snapshot()
            self.assertEqual(status, 200)
            candidates = snapshot["context"]["required_retain"] + [self.candidate(8)]
            status, result = self.post_generation(snapshot["revision"], candidates)
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertEqual(self.current_doc()["revision"], snapshot["revision"] + 1)

    def test_stale_snapshot_returns_409_without_mutating_transaction(self):
        self.seed([make_item(7)], presented=["movie:7"])
        status, snapshot = self.snapshot()
        self.assertEqual(status, 200)
        self.store.update(lambda doc: doc["items"][0].update({"feedback": "liked"}))
        before = self.current_doc()

        status, payload = self.post_generation(
            snapshot["revision"], [self.candidate(8)]
        )

        self.assertEqual(status, 409)
        self.assertEqual(payload["error"], "stale_base_revision")
        self.assertEqual(self.current_doc(), before)

    def test_public_response_excludes_injected_private_and_unknown_fields(self):
        self.seed([make_item(7)], presented=["movie:7"])

        def inject_private_fields(doc):
            doc["secret"] = "TOKEN raw-history HTML https://upstream.example"
            doc["unknown_top_level"] = {"path": "C:\\private\\history"}
            doc["items"][0].update(
                {
                    "secret": "TOKEN",
                    "raw_history": "watched title movie:909",
                    "unknown_row_property": "should stay private",
                }
            )

        self.store.update(inject_private_fields)
        status, payload = self.request("GET", "/discover/hermes")
        encoded = json.dumps(payload)
        self.assertEqual(status, 200)
        for private in (
            "TOKEN",
            "raw-history",
            "watched title",
            "unknown_row_property",
            "unknown_top_level",
            "revision",
            "presented_media_ids",
            "context",
        ):
            self.assertNotIn(private, encoded)


class DiscoverSafeErrorBoundaryTests(GenerationApiTestCase):
    SECRET_ERROR = "path=C:\\private\\token SECRET raw-history=Watched Title <html> upstream=https://evil.example"

    def test_browser_visible_provider_and_operation_errors_are_fixed(self):
        cases = (
            ("GET", "/discover/hermes", 500, "Discover recommendations are temporarily unavailable", "RECOMMENDATIONS_STORE.load"),
            ("GET", "/discover/jellyseerr?kind=trending", 502, "Jellyseerr is temporarily unavailable", "_jellyseerr_get"),
            ("GET", "/discover/trakt?type=movies", 502, "Trakt temporarily unavailable", "_trakt_get"),
            ("POST", "/discover/hermes/sync", 502, "Hermes collection is temporarily unavailable", "sync_hermes_collection"),
            ("POST", "/discover/hermes/request-more", 500, "Generation request could not be queued", "_request_hermes_generation"),
            ("POST", "/discover/request/reconcile", 500, "Request reconciliation is temporarily unavailable", "run_reconciliation_cycle"),
        )
        for method, path, expected_status, expected, operation in cases:
            with self.subTest(operation=operation), mock.patch("builtins.print") as printed:
                if operation == "RECOMMENDATIONS_STORE.load":
                    patcher = mock.patch.object(
                        self.store, "load", side_effect=RuntimeError(self.SECRET_ERROR)
                    )
                elif operation == "_jellyseerr_get":
                    patcher = mock.patch.object(
                        discover_routes, operation, side_effect=RuntimeError(self.SECRET_ERROR)
                    )
                elif operation == "_trakt_get":
                    patcher = mock.patch.object(
                        discover_routes, operation, side_effect=RuntimeError(self.SECRET_ERROR)
                    )
                elif operation == "sync_hermes_collection":
                    patcher = mock.patch.object(
                        discover_routes, operation, side_effect=RuntimeError(self.SECRET_ERROR)
                    )
                elif operation == "_request_hermes_generation":
                    patcher = mock.patch.object(
                        discover_routes, operation, side_effect=rs.RecommendationError(self.SECRET_ERROR)
                    )
                else:
                    patcher = mock.patch.object(
                        discover_routes, operation, side_effect=RuntimeError(self.SECRET_ERROR)
                    )
                with patcher, mock.patch.object(config, "TRAKT_CLIENT_ID", "client-id"), mock.patch.object(
                    config, "JELLYSEERR_ENABLED", True
                ), mock.patch.object(config, "JELLYSEERR_API_KEY", "jellyseerr-key"):
                    status, payload = self.request(method, path)
            self.assertEqual(status, expected_status)
            self.assertEqual(payload["error"], expected)
            self.assertNotIn(self.SECRET_ERROR, json.dumps(payload))
            self.assertNotIn(self.SECRET_ERROR, " ".join(str(call) for call in printed.call_args_list))

    def test_feedback_request_generation_and_best_effort_logs_are_sanitized(self):
        self.seed([make_item(7)], presented=["movie:7"])
        with mock.patch.object(
            self.store, "update", side_effect=RuntimeError(self.SECRET_ERROR)
        ):
            status, payload = self.request(
                "PATCH", "/discover/hermes/hermes-movie-7", {"status": "liked"}
            )
        self.assertEqual(status, 500)
        self.assertEqual(payload["error"], "Feedback could not be saved")

        with mock.patch.object(
            discover_routes,
            "_add_to_arr_unmonitored",
            side_effect=RuntimeError(self.SECRET_ERROR),
        ):
            status, payload = self.request(
                "POST",
                "/discover/request",
                {"mediaType": "movie", "mediaId": 7},
            )
        self.assertEqual(status, 502)
        self.assertEqual(payload["error"], "Unable to add this title to the library")

        with mock.patch.object(
            discover_routes,
            "_resolve_poster_paths",
            side_effect=RuntimeError(self.SECRET_ERROR),
        ), mock.patch.object(
            discover_routes,
            "_hermes_exclusion_sets",
            return_value=(set(), set(), set(), []),
        ), mock.patch("builtins.print") as printed:
            status, payload = self.post_generation(
                self.current_doc()["revision"], [self.candidate(8)]
            )
        self.assertEqual(status, 200)
        self.assertNotIn(self.SECRET_ERROR, json.dumps(payload))
        self.assertNotIn(self.SECRET_ERROR, " ".join(str(call) for call in printed.call_args_list))

        with mock.patch.object(config, "JELLYFIN_API_KEY", "jellyfin-key"), mock.patch.object(
            discover_routes, "sync_hermes_collection", side_effect=RuntimeError(self.SECRET_ERROR)
        ):
            result = discover_routes._sync_hermes_collection_best_effort()
        self.assertEqual(result, {"ok": False, "error": "Hermes collection is temporarily unavailable"})

class ExclusionEnforcementTests(GenerationApiTestCase):
    def test_already_tracked_candidate_rejected(self):
        with mock.patch(
            "routes.discover._hermes_exclusion_sets",
            return_value=({"movie:777"}, set(), set(), []),
        ):
            status, payload = self.post_generation(0, [self.candidate(777)])
        self.assertEqual(status, 200)
        self.assertEqual(payload["accepted"], [])
        self.assertEqual(
            payload["rejected"],
            [
                {
                    "index": 0,
                    "identity": "movie:777",
                    "tmdb_id": 777,
                    "reason": "already_tracked",
                }
            ],
        )
        self.assertIsNone(self.item_by_tmdb(self.current_doc(), 777))

    def test_already_in_library_candidate_rejected(self):
        with mock.patch(
            "routes.discover._hermes_exclusion_sets",
            return_value=(set(), {"movie:888"}, set(), []),
        ):
            status, payload = self.post_generation(0, [self.candidate(888)])
        self.assertEqual(status, 200)
        self.assertEqual(payload["accepted"], [])
        self.assertEqual(
            payload["rejected"],
            [
                {
                    "index": 0,
                    "identity": "movie:888",
                    "tmdb_id": 888,
                    "reason": "already_in_library",
                }
            ],
        )
        self.assertIsNone(self.item_by_tmdb(self.current_doc(), 888))

    def test_tracked_takes_precedence_over_in_library(self):
        with mock.patch(
            "routes.discover._hermes_exclusion_sets",
            return_value=({"movie:999"}, {"movie:999"}, set(), []),
        ):
            status, payload = self.post_generation(0, [self.candidate(999)])
        self.assertEqual(status, 200)
        self.assertEqual(payload["rejected"][0]["reason"], "already_tracked")

    def test_already_watched_candidate_rejected_with_typed_identity(self):
        with mock.patch(
            "routes.discover._hermes_exclusion_sets",
            return_value=(set(), set(), {"movie:777"}, []),
        ):
            status, payload = self.post_generation(0, [self.candidate(777)])
        self.assertEqual(status, 200)
        self.assertEqual(payload["accepted"], [])
        self.assertEqual(
            payload["rejected"],
            [
                {
                    "index": 0,
                    "identity": "movie:777",
                    "tmdb_id": 777,
                    "reason": "already_watched",
                }
            ],
        )
        self.assertIsNone(self.item_by_tmdb(self.current_doc(), 777))

    def test_watched_typed_identity_does_not_reject_same_numeric_tv_candidate(self):
        with mock.patch(
            "routes.discover._hermes_exclusion_sets",
            return_value=(set(), set(), {"movie:777"}, []),
        ):
            status, payload = self.post_generation(
                0, [self.candidate(777, media_type="tv")]
            )
        self.assertEqual(status, 200)
        self.assertEqual(payload["accepted"][0]["identity"], "tv:777")

    def test_tracked_and_library_precedence_is_preserved_over_watched(self):
        with mock.patch(
            "routes.discover._hermes_exclusion_sets",
            return_value=({"movie:999"}, {"movie:999"}, {"movie:999"}, []),
        ):
            status, payload = self.post_generation(0, [self.candidate(999)])
        self.assertEqual(status, 200)
        self.assertEqual(payload["rejected"][0]["reason"], "already_tracked")

    def test_legacy_tombstone_blocks_both_typed_candidates(self):
        self.seed([], presented=["legacy:777"])
        status, payload = self.post_generation(
            1,
            [self.candidate(777), self.candidate(777, media_type="tv")],
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["accepted"], [])
        self.assertEqual(
            [(entry["identity"], entry["reason"]) for entry in payload["rejected"]],
            [("movie:777", "already_presented"), ("tv:777", "already_presented")],
        )
        self.assertEqual(self.current_doc()["presented_media_ids"], ["legacy:777"])


class WatchedGenerationRotationTests(GenerationApiTestCase):
    def test_excluded_active_rows_cannot_be_explicitly_retained(self):
        self.seed(
            [make_item(7), make_item(8), make_item(9)],
            presented=["movie:7", "movie:8", "movie:9"],
        )
        rev = self.current_doc()["revision"]
        with mock.patch(
            "routes.discover._hermes_exclusion_sets",
            return_value=(set(), {"movie:8"}, {"movie:7"}, []),
        ):
            status, payload = self.post_generation(
                rev,
                [
                    self.candidate(7, retain=True),
                    self.candidate(8, retain=True),
                    self.candidate(10),
                ],
            )
        self.assertEqual(status, 200)
        self.assertEqual(
            [(entry["identity"], entry["reason"]) for entry in payload["rejected"]],
            [("movie:7", "already_watched"), ("movie:8", "already_in_library")],
        )
        self.assertEqual(sorted(payload["rotated"]), ["movie:7", "movie:8"])
        self.assertFalse(self.item_by_tmdb(self.current_doc(), 7)["active"])
        self.assertFalse(self.item_by_tmdb(self.current_doc(), 8)["active"])
        self.assertTrue(self.item_by_tmdb(self.current_doc(), 9)["active"])

    def test_excluded_active_rows_rotate_even_without_retain_flag(self):
        self.seed(
            [make_item(7), make_item(8)],
            presented=["movie:7", "movie:8"],
        )
        rev = self.current_doc()["revision"]
        with mock.patch(
            "routes.discover._hermes_exclusion_sets",
            return_value=(set(), {"movie:8"}, {"movie:7"}, []),
        ):
            status, payload = self.post_generation(
                rev,
                [self.candidate(7), self.candidate(8)],
            )
        self.assertEqual(status, 200)
        self.assertEqual(
            [(entry["identity"], entry["reason"]) for entry in payload["rejected"]],
            [("movie:7", "already_watched"), ("movie:8", "already_in_library")],
        )
        self.assertEqual(sorted(payload["rotated"]), ["movie:7", "movie:8"])
        self.assertFalse(self.item_by_tmdb(self.current_doc(), 7)["active"])
        self.assertFalse(self.item_by_tmdb(self.current_doc(), 8)["active"])

    def test_excluded_active_rows_rotate_and_preserve_all_metadata(self):
        watched = make_item(7, feedback="liked", request_state="requested")
        watched["feedback_at"] = "2026-01-02T00:00:00Z"
        watched["requested_at"] = "2026-01-03T00:00:00Z"
        watched["jellyseerr_request_id"] = 77
        watched["added_at"] = "2025-12-01T00:00:00Z"
        library = make_item(8)
        library["feedback_at"] = None
        library["requested_at"] = None
        library["jellyseerr_request_id"] = None
        library["added_at"] = "2025-12-02T00:00:00Z"
        untouched = make_item(9)
        self.seed(
            [watched, library, untouched],
            presented=["movie:7", "movie:8", "movie:9"],
        )
        before = {
            key: watched[key]
            for key in (
                "id", "identity", "type", "tmdb_id", "feedback", "feedback_at",
                "request_state", "requested_at", "jellyseerr_request_id", "added_at",
            )
        }
        rev = self.current_doc()["revision"]
        with mock.patch(
            "routes.discover._hermes_exclusion_sets",
            return_value=(set(), {"movie:8"}, {"movie:7"}, []),
        ):
            status, payload = self.post_generation(rev, [self.candidate(10)])
        self.assertEqual(status, 200)
        self.assertEqual(sorted(payload["rotated"]), ["movie:7", "movie:8"])
        self.assertNotIn("movie:9", payload["rotated"])
        self.assertTrue(self.item_by_tmdb(self.current_doc(), 9)["active"])
        rotated_watched = self.item_by_tmdb(self.current_doc(), 7)
        self.assertFalse(rotated_watched["active"])
        self.assertEqual(
            {key: rotated_watched[key] for key in before}, before
        )
        self.assertFalse(self.item_by_tmdb(self.current_doc(), 8)["active"])

    def test_stale_watched_snapshot_is_enforced_and_unavailable_is_soft(self):
        self.seed([make_item(7)], presented=["movie:7"])
        rev = self.current_doc()["revision"]
        with mock.patch(
            "routes.discover._hermes_exclusion_sets",
            return_value=(set(), {"movie:8"}, {"movie:10"}, ["trakt_watched: stale"]),
        ):
            status, payload = self.post_generation(rev, [self.candidate(10)])
        self.assertEqual(status, 200)
        self.assertEqual(payload["rejected"][0]["reason"], "already_watched")

        rev = self.current_doc()["revision"]
        with mock.patch(
            "routes.discover._hermes_exclusion_sets",
            return_value=(set(), {"movie:8"}, set(), ["trakt_watched: unavailable"]),
        ):
            status, payload = self.post_generation(rev, [self.candidate(8)])
        self.assertEqual(status, 200)
        self.assertEqual(payload["accepted"], [])
        self.assertEqual(payload["rejected"][0]["reason"], "already_in_library")


class TrackedGenerationRotationTests(GenerationApiTestCase):
    def test_tracked_active_identity_is_not_required_retain(self):
        self.seed(
            [make_item(7), make_item(8)],
            presented=["movie:7", "movie:8"],
        )
        tracked = {"movie:7"}
        snapshot = discover_routes.LibraryExclusionSnapshot.from_maps(
            {}, {}, status="fresh", last_successful_refresh_at=None
        )
        watched = discover_routes.WatchedSnapshot(frozenset(), None, "fresh")
        with mock.patch.object(
            discover_routes, "_get_tracked_media_ids", return_value=(sorted(tracked), [])
        ):
            context = discover_routes._hermes_generation_context(
                self.current_doc(), snapshot, watched
            )
        retained = {item["type"] + ":" + str(item["tmdb_id"]) for item in context["required_retain"]}
        self.assertNotIn("movie:7", retained)
        self.assertIn("movie:8", retained)

    def test_tracked_active_identity_retain_is_rejected_and_rotated(self):
        tracked = make_item(7, feedback="liked", request_state="requested")
        tracked["feedback_at"] = "2026-02-02T00:00:00Z"
        tracked["requested_at"] = "2026-02-03T00:00:00Z"
        tracked["jellyseerr_request_id"] = 707
        tracked["added_at"] = "2025-12-07T00:00:00Z"
        before = {
            key: tracked[key]
            for key in (
                "id", "identity", "type", "tmdb_id", "feedback", "feedback_at",
                "request_state", "requested_at", "jellyseerr_request_id", "added_at",
            )
        }
        self.seed([tracked, make_item(8)], presented=["movie:7", "movie:8"])
        rev = self.current_doc()["revision"]
        with mock.patch(
            "routes.discover._hermes_exclusion_sets",
            return_value=({"movie:7"}, set(), set(), []),
        ):
            status, payload = self.post_generation(
                rev, [self.candidate(7, retain=True)]
            )
        self.assertEqual(status, 200)
        self.assertEqual(payload["rejected"][0]["reason"], "already_tracked")
        self.assertEqual(payload["rotated"], ["movie:7"])
        rotated = self.item_by_tmdb(self.current_doc(), 7)
        self.assertFalse(rotated["active"])
        self.assertEqual({key: rotated[key] for key in before}, before)
        self.assertTrue(self.item_by_tmdb(self.current_doc(), 8)["active"])

    def test_tracked_active_omission_rotates_but_unrelated_untouched_stays_active(self):
        self.seed(
            [make_item(7), make_item(8)],
            presented=["movie:7", "movie:8"],
        )
        rev = self.current_doc()["revision"]
        with mock.patch(
            "routes.discover._hermes_exclusion_sets",
            return_value=({"movie:7"}, set(), set(), []),
        ):
            status, payload = self.post_generation(rev, [])
        self.assertEqual(status, 200)
        self.assertEqual(payload["rotated"], ["movie:7"])
        self.assertFalse(self.item_by_tmdb(self.current_doc(), 7)["active"])
        self.assertTrue(self.item_by_tmdb(self.current_doc(), 8)["active"])


class HermesGenerationContextContractTests(GenerationApiTestCase):
    def test_get_keeps_watched_filtering_badges_without_generation_context(self):
        self.seed(
            [make_item(1), make_item(2, media_type="tv"), make_item(3)],
            presented=["movie:1", "tv:2", "movie:3"],
        )
        watched = discover_routes.WatchedSnapshot(
            frozenset({"tv:42", "movie:42", "movie:42"}),
            "2026-08-11T12:00:00+00:00",
            "stale",
        )
        library = discover_routes.LibraryExclusionSnapshot.from_maps(
            {1: "movie-jf"}, {2: "tv-jf"}, status="fresh", last_successful_refresh_at=None
        )
        with mock.patch.object(
            discover_routes, "_trakt_watched_snapshot", return_value=watched
        ) as watched_snapshot, mock.patch.object(
            discover_routes, "_library_exclusion_snapshot", return_value=library
        ), mock.patch.object(
            discover_routes, "_enrich_hermes_posters", side_effect=lambda values: values
        ), mock.patch.object(
            discover_routes, "_get_tracked_media_ids", return_value=([], [])
        ), mock.patch.object(
            discover_routes, "send_json", side_effect=lambda _h, _s, payload: setattr(self, "payload", payload)
        ):
            discover_routes.handle_discover_hermes_get(object())
        watched_snapshot.assert_called_once_with()
        self.assertNotIn("context", self.payload)
        self.assertEqual(self.payload["watched_exclusion"]["status"], "stale")
        self.assertEqual(self.payload["items"][0]["excluded_reason"], "in_library")
        self.assertEqual(self.payload["items"][1]["excluded_reason"], "in_library")

    def test_context_normalizes_duplicate_watched_iterable_at_boundary(self):
        watched = discover_routes.WatchedSnapshot(
            ["tv:42", "movie:42", "movie:42"],
            "2026-08-11T12:00:00+00:00",
            "stale",
        )
        snapshot = discover_routes.LibraryExclusionSnapshot.from_maps(
            {}, {}, status="fresh", last_successful_refresh_at=None
        )
        context = discover_routes._hermes_generation_context(
            {"items": []}, snapshot, watched
        )
        self.assertEqual(context["watched_media_ids"], ["movie:42", "tv:42"])

    def test_watched_active_identity_is_absent_from_required_retain(self):
        self.seed(
            [make_item(7), make_item(8, media_type="tv")],
            presented=["movie:7", "tv:8"],
        )
        snapshot = discover_routes.LibraryExclusionSnapshot.from_maps(
            {}, {}, status="fresh", last_successful_refresh_at=None
        )
        watched = discover_routes.WatchedSnapshot(
            frozenset({"movie:7"}), "2026-08-11T12:00:00+00:00", "stale"
        )
        with mock.patch.object(
            discover_routes, "_get_tracked_media_ids", return_value=([], [])
        ):
            context = discover_routes._hermes_generation_context(
                self.current_doc(), snapshot, watched
            )
        self.assertIn("movie:7", context["watched_media_ids"])
        retained = {item["type"] + ":" + str(item["tmdb_id"]) for item in context["required_retain"]}
        self.assertNotIn("movie:7", retained)
        self.assertIn("tv:8", retained)

    def test_unavailable_watched_acquisition_is_soft_and_sanitized(self):
        def fail_watched_fetch(_path):
            raise RuntimeError(
                "credential=SECRET_TOKEN raw-history=Watched Title movie:909"
            )

        watched_service = discover_routes.TraktWatchedService(fail_watched_fetch)
        library = discover_routes.LibraryExclusionSnapshot.from_maps(
            {}, {}, status="fresh", last_successful_refresh_at=None
        )
        with mock.patch.object(
            discover_routes, "_TRAKT_WATCHED_SERVICE", watched_service
        ), mock.patch.object(
            discover_routes,
            "_get_tracked_media_ids",
            return_value=([], ["radarr: SECRET_TOKEN raw-history=Watched Title movie:909"]),
        ), mock.patch.object(
            discover_routes, "_library_exclusion_snapshot", return_value=library
        ), mock.patch("builtins.print") as printed:
            tracked, in_library, watched, errors = discover_routes._hermes_exclusion_sets()
            status, payload = self.post_generation(0, [self.candidate(910)])
            context = discover_routes._hermes_generation_context(
                {"items": []}, library
            )
        self.assertEqual(status, 200)
        self.assertEqual(tracked, set())
        self.assertEqual(in_library, set())
        self.assertEqual(watched, set())
        self.assertEqual(
            errors, ["radarr: unavailable", "trakt_watched: unavailable"]
        )
        self.assertEqual(
            context["context_errors"],
            ["radarr: unavailable", "trakt_watched: unavailable"],
        )
        logged = " ".join(str(call) for call in printed.call_args_list)
        for secret in ("SECRET_TOKEN", "Watched Title", "movie:909"):
            self.assertNotIn(secret, logged)
        for error in context["context_errors"]:
            self.assertNotIn("SECRET_TOKEN", error)
            self.assertNotIn("Watched Title", error)
            self.assertNotIn("movie:909", error)

    def test_prompt_documents_watched_deny_list_and_server_rejection(self):
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "recommendations",
            "HERMES_DISCOVER_PROMPT.md",
        )
        with open(prompt_path, encoding="utf-8") as handle:
            prompt = handle.read()
        self.assertIn("watched_media_ids", prompt)
        self.assertIn('"retain": true', prompt)
        self.assertIn("already_watched", prompt)
        self.assertIn("Trakt watched", prompt)
        self.assertIn("tracked, library, and watched", prompt)

    def test_prompt_uses_normalized_trakt_item_identity_fields(self):
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "recommendations",
            "HERMES_DISCOVER_PROMPT.md",
        )
        with open(prompt_path, encoding="utf-8") as handle:
            prompt = handle.read()
        self.assertIn("items[].type", prompt)
        self.assertIn("items[].tmdb_id", prompt)
        self.assertNotIn("ids.tmdb", prompt)


class FeedbackPatchTests(GenerationApiTestCase):
    def test_patch_requested_status_rejected(self):
        # Request lifecycle is owned by POST /discover/request; a feedback
        # PATCH must never fabricate request_state=requested.
        self.seed([make_item(42)], presented=["movie:42"])
        status, payload = self.request(
            "PATCH", "/discover/hermes/hermes-movie-42", {"status": "requested"}
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        item = self.item_by_tmdb(self.current_doc(), 42)
        self.assertIsNone(item["request_state"])

    def test_patch_feedback_still_accepted(self):
        self.seed([make_item(42)], presented=["movie:42"])
        status, payload = self.request(
            "PATCH", "/discover/hermes/hermes-movie-42", {"status": "liked"}
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        item = self.item_by_tmdb(self.current_doc(), 42)
        self.assertEqual(item["feedback"], "liked")
        self.assertFalse(item["active"])
        self.assertIsNone(item["request_state"])


class RequestPartialSuccessTests(GenerationApiTestCase):
    def test_arr_success_with_store_failure_is_explicit_and_reconcilable(self):
        self.seed([make_item(42)], presented=["movie:42"])
        original_update = self.store.update
        failed = True

        def fail_once(mutator):
            nonlocal failed
            if failed:
                failed = False
                raise OSError("simulated dashboard persistence failure")
            return original_update(mutator)

        with mock.patch.object(self.store, "update", side_effect=fail_once), mock.patch(
            "routes.discover._add_to_arr_unmonitored",
            return_value={
                "service": "radarr",
                "already_added": False,
                "arr_id": 812,
                "title": "Title 42",
                "monitored": False,
            },
        ):
            status, payload = self.request(
                "POST",
                "/discover/request",
                {"mediaType": "movie", "mediaId": 42, "hermesId": "hermes-movie-42"},
            )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["partial_success"])
        self.assertEqual(payload["arr_id"], 812)
        self.assertEqual(payload["jellyseerr_request_id"], 812)
        self.assertFalse(payload["dashboard_state_persisted"])
        self.assertTrue(payload["reconciliation_queued"])
        self.assertEqual(
            payload["message"],
            "Added to Sonarr/Radarr; dashboard synchronization failed.",
        )
        self.assertIsNone(self.item_by_tmdb(self.current_doc(), 42)["request_state"])

        status, reconcile = self.request("POST", "/discover/request/reconcile")
        self.assertEqual(status, 200)
        self.assertEqual(reconcile["reconciled"], 1)
        self.assertEqual(reconcile["pending"], 0)
        item = self.item_by_tmdb(self.current_doc(), 42)
        self.assertEqual(item["request_state"], "requested")
        self.assertEqual(item["jellyseerr_request_id"], 812)

        # Retrying reconciliation is idempotent after the durable mutation.
        status, retry = self.request("POST", "/discover/request/reconcile")
        self.assertEqual(status, 200)
        self.assertEqual(retry["reconciled"], 0)
        self.assertEqual(retry["pending"], 0)

    def test_request_adds_unmonitored_without_search(self):
        self.seed([make_item(42)], presented=["movie:42"])
        with mock.patch(
            "routes.discover._add_to_arr_unmonitored",
            return_value={
                "service": "radarr",
                "already_added": False,
                "arr_id": 901,
                "title": "Title 42",
                "monitored": False,
            },
        ) as add_mock:
            status, payload = self.request(
                "POST",
                "/discover/request",
                {"mediaType": "movie", "mediaId": 42, "hermesId": "hermes-movie-42"},
            )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["service"], "radarr")
        self.assertFalse(payload["monitored"])
        self.assertFalse(payload["already_added"])
        self.assertEqual(payload["arr_id"], 901)
        add_mock.assert_called_once_with("movie", 42)
        item = self.item_by_tmdb(self.current_doc(), 42)
        self.assertEqual(item["request_state"], "requested")
        self.assertEqual(item["jellyseerr_request_id"], 901)
        self.assertFalse(item["active"])

    def test_stale_reconciliation_does_not_overwrite_newer_request_state(self):
        # Failure ordering: queue A (stale), then persist B successfully.
        # Reconciling A must preserve B and drop A as a conflict.
        self.seed([make_item(42)], presented=["movie:42"])
        reconciliation._enqueue_request_reconciliation("hermes-movie-42", 111)

        def _persist_newer(doc):
            item = self.item_by_tmdb(doc, 42)
            rs.apply_request(item, request_id=222)

        self.store.update(_persist_newer)
        before = self.item_by_tmdb(self.current_doc(), 42)
        self.assertEqual(before["jellyseerr_request_id"], 222)
        revision_before = self.current_doc()["revision"]

        status, reconcile = self.request("POST", "/discover/request/reconcile")
        self.assertEqual(status, 200)
        self.assertEqual(reconcile["reconciled"], 0)
        self.assertEqual(reconcile["conflicts"], 1)
        self.assertEqual(reconcile["pending"], 0)

        after = self.item_by_tmdb(self.current_doc(), 42)
        self.assertEqual(after["request_state"], "requested")
        self.assertEqual(after["jellyseerr_request_id"], 222)
        self.assertEqual(after["requested_at"], before["requested_at"])
        self.assertEqual(self.current_doc()["revision"], revision_before)

        status, hermes = self.request("GET", "/discover/hermes")
        self.assertEqual(status, 200)
        self.assertEqual(hermes["pending_request_sync"], [])

    def test_malformed_queue_entries_are_dropped_without_blocking_valid_ones(self):
        self.seed([make_item(42)], presented=["movie:42"])
        with config._reconciliation_lock:
            reconciliation._write_reconciliation_queue(
                [
                    {"hermes_id": "", "jellyseerr_request_id": 1},
                    {"not": "an entry"},
                    {
                        "hermes_id": "hermes-movie-42",
                        "jellyseerr_request_id": 812,
                        "queued_at": "2026-01-01T00:00:00Z",
                    },
                ]
            )

        status, reconcile = self.request("POST", "/discover/request/reconcile")
        self.assertEqual(status, 200)
        self.assertEqual(reconcile["dropped_malformed"], 2)
        self.assertEqual(reconcile["reconciled"], 1)
        self.assertEqual(reconcile["pending"], 0)
        item = self.item_by_tmdb(self.current_doc(), 42)
        self.assertEqual(item["jellyseerr_request_id"], 812)

    def test_get_exposes_pending_request_sync_without_errors(self):
        self.seed([make_item(42)], presented=["movie:42"])
        reconciliation._enqueue_request_reconciliation("hermes-movie-42", 812)
        with config._reconciliation_lock:
            queue = reconciliation._read_reconciliation_queue()
            queue[0]["last_error"] = "OSError"
            reconciliation._write_reconciliation_queue(queue)

        status, payload = self.request("GET", "/discover/hermes")
        self.assertEqual(status, 200)
        self.assertEqual(
            payload["pending_request_sync"],
            [{"id": "hermes-movie-42", "jellyseerr_request_id": 812}],
        )
        for entry in payload["pending_request_sync"]:
            self.assertNotIn("last_error", entry)
            self.assertNotIn("queued_at", entry)

    def test_request_more_queues_and_is_idempotent(self):
        self.seed([make_item(42)], presented=["movie:42"])
        status, payload = self.request("POST", "/discover/hermes/request-more")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["queued"])
        self.assertFalse(payload["already_pending"])
        requested_at = payload["requested_at"]

        status, again = self.request("POST", "/discover/hermes/request-more")
        self.assertEqual(status, 200)
        self.assertTrue(again["already_pending"])
        self.assertEqual(again["requested_at"], requested_at)

        status, hermes = self.request("GET", "/discover/hermes")
        self.assertEqual(status, 200)
        self.assertEqual(
            hermes["generation_request"],
            {"requested_at": requested_at, "status": "pending"},
        )

    def test_successful_generation_clears_request_more_flag(self):
        self.seed([make_item(1)], presented=["movie:1"])
        status, queued = self.request("POST", "/discover/hermes/request-more")
        self.assertEqual(status, 200)
        self.assertTrue(queued["queued"])
        rev = self.current_doc()["revision"]
        status, payload = self.post_generation(
            rev,
            [self.candidate(949, title="Heat")],
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        status, hermes = self.request("GET", "/discover/hermes")
        self.assertEqual(status, 200)
        self.assertIsNone(hermes.get("generation_request"))


class ReconciliationSchedulerTests(unittest.TestCase):
    def setUp(self):
        reconciliation.stop_reconciliation_scheduler(timeout=1.0)
        self.calls = []

    def tearDown(self):
        reconciliation.stop_reconciliation_scheduler(timeout=1.0)

    def test_scheduler_loop_runs_startup_then_interval_without_sleep(self):
        stop = threading.Event()
        waits = []

        def wait(event, timeout):
            waits.append(timeout)
            if len(waits) >= 2:
                event.set()
                return True
            return False

        def run_cycle():
            self.calls.append("cycle")

        reconciliation._reconciliation_scheduler_loop(30, stop, run_cycle, wait)
        self.assertEqual(self.calls, ["cycle", "cycle"])
        self.assertEqual(waits, [30, 30])

    def test_run_reconciliation_cycle_skips_overlapping_invocation(self):
        entered = threading.Event()
        release = threading.Event()

        def blocking_reconcile():
            entered.set()
            release.wait(timeout=2)
            return {"ok": True, "reconciled": 0, "pending": 0}

        with mock.patch.object(reconciliation, "_reconcile_pending_requests", side_effect=blocking_reconcile):
            worker = threading.Thread(target=reconciliation.run_reconciliation_cycle)
            worker.start()
            self.assertTrue(entered.wait(timeout=2))
            skipped = reconciliation.run_reconciliation_cycle()
            self.assertTrue(skipped.get("skipped"))
            release.set()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())

    def test_stop_reconciliation_scheduler_joins_thread(self):
        started = reconciliation.start_reconciliation_scheduler(interval_seconds=60)
        self.assertTrue(started)
        self.assertTrue(reconciliation.start_reconciliation_scheduler(interval_seconds=60) is False)
        self.assertTrue(reconciliation.stop_reconciliation_scheduler(timeout=2.0))
        self.assertIsNone(config._reconcile_thread)


if __name__ == "__main__":
    unittest.main()
