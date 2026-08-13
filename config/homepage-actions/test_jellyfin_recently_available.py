#!/usr/bin/env python3
"""Recently-available Jellyfin contract tests."""

import io
import json
import unittest
from datetime import datetime, timezone
from unittest import mock

import config
import clients.jellyfin as jellyfin_client
import routes.jellyfin as jellyfin_routes


RECENTLY_AVAILABLE_FIELDS = (
    "Path,DateCreated,SeriesName,SeriesId,IndexNumber,ParentIndexNumber,"
    "ProductionYear,ImageTags,BackdropImageTags,Overview,IsPlaceHolder,Type,Name,UserData"
)


class RecentlyAvailableLimitTests(unittest.TestCase):
    def test_limit_rules(self):
        cases = [
            ({}, 10),
            ({"limit": ["abc"]}, 10),
            ({"limit": ["1.5"]}, 10),
            ({"limit": ["0"]}, 1),
            ({"limit": ["-3"]}, 1),
            ({"limit": ["51"]}, 50),
            ({"limit": ["5"]}, 5),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                self.assertEqual(jellyfin_routes._recently_available_limit(query), expected)


class RecentlyAvailableTimestampTests(unittest.TestCase):
    def test_parses_timezone_bearing_values(self):
        parsed = jellyfin_client._parse_recently_available_timestamp("2026-08-11T12:14:33Z")
        self.assertIsNotNone(parsed)
        dt, canonical = parsed
        self.assertEqual(dt, datetime(2026, 8, 11, 12, 14, 33, tzinfo=timezone.utc))
        self.assertEqual(canonical, "2026-08-11T12:14:33Z")

    def test_rejects_timezone_less_values(self):
        self.assertIsNone(jellyfin_client._parse_recently_available_timestamp("2026-08-11T12:14:33"))


class RecentlyAvailableValidationTests(unittest.TestCase):
    def _episode(self, **overrides):
        base = {
            "Id": "ep-1",
            "Type": "Episode",
            "SeriesId": "series-1",
            "SeriesName": "Saga of Tanya the Evil",
            "Name": "Lamb",
            "ParentIndexNumber": 2,
            "IndexNumber": 5,
            "Path": "/data/media/tv/tanya/s02e05.mkv",
            "DateCreated": "2026-08-11T12:14:33Z",
            "IsPlaceHolder": False,
        }
        base.update(overrides)
        return base

    def test_accepts_valid_episode_and_movie(self):
        self.assertTrue(jellyfin_client._recently_available_item_is_valid(self._episode()))
        self.assertTrue(
            jellyfin_client._recently_available_item_is_valid(
                {
                    "Id": "mv-1",
                    "Type": "Movie",
                    "Name": "Dune",
                    "Path": "/data/media/movies/dune.mkv",
                    "DateCreated": "2026-08-10T08:00:00Z",
                }
            )
        )

    def test_rejects_pathless_episode_and_movie(self):
        self.assertFalse(jellyfin_client._recently_available_item_is_valid(self._episode(Path="")))
        self.assertFalse(
            jellyfin_client._recently_available_item_is_valid(
                {
                    "Id": "mv-1",
                    "Type": "Movie",
                    "Name": "Dune",
                    "Path": "",
                    "DateCreated": "2026-08-10T08:00:00Z",
                }
            )
        )

    def test_rejects_placeholder_virtual_and_series_container(self):
        self.assertFalse(jellyfin_client._recently_available_item_is_valid(self._episode(IsPlaceHolder=True)))
        self.assertFalse(
            jellyfin_client._recently_available_item_is_valid(
                self._episode(Path="/plugins/JellyNext/jellynext-virtual/show/file.strm")
            )
        )
        self.assertFalse(
            jellyfin_client._recently_available_item_is_valid(
                {
                    "Id": "series-1",
                    "Type": "Series",
                    "Name": "Show",
                    "Path": "/data/media/tv/show",
                    "DateCreated": "2026-08-10T08:00:00Z",
                }
            )
        )

    def test_rejects_missing_identity_fields(self):
        self.assertFalse(jellyfin_client._recently_available_item_is_valid(self._episode(Id="")))
        self.assertFalse(jellyfin_client._recently_available_item_is_valid(self._episode(SeriesId="")))
        self.assertFalse(jellyfin_client._recently_available_item_is_valid(self._episode(SeriesName="")))
        self.assertFalse(jellyfin_client._recently_available_item_is_valid(self._episode(Name="")))
        self.assertFalse(jellyfin_client._recently_available_item_is_valid(self._episode(ParentIndexNumber=True)))
        self.assertFalse(jellyfin_client._recently_available_item_is_valid(self._episode(IndexNumber=None)))
        self.assertFalse(
            jellyfin_client._recently_available_item_is_valid(
                {
                    "Id": "mv-1",
                    "Type": "Movie",
                    "Name": "",
                    "Path": "/data/media/movies/dune.mkv",
                    "DateCreated": "2026-08-10T08:00:00Z",
                }
            )
        )

    def test_rejects_malformed_timestamp(self):
        self.assertFalse(jellyfin_client._recently_available_item_is_valid(self._episode(DateCreated="not-a-date")))
        self.assertFalse(
            jellyfin_client._recently_available_item_is_valid(self._episode(DateCreated="2026-08-11T12:14:33"))
        )

    def test_rejects_fully_watched_episode_and_movie(self):
        self.assertFalse(
            jellyfin_client._recently_available_item_is_valid(
                self._episode(UserData={"Played": True, "PlayCount": 1})
            )
        )
        self.assertFalse(
            jellyfin_client._recently_available_item_is_valid(
                {
                    "Id": "mv-1",
                    "Type": "Movie",
                    "Name": "Dune",
                    "Path": "/data/media/movies/dune.mkv",
                    "DateCreated": "2026-08-10T08:00:00Z",
                    "UserData": {"Played": True, "PlayCount": 1},
                }
            )
        )

    def test_accepts_unwatched_and_in_progress_items(self):
        self.assertTrue(jellyfin_client._recently_available_item_is_valid(self._episode()))
        self.assertTrue(
            jellyfin_client._recently_available_item_is_valid(
                self._episode(UserData={"Played": False, "PlaybackPositionTicks": 600000000})
            )
        )
        self.assertTrue(
            jellyfin_client._recently_available_item_is_valid(
                {
                    "Id": "mv-1",
                    "Type": "Movie",
                    "Name": "Dune",
                    "Path": "/data/media/movies/dune.mkv",
                    "DateCreated": "2026-08-10T08:00:00Z",
                    "UserData": {"Played": False},
                }
            )
        )


class RecentlyAvailableMappingTests(unittest.TestCase):
    def setUp(self):
        config._jellyfin_cache.clear()

    def test_maps_episode_with_series_thumb(self):
        meta = {
            "year": 2026,
            "rating": None,
            "genres": [],
            "overview": None,
            "backdropUrl": None,
            "thumbUrl": "http://localhost:8096/Items/series-id/Images/Thumb",
        }
        with (
            mock.patch.object(jellyfin_client, "_watch_next_image", return_value="http://localhost:8096/Items/series-id/Images/Primary"),
            mock.patch.object(jellyfin_client, "_get_series_metadata", return_value=meta),
        ):
            mapped = jellyfin_client._map_recently_available_item(
                {
                    "Id": "episode-jellyfin-id",
                    "Type": "Episode",
                    "SeriesId": "series-jellyfin-id",
                    "SeriesName": "Saga of Tanya the Evil",
                    "Name": "Lamb",
                    "ParentIndexNumber": 2,
                    "IndexNumber": 5,
                    "Path": "/data/media/tv/tanya/s02e05.mkv",
                    "DateCreated": "2026-08-11T12:14:33Z",
                    "ProductionYear": 2026,
                }
            )
        mapped.pop("_sort_dt", None)
        self.assertEqual(
            mapped,
            {
                "id": "episode-jellyfin-id",
                "parentId": "series-jellyfin-id",
                "kind": "episode",
                "title": "Saga of Tanya the Evil",
                "subtitle": "S02E05 · Lamb",
                "year": 2026,
                "availableAt": "2026-08-11T12:14:33Z",
                "image": "http://localhost:8096/Items/series-id/Images/Primary",
                "thumbUrl": "http://localhost:8096/Items/series-id/Images/Thumb",
                "playable": True,
            },
        )

    def test_maps_movie_with_empty_subtitle(self):
        with mock.patch.object(
            jellyfin_client,
            "_watch_next_image",
            return_value="http://localhost:8096/Items/movie-id/Images/Primary",
        ), mock.patch.object(
            jellyfin_client,
            "_watch_next_item_metadata",
            return_value={"thumbUrl": None},
        ):
            mapped = jellyfin_client._map_recently_available_item(
                {
                    "Id": "movie-id",
                    "Type": "Movie",
                    "Name": "Dune",
                    "Path": "/data/media/movies/dune.mkv",
                    "DateCreated": "2026-08-10T08:00:00Z",
                    "ProductionYear": 2021,
                }
            )
        self.assertEqual(mapped["parentId"], None)
        self.assertEqual(mapped["kind"], "movie")
        self.assertEqual(mapped["subtitle"], "")
        self.assertEqual(mapped["year"], 2021)
        self.assertNotIn("Path", mapped)


class RecentlyAvailableFetchTests(unittest.TestCase):
    def setUp(self):
        config._jellyfin_cache.clear()

    def test_queries_jellyfin_with_expected_params(self):
        calls = []

        def fake_get(path, query=None):
            calls.append((path, query))
            return {"Items": [], "TotalRecordCount": 0}

        with (
            mock.patch.object(jellyfin_client, "jellyfin_get", side_effect=fake_get),
            mock.patch.object(jellyfin_client, "_jellyfin_items_path", return_value="/Users/u1/Items"),
        ):
            jellyfin_client._fetch_recently_available_items(5)

        self.assertEqual(len(calls), 1)
        _, query = calls[0]
        self.assertEqual(query["Recursive"], "true")
        self.assertEqual(query["IncludeItemTypes"], "Episode,Movie")
        self.assertEqual(query["SortBy"], "DateCreated")
        self.assertEqual(query["SortOrder"], "Descending")
        self.assertEqual(query["StartIndex"], "0")
        self.assertEqual(query["Limit"], str(jellyfin_client.RECENTLY_AVAILABLE_PAGE_SIZE))
        self.assertEqual(query["Fields"], RECENTLY_AVAILABLE_FIELDS)
        self.assertEqual(query["Filters"], "IsUnplayed")

    def test_newest_first_mixed_output(self):
        pages = [
            {
                "Items": [
                    {
                        "Id": "mv-old",
                        "Type": "Movie",
                        "Name": "Older",
                        "Path": "/movies/old.mkv",
                        "DateCreated": "2026-08-09T08:00:00Z",
                    },
                    {
                        "Id": "ep-new",
                        "Type": "Episode",
                        "SeriesId": "series-1",
                        "SeriesName": "Show",
                        "Name": "Latest",
                        "ParentIndexNumber": 1,
                        "IndexNumber": 1,
                        "Path": "/tv/latest.mkv",
                        "DateCreated": "2026-08-11T12:14:33Z",
                    },
                ],
                "TotalRecordCount": 2,
            }
        ]

        with (
            mock.patch.object(jellyfin_client, "jellyfin_get", side_effect=lambda *_args, **_kwargs: pages.pop(0)),
            mock.patch.object(jellyfin_client, "_jellyfin_items_path", return_value="/Users/u1/Items"),
            mock.patch.object(jellyfin_client, "_watch_next_image", return_value=None),
            mock.patch.object(jellyfin_client, "_watch_next_item_metadata", return_value={"thumbUrl": None}),
            mock.patch.object(jellyfin_client, "_get_series_metadata", return_value=jellyfin_client._empty_series_metadata()),
        ):
            items = jellyfin_client._fetch_recently_available_items(10)

        self.assertEqual([item["id"] for item in items], ["ep-new", "mv-old"])

    def test_pages_until_limit_filled(self):
        responses = [
            {
                "Items": [
                    {
                        "Id": "skip",
                        "Type": "Episode",
                        "SeriesId": "series-1",
                        "SeriesName": "Show",
                        "Name": "Bad",
                        "ParentIndexNumber": 1,
                        "IndexNumber": 1,
                        "Path": "",
                        "DateCreated": "2026-08-12T00:00:00Z",
                    }
                ],
                "TotalRecordCount": 2,
            },
            {
                "Items": [
                    {
                        "Id": "mv-1",
                        "Type": "Movie",
                        "Name": "Fresh",
                        "Path": "/movies/fresh.mkv",
                        "DateCreated": "2026-08-12T01:00:00Z",
                    }
                ],
                "TotalRecordCount": 2,
            },
        ]

        with (
            mock.patch.object(jellyfin_client, "jellyfin_get", side_effect=lambda *_args, **_kwargs: responses.pop(0)),
            mock.patch.object(jellyfin_client, "_jellyfin_items_path", return_value="/Users/u1/Items"),
            mock.patch.object(jellyfin_client, "_watch_next_image", return_value=None),
            mock.patch.object(jellyfin_client, "_watch_next_item_metadata", return_value={"thumbUrl": None}),
        ):
            items = jellyfin_client._fetch_recently_available_items(1)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "mv-1")

    def test_skips_watched_items_while_paging(self):
        responses = [
            {
                "Items": [
                    {
                        "Id": "ep-watched",
                        "Type": "Episode",
                        "SeriesId": "series-1",
                        "SeriesName": "House of the Dragon",
                        "Name": "The Heirs of the Dragon",
                        "ParentIndexNumber": 1,
                        "IndexNumber": 1,
                        "Path": "/tv/hotd/s01e01.mkv",
                        "DateCreated": "2026-08-13T00:00:00Z",
                        "UserData": {"Played": True, "PlayCount": 1},
                    }
                ],
                "TotalRecordCount": 2,
            },
            {
                "Items": [
                    {
                        "Id": "mv-fresh",
                        "Type": "Movie",
                        "Name": "Fresh",
                        "Path": "/movies/fresh.mkv",
                        "DateCreated": "2026-08-12T01:00:00Z",
                        "UserData": {"Played": False},
                    }
                ],
                "TotalRecordCount": 2,
            },
        ]

        with (
            mock.patch.object(jellyfin_client, "jellyfin_get", side_effect=lambda *_args, **_kwargs: responses.pop(0)),
            mock.patch.object(jellyfin_client, "_jellyfin_items_path", return_value="/Users/u1/Items"),
            mock.patch.object(jellyfin_client, "_watch_next_image", return_value=None),
            mock.patch.object(jellyfin_client, "_watch_next_item_metadata", return_value={"thumbUrl": None}),
        ):
            items = jellyfin_client._fetch_recently_available_items(1)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "mv-fresh")

    def test_stops_mapping_once_limit_reached(self):
        episodes = [
            {
                "Id": f"ep-{index}",
                "Type": "Episode",
                "SeriesId": f"series-{index}",
                "SeriesName": f"Show {index}",
                "Name": f"Episode {index}",
                "ParentIndexNumber": 1,
                "IndexNumber": index,
                "Path": f"/tv/show-{index}.mkv",
                "DateCreated": f"2026-08-1{index}T12:00:00Z",
            }
            for index in range(5)
        ]

        with (
            mock.patch.object(
                jellyfin_client,
                "jellyfin_get",
                return_value={"Items": episodes, "TotalRecordCount": len(episodes)},
            ),
            mock.patch.object(jellyfin_client, "_jellyfin_items_path", return_value="/Users/u1/Items"),
            mock.patch.object(jellyfin_client, "_watch_next_image", return_value=None),
            mock.patch.object(jellyfin_client, "_watch_next_item_metadata", return_value={"thumbUrl": None}),
            mock.patch.object(
                jellyfin_client,
                "_get_series_metadata",
                return_value=jellyfin_client._empty_series_metadata(),
            ) as metadata_mock,
        ):
            items = jellyfin_client._fetch_recently_available_items(2)

        self.assertEqual(len(items), 2)
        self.assertEqual(metadata_mock.call_count, 2)

    def test_payload_has_no_path_and_no_envelope_cache(self):
        with mock.patch.object(
            jellyfin_client,
            "_fetch_recently_available_items",
            return_value=[{"id": "mv-1", "kind": "movie"}],
        ):
            first = jellyfin_client._get_recently_available_payload(1)
            second = jellyfin_client._get_recently_available_payload(1)
        self.assertEqual(first, {"ok": True, "items": [{"id": "mv-1", "kind": "movie"}]})
        self.assertEqual(second, first)
        self.assertNotIn("recently-available", config._jellyfin_cache)


class RecentlyAvailableHandlerTests(unittest.TestCase):
    def test_returns_503_without_api_key(self):
        handler = mock.Mock()
        handler.wfile = io.BytesIO()
        with mock.patch.object(config, "JELLYFIN_API_KEY", ""):
            jellyfin_routes.handle_jellyfin_recently_available(handler, {})
        handler.wfile.seek(0)
        body = json.loads(handler.wfile.read().decode("utf-8"))
        self.assertFalse(body["ok"])
        handler.send_response.assert_called_with(503)

    def test_returns_502_with_stable_message(self):
        handler = mock.Mock()
        handler.wfile = io.BytesIO()
        with (
            mock.patch.object(config, "JELLYFIN_API_KEY", "configured"),
            mock.patch.object(
                jellyfin_routes,
                "_get_recently_available_payload",
                side_effect=RuntimeError("upstream exploded with /secret/path"),
            ),
        ):
            jellyfin_routes.handle_jellyfin_recently_available(handler, {})
        handler.wfile.seek(0)
        body = json.loads(handler.wfile.read().decode("utf-8"))
        self.assertEqual(body, {"ok": False, "error": "Jellyfin is temporarily unavailable"})
        handler.send_response.assert_called_with(502)


if __name__ == "__main__":
    unittest.main()
