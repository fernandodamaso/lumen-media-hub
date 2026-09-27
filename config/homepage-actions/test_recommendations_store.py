#!/usr/bin/env python3
"""Unit tests for recommendations_store (v4 schema, migration, transactions).

Run from the repo root:
    python -m unittest discover -s config/homepage-actions -p "test_*.py" -t .
or from inside config/homepage-actions:
    python -m unittest test_recommendations_store -v
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import recommendations_store as rs

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LIVE_V1_PATH = os.path.join(
    REPO_ROOT, "config", "recommendations", "recommendations.json"
)
SCHEMA_PATH = os.path.join(REPO_ROOT, "config", "recommendations", "schema-v2.json")
SCHEMA_V3_PATH = os.path.join(REPO_ROOT, "config", "recommendations", "schema-v3.json")
SCHEMA_V4_PATH = os.path.join(REPO_ROOT, "config", "recommendations", "schema-v4.json")
EXAMPLE_PATH = os.path.join(
    REPO_ROOT, "config", "recommendations", "recommendations.example.json"
)


def make_v1(statuses):
    items = []
    for i, status in enumerate(statuses, start=1):
        items.append(
            {
                "id": f"hermes-{i}",
                "source": "hermes",
                "type": "movie",
                "title": f"Title {i}",
                "year": 2000 + i,
                "tmdb_id": i,
                "reason": "fixture",
                "status": status,
                "in_library": False,
                "jellyfin_id": None,
                "added_at": "2026-01-01T00:00:00",
                "feedback_at": None,
                "notes": "",
            }
        )
    return {
        "version": 1,
        "updated_at": "2026-01-01T00:00:00",
        "items": items,
        "seen_tmdb_ids": [1000 + i for i in range(len(statuses))],
    }


def copy_item(item, **changes):
    clone = json.loads(json.dumps(item))
    clone.update(changes)
    return clone


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="recstore-test-")
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.path = os.path.join(self.tmpdir, "recommendations.json")
        self.store = rs.RecommendationStore(self.path)

    def write_json(self, data):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def read_raw(self):
        with open(self.path, encoding="utf-8") as fh:
            return fh.read()

    def read_json(self):
        return json.loads(self.read_raw())


class MigrationTests(StoreTestCase):
    def test_ensure_current_upgrades_legacy_ai_v4_request_providers_with_backup(self):
        generation = {
            "id": "generation-1",
            "status": "running",
            "trigger": "on_demand",
            "requested_at": "2026-08-29T12:00:00Z",
            "started_at": "2026-08-29T12:00:01Z",
            "finished_at": None,
            "desired_count": 10,
            "attempt": 1,
            "lease_expires_at": "2026-08-29T12:05:00Z",
            "lease_token": "lease-1",
            "base_revision": 19,
            "candidates": [],
            "taste": {},
            "required_retain": [],
            "error_code": None,
            "counts": None,
        }
        legacy_v4 = {
            "version": 4,
            "revision": 19,
            "updated_at": "2026-08-29T12:00:00Z",
            "presented_media_ids": ["movie:42", "tv:84"],
            "items": [
                {
                    "id": "ai-movie-42",
                    "identity": "movie:42",
                    "source": "ai",
                    "type": "movie",
                    "title": "Requested",
                    "year": 2024,
                    "tmdb_id": 42,
                    "reason": "fixture",
                    "active": False,
                    "feedback": None,
                    "feedback_at": None,
                    "request_state": "requested",
                    "requested_at": "2026-08-29T11:00:00Z",
                    "jellyseerr_request_id": 101,
                    "added_at": "2026-08-01T00:00:00Z",
                },
                {
                    "id": "ai-tv-84",
                    "identity": "tv:84",
                    "source": "ai",
                    "type": "tv",
                    "title": "Unrequested",
                    "year": 2025,
                    "tmdb_id": 84,
                    "reason": "fixture",
                    "active": True,
                    "feedback": None,
                    "feedback_at": None,
                    "request_state": None,
                    "requested_at": None,
                    "jellyseerr_request_id": None,
                    "added_at": "2026-08-01T00:00:00Z",
                },
            ],
            "generation": generation,
        }
        self.write_json(legacy_v4)
        original = self.read_raw()

        migrated = self.store.ensure_current()

        self.assertEqual(migrated["items"][0]["request_provider"], "arr_legacy")
        self.assertIsNone(migrated["items"][1]["request_provider"])
        self.assertEqual(migrated["generation"], generation)
        self.assertEqual(migrated["revision"], 19)
        self.assertTrue(rs.validate_v4(migrated))
        self.assertEqual(self.read_json(), migrated)
        backup_path = f"{self.path}.v4-pre-request-provider.bak"
        with open(backup_path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), original)

        with open(backup_path, "w", encoding="utf-8") as fh:
            fh.write("keep-existing-backup")
        self.store.ensure_current()
        with open(backup_path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "keep-existing-backup")

    def test_legacy_ai_v4_migration_rejects_mixed_provider_shape_without_rewrite(self):
        mixed_v4 = {
            "version": 4,
            "revision": 1,
            "updated_at": "2026-08-29T12:00:00Z",
            "presented_media_ids": ["movie:42", "tv:84"],
            "items": [
                {
                    "id": "ai-movie-42",
                    "identity": "movie:42",
                    "source": "ai",
                    "type": "movie",
                    "title": "Current",
                    "year": 2024,
                    "tmdb_id": 42,
                    "reason": "fixture",
                    "active": True,
                    "feedback": None,
                    "feedback_at": None,
                    "request_state": None,
                    "request_provider": None,
                    "requested_at": None,
                    "jellyseerr_request_id": None,
                    "added_at": "2026-08-01T00:00:00Z",
                },
                {
                    "id": "ai-tv-84",
                    "identity": "tv:84",
                    "source": "ai",
                    "type": "tv",
                    "title": "Legacy",
                    "year": 2025,
                    "tmdb_id": 84,
                    "reason": "fixture",
                    "active": True,
                    "feedback": None,
                    "feedback_at": None,
                    "request_state": None,
                    "requested_at": None,
                    "jellyseerr_request_id": None,
                    "added_at": "2026-08-01T00:00:00Z",
                },
            ],
            "generation": None,
        }
        self.write_json(mixed_v4)
        original = self.read_raw()

        with self.assertRaises(rs.RecommendationValidationError):
            self.store.ensure_current()

        self.assertEqual(self.read_raw(), original)
        self.assertFalse(
            os.path.exists(f"{self.path}.v4-pre-request-provider.bak")
        )

    def test_v3_to_v4_preserves_user_state_and_renames_ai_pick_identity(self):
        event = {
            "event_id": "event-1",
            "identity": "movie:42",
            "watched_at": "2026-08-01T12:00:00Z",
            "status": "pending",
            "attempts": 1,
            "next_attempt_at": "2026-08-01T12:05:00Z",
            "error": None,
            "completed_at": None,
            "trakt_history_ids": [],
            "last_post_status": None,
        }
        v3 = {
            "version": 3,
            "revision": 9,
            "updated_at": "2026-08-01T12:00:00Z",
            "presented_media_ids": ["movie:42", "legacy:77"],
            "items": [
                {
                    "id": "hermes-movie-42",
                    "identity": "movie:42",
                    "source": "hermes",
                    "type": "movie",
                    "title": "Fixture",
                    "year": 2024,
                    "tmdb_id": 42,
                    "reason": "Because it fits.",
                    "active": False,
                    "feedback": "watched",
                    "feedback_at": "2026-08-01T12:00:00Z",
                    "request_state": "requested",
                    "requested_at": "2026-08-01T11:00:00Z",
                    "jellyseerr_request_id": 123,
                    "added_at": "2026-07-01T00:00:00Z",
                    "trakt_history_event": event,
                }
            ],
        }

        migrated = rs.migrate_to_v4(v3)

        self.assertTrue(rs.validate_v4(migrated))
        self.assertEqual(migrated["version"], 4)
        self.assertEqual(migrated["revision"], 9)
        self.assertEqual(migrated["presented_media_ids"], ["movie:42", "legacy:77"])
        self.assertIsNone(migrated["generation"])
        item = migrated["items"][0]
        self.assertEqual(item["id"], "ai-movie-42")
        self.assertEqual(item["source"], "ai")
        self.assertEqual(item["feedback"], "watched")
        self.assertEqual(item["request_state"], "requested")
        self.assertEqual(item["request_provider"], "arr_legacy")
        self.assertEqual(item["jellyseerr_request_id"], 123)
        self.assertEqual(item["trakt_history_event"], event)
        self.assertEqual(v3["items"][0]["id"], "hermes-movie-42")

    def test_ensure_current_persists_v4_and_non_overwriting_v3_backup(self):
        v3 = {
            "version": 3,
            "revision": 0,
            "updated_at": "",
            "presented_media_ids": [],
            "items": [],
        }
        self.write_json(v3)
        original = self.read_raw()

        migrated = self.store.ensure_current()

        self.assertEqual(migrated["version"], 4)
        self.assertEqual(self.read_json()["version"], 4)
        backup_path = f"{self.path}.v3.bak"
        with open(backup_path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), original)

        with open(backup_path, "w", encoding="utf-8") as fh:
            fh.write("keep-existing-backup")
        self.store.ensure_current()
        with open(backup_path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "keep-existing-backup")

    def test_live_copy_loads_valid_v2_v3_or_v4_or_rejects_legacy(self):
        if not os.path.isfile(LIVE_V1_PATH):
            self.skipTest("live recommendations.json not present")
        shutil.copyfile(LIVE_V1_PATH, self.path)
        with open(LIVE_V1_PATH, encoding="utf-8-sig") as fh:
            live = json.load(fh)
        before = self.read_raw()

        if live.get("version") == 4:
            doc = self.store.load()
            self.assertTrue(rs.validate_v4(doc))
            self.assertGreaterEqual(len(doc["items"]), 10)
            self.assertEqual(
                [item["title"] for item in doc["items"]],
                [item["title"] for item in live["items"]],
            )
            self.assertEqual(doc["revision"], live["revision"])
            self.assertEqual(self.read_raw(), before)
            return

        if live.get("version") == 3:
            doc = self.store.load()
            self.assertTrue(rs.validate_v4(doc))
            self.assertGreaterEqual(len(doc["items"]), 10)
            self.assertEqual(
                [item["title"] for item in doc["items"]],
                [item["title"] for item in live["items"]],
            )
            self.assertEqual(self.read_raw(), before)
            self.assertEqual(self.read_json()["version"], 3)
            return

        if live.get("version") == 2:
            doc = self.store.load()
            self.assertTrue(rs.validate_v4(doc))
            self.assertGreaterEqual(len(doc["items"]), 10)
            self.assertEqual(
                [item["title"] for item in doc["items"]],
                [item["title"] for item in live["items"]],
            )
            # Load migrates in memory only; on-disk bytes stay v2.
            self.assertEqual(self.read_raw(), before)
            self.assertEqual(self.read_json()["version"], 2)
            return

        # Post-cutover: legacy v1 / unknown versions are rejected unchanged.
        with self.assertRaises(rs.RecommendationValidationError):
            self.store.load()
        self.assertEqual(self.read_raw(), before)

    def test_legacy_v1_is_rejected_without_rewriting_file(self):
        self.write_json(make_v1(["suggested", "liked", "requested"]))
        before = self.read_raw()
        with self.assertRaises(rs.RecommendationValidationError) as ctx:
            self.store.load()
        self.assertIn("unsupported version", str(ctx.exception))
        self.assertEqual(self.read_raw(), before)
        with self.assertRaises(rs.RecommendationValidationError):
            self.store.update(lambda doc: None)
        self.assertEqual(self.read_raw(), before)

    def test_unknown_and_malformed_versions_are_rejected_unchanged(self):
        cases = [
            {"version": 1, "items": []},
            {"version": 99, "revision": 0, "updated_at": "", "items": []},
            {"revision": 0, "updated_at": "", "items": []},
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                self.write_json(raw)
                before = self.read_raw()
                with self.assertRaises(rs.RecommendationValidationError):
                    self.store.load()
                self.assertEqual(self.read_raw(), before)

        with self.assertRaises(rs.RecommendationValidationError):
            rs.migrate_to_v3("not-an-object")
        with self.assertRaises(rs.RecommendationValidationError):
            rs.migrate_to_v3(None)

    def test_v2_to_v3_migration_preserves_history_as_conservative_tombstones(self):
        v2 = {
            "version": 2,
            "revision": 7,
            "updated_at": "2026-01-01T00:00:00Z",
            "presented_tmdb_ids": [123, 456],
            "items": [
                {
                    "id": "hermes-123",
                    "source": "hermes",
                    "type": "tv",
                    "title": "A series",
                    "year": 2020,
                    "tmdb_id": 123,
                    "reason": "fixture",
                    "active": True,
                    "feedback": None,
                    "feedback_at": None,
                    "request_state": None,
                    "requested_at": None,
                    "jellyseerr_request_id": None,
                    "added_at": "2026-01-01T00:00:00Z",
                }
            ],
        }
        before = json.loads(json.dumps(v2))
        migrated = rs.migrate_to_v3(v2)
        self.assertTrue(rs.validate_v3(migrated))
        self.assertEqual(migrated["version"], 3)
        self.assertEqual(
            migrated["presented_media_ids"],
            ["legacy:123", "legacy:456", "tv:123"],
        )
        self.assertEqual(migrated["items"][0]["identity"], "tv:123")
        self.assertEqual(migrated["items"][0]["id"], "hermes-tv-123")
        # Migration is pure and never discards or rewrites v2 input.
        self.assertEqual(v2, before)

    def test_v2_load_persists_as_v4_only_after_successful_mutation(self):
        v2 = {
            "version": 2,
            "revision": 0,
            "updated_at": "",
            "presented_tmdb_ids": [1],
            "items": [
                {
                    "id": "hermes-1",
                    "source": "hermes",
                    "type": "movie",
                    "title": "Title 1",
                    "year": 2001,
                    "tmdb_id": 1,
                    "reason": "fixture",
                    "active": True,
                    "feedback": None,
                    "feedback_at": None,
                    "request_state": None,
                    "requested_at": None,
                    "jellyseerr_request_id": None,
                    "added_at": "2026-01-01T00:00:00Z",
                }
            ],
        }
        self.write_json(v2)
        before = self.read_raw()
        self.store.load()
        self.assertEqual(self.read_raw(), before)
        self.assertEqual(self.read_json()["version"], 2)
        self.store.update(lambda doc: None)
        saved = self.read_json()
        self.assertEqual(saved["version"], 4)
        self.assertEqual(saved["revision"], 1)
        self.assertIsNone(saved["items"][0]["request_provider"])
        self.assertTrue(rs.validate_v4(saved))

    def test_v2_numeric_tombstone_blocks_both_composite_types(self):
        v2 = {
            "version": 2,
            "revision": 0,
            "updated_at": "",
            "presented_tmdb_ids": [123],
            "items": [],
        }
        migrated = rs.migrate_to_v3(v2)
        self.assertTrue(rs._identity_is_present(set(migrated["presented_media_ids"]), "movie:123", 123))
        self.assertTrue(rs._identity_is_present(set(migrated["presented_media_ids"]), "tv:123", 123))

    def test_v3_migrate_is_idempotent(self):
        v2 = {
            "version": 2,
            "revision": 0,
            "updated_at": "",
            "presented_tmdb_ids": [5],
            "items": [],
        }
        once = rs.migrate_to_v3(v2)
        twice = rs.migrate_to_v3(once)
        self.assertEqual(once, twice)

    def test_v3_to_v4_migration_records_legacy_provider_by_request_state(self):
        v3 = {
            "version": 3,
            "revision": 7,
            "updated_at": "2026-01-01T00:00:00Z",
            "presented_media_ids": ["movie:42", "tv:84"],
            "items": [
                {
                    "id": "hermes-movie-42",
                    "identity": "movie:42",
                    "source": "hermes",
                    "type": "movie",
                    "title": "Requested",
                    "year": 2024,
                    "tmdb_id": 42,
                    "reason": "fixture",
                    "active": False,
                    "feedback": None,
                    "feedback_at": None,
                    "request_state": "requested",
                    "requested_at": "2026-01-01T00:00:00Z",
                    "jellyseerr_request_id": 101,
                    "added_at": "2026-01-01T00:00:00Z",
                },
                {
                    "id": "hermes-tv-84",
                    "identity": "tv:84",
                    "source": "hermes",
                    "type": "tv",
                    "title": "Unrequested",
                    "year": 2024,
                    "tmdb_id": 84,
                    "reason": "fixture",
                    "active": True,
                    "feedback": None,
                    "feedback_at": None,
                    "request_state": None,
                    "requested_at": None,
                    "jellyseerr_request_id": None,
                    "added_at": "2026-01-01T00:00:00Z",
                },
            ],
        }
        before = json.loads(json.dumps(v3))

        migrated = rs.migrate_to_v4(v3)

        self.assertTrue(rs.validate_v4(migrated))
        self.assertEqual(migrated["version"], 4)
        self.assertEqual(migrated["items"][0]["request_provider"], "arr_legacy")
        self.assertIsNone(migrated["items"][1]["request_provider"])
        self.assertEqual(v3, before)

    def test_v2_load_runs_v2_to_v3_to_v4_without_rewriting_source(self):
        v2 = {
            "version": 2,
            "revision": 3,
            "updated_at": "2026-01-01T00:00:00Z",
            "presented_tmdb_ids": [42],
            "items": [
                {
                    "id": "hermes-42",
                    "source": "hermes",
                    "type": "movie",
                    "title": "Requested",
                    "year": 2024,
                    "tmdb_id": 42,
                    "reason": "fixture",
                    "active": False,
                    "feedback": None,
                    "feedback_at": None,
                    "request_state": "requested",
                    "requested_at": "2026-01-01T00:00:00Z",
                    "jellyseerr_request_id": 101,
                    "added_at": "2026-01-01T00:00:00Z",
                }
            ],
        }
        self.write_json(v2)
        before = self.read_raw()

        loaded = self.store.load()

        self.assertEqual(loaded["version"], 4)
        self.assertEqual(loaded["items"][0]["identity"], "movie:42")
        self.assertEqual(loaded["items"][0]["request_provider"], "arr_legacy")
        self.assertEqual(self.read_raw(), before)


class TransactionTests(StoreTestCase):
    def test_like_then_request_preserves_both_fields(self):
        self.store.update(self._append_item)
        self.store.update(
            lambda doc: rs.apply_feedback(self._first(doc), "liked")
        )
        self.store.update(
            lambda doc: rs.apply_request(self._first(doc), provider="jellyseerr")
        )
        item = self._first(self.store.load())
        self.assertEqual(item["feedback"], "liked")
        self.assertEqual(item["request_state"], "requested")
        self.assertEqual(item["request_provider"], "jellyseerr")
        self.assertFalse(item["active"])

    def test_request_then_feedback_preserves_request_state(self):
        self.store.update(self._append_item)
        self.store.update(
            lambda doc: rs.apply_request(self._first(doc), provider="arr_legacy")
        )
        self.store.update(
            lambda doc: rs.apply_feedback(self._first(doc), "disliked")
        )
        item = self._first(self.store.load())
        self.assertEqual(item["request_state"], "requested")
        self.assertIsNotNone(item["requested_at"])
        self.assertEqual(item["feedback"], "disliked")
        self.assertFalse(item["active"])

    def test_revision_increments_monotonically(self):
        r1 = self.store.update(lambda doc: None)["revision"]
        r2 = self.store.update(lambda doc: None)["revision"]
        r3 = self.store.update(lambda doc: None)["revision"]
        self.assertEqual((r1, r2, r3), (1, 2, 3))

    def test_caller_document_not_mutated_in_place(self):
        committed = self.store.update(self._append_item)
        snapshot = json.loads(json.dumps(committed))
        self.store.update(lambda doc: rs.apply_feedback(doc["items"][0], "liked"))
        self.assertEqual(committed, snapshot)

    def test_mutator_exception_aborts_without_write(self):
        self.store.update(self._append_item)
        before = self.read_raw()

        def boom(doc):
            doc["items"].clear()
            raise RuntimeError("abort")

        with self.assertRaises(RuntimeError):
            self.store.update(boom)
        self.assertEqual(self.read_raw(), before)

    def test_invalid_document_rejected_and_file_unchanged(self):
        self.store.update(self._append_item)
        before = self.read_raw()

        def corrupt(doc):
            doc["items"][0]["feedback"] = "meh"

        with self.assertRaises(rs.RecommendationValidationError):
            self.store.update(corrupt)
        self.assertEqual(self.read_raw(), before)
        self.assertEqual(self.store.load()["revision"], 1)

    def test_each_v2_invariant_rejection_leaves_file_byte_for_byte_unchanged(self):
        self.store.update(self._append_item)
        before = self.read_raw()

        mutations = {
            "duplicate item id": lambda doc: doc["items"].append(
                copy_item(doc["items"][0], tmdb_id=43)
            ),
            "duplicate current tmdb identity": lambda doc: doc["items"].append(
                copy_item(doc["items"][0], id="ai-copy")
            ),
            "duplicate presented identity": lambda doc: doc["presented_media_ids"].append("movie:42"),
            "current identity absent from presented": lambda doc: doc[
                "presented_media_ids"
            ].clear(),
            "malformed enum": lambda doc: doc["items"][0].update(feedback="invalid"),
            "malformed type": lambda doc: doc["items"][0].update(in_library="yes"),
        }

        # Make the duplicate-item-id and duplicate-TMDB cases distinct.
        for name, mutate in mutations.items():
            with self.subTest(invariant=name):
                with self.assertRaises(rs.RecommendationValidationError):
                    self.store.update(mutate)
                self.assertEqual(self.read_raw(), before)

    def test_duplicate_current_tmdb_identity_is_rejected_even_with_distinct_ids(self):
        self.store.update(self._append_item)
        before = self.read_raw()

        def mutate(doc):
            item = copy_item(doc["items"][0], id="ai-copy")
            doc["items"].append(item)

        with self.assertRaises(rs.RecommendationValidationError):
            self.store.update(mutate)
        self.assertEqual(self.read_raw(), before)

    def test_atomic_write_failure_leaves_previous_json_readable(self):
        self.store.update(self._append_item)
        before = self.read_raw()
        with mock.patch(
            "recommendations_store.os.replace",
            side_effect=OSError("simulated replace failure"),
        ):
            with self.assertRaises(OSError):
                self.store.update(
                    lambda doc: rs.apply_feedback(doc["items"][0], "liked")
                )
        self.assertEqual(self.read_raw(), before)
        self.assertEqual(self.store.load()["items"][0]["feedback"], None)
        self.assertFalse(os.path.isfile(f"{self.path}.tmp"))

    def test_corrupt_file_raises_recommendation_error_on_load(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        with self.assertRaises(rs.RecommendationError) as ctx:
            self.store.load()
        self.assertNotIsInstance(ctx.exception, ValueError)
        self.assertIn("cannot read", str(ctx.exception))

    def test_like_does_not_reactivate_inactive_item(self):
        self.store.update(self._append_item)
        self.store.update(
            lambda doc: rs.apply_request(self._first(doc), provider="arr_legacy")
        )
        item = self._first(self.store.load())
        self.assertFalse(item["active"])
        self.store.update(
            lambda doc: rs.apply_feedback(self._first(doc), "liked")
        )
        item = self._first(self.store.load())
        self.assertEqual(item["feedback"], "liked")
        self.assertFalse(item["active"])
        self.assertEqual(item["request_state"], "requested")

    def test_like_deactivates_active_item(self):
        self.store.update(self._append_item)
        self.store.update(
            lambda doc: rs.apply_feedback(self._first(doc), "liked")
        )
        item = self._first(self.store.load())
        self.assertEqual(item["feedback"], "liked")
        self.assertFalse(item["active"])

    def test_missing_file_loads_empty_v4_default(self):
        doc = self.store.load()
        self.assertEqual(doc["version"], 4)
        self.assertEqual(doc["items"], [])
        self.assertTrue(rs.validate_v4(doc))

    def test_concurrent_updates_commit_serially_without_corruption(self):
        import threading

        errors = []

        def writer(n):
            try:
                for _ in range(5):
                    self.store.update(
                        lambda doc: doc["presented_media_ids"].append(f"movie:{n}")
                        if f"movie:{n}" not in doc["presented_media_ids"]
                        else None
                    )
            except Exception as e:  # pragma: no cover - failure reporting
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(1, 5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        doc = self.store.load()
        self.assertEqual(doc["revision"], 20)
        self.assertEqual(sorted(doc["presented_media_ids"]), ["movie:1", "movie:2", "movie:3", "movie:4"])
        self.assertTrue(rs.validate_v4(doc))
        # The file on disk is one well-formed JSON document.
        self.assertEqual(self.read_json()["revision"], 20)

    def _item(self):
        return {
            "id": "ai-movie-42",
            "identity": "movie:42",
            "source": "ai",
            "type": "movie",
            "title": "Fixture",
            "year": 2024,
            "tmdb_id": 42,
            "reason": "test",
            "active": True,
            "feedback": None,
            "feedback_at": None,
            "request_state": None,
            "request_provider": None,
            "requested_at": None,
            "jellyseerr_request_id": None,
            "added_at": rs.utc_now(),
        }

    def _append_item(self, doc):
        item = self._item()
        doc["items"].append(item)
        doc["presented_media_ids"].append(item["identity"])

    @staticmethod
    def _first(doc):
        return doc["items"][0]


class ValidatorTests(unittest.TestCase):
    def test_schema_file_is_valid_json_and_matches_validator(self):
        if not os.path.isfile(SCHEMA_PATH):
            self.skipTest("schema-v2.json not present")
        with open(SCHEMA_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
        self.assertEqual(schema.get("title"), "Hermes Recommendations v2")
        props = schema["properties"]
        self.assertEqual(props["version"]["const"], 2)
        self.assertEqual(
            set(props["items"]["items"]["required"]),
            {
                "id",
                "source",
                "type",
                "title",
                "tmdb_id",
                "reason",
                "active",
                "feedback",
                "feedback_at",
                "request_state",
                "requested_at",
                "jellyseerr_request_id",
                "added_at",
            },
        )

    def test_example_document_passes_validator(self):
        if not os.path.isfile(EXAMPLE_PATH):
            self.skipTest("recommendations.example.json not present")
        with open(EXAMPLE_PATH, encoding="utf-8") as fh:
            example = json.load(fh)
        self.assertTrue(rs.validate_v4(example))

    def test_v4_schema_file_matches_ai_pick_contract(self):
        with open(SCHEMA_V4_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
        self.assertEqual(schema["properties"]["version"]["const"], 4)
        self.assertEqual(schema["properties"]["items"]["items"]["properties"]["source"]["const"], "ai")
        self.assertIn("request_provider", schema["properties"]["items"]["items"]["required"])
        self.assertIn("generation", schema["required"])

    def test_v3_schema_file_declares_unique_composite_history_and_identity(self):
        with open(SCHEMA_V3_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
        self.assertEqual(schema["title"], "Hermes Recommendations v3")
        self.assertEqual(schema["properties"]["version"]["const"], 3)
        self.assertTrue(schema["properties"]["presented_media_ids"]["uniqueItems"])
        self.assertIn("identity", schema["properties"]["items"]["items"]["required"])
        event_schema = schema["properties"]["items"]["items"]["properties"]["trakt_history_event"]
        self.assertIn("event_id", event_schema["required"])

    def test_v4_schema_requires_provider_and_declares_exact_values(self):
        with open(SCHEMA_V4_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
        self.assertEqual(schema["title"], "AI Picks Recommendations v4")
        self.assertEqual(schema["properties"]["version"]["const"], 4)
        item_schema = schema["properties"]["items"]["items"]
        self.assertIn("request_provider", item_schema["required"])
        self.assertEqual(
            item_schema["properties"]["request_provider"]["enum"],
            [None, "jellyseerr", "arr_legacy"],
        )

    def test_v4_provider_must_match_request_state(self):
        base = {
            "version": 4,
            "revision": 1,
            "updated_at": "2026-01-01T00:00:00Z",
            "presented_media_ids": ["movie:42"],
            "items": [
                {
                    "id": "hermes-movie-42",
                    "identity": "movie:42",
                    "source": "hermes",
                    "type": "movie",
                    "title": "Fixture",
                    "year": 2024,
                    "tmdb_id": 42,
                    "reason": "test",
                    "active": False,
                    "feedback": None,
                    "feedback_at": None,
                    "request_state": "requested",
                    "request_provider": "jellyseerr",
                    "requested_at": "2026-01-01T00:00:00Z",
                    "jellyseerr_request_id": 123,
                    "added_at": "2026-01-01T00:00:00Z",
                }
            ],
        }
        invalid_pairs = [
            ("requested", None),
            ("requested", "sonarr"),
            (None, "jellyseerr"),
            (None, "arr_legacy"),
        ]
        for request_state, provider in invalid_pairs:
            with self.subTest(request_state=request_state, provider=provider):
                doc = json.loads(json.dumps(base))
                doc["items"][0]["request_state"] = request_state
                doc["items"][0]["request_provider"] = provider
                with self.assertRaises(rs.RecommendationValidationError):
                    rs.validate_v4(doc)

        missing = json.loads(json.dumps(base))
        del missing["items"][0]["request_provider"]
        with self.assertRaises(rs.RecommendationValidationError):
            rs.validate_v4(missing)

    def test_invalid_trakt_history_event_rejected(self):
        doc = {
            "version": 3,
            "revision": 1,
            "updated_at": "2026-01-01T00:00:00Z",
            "presented_media_ids": ["movie:42"],
            "items": [
                {
                    "id": "hermes-movie-42",
                    "identity": "movie:42",
                    "source": "hermes",
                    "type": "movie",
                    "title": "Fixture",
                    "year": 2024,
                    "tmdb_id": 42,
                    "reason": "test",
                    "active": True,
                    "feedback": "watched",
                    "feedback_at": "2026-01-01T00:00:00Z",
                    "request_state": None,
                    "requested_at": None,
                    "jellyseerr_request_id": None,
                    "added_at": "2026-01-01T00:00:00Z",
                    "trakt_history_event": {},
                }
            ],
        }
        with self.assertRaises(rs.RecommendationValidationError):
            rs.validate_v3(doc)

    def test_v4_rejects_malformed_private_candidate_snapshot(self):
        doc = rs.RecommendationStore("unused").default_document()
        doc["generation"] = {
            "id": "job", "status": "running", "trigger": "on_demand",
            "requested_at": "2026-08-29T10:00:00Z", "started_at": "2026-08-29T10:00:00Z",
            "finished_at": None, "desired_count": 10, "attempt": 1,
            "lease_expires_at": "2026-08-29T10:05:00Z", "lease_token": "lease",
            "base_revision": 1,
            "candidates": [{"identity": "movie:42", "type": "tv", "tmdb_id": 42, "title": "Mismatch"}],
            "taste": {}, "required_retain": ["movie:42"], "error_code": None,
            "counts": None,
        }

        with self.assertRaises(rs.RecommendationValidationError):
            rs.validate_v4(doc)

    def test_v4_rejects_generation_count_above_candidate_cap(self):
        doc = rs.RecommendationStore("unused").default_document()
        doc["generation"] = {
            "id": "job", "status": "queued", "trigger": "on_demand",
            "requested_at": "2026-08-29T10:00:00Z", "started_at": None,
            "finished_at": None, "desired_count": 101, "attempt": 0,
            "lease_expires_at": None, "lease_token": None,
            "base_revision": None, "candidates": [], "taste": {},
            "required_retain": [], "error_code": None, "counts": None,
        }

        with self.assertRaises(rs.RecommendationValidationError):
            rs.validate_v4(doc)

    def test_invalid_documents_raise(self):
        base = {
            "version": 2,
            "revision": 1,
            "updated_at": "2026-01-01T00:00:00Z",
            "presented_tmdb_ids": [42],
            "items": [
                {
                    "id": "hermes-42",
                    "source": "hermes",
                    "type": "movie",
                    "title": "Fixture",
                    "year": 2024,
                    "tmdb_id": 42,
                    "reason": "test",
                    "active": True,
                    "feedback": None,
                    "feedback_at": None,
                    "request_state": None,
                    "requested_at": None,
                    "jellyseerr_request_id": None,
                    "added_at": "2026-01-01T00:00:00Z",
                }
            ],
        }
        bad_docs = []
        doc = json.loads(json.dumps(base))
        doc["version"] = 1
        bad_docs.append(doc)
        doc = json.loads(json.dumps(base))
        doc["revision"] = "1"
        bad_docs.append(doc)
        doc = json.loads(json.dumps(base))
        doc["presented_tmdb_ids"] = [0]
        bad_docs.append(doc)
        doc = json.loads(json.dumps(base))
        doc["items"][0]["feedback"] = "meh"
        bad_docs.append(doc)
        doc = json.loads(json.dumps(base))
        doc["items"][0]["request_state"] = "downloaded"
        bad_docs.append(doc)
        doc = json.loads(json.dumps(base))
        doc["items"][0]["active"] = "yes"
        bad_docs.append(doc)
        doc = json.loads(json.dumps(base))
        doc["items"][0]["type"] = "anime"
        bad_docs.append(doc)
        doc = json.loads(json.dumps(base))
        doc["items"][0]["tmdb_id"] = -5
        bad_docs.append(doc)
        doc = json.loads(json.dumps(base))
        doc["items"][0]["jellyseerr_request_id"] = "abc"
        bad_docs.append(doc)
        doc = json.loads(json.dumps(base))
        del doc["items"][0]["id"]
        bad_docs.append(doc)
        for bad in bad_docs:
            with self.subTest(bad=json.dumps(bad)[:80]):
                with self.assertRaises(rs.RecommendationValidationError):
                    rs.validate_v2(bad)


class CutoverTests(unittest.TestCase):
    def test_legacy_status_helpers_are_removed(self):
        self.assertFalse(hasattr(rs, "legacy_status"))
        self.assertFalse(hasattr(rs, "STATUS_TO_V2"))
        self.assertFalse(hasattr(rs, "migrate_to_v2"))
        self.assertFalse(hasattr(rs, "_migrate_v1"))

    def test_apply_helpers_validate(self):
        with self.assertRaises(rs.RecommendationValidationError):
            rs.apply_feedback({}, "meh")

        with self.assertRaises(TypeError):
            rs.apply_request({})
        with self.assertRaises(rs.RecommendationValidationError):
            rs.apply_request({}, provider="sonarr")

        item = {"active": True, "request_state": None, "request_provider": None}
        rs.apply_request(
            item,
            provider="jellyseerr",
            request_id=123,
            now="2026-01-01T00:00:00Z",
        )
        self.assertEqual(item["request_state"], "requested")
        self.assertEqual(item["request_provider"], "jellyseerr")
        self.assertEqual(item["jellyseerr_request_id"], 123)


if __name__ == "__main__":
    unittest.main()
