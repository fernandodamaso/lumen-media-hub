#!/usr/bin/env python3
import os
import shutil
import tempfile
import unittest
import json
import threading
from unittest import mock

from ai_generation import AiGenerationCoordinator, public_generation
from recommendations_store import RecommendationStore
import reconciliation


NOW = "2026-08-29T10:00:00Z"


class AiGenerationCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ai-generation-test-")
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.store = RecommendationStore(os.path.join(self.tmpdir, "recommendations.json"))
        self.pool = {
            "candidates": [
                {
                    "identity": "movie:42",
                    "type": "movie",
                    "title": "Fixture",
                    "year": 2024,
                    "tmdb_id": 42,
                    "overview": "A complete verified candidate.",
                    "rating": 8.2,
                    "signals": ["trakt", "jellyseerr"],
                    "poster_path": "/fixture.jpg",
                }
            ],
            "taste": {"liked": [], "disliked": [], "watched": [], "skipped": []},
            "required_retain": [],
        }
        self.coordinator = AiGenerationCoordinator(
            self.store,
            candidate_builder=lambda _doc: self.pool,
            now=lambda: NOW,
            lease_token=lambda: "lease-token",
            job_id=lambda: "job-1",
            lease_seconds=300,
        )

    def test_queue_is_idempotent_while_work_is_non_terminal(self):
        first = self.coordinator.queue("on_demand", 10)
        revision = self.store.load()["revision"]
        second = self.coordinator.queue("scheduled", 5)

        self.assertEqual(first["queued"], True)
        self.assertEqual(second["queued"], False)
        self.assertEqual(second["already_pending"], True)
        generation = self.store.load()["generation"]
        self.assertEqual(generation["id"], "job-1")
        self.assertEqual(generation["trigger"], "on_demand")
        self.assertEqual(generation["status"], "queued")
        self.assertEqual(self.store.load()["revision"], revision)

    def test_queue_rejects_counts_outside_the_worker_contract(self):
        for desired_count in (0, 101):
            with self.subTest(desired_count=desired_count):
                with self.assertRaises(ValueError):
                    self.coordinator.queue("on_demand", desired_count)

        self.assertEqual(self.store.load()["generation"], None)

    def test_empty_claim_poll_does_not_mutate_store_revision(self):
        self.assertEqual(self.coordinator.claim(), None)
        self.assertEqual(self.store.load()["revision"], 0)

    def test_claim_returns_only_verified_pool_and_private_lease(self):
        self.coordinator.queue("on_demand", 10)

        claimed = self.coordinator.claim()

        self.assertEqual(claimed["id"], "job-1")
        self.assertEqual(claimed["lease_token"], "lease-token")
        self.assertEqual(claimed["desired_count"], 10)
        self.assertEqual(claimed["candidates"], self.pool["candidates"])
        self.assertEqual(claimed["taste"], self.pool["taste"])
        generation = self.store.load()["generation"]
        self.assertEqual(generation["status"], "running")
        self.assertEqual(generation["attempt"], 1)
        self.assertIsInstance(generation["base_revision"], int)

    def test_invalid_model_identity_fails_without_mutating_picks_or_history(self):
        self.coordinator.queue("on_demand", 10)
        claimed = self.coordinator.claim()
        before = self.store.load()

        result = self.coordinator.complete(
            "job-1",
            claimed["lease_token"],
            [{"identity": "movie:999", "reason": "Invented."}],
        )

        after = self.store.load()
        self.assertEqual(result["ok"], False)
        self.assertEqual(result["code"], "invalid_output")
        self.assertEqual(after["items"], before["items"])
        self.assertEqual(after["presented_media_ids"], before["presented_media_ids"])
        self.assertEqual(after["generation"]["status"], "failed")

    def test_completion_joins_server_metadata_and_commits_ai_pick(self):
        self.coordinator.queue("on_demand", 10)
        claimed = self.coordinator.claim()

        result = self.coordinator.complete(
            "job-1",
            claimed["lease_token"],
            [{"identity": "movie:42", "reason": "Matches your taste."}],
        )

        self.assertEqual(result["ok"], True)
        self.assertEqual(result["counts"]["accepted"], 1)
        doc = self.store.load()
        self.assertEqual(doc["presented_media_ids"], ["movie:42"])
        self.assertEqual(doc["generation"]["status"], "succeeded")
        item = doc["items"][0]
        self.assertEqual(item["id"], "ai-movie-42")
        self.assertEqual(item["source"], "ai")
        self.assertEqual(item["title"], "Fixture")
        self.assertEqual(item["reason"], "Matches your taste.")
        self.assertEqual(item["poster_path"], "/fixture.jpg")

    def test_completion_rejects_a_pick_that_became_authoritatively_excluded(self):
        coordinator = AiGenerationCoordinator(
            self.store,
            candidate_builder=lambda _doc: self.pool,
            commit_exclusions=lambda _doc: {
                "tracked": ["movie:42"],
                "in_library": [],
                "watched": [],
                "errors": [],
            },
            now=lambda: NOW,
            lease_token=lambda: "lease-token",
            job_id=lambda: "job-1",
        )
        coordinator.queue("on_demand", 10)
        claimed = coordinator.claim()

        result = coordinator.complete(
            "job-1",
            claimed["lease_token"],
            [{"identity": "movie:42", "reason": "No longer eligible."}],
        )

        self.assertEqual(result, {"ok": False, "code": "stale_revision"})
        doc = self.store.load()
        self.assertEqual(doc["items"], [])
        self.assertEqual(doc["presented_media_ids"], [])
        self.assertEqual(doc["generation"]["status"], "failed")

    def test_completion_fails_closed_when_authoritative_exclusions_are_unavailable(self):
        coordinator = AiGenerationCoordinator(
            self.store,
            candidate_builder=lambda _doc: self.pool,
            commit_exclusions=lambda _doc: {
                "tracked": [],
                "in_library": [],
                "watched": [],
                "errors": ["jellyfin: unavailable"],
            },
            now=lambda: NOW,
            lease_token=lambda: "lease-token",
            job_id=lambda: "job-1",
        )
        coordinator.queue("on_demand", 10)
        claimed = coordinator.claim()

        result = coordinator.complete(
            "job-1",
            claimed["lease_token"],
            [{"identity": "movie:42", "reason": "Cannot verify exclusions."}],
        )

        self.assertEqual(result, {"ok": False, "code": "candidate_unavailable"})
        self.assertEqual(self.store.load()["items"], [])

    def test_concurrent_claims_issue_only_one_private_lease(self):
        self.coordinator.queue("on_demand", 10)
        results = []
        threads = [threading.Thread(target=lambda: results.append(self.coordinator.claim())) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sum(result is not None for result in results), 1)

    def test_duplicate_or_empty_output_fails_without_accepting_any_item(self):
        for picks in ([], [
            {"identity": "movie:42", "reason": "One"},
            {"identity": "movie:42", "reason": "Two"},
        ]):
            with self.subTest(picks=picks):
                store = RecommendationStore(os.path.join(self.tmpdir, f"{len(picks)}.json"))
                coordinator = AiGenerationCoordinator(
                    store, candidate_builder=lambda _doc: self.pool,
                    now=lambda: NOW, lease_token=lambda: "lease", job_id=lambda: "job",
                )
                coordinator.queue("on_demand", 10)
                claimed = coordinator.claim()
                result = coordinator.complete("job", claimed["lease_token"], picks)
                self.assertEqual(result, {"ok": False, "code": "invalid_output"})
                self.assertEqual(store.load()["items"], [])

    def test_stale_revision_fails_without_overwriting_intervening_feedback(self):
        self.coordinator.queue("on_demand", 10)
        claimed = self.coordinator.claim()
        self.store.update(lambda doc: doc.setdefault("audit_marker", None))

        result = self.coordinator.complete(
            "job-1", claimed["lease_token"],
            [{"identity": "movie:42", "reason": "Fit."}],
        )

        self.assertEqual(result["code"], "stale_revision")
        self.assertEqual(self.store.load()["items"], [])

    def test_expired_lease_is_failed_and_stale_worker_cannot_complete(self):
        clock = ["2026-08-29T10:00:00Z"]
        coordinator = AiGenerationCoordinator(
            self.store,
            candidate_builder=lambda _doc: self.pool,
            now=lambda: clock[0],
            lease_token=lambda: "expiring-lease",
            job_id=lambda: "expiring-job",
            lease_seconds=300,
        )
        coordinator.queue("on_demand", 10)
        claimed = coordinator.claim()
        clock[0] = "2026-08-29T10:06:00Z"

        result = coordinator.complete(
            "expiring-job", claimed["lease_token"],
            [{"identity": "movie:42", "reason": "Too late."}],
        )

        self.assertEqual(result, {"ok": False, "code": "stale_revision"})
        generation = self.store.load()["generation"]
        self.assertEqual(generation["status"], "failed")
        self.assertEqual(generation["error_code"], "provider_failure")
        self.assertEqual(self.store.load()["items"], [])

    def test_public_generation_projection_never_contains_pool_taste_revision_or_lease(self):
        self.coordinator.queue("on_demand", 10)
        self.coordinator.claim()
        projected = public_generation(self.store.load()["generation"])
        self.assertTrue(projected)
        for private in ("candidates", "taste", "required_retain", "base_revision", "lease_token", "lease_expires_at"):
            self.assertNotIn(private, projected)

    def test_legacy_generation_request_imports_once_as_on_demand_job(self):
        legacy_path = os.path.join(self.tmpdir, "generation-request.json")
        with open(legacy_path, "w", encoding="utf-8") as handle:
            json.dump({"status": "pending", "requested_at": NOW}, handle)

        with mock.patch.object(reconciliation.settings, "GENERATION_REQUEST_PATH", legacy_path):
            result = reconciliation.migrate_legacy_generation_request(self.coordinator, 10)

        self.assertEqual(result["queued"], True)
        self.assertFalse(os.path.exists(legacy_path))
        self.assertEqual(self.store.load()["generation"]["trigger"], "on_demand")

    def test_legacy_reconciliation_entry_is_normalized_to_ai_pick_id(self):
        normalized = reconciliation._normalize_reconciliation_entry(
            {"hermes_id": "hermes-movie-42", "jellyseerr_request_id": 7}
        )

        self.assertEqual(normalized["ai_pick_id"], "ai-movie-42")


if __name__ == "__main__":
    unittest.main()
