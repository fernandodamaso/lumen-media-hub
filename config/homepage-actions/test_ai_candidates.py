#!/usr/bin/env python3
import unittest

from ai_candidates import CandidateUnavailable, build_candidate_snapshot


class AiCandidateSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.doc = {
            "presented_media_ids": ["movie:1"],
            "items": [
                {
                    "identity": "tv:2",
                    "type": "tv",
                    "tmdb_id": 2,
                    "title": "Liked show",
                    "feedback": "liked",
                    "active": False,
                }
            ],
        }
        self.exclusions = {
            "tracked": {"movie:3"},
            "in_library": {"tv:4"},
            "watched": {"movie:5"},
            "errors": [],
            "required_retain": [],
            "taste": {"liked": [{"identity": "tv:2"}]},
        }

    def test_deduplicates_typed_identities_and_filters_authoritative_denies(self):
        raw = [
            {"type": "movie", "tmdb_id": 1, "title": "Presented"},
            {"type": "movie", "tmdb_id": 3, "title": "Tracked"},
            {"type": "tv", "tmdb_id": 4, "title": "Playable"},
            {"type": "movie", "tmdb_id": 5, "title": "Watched"},
            {"type": "movie", "tmdb_id": 9, "title": "Eligible", "overview": "A"},
            {"type": "movie", "tmdb_id": 9, "title": "Duplicate", "overview": "B"},
            {"type": "tv", "tmdb_id": 9, "title": "Typed distinct"},
        ]

        snapshot = build_candidate_snapshot(
            self.doc,
            sources=[lambda: raw],
            exclusions=lambda _doc: self.exclusions,
        )

        self.assertEqual(
            [item["identity"] for item in snapshot["candidates"]],
            ["movie:9", "tv:9"],
        )
        self.assertEqual(snapshot["taste"], self.exclusions["taste"])

    def test_one_source_failure_is_tolerated_when_another_is_usable(self):
        def failed_source():
            raise RuntimeError("token must not leak")

        snapshot = build_candidate_snapshot(
            self.doc,
            sources=[failed_source, lambda: [{"type": "movie", "tmdb_id": 9, "title": "Eligible"}]],
            exclusions=lambda _doc: self.exclusions,
        )

        self.assertEqual(len(snapshot["candidates"]), 1)

    def test_missing_authoritative_exclusion_snapshot_fails_closed(self):
        unavailable = dict(self.exclusions, errors=["trakt_watched: unavailable"])

        with self.assertRaises(CandidateUnavailable):
            build_candidate_snapshot(
                self.doc,
                sources=[lambda: [{"type": "movie", "tmdb_id": 9, "title": "Eligible"}]],
                exclusions=lambda _doc: unavailable,
            )

    def test_legacy_untyped_tombstone_blocks_both_media_types(self):
        self.doc["presented_media_ids"] = ["legacy:9"]

        with self.assertRaisesRegex(CandidateUnavailable, "empty") as raised:
            build_candidate_snapshot(
                self.doc,
                sources=[lambda: [
                    {"type": "movie", "tmdb_id": 9, "title": "Movie"},
                    {"type": "tv", "tmdb_id": 9, "title": "Show"},
                ]],
                exclusions=lambda _doc: self.exclusions,
            )

        self.assertEqual(raised.exception.code, "empty_pool")


if __name__ == "__main__":
    unittest.main()
