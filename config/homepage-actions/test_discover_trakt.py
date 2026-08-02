import unittest

from routes.discover import _map_trakt_result


class TraktDiscoverMappingTests(unittest.TestCase):
    def test_movie_includes_slug(self):
        raw = {
            "title": "Dune: Part Two",
            "year": 2024,
            "ids": {"tmdb": 693134, "slug": "dune-part-two-2024"},
            "overview": "Epic continuation.",
            "rating": 8.3,
        }
        result = _map_trakt_result(raw, "movies")
        self.assertEqual(result["type"], "movie")
        self.assertEqual(result["title"], "Dune: Part Two")
        self.assertEqual(result["trakt_slug"], "dune-part-two-2024")
        self.assertEqual(result["tmdb_id"], 693134)

    def test_show_includes_slug(self):
        raw = {
            "show": {
                "title": "Severance",
                "year": 2022,
                "ids": {"tmdb": 95396, "slug": "severance"},
                "overview": "Work-life balance taken literally.",
            },
            "rating": 8.7,
        }
        result = _map_trakt_result(raw, "shows")
        self.assertEqual(result["type"], "tv")
        self.assertEqual(result["title"], "Severance")
        self.assertEqual(result["trakt_slug"], "severance")
        self.assertEqual(result["tmdb_id"], 95396)

    def test_missing_slug_is_none(self):
        raw = {
            "title": "Untitled",
            "year": 2026,
            "ids": {"tmdb": 1},
            "overview": "",
        }
        result = _map_trakt_result(raw, "movies")
        self.assertIsNone(result["trakt_slug"])


if __name__ == "__main__":
    unittest.main()
