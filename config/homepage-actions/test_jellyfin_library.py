#!/usr/bin/env python3
"""Focused Jellyfin library contract tests."""

import unittest

import main


class JellyfinLibraryTests(unittest.TestCase):
    def test_requests_and_maps_community_rating(self):
        calls = []
        original_get = main.jellyfin_get
        original_path = main._jellyfin_items_path
        try:
            main._jellyfin_items_path = lambda: "/Items"
            main.jellyfin_get = lambda path, query=None: calls.append((path, query)) or {
                "Items": [], "TotalRecordCount": 0
            }
            main._fetch_all_jellyfin_raw("Movie")
        finally:
            main.jellyfin_get = original_get
            main._jellyfin_items_path = original_path

        self.assertIn("CommunityRating", calls[0][1]["Fields"].split(","))
        self.assertEqual(main._map_jellyfin_item({"CommunityRating": 8.4}, "Movie")["rating"], 8.4)

    def test_missing_or_invalid_rating_maps_to_none(self):
        for value in (None, True, "8.4", -1, 11, float("nan")):
            raw = {} if value is None else {"CommunityRating": value}
            with self.subTest(value=value):
                self.assertIsNone(main._map_jellyfin_item(raw, "Movie")["rating"])


if __name__ == "__main__":
    unittest.main()
