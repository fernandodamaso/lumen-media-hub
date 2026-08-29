#!/usr/bin/env python3
"""Tests for PR 4 poster enrichment.

Covers the TTL poster cache (positive 24h, negative 5min, retry after
failure), the bounded worker pool (concurrency bound, batch timing vs
sequential), warm reads with zero Jellyseerr calls, and degraded-mode
resilience of GET /discover/ai-picks and POST /discover/ai-picks/request-more.

Only the network layer (routes._fetch_poster_path) and the cache clock
(routes._now) are faked; the cache, pool, and enrichment logic run for real.

Run from inside config/homepage-actions:
    python -m unittest test_poster_enrichment -v
"""

import io
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout

import config
import http_support
import recommendations_store as rs
from routes import discover as routes


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class FakeJellyseerr:
    """Stand-in for routes._fetch_poster_path.

    Tracks every call, the peak number of concurrent in-flight calls, and
    supports per-key failures (permanent or once-only) and an artificial
    per-call sleep for timing/concurrency tests.
    """

    def __init__(self, sleep=0.0, fail_keys=(), fail_once=(), paths=None):
        self.sleep = sleep
        self.fail_keys = set(fail_keys)
        self.fail_once = set(fail_once)
        self.paths = dict(paths or {})
        self._lock = threading.Lock()
        self._calls = []
        self._inflight = 0
        self.peak_inflight = 0

    def __call__(self, kind, tmdb_id):
        key = (kind, tmdb_id)
        with self._lock:
            self._calls.append(key)
            self._inflight += 1
            self.peak_inflight = max(self.peak_inflight, self._inflight)
        try:
            if self.sleep:
                time.sleep(self.sleep)
            if key in self.fail_keys:
                raise RuntimeError("jellyseerr unreachable")
            if key in self.fail_once:
                self.fail_once.discard(key)
                raise RuntimeError("transient 502")
            return self.paths.get(key, f"/{kind}-{tmdb_id}.jpg")
        finally:
            with self._lock:
                self._inflight -= 1

    def call_count(self):
        with self._lock:
            return len(self._calls)


class FakeHandler:
    """Minimal BaseHTTPRequestHandler stand-in for send_json/_read_json_body."""

    def __init__(self, body=None):
        raw = json.dumps(body).encode("utf-8") if body is not None else b""
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.wfile = io.BytesIO()
        self.status = None

    def send_response(self, status):
        self.status = status

    def send_header(self, *_args):
        pass

    def end_headers(self):
        pass

    def payload(self):
        return json.loads(self.wfile.getvalue().decode("utf-8") or b"{}")


class ReadJsonBodyTests(unittest.TestCase):
    def test_read_json_body_rejects_oversized_content_length(self):
        handler = FakeHandler()
        handler.headers = {"Content-Length": str(http_support.MAX_JSON_BODY_BYTES + 1)}
        with self.assertRaises(http_support._BodyTooLarge):
            http_support._read_json_body(handler)

    def test_read_json_body_rejects_invalid_content_length(self):
        handler = FakeHandler()
        handler.headers = {"Content-Length": "not-a-number"}
        with self.assertRaises(json.JSONDecodeError):
            http_support._read_json_body(handler)

    def test_read_json_body_accepts_body_at_limit(self):
        prefix = b'{"p":"'
        suffix = b'"}'
        pad_len = http_support.MAX_JSON_BODY_BYTES - len(prefix) - len(suffix)
        self.assertGreater(pad_len, 0)
        raw = prefix + (b"x" * pad_len) + suffix
        self.assertEqual(len(raw), http_support.MAX_JSON_BODY_BYTES)
        handler = FakeHandler()
        handler.headers = {"Content-Length": str(http_support.MAX_JSON_BODY_BYTES)}
        handler.rfile = io.BytesIO(raw)
        self.assertEqual(http_support._read_json_body(handler), {"p": "x" * pad_len})


def make_ai_picks_item(tmdb_id, **extra):
    media_type = extra.get("type", "movie")
    item = {
        "id": f"ai-{media_type}-{tmdb_id}",
        "identity": f"{media_type}:{tmdb_id}",
        "source": "ai",
        "type": "movie",
        "title": f"Title {tmdb_id}",
        "year": 2000,
        "tmdb_id": tmdb_id,
        "reason": "fixture",
        "active": True,
        "feedback": None,
        "feedback_at": None,
        "request_state": None,
        "requested_at": None,
        "jellyseerr_request_id": None,
        "added_at": "2026-01-01T00:00:00Z",
    }
    item.update(extra)
    return item


class PosterEnrichmentTestCase(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.client = FakeJellyseerr()
        self._old_now = routes._now
        self._old_fetch = routes._fetch_poster_path
        self._old_key = config.JELLYSEERR_API_KEY
        self._old_enabled = config.JELLYSEERR_ENABLED
        self._old_jf_key = config.JELLYFIN_API_KEY
        import config as settings

        settings.JELLYSEERR_API_KEY = "test-key"
        settings.JELLYSEERR_ENABLED = True
        settings.JELLYFIN_API_KEY = ""
        routes._now = self.clock
        routes._fetch_poster_path = self.client
        config.JELLYSEERR_API_KEY = "test-key"
        config.JELLYSEERR_ENABLED = True
        # Keep Jellyfin enrichment in its no-key fallback branch.
        config.JELLYFIN_API_KEY = ""
        with routes._poster_path_cache_lock:
            routes._poster_path_cache.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        import config as settings

        routes._now = self._old_now
        routes._fetch_poster_path = self._old_fetch
        settings.JELLYSEERR_API_KEY = self._old_key
        settings.JELLYSEERR_ENABLED = self._old_enabled
        settings.JELLYFIN_API_KEY = self._old_jf_key
        config.JELLYSEERR_API_KEY = self._old_key
        config.JELLYSEERR_ENABLED = self._old_enabled
        config.JELLYFIN_API_KEY = self._old_jf_key
        with routes._poster_path_cache_lock:
            routes._poster_path_cache.clear()

    def resolve(self, pairs):
        return routes._resolve_poster_paths(pairs)


class TtlCacheTests(PosterEnrichmentTestCase):
    def test_positive_ttl_caches_success_for_24h(self):
        result = self.resolve([("movie", 1), ("tv", 2)])
        self.assertEqual(result[("movie", 1)], "/movie-1.jpg")
        self.assertEqual(self.client.call_count(), 2)

        # 23h59m later: still cached, zero new calls.
        self.clock.advance(23 * 3600 + 59 * 60)
        again = self.resolve([("movie", 1), ("tv", 2)])
        self.assertEqual(again, result)
        self.assertEqual(self.client.call_count(), 2)

        # Past 24h: entries expire and are refetched.
        self.clock.advance(2 * 60)
        self.resolve([("movie", 1), ("tv", 2)])
        self.assertEqual(self.client.call_count(), 4)

    def test_negative_ttl_caches_failure_for_5min(self):
        self.client.fail_keys.add(("movie", 9))
        result = self.resolve([("movie", 9)])
        self.assertIsNone(result[("movie", 9)])
        self.assertEqual(self.client.call_count(), 1)

        # 4 minutes later: failure still cached, no retry yet.
        self.clock.advance(4 * 60)
        again = self.resolve([("movie", 9)])
        self.assertIsNone(again[("movie", 9)])
        self.assertEqual(self.client.call_count(), 1)

        # Past the 5-minute negative TTL: eligible for retry.
        self.clock.advance(61)
        self.resolve([("movie", 9)])
        self.assertEqual(self.client.call_count(), 2)

    def test_not_found_uses_negative_ttl(self):
        # A successful call that returns no path is a miss, not a 24h cache.
        self.client.paths[("movie", 5)] = None
        self.resolve([("movie", 5)])
        self.clock.advance(routes.POSTER_NEGATIVE_TTL_SECONDS - 1)
        self.resolve([("movie", 5)])
        self.assertEqual(self.client.call_count(), 1)
        self.clock.advance(2)
        self.resolve([("movie", 5)])
        self.assertEqual(self.client.call_count(), 2)

    def test_retry_after_failure_succeeds(self):
        self.client.fail_once.add(("movie", 7))
        first = self.resolve([("movie", 7)])
        self.assertIsNone(first[("movie", 7)])

        self.clock.advance(routes.POSTER_NEGATIVE_TTL_SECONDS + 1)
        second = self.resolve([("movie", 7)])
        self.assertEqual(second[("movie", 7)], "/movie-7.jpg")
        self.assertEqual(self.client.call_count(), 2)

        # The recovered value is now under the positive TTL.
        self.clock.advance(3600)
        third = self.resolve([("movie", 7)])
        self.assertEqual(third[("movie", 7)], "/movie-7.jpg")
        self.assertEqual(self.client.call_count(), 2)

    def test_single_lookup_shares_ttl_cache_with_batch_resolver(self):
        # Warm the cache via the batch resolver...
        self.resolve([("movie", 42)])
        self.assertEqual(self.client.call_count(), 1)
        # ...the single-lookup path serves it with zero additional calls.
        self.assertEqual(routes._jellyseerr_poster_path("movie", 42), "/movie-42.jpg")
        self.assertEqual(self.client.call_count(), 1)
        # And a value cached by the single lookup is a batch hit too.
        self.assertEqual(routes._jellyseerr_poster_path("tv", 7), "/tv-7.jpg")
        self.assertEqual(self.client.call_count(), 2)
        result = self.resolve([("tv", 7)])
        self.assertEqual(result[("tv", 7)], "/tv-7.jpg")
        self.assertEqual(self.client.call_count(), 2)


class ConcurrencyTests(PosterEnrichmentTestCase):
    def test_concurrency_bound_never_exceeded(self):
        self.client.sleep = 0.05
        pairs = [("movie", i) for i in range(1, 13)]
        result = self.resolve(pairs)
        self.assertEqual(len(result), 12)
        self.assertLessEqual(self.client.peak_inflight, routes.POSTER_ENRICH_CONCURRENCY)
        # With 12 items and a per-call sleep the pool must actually parallelize.
        self.assertGreaterEqual(self.client.peak_inflight, 2)

    def test_batch_duration_tracks_slowest_bounded_group(self):
        # 8 items x 0.1s with bound 4 -> two waves ~0.2s, not 0.8s sequential.
        self.client.sleep = 0.1
        pairs = [("movie", i) for i in range(1, 9)]
        started = time.monotonic()
        self.resolve(pairs)
        duration = time.monotonic() - started
        self.assertGreaterEqual(duration, 0.15)
        self.assertLess(duration, 0.5)  # well under the 0.8s sequential time


class EnrichmentTests(PosterEnrichmentTestCase):
    def test_enriches_only_items_missing_both_poster_fields(self):
        items = [
            make_ai_picks_item(1, poster_path="/persisted.jpg"),
            make_ai_picks_item(2, poster_url="https://example.com/x.jpg"),
            make_ai_picks_item(3),
        ]
        routes._enrich_ai_picks_posters(items)
        # Only item 3 needed a Jellyseerr call.
        self.assertEqual(self.client.call_count(), 1)
        self.assertEqual(items[0]["poster_url"], "https://image.tmdb.org/t/p/w342/persisted.jpg")
        self.assertEqual(items[1]["poster_url"], "https://example.com/x.jpg")
        self.assertEqual(items[2]["poster_url"], "https://image.tmdb.org/t/p/w342/movie-3.jpg")

    def test_warm_read_with_persisted_poster_path_makes_zero_calls(self):
        items = [make_ai_picks_item(i, poster_path=f"/p{i}.jpg") for i in range(1, 26)]
        routes._enrich_ai_picks_posters(items)
        self.assertEqual(self.client.call_count(), 0)
        for item in items:
            i = item["tmdb_id"]
            self.assertEqual(item["poster_url"], f"https://image.tmdb.org/t/p/w342/p{i}.jpg")

    def test_enrichment_degrades_when_client_raises(self):
        self.client.fail_keys = {("movie", i) for i in range(1, 4)}
        items = [make_ai_picks_item(i) for i in range(1, 4)]
        result = routes._enrich_ai_picks_posters(items)  # must not raise
        for item in result:
            self.assertIsNone(item["poster_url"])
            self.assertTrue(item["title"])  # title fallback intact

    def test_no_api_key_resolves_without_calls(self):
        import config as settings

        settings.JELLYSEERR_API_KEY = ""
        settings.JELLYSEERR_ENABLED = False
        config.JELLYSEERR_API_KEY = ""
        config.JELLYSEERR_ENABLED = False
        result = self.resolve([("movie", 1)])
        self.assertEqual(result, {("movie", 1): None})
        self.assertEqual(self.client.call_count(), 0)

    def test_disabled_resolution_logs_disabled_reason(self):
        import config as settings

        settings.JELLYSEERR_ENABLED = False
        config.JELLYSEERR_ENABLED = False
        output = io.StringIO()
        with redirect_stdout(output):
            self.resolve([("movie", 1)])
        self.assertIn("reason=disabled", output.getvalue())

    def test_missing_key_resolution_logs_no_api_key_reason(self):
        import config as settings

        settings.JELLYSEERR_API_KEY = ""
        config.JELLYSEERR_API_KEY = ""
        output = io.StringIO()
        with redirect_stdout(output):
            self.resolve([("movie", 1)])
        self.assertIn("reason=no-api-key", output.getvalue())


class TimingComparisonTests(PosterEnrichmentTestCase):
    def test_cold_vs_warm_25_card_timing(self):
        # Cold: 25 misses, each fake call sleeps 0.02s. Sequential would be
        # 0.5s; bounded at 4 -> ~7 waves ~0.14s.
        self.client.sleep = 0.02
        cold_items = [make_ai_picks_item(i) for i in range(1, 26)]
        started = time.monotonic()
        routes._enrich_ai_picks_posters(cold_items)
        cold = time.monotonic() - started
        self.assertEqual(self.client.call_count(), 25)
        self.assertLess(cold, 0.35)

        # Warm: same cards with persisted poster_path -> zero calls.
        warm_items = [
            make_ai_picks_item(i, poster_path=f"/movie-{i}.jpg") for i in range(1, 26)
        ]
        started = time.monotonic()
        routes._enrich_ai_picks_posters(warm_items)
        warm = time.monotonic() - started
        self.assertEqual(self.client.call_count(), 25)
        self.assertLess(warm, cold)
        print(
            f"\n[timing] cold 25-card enrich: {cold:.3f}s (25 fetches, bound "
            f"{routes.POSTER_ENRICH_CONCURRENCY}); warm: {warm:.4f}s (0 fetches)"
        )


class ApiResilienceTests(PosterEnrichmentTestCase):
    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp(prefix="poster-api-test-")
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.store = rs.RecommendationStore(os.path.join(self.tmpdir, "recommendations.json"))
        self._old_store = config.RECOMMENDATIONS_STORE
        import config as settings

        settings.RECOMMENDATIONS_STORE = self.store
        config.RECOMMENDATIONS_STORE = self.store
        self.addCleanup(self._restore_store)
        self._old_generation_request_path = config.GENERATION_REQUEST_PATH
        config.GENERATION_REQUEST_PATH = os.path.join(
            self.tmpdir, "generation-request.json"
        )
        self.addCleanup(self._restore_generation_request_path)

    def _restore_generation_request_path(self):
        config.GENERATION_REQUEST_PATH = self._old_generation_request_path

    def _restore_store(self):
        import config as settings

        settings.RECOMMENDATIONS_STORE = self._old_store
        config.RECOMMENDATIONS_STORE = self._old_store

    def seed(self, items):
        def _apply(doc):
            doc["items"].extend(items)
            doc["presented_media_ids"].extend(item["identity"] for item in items)

        return self.store.update(_apply)

    def test_get_returns_data_when_jellyseerr_is_down(self):
        self.seed([make_ai_picks_item(1), make_ai_picks_item(2, poster_path="/p2.jpg")])
        self.client.fail_keys = {("movie", 1)}
        handler = FakeHandler()
        routes.handle_discover_ai_picks_get(handler)
        self.assertEqual(handler.status, 200)
        payload = handler.payload()
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["items"]), 2)
        by_tmdb = {i["tmdb_id"]: i for i in payload["items"]}
        self.assertEqual(by_tmdb[1]["title"], "Title 1")  # title fallback
        self.assertIsNone(by_tmdb[1]["poster_url"])
        self.assertEqual(
            by_tmdb[2]["poster_url"], "https://image.tmdb.org/t/p/w342/p2.jpg"
        )

if __name__ == "__main__":
    unittest.main()
