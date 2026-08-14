#!/usr/bin/env python3
"""Focused Jellyfin library contract tests."""

import unittest
from unittest import mock

import clients.jellyfin as jellyfin_client


class JellyfinLibraryTests(unittest.TestCase):
    def test_requests_and_maps_community_rating(self):
        calls = []
        original_get = jellyfin_client.jellyfin_get
        original_path = jellyfin_client._jellyfin_items_path
        try:
            jellyfin_client._jellyfin_items_path = lambda: "/Items"
            jellyfin_client.jellyfin_get = lambda path, query=None: calls.append(
                (path, query)
            ) or {"Items": [], "TotalRecordCount": 0}
            jellyfin_client._fetch_all_jellyfin_raw("Movie")
        finally:
            jellyfin_client.jellyfin_get = original_get
            jellyfin_client._jellyfin_items_path = original_path

        self.assertIn("CommunityRating", calls[0][1]["Fields"].split(","))
        self.assertEqual(
            jellyfin_client._map_jellyfin_item({"CommunityRating": 8.4}, "Movie")["rating"], 8.4
        )

    def test_missing_or_invalid_rating_maps_to_none(self):
        for value in (None, True, "8.4", -1, 11, float("nan")):
            raw = {} if value is None else {"CommunityRating": value}
            with self.subTest(value=value):
                self.assertIsNone(jellyfin_client._map_jellyfin_item(raw, "Movie")["rating"])

    def test_requests_userdata_and_provider_ids_fields(self):
        calls = []
        original_get = jellyfin_client.jellyfin_get
        original_path = jellyfin_client._jellyfin_items_path
        try:
            jellyfin_client._jellyfin_items_path = lambda: "/Items"
            jellyfin_client.jellyfin_get = lambda path, query=None: calls.append(
                (path, query)
            ) or {"Items": [], "TotalRecordCount": 0}
            jellyfin_client._fetch_all_jellyfin_raw("Movie")
        finally:
            jellyfin_client.jellyfin_get = original_get
            jellyfin_client._jellyfin_items_path = original_path
        fields = calls[0][1]["Fields"].split(",")
        self.assertIn("UserData", fields)
        self.assertIn("ProviderIds", fields)

    def test_maps_played_from_userdata(self):
        self.assertTrue(
            jellyfin_client._map_jellyfin_item(
                {"Id": "a", "UserData": {"Played": True}}, "Movie"
            )["played"]
        )
        self.assertFalse(
            jellyfin_client._map_jellyfin_item(
                {"Id": "a", "UserData": {"Played": False}}, "Movie"
            )["played"]
        )
        self.assertFalse(jellyfin_client._map_jellyfin_item({"Id": "a"}, "Movie")["played"])

    def test_series_keeps_episode_count_movies_omit_it(self):
        with mock.patch.object(jellyfin_client, "_series_episode_count", return_value=13):
            series = jellyfin_client._map_jellyfin_item({"Id": "s1", "Name": "Show"}, "Series")
        movie = jellyfin_client._map_jellyfin_item({"Id": "m1", "Name": "Film"}, "Movie")
        self.assertEqual(series["episodeCount"], 13)
        self.assertNotIn("episodeCount", movie)
        self.assertNotIn("ProviderIds", series)
        self.assertNotIn("ProviderIds", movie)

    def test_tombstoned_items_filtered_from_cached_payload(self):
        jellyfin_client._DELETED_ITEM_TOMBSTONES.clear()
        self.addCleanup(jellyfin_client._DELETED_ITEM_TOMBSTONES.clear)
        payload = {
            "ok": True,
            "total": 2,
            "items": [
                {"id": "keep", "name": "Keep"},
                {"id": "gone", "name": "Gone"},
            ],
        }
        with mock.patch.object(jellyfin_client.settings, "_jellyfin_cache", {"Movie": {"ts": 0, "payload": payload}}), mock.patch.object(
            jellyfin_client.settings, "JELLYFIN_CACHE_TTL", 45.0
        ), mock.patch.object(jellyfin_client.time, "monotonic", return_value=1.0):
            jellyfin_client.tombstone_jellyfin_item("gone")
            filtered = jellyfin_client._get_jellyfin_payload("Movie")
        self.assertEqual([item["id"] for item in filtered["items"]], ["keep"])
        self.assertEqual(filtered["total"], 1)


if __name__ == "__main__":
    unittest.main()

