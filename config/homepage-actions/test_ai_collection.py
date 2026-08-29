#!/usr/bin/env python3
import unittest
from unittest import mock

from routes import discover


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


if __name__ == "__main__":
    unittest.main()
