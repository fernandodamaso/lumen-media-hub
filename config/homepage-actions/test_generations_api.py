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
        self._old_reconciliation_path = config.RECONCILIATION_PATH
        self._old_generation_request_path = config.GENERATION_REQUEST_PATH

        config.RECOMMENDATIONS_STORE = self.store
        config.ACTIONS_TOKEN = TOKEN
        config.RECONCILIATION_PATH = os.path.join(self.tmpdir, "reconciliation.json")
        config.GENERATION_REQUEST_PATH = os.path.join(
            self.tmpdir, "generation-request.json"
        )
        discover_routes._tracked_media_cache["expires"] = 0.0
        discover_routes._tracked_media_cache["ids"] = []
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

    def request(self, method, path, body=None, token=TOKEN):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["X-Actions-Token"] = token
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
    def test_get_exposes_v2_state_without_legacy_status(self):
        self.seed(
            [make_item(1), make_item(2, active=False), make_item(3, feedback="liked")],
            presented=["movie:1", "movie:2", "movie:3"],
        )
        status, payload = self.request("GET", "/discover/hermes")
        self.assertEqual(status, 200)
        self.assertEqual(payload["revision"], self.current_doc()["revision"])
        self.assertEqual(payload["presented_media_ids"], ["movie:1", "movie:2", "movie:3"])
        by_tmdb = {item["tmdb_id"]: item for item in payload["items"]}
        self.assertTrue(by_tmdb[1]["active"])
        self.assertFalse(by_tmdb[2]["active"])
        self.assertEqual(by_tmdb[2]["feedback"], None)
        self.assertEqual(by_tmdb[3]["feedback"], "liked")
        self.assertFalse(by_tmdb[3]["active"])
        for item in payload["items"]:
            self.assertNotIn("status", item)

    def test_get_exposes_generation_context(self):
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
            "routes.discover._get_in_library_media_ids",
            return_value=(["movie:300"], []),
        ):
            status, payload = self.request("GET", "/discover/hermes")
        self.assertEqual(status, 200)
        context = payload["context"]
        self.assertEqual(context["tracked_media_ids"], ["movie:100", "tv:200"])
        self.assertEqual(context["in_library_media_ids"], ["movie:300"])
        self.assertEqual(sorted(context["required_retain"]), ["movie:1"])
        self.assertEqual(
            [entry["identity"] for entry in context["taste"]["liked"]], ["movie:2"]
        )
        self.assertEqual(
            [entry["identity"] for entry in context["taste"]["disliked"]], ["movie:3"]
        )
        self.assertEqual(
            [entry["identity"] for entry in context["taste"]["skipped"]], ["movie:4"]
        )
        self.assertEqual(
            [entry["identity"] for entry in context["taste"]["watched"]],
            ["movie:2", "movie:5"],
        )
        self.assertNotIn("context_errors", context)

    def test_retired_upsert_route_returns_410(self):
        status, payload = self.request(
            "POST", "/discover/hermes", {"tmdb_id": 42, "title": "Heat"}
        )
        self.assertEqual(status, 410)
        self.assertFalse(payload["ok"])
        self.assertIn("generations", payload["use"])
        self.assertEqual(self.current_doc()["items"], [])


class ExclusionEnforcementTests(GenerationApiTestCase):
    def test_already_tracked_candidate_rejected(self):
        with mock.patch(
            "routes.discover._hermes_exclusion_sets",
            return_value=({"movie:777"}, set(), []),
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
            return_value=(set(), {"movie:888"}, []),
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
            return_value=({"movie:999"}, {"movie:999"}, []),
        ):
            status, payload = self.post_generation(0, [self.candidate(999)])
        self.assertEqual(status, 200)
        self.assertEqual(payload["rejected"][0]["reason"], "already_tracked")


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
