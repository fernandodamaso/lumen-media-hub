#!/usr/bin/env python3
"""Watch-next Jellyfin contract tests."""

import io
import json
import unittest
from unittest import mock

import config
import clients.jellyfin as jellyfin_client
import routes.jellyfin as jellyfin_routes


class WatchNextMappingTests(unittest.TestCase):
    def test_progress_percent_clamps_and_handles_missing_runtime(self):
        self.assertEqual(jellyfin_client._progress_percent({"Played": False, "PlaybackPositionTicks": 0}, 1000), 0)
        self.assertEqual(jellyfin_client._progress_percent({"Played": False, "PlaybackPositionTicks": 500}, 1000), 50)
        self.assertEqual(jellyfin_client._progress_percent({"Played": False, "PlaybackPositionTicks": 2000}, 1000), 100)
        self.assertEqual(jellyfin_client._progress_percent({"Played": False, "PlaybackPositionTicks": 100}, 0), 1)
        self.assertIsNone(jellyfin_client._progress_percent({"Played": True, "PlaybackPositionTicks": 500}, 1000))

    def test_format_episode_subtitle(self):
        raw = {"ParentIndexNumber": 4, "IndexNumber": 2, "Name": "Jetsam"}
        self.assertEqual(jellyfin_client._format_episode_subtitle(raw), "S04E02 · Jetsam")

    def test_maps_partial_movie_and_episode(self):
        movie = jellyfin_client._map_watch_next_item(
            {
                "Id": "mv-1",
                "Type": "Movie",
                "Name": "Dune",
                "Path": "/movies/dune.mkv",
                "RunTimeTicks": 10_000,
                "UserData": {"Played": False, "PlaybackPositionTicks": 1800},
            }
        )
        self.assertEqual(
            movie,
            {
                "id": "mv-1",
                "parentId": None,
                "title": "Dune",
                "subtitle": "",
                "kind": "movie",
                "image": None,
                "playable": True,
                "progressPercent": 18,
                "_sort_last_played": "",
                "_sort_date": "",
            },
        )

        episode = jellyfin_client._map_watch_next_item(
            {
                "Id": "ep-1",
                "Type": "Episode",
                "SeriesId": "series-1",
                "SeriesName": "The Expanse",
                "Name": "Jetsam",
                "ParentIndexNumber": 4,
                "IndexNumber": 2,
                "Path": "/tv/expanse.mkv",
                "RunTimeTicks": 1000,
                "UserData": {"Played": False, "PlaybackPositionTicks": 420},
            }
        )
        self.assertEqual(episode["parentId"], "series-1")
        self.assertEqual(episode["subtitle"], "S04E02 · Jetsam")
        self.assertEqual(episode["progressPercent"], 42)

    def test_skips_jellynext_virtual_paths(self):
        self.assertIsNone(
            jellyfin_client._map_watch_next_item(
                {
                    "Id": "ep-bad",
                    "Type": "Episode",
                    "SeriesId": "series-1",
                    "SeriesName": "Show",
                    "Name": "Pilot",
                    "Path": "/jellynext-virtual/show/pilot.strm",
                },
                force_progress=0,
            )
        )

    def test_episode_image_prefers_series_poster(self):
        with mock.patch.object(
            jellyfin_client,
            "_jellyfin_image_url",
            side_effect=lambda item_id, image_tag=None: f"{item_id}:{image_tag}",
        ) as image_url:
            url = jellyfin_client._watch_next_image(
                {
                    "Id": "ep-1",
                    "Type": "Episode",
                    "SeriesId": "series-1",
                    "ImageTags": {"Primary": "episode-tag"},
                }
            )
        image_url.assert_called_once_with("series-1")
        self.assertEqual(url, "series-1:None")


class WatchNextFetchTests(unittest.TestCase):
    def setUp(self):
        config._jellyfin_cache.clear()

    def _patch_watch_next_sources(
        self,
        resume=None,
        next_up=None,
        unwatched_movies=None,
        unplayed_series=None,
        first_episode=None,
    ):
        resume = resume if resume is not None else []
        next_up = next_up if next_up is not None else []
        unwatched_movies = unwatched_movies if unwatched_movies is not None else []
        unplayed_series = unplayed_series if unplayed_series is not None else []
        first_episode = first_episode if first_episode is not None else {}

        return mock.patch.multiple(
            "clients.jellyfin",
            _fetch_jellyfin_resume_raw=mock.Mock(return_value=resume),
            _fetch_jellyfin_next_up_raw=mock.Mock(return_value=next_up),
            _fetch_jellyfin_unwatched_movies_raw=mock.Mock(return_value=unwatched_movies),
            _fetch_jellyfin_unplayed_series_raw=mock.Mock(return_value=unplayed_series),
            _fetch_first_playable_episode_for_series=mock.Mock(
                side_effect=lambda series_id: first_episode.get(series_id)
            ),
        )

    def test_resume_episode_wins_over_next_up_for_same_series(self):
        resume_episode = {
            "Id": "ep-resume",
            "Type": "Episode",
            "SeriesId": "series-1",
            "SeriesName": "The Expanse",
            "Name": "Jetsam",
            "ParentIndexNumber": 4,
            "IndexNumber": 2,
            "Path": "/tv/jetsam.mkv",
            "RunTimeTicks": 1000,
            "UserData": {"Played": False, "PlaybackPositionTicks": 100},
        }
        next_up_episode = {
            "Id": "ep-next",
            "Type": "Episode",
            "SeriesId": "series-1",
            "SeriesName": "The Expanse",
            "Name": "Later",
            "ParentIndexNumber": 4,
            "IndexNumber": 3,
            "Path": "/tv/later.mkv",
            "UserData": {"Played": False},
        }
        with self._patch_watch_next_sources(resume=[resume_episode], next_up=[next_up_episode]):
            payload = jellyfin_client._fetch_watch_next_items()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["id"], "ep-resume")

    def test_includes_unwatched_movie_at_zero_percent(self):
        movie = {
            "Id": "mv-michael",
            "Type": "Movie",
            "Name": "Michael",
            "Path": "/movies/michael.mkv",
            "RunTimeTicks": 10_000,
            "UserData": {"Played": False, "PlaybackPositionTicks": 0},
            "DateCreated": "2025-06-01T00:00:00.0000000Z",
        }
        with self._patch_watch_next_sources(unwatched_movies=[movie]):
            payload = jellyfin_client._fetch_watch_next_items()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["id"], "mv-michael")
        self.assertEqual(payload["items"][0]["progressPercent"], 0)

    def test_unstarted_series_contributes_first_episode(self):
        series = {
            "Id": "series-apothecary",
            "Type": "Series",
            "Name": "The Apothecary Diaries",
            "DateCreated": "2025-05-01T00:00:00.0000000Z",
        }
        pilot = {
            "Id": "ep-pilot",
            "Type": "Episode",
            "SeriesId": "series-apothecary",
            "SeriesName": "The Apothecary Diaries",
            "Name": "Episode 1",
            "ParentIndexNumber": 1,
            "IndexNumber": 1,
            "Path": "/tv/apothecary/s01e01.mkv",
            "UserData": {"Played": False},
        }
        with self._patch_watch_next_sources(
            unplayed_series=[series],
            first_episode={"series-apothecary": pilot},
        ):
            payload = jellyfin_client._fetch_watch_next_items()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["id"], "ep-pilot")
        self.assertEqual(payload["items"][0]["subtitle"], "S01E01 · Episode 1")

    def test_series_already_in_next_up_not_duplicated_from_unplayed_list(self):
        next_up_episode = {
            "Id": "ep-next",
            "Type": "Episode",
            "SeriesId": "series-1",
            "SeriesName": "Show",
            "Name": "Next",
            "ParentIndexNumber": 1,
            "IndexNumber": 2,
            "Path": "/tv/next.mkv",
            "UserData": {"Played": False},
        }
        series = {"Id": "series-1", "Type": "Series", "Name": "Show"}
        with self._patch_watch_next_sources(
            next_up=[next_up_episode],
            unplayed_series=[series],
            first_episode={"series-1": {"Id": "ep-should-not-fetch"}},
        ):
            payload = jellyfin_client._fetch_watch_next_items()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["id"], "ep-next")

    def test_empty_when_all_sources_empty(self):
        with self._patch_watch_next_sources():
            payload = jellyfin_client._fetch_watch_next_items()
        self.assertEqual(payload, {"ok": True, "items": []})

    def test_empty_when_no_resume_or_next_up(self):
        with self._patch_watch_next_sources():
            payload = jellyfin_client._fetch_watch_next_items()
        self.assertEqual(payload, {"ok": True, "items": []})


class WatchNextHandlerTests(unittest.TestCase):
    def test_returns_503_without_api_key(self):
        handler = mock.Mock()
        handler.wfile = io.BytesIO()
        with mock.patch.object(config, "JELLYFIN_API_KEY", ""):
            jellyfin_routes.handle_jellyfin_watch_next(handler)
        handler.wfile.seek(0)
        body = json.loads(handler.wfile.read().decode("utf-8"))
        self.assertFalse(body["ok"])
        handler.send_response.assert_called_with(503)


if __name__ == "__main__":
    unittest.main()
