#!/usr/bin/env python3
"""Combined Sonarr/Radarr calendar contract tests for FDM-680."""

import json
import threading
import time
import unittest
from datetime import date, timedelta
from io import BytesIO
from unittest import mock

import config
import routes.arr as arr_routes
import server


def _air(day_offset, hour=12, minute=0):
    day = date.today() + timedelta(days=day_offset)
    return f"{day.isoformat()}T{hour:02d}:{minute:02d}:00Z"


def _episode(
    episode_id,
    title="Cowboy Bebop",
    series_id=42,
    day_offset=2,
    hour=18,
    minute=0,
    season=1,
    number=5,
):
    return {
        "id": episode_id,
        "seriesId": series_id,
        "seasonNumber": season,
        "episodeNumber": number,
        "title": f"Episode {number}",
        "airDateUtc": _air(day_offset, hour, minute),
        "hasFile": False,
        "monitored": True,
        "series": {"id": series_id, "title": title, "monitored": True},
    }


def _movie(movie_id, title="Dune", day_offset=1, hour=10, minute=0):
    return {
        "id": movie_id,
        "title": title,
        "monitored": True,
        "hasFile": False,
        "digitalRelease": _air(day_offset, hour, minute),
    }


class _CaptureHandler:
    def __init__(self):
        self.headers = {}
        self.status = None
        self.wfile = BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.headers[name] = value

    def end_headers(self):
        pass

    def body(self):
        self.wfile.seek(0)
        return json.loads(self.wfile.read().decode("utf-8"))


class CalendarFeedTests(unittest.TestCase):
    def setUp(self):
        config._arr_cache.clear()

    def _call(self, fake_get, *, max_events=10, provider_timeout=0.25):
        with (
            mock.patch.object(config, "SONARR_API_KEY", "sonarr-key"),
            mock.patch.object(config, "RADARR_API_KEY", "radarr-key"),
            mock.patch.object(config, "CALENDAR_MAX_EVENTS", max_events),
            mock.patch.object(config, "CALENDAR_PROVIDER_TIMEOUT", provider_timeout, create=True),
            mock.patch.object(arr_routes, "_arr_get", side_effect=fake_get),
        ):
            handler = _CaptureHandler()
            arr_routes.handle_sonarr_calendar(handler)
        return handler

    def test_mixed_success_normalizes_provider_ids_and_source_health(self):
        calls = []

        def fake_get(base, api_key, path):
            calls.append((base, path))
            if base == config.SONARR_URL:
                return [_episode(11)]
            if base == config.RADARR_URL:
                return [_movie(22)]
            raise AssertionError(base)

        handler = self._call(fake_get)
        self.assertEqual(handler.status, 200)
        body = handler.body()
        self.assertEqual(body.get("sources"), {"sonarr": "ok", "radarr": "ok"})
        self.assertEqual([event["kind"] for event in body["events"]], ["movie", "episode"])
        movie, episode = body["events"]
        self.assertEqual(movie["id"], "radarr:movie:22")
        self.assertEqual(movie["movieId"], 22)
        self.assertEqual(episode["id"], "sonarr:episode:11")
        self.assertEqual(episode["episodeId"], 11)
        self.assertEqual(episode["seriesId"], 42)
        self.assertTrue(any(base == config.SONARR_URL for base, _ in calls))
        self.assertTrue(any(base == config.RADARR_URL for base, _ in calls))

    def test_sonarr_failure_keeps_radarr_events_and_sanitizes_degradation(self):
        def fake_get(base, api_key, path):
            if base == config.SONARR_URL:
                raise RuntimeError("sonarr-secret-upstream-body")
            return [_movie(22)]

        handler = self._call(fake_get)
        self.assertEqual(handler.status, 200)
        body = handler.body()
        self.assertEqual(body.get("sources"), {"sonarr": "error", "radarr": "ok"})
        self.assertEqual([event["kind"] for event in body["events"]], ["movie"])
        self.assertNotIn("sonarr-secret-upstream-body", json.dumps(body))

    def test_radarr_failure_keeps_sonarr_events_and_sanitizes_degradation(self):
        def fake_get(base, api_key, path):
            if base == config.RADARR_URL:
                raise RuntimeError("radarr-secret-upstream-body")
            return [_episode(11)]

        handler = self._call(fake_get)
        self.assertEqual(handler.status, 200)
        body = handler.body()
        self.assertEqual(body.get("sources"), {"sonarr": "ok", "radarr": "error"})
        self.assertEqual([event["kind"] for event in body["events"]], ["episode"])
        self.assertNotIn("radarr-secret-upstream-body", json.dumps(body))

    def test_complete_failure_only_when_neither_provider_is_usable(self):
        def fake_get(base, api_key, path):
            raise RuntimeError(f"secret-body-from-{base}")

        handler = self._call(fake_get)
        self.assertEqual(handler.status, 502)
        body = handler.body()
        self.assertEqual(body.get("sources"), {"sonarr": "error", "radarr": "error"})
        self.assertEqual(body.get("events"), [])
        self.assertEqual(body.get("error"), "Calendar is temporarily unavailable")
        self.assertNotIn("secret-body", json.dumps(body))

    def test_fetches_both_providers_concurrently(self):
        sonarr_started = threading.Event()
        radarr_started = threading.Event()

        def fake_get(base, api_key, path):
            if base == config.SONARR_URL:
                sonarr_started.set()
                radarr_started.wait(0.2)
                return [_episode(11)]
            radarr_started.set()
            sonarr_started.wait(0.2)
            return [_movie(22)]

        handler = self._call(fake_get)
        self.assertEqual(handler.status, 200)
        self.assertTrue(sonarr_started.is_set())
        self.assertTrue(radarr_started.is_set())
        self.assertEqual(len(handler.body()["events"]), 2)

    def test_provider_timeout_bounds_total_wait(self):
        def fake_get(base, api_key, path):
            time.sleep(0.2)
            return []

        started = time.monotonic()
        handler = self._call(fake_get, provider_timeout=0.03)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.15)
        self.assertEqual(handler.status, 502)
        self.assertEqual(handler.body().get("sources"), {"sonarr": "error", "radarr": "error"})

    def test_sorts_before_truncating_with_deterministic_ties(self):
        earlier = _movie(9, title="Earlier Movie", day_offset=1, hour=8)
        same_time = 2
        sonarr = [
            _episode(2, title="Zulu Show", day_offset=same_time, hour=20),
            _episode(1, title="Alpha Show", day_offset=same_time, hour=20),
        ]
        radarr = [
            _movie(4, title="Alpha Movie", day_offset=same_time, hour=20),
            _movie(3, title="Beta Movie", day_offset=same_time, hour=20),
            earlier,
        ]

        def fake_get(base, api_key, path):
            return sonarr if base == config.SONARR_URL else radarr

        handler = self._call(fake_get, max_events=4)
        self.assertEqual(handler.status, 200)
        self.assertEqual(
            [event["id"] for event in handler.body()["events"]],
            [
                "radarr:movie:9",
                "sonarr:episode:1",
                "sonarr:episode:2",
                "radarr:movie:4",
            ],
        )

    def test_unconfigured_provider_is_reported_without_failing_healthy_source(self):
        def fake_get(base, api_key, path):
            self.assertEqual(base, config.SONARR_URL)
            return [_episode(11)]

        with (
            mock.patch.object(config, "SONARR_API_KEY", "sonarr-key"),
            mock.patch.object(config, "RADARR_API_KEY", ""),
            mock.patch.object(config, "CALENDAR_PROVIDER_TIMEOUT", 0.25, create=True),
            mock.patch.object(arr_routes, "_arr_get", side_effect=fake_get),
        ):
            handler = _CaptureHandler()
            arr_routes.handle_sonarr_calendar(handler)
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.body().get("sources"), {"sonarr": "ok", "radarr": "unconfigured"})


class CalendarRouteTests(unittest.TestCase):
    def _dispatch(self, path):
        handler = object.__new__(server.ActionsHandler)
        handler.path = path
        with (
            mock.patch.object(server.arr, "handle_sonarr_calendar") as calendar,
            mock.patch.object(server, "send_json") as send_json,
        ):
            server.ActionsHandler.do_GET(handler)
        return calendar, send_json

    def test_neutral_calendar_route_dispatches_to_calendar_handler(self):
        calendar, send_json = self._dispatch("/calendar")
        calendar.assert_called_once()
        send_json.assert_not_called()

    def test_sonarr_calendar_remains_a_compatibility_alias(self):
        calendar, send_json = self._dispatch("/sonarr/calendar")
        calendar.assert_called_once()
        send_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
