#!/usr/bin/env python3
"""Unit tests for Discover -> Trakt history sync."""

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import config
import routes.discover as discover_routes
from clients.trakt import TraktAuthError, TraktHttpError
from recommendations_store import RecommendationStore, apply_feedback
from trakt_history_sync import (
    TraktHistorySyncService,
    apply_watched_feedback,
    cancel_pending_trakt_history_event,
    clear_local_synced_identities,
    clear_rate_limit_state,
    create_trakt_history_event,
    deliver_trakt_history_for_item,
    get_trakt_history_sync_service,
    local_synced_identities,
    public_trakt_history_sync,
    reconcile_trakt_history_sync,
    register_local_synced_identity,
)


def make_item(tmdb_id, media_type="movie", **overrides):
    identity = f"{media_type}:{tmdb_id}"
    item = {
        "id": f"hermes-{media_type}-{tmdb_id}",
        "identity": identity,
        "source": "hermes",
        "type": media_type,
        "title": f"Title {tmdb_id}",
        "year": 2000,
        "tmdb_id": tmdb_id,
        "reason": "fixture",
        "active": True,
        "feedback": None,
        "feedback_at": None,
        "request_state": None,
        "request_provider": None,
        "requested_at": None,
        "jellyseerr_request_id": None,
        "added_at": "2026-01-01T00:00:00Z",
    }
    item.update(overrides)
    return item


def base_doc(*items):
    presented = [item["identity"] for item in items]
    return {
        "version": 4,
        "revision": 1,
        "updated_at": "2026-01-01T00:00:00Z",
        "presented_media_ids": presented,
        "items": list(items),
    }


class FakeTraktClient:
    def __init__(self, *, get_pages=None, post_results=None, post_error=None):
        self.get_pages = list(get_pages or [])
        self.post_results = list(post_results or [])
        self.post_error = post_error
        self.post_calls = []
        self.get_calls = []

    def get_page(self, path):
        self.get_calls.append(path)
        if not self.get_pages:
            return mock.Mock(payload=[])
        response = self.get_pages.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, tuple):
            if len(response) == 3:
                status, payload, headers = response
                if status >= 400:
                    raise TraktHttpError(status, payload=payload, headers=headers or {})
                return mock.Mock(payload=payload, headers=headers or {})
            status, payload = response
            if status >= 400:
                raise TraktHttpError(status, payload=payload, headers={})
        if isinstance(response, dict):
            return mock.Mock(
                payload=response.get("payload", []),
                headers=response.get("headers", {}),
            )
        return mock.Mock(payload=response, headers={})

    def post(self, path, payload):
        self.post_calls.append((path, payload))
        if self.post_error:
            raise self.post_error
        if self.post_results:
            result = self.post_results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return {"added": {"movies": 1, "episodes": 0}}


class TraktHistorySyncModuleTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="trakt-sync-test-")
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.path = os.path.join(self.tmpdir, "recommendations.json")
        self.store = RecommendationStore(self.path)
        clear_local_synced_identities()
        clear_rate_limit_state()
        self.now = 1_700_000_000.0
        self.clock = lambda: self.now

    def service(self, client):
        return TraktHistorySyncService(
            lambda: client,
            self.store,
            clock=self.clock,
            refresh_watched_snapshot=lambda identity: None,
        )

    def seed(self, item):
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(base_doc(item), handle)

    def test_apply_watched_feedback_is_atomic(self):
        item = make_item(42)
        created = apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        self.assertTrue(created)
        self.assertEqual(item["feedback"], "watched")
        self.assertFalse(item["active"])
        event = item["trakt_history_event"]
        self.assertEqual(event["status"], "pending")
        self.assertEqual(event["identity"], "movie:42")
        self.assertEqual(event["watched_at"], "2026-08-13T17:00:00Z")

    def test_reapply_watched_does_not_create_second_event(self):
        item = make_item(7)
        apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        first_id = item["trakt_history_event"]["event_id"]
        self.assertFalse(apply_watched_feedback(item, now="2026-08-13T17:01:00Z"))
        self.assertEqual(item["trakt_history_event"]["event_id"], first_id)

    def test_public_projection_exposes_status_only(self):
        event = create_trakt_history_event(make_item(1))
        event["attempts"] = 3
        event["trakt_history_ids"] = [999]
        self.assertEqual(public_trakt_history_sync(event), {"status": "pending"})

    def test_movie_post_payload_and_sync(self):
        item = make_item(155)
        apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        self.seed(item)
        client = FakeTraktClient(
            get_pages=[
                [],
                [{"id": 1001, "watched_at": "2026-08-13T17:00:00Z", "movie": {"ids": {"tmdb": 155}}}],
            ]
        )
        result = self.service(client).deliver_item(item["id"])
        self.assertEqual(result, {"status": "synced"})
        self.assertEqual(len(client.post_calls), 1)
        self.assertEqual(client.post_calls[0][1]["movies"][0]["ids"]["tmdb"], 155)
        saved = self.store.load()["items"][0]["trakt_history_event"]
        self.assertEqual(saved["status"], "synced")
        self.assertEqual(saved["trakt_history_ids"], [1001])

    def test_show_post_payload(self):
        item = make_item(60, media_type="tv")
        apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        self.seed(item)
        client = FakeTraktClient(
            get_pages=[
                [],
                [
                    {
                        "id": 2001,
                        "watched_at": "2026-08-13T17:00:00Z",
                        "show": {"ids": {"tmdb": 60}},
                        "episode": {"ids": {"tmdb": 1}},
                    }
                ],
            ]
        )
        result = self.service(client).deliver_item(item["id"])
        self.assertEqual(result, {"status": "synced"})
        self.assertIn("shows", client.post_calls[0][1])
        self.assertTrue(
            any("/sync/history/episodes?" in call for call in client.get_calls),
            client.get_calls,
        )

    def test_get_match_prevents_duplicate_post(self):
        item = make_item(9)
        apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        self.seed(item)
        client = FakeTraktClient(
            get_pages=[[{"id": 42, "watched_at": "2026-08-13T17:00:00Z", "movie": {"ids": {"tmdb": 9}}}]]
        )
        result = self.service(client).deliver_item(item["id"])
        self.assertEqual(result, {"status": "synced"})
        self.assertEqual(client.post_calls, [])

    def test_oauth_failure_marks_reconnect_required(self):
        item = make_item(11)
        apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        self.seed(item)

        class AuthClient:
            def get_page(self, path):
                raise TraktAuthError()

        result = self.service(AuthClient()).deliver_item(item["id"])
        self.assertEqual(result, {"status": "reconnect_required"})

    def test_429_honors_retry_after(self):
        item = make_item(12)
        apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        self.seed(item)
        client = FakeTraktClient(
            get_pages=[TraktHttpError(429, payload={}, headers={"Retry-After": "120"})]
        )
        result = self.service(client).deliver_item(item["id"])
        self.assertEqual(result, {"status": "pending"})
        event = self.store.load()["items"][0]["trakt_history_event"]
        self.assertEqual(event["attempts"], 1)
        self.assertEqual(event["next_attempt_at"], datetime_from_offset(self.now + 120))

    def test_backoff_caps_at_fifteen_minutes(self):
        item = make_item(13)
        apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        self.seed(item)
        client = FakeTraktClient(get_pages=[TraktHttpError(503, payload={}, headers={})])
        service = self.service(client)
        for expected in (30, 60, 120, 240, 480, 900, 900):
            service.deliver_item(item["id"])
            event = self.store.load()["items"][0]["trakt_history_event"]
            self.assertEqual(
                event["next_attempt_at"],
                datetime_from_offset(self.now + expected),
            )
            event["next_attempt_at"] = "2026-01-01T00:00:00Z"
            self.store.update(lambda doc: doc["items"][0].update({"trakt_history_event": event}))

    def test_ambiguous_post_does_not_post_again(self):
        item = make_item(14)
        apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        self.seed(item)
        client = FakeTraktClient(get_pages=[[], []])
        service = self.service(client)
        service.deliver_item(item["id"])
        self.assertEqual(len(client.post_calls), 1)
        event = self.store.load()["items"][0]["trakt_history_event"]
        event["next_attempt_at"] = "2026-01-01T00:00:00Z"
        self.store.update(lambda doc: doc["items"][0].update({"trakt_history_event": event}))
        service.deliver_item(item["id"])
        self.assertEqual(len(client.post_calls), 1)

    def test_not_found_marks_failed(self):
        item = make_item(15)
        apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        self.seed(item)
        client = FakeTraktClient(
            get_pages=[[]],
            post_error=TraktHttpError(
                422,
                payload={"not_found": {"movies": [{"ids": {"tmdb": 15}}]}},
                headers={},
            ),
        )
        result = self.service(client).deliver_item(item["id"])
        self.assertEqual(result, {"status": "failed"})

    def test_liked_feedback_never_posts(self):
        item = make_item(16)
        apply_feedback(item, "liked")
        self.seed(item)
        client = FakeTraktClient()
        self.service(client).reconcile_due_events()
        self.assertEqual(client.post_calls, [])

    def test_trakt_minute_precision_matches_history(self):
        item = make_item(18)
        apply_watched_feedback(item, now="2026-08-13T17:00:45Z")
        self.assertEqual(item["trakt_history_event"]["watched_at"], "2026-08-13T17:00:00Z")
        self.seed(item)
        client = FakeTraktClient(
            get_pages=[
                [],
                [
                    {
                        "id": 88,
                        "watched_at": "2026-08-13T17:00:00.000Z",
                        "movie": {"ids": {"tmdb": 18}},
                    }
                ],
            ]
        )
        result = self.service(client).deliver_item(item["id"])
        self.assertEqual(result, {"status": "synced"})
        get_path = client.get_calls[-1]
        self.assertIn("start_at=2026-08-13T17%3A00%3A00Z", get_path)
        self.assertIn("end_at=2026-08-13T17%3A00%3A59Z", get_path)

    def test_post_success_body_not_found_marks_failed(self):
        item = make_item(19)
        apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        self.seed(item)
        client = FakeTraktClient(
            get_pages=[[]],
            post_results=[{"not_found": {"movies": [{"ids": {"tmdb": 19}}]}, "added": {"movies": 0}}],
        )
        result = self.service(client).deliver_item(item["id"])
        self.assertEqual(result, {"status": "failed"})

    def test_cancel_pending_event_on_feedback_change(self):
        item = make_item(20)
        apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        self.assertTrue(cancel_pending_trakt_history_event(item))
        self.assertNotIn("trakt_history_event", item)

    def test_apply_feedback_clears_undelivered_event(self):
        item = make_item(20)
        apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        apply_feedback(item, "liked")
        self.assertNotIn("trakt_history_event", item)

    def test_delivery_skips_when_feedback_is_not_watched(self):
        item = make_item(25)
        apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        item["feedback"] = "liked"
        self.seed(item)
        client = FakeTraktClient(get_pages=[[]])
        result = self.service(client).deliver_item(item["id"])
        self.assertIsNone(result)
        self.assertEqual(client.get_calls, [])
        self.assertNotIn(
            "trakt_history_event",
            self.store.load()["items"][0],
        )

    def test_reconnect_required_is_retried_when_due(self):
        item = make_item(21)
        apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        item["trakt_history_event"]["status"] = "reconnect_required"
        item["trakt_history_event"]["next_attempt_at"] = "2026-01-01T00:00:00Z"
        self.seed(item)
        client = FakeTraktClient(
            get_pages=[
                [{"id": 91, "watched_at": "2026-08-13T17:00:00Z", "movie": {"ids": {"tmdb": 21}}}]
            ]
        )
        result = self.service(client).deliver_item(item["id"])
        self.assertEqual(result, {"status": "synced"})
        self.assertEqual(client.post_calls, [])

    def test_history_match_paginates_before_post(self):
        item = make_item(22)
        apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        self.seed(item)
        page_one = [
            {
                "id": 1000 + index,
                "watched_at": "2026-08-13T17:00:00.000Z",
                "movie": {"ids": {"tmdb": 999}},
            }
            for index in range(100)
        ]
        page_two = [
            {
                "id": 922,
                "watched_at": "2026-08-13T17:00:00.000Z",
                "movie": {"ids": {"tmdb": 22}},
            }
        ]
        client = FakeTraktClient(
            get_pages=[
                {
                    "payload": page_one,
                    "headers": {
                        "X-Pagination-Page": "1",
                        "X-Pagination-Page-Count": "2",
                    },
                },
                {
                    "payload": page_two,
                    "headers": {
                        "X-Pagination-Page": "2",
                        "X-Pagination-Page-Count": "2",
                    },
                },
            ]
        )
        result = self.service(client).deliver_item(item["id"])
        self.assertEqual(result, {"status": "synced"})
        self.assertEqual(client.post_calls, [])
        self.assertEqual(len(client.get_calls), 2)

    def test_reconcile_stops_batch_after_429(self):
        first = make_item(23)
        second = make_item(24)
        apply_watched_feedback(first, now="2026-08-13T17:00:00Z")
        apply_watched_feedback(second, now="2026-08-13T17:00:01Z")
        doc = base_doc(first)
        doc["items"].append(second)
        doc["presented_media_ids"] = [first["identity"], second["identity"]]
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(doc, handle)
        client = FakeTraktClient(
            get_pages=[TraktHttpError(429, payload={}, headers={"Retry-After": "120"})]
        )
        service = self.service(client)
        summary = service.reconcile_due_events()
        self.assertEqual(summary["attempted"], 1)
        self.assertEqual(len(client.get_calls), 1)
        second_event = self.store.load()["items"][1]["trakt_history_event"]
        self.assertEqual(
            second_event["next_attempt_at"],
            datetime_from_offset(self.now + 120),
        )

    def test_local_synced_identity_expires(self):
        clear_local_synced_identities()
        register_local_synced_identity("movie:55", clock=self.clock)
        self.assertIn("movie:55", local_synced_identities(clock=self.clock))
        self.now += 16 * 60
        self.assertNotIn("movie:55", local_synced_identities(clock=self.clock))

    def test_restart_persistence_completes_once(self):
        item = make_item(17)
        apply_watched_feedback(item, now="2026-08-13T17:00:00Z")
        self.seed(item)
        client = FakeTraktClient(
            get_pages=[
                [],
                [{"id": 77, "watched_at": "2026-08-13T17:00:00Z", "movie": {"ids": {"tmdb": 17}}}],
            ]
        )
        service = self.service(client)
        service.deliver_item(item["id"])
        reloaded = TraktHistorySyncService(lambda: client, self.store, clock=self.clock)
        reloaded.deliver_item(item["id"])
        self.assertEqual(len(client.post_calls), 1)
        self.assertEqual(
            self.store.load()["items"][0]["trakt_history_event"]["status"],
            "synced",
        )


def datetime_from_offset(seconds):
    from datetime import datetime, timezone

    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DiscoverPatchTraktSyncTests(unittest.TestCase):
    def test_show_requires_confirmation_guard(self):
        self.assertTrue(
            issubclass(
                discover_routes.ShowWatchConfirmationRequired,
                Exception,
            )
        )


if __name__ == "__main__":
    unittest.main()
