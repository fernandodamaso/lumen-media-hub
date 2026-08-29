import threading
import time
import unittest

from clients.jellyseerr import JellyseerrUpstreamError
from clients import arr as arr_client
import media_requests
from routes import discover as discover_routes


class _Store:
    def __init__(self, item, *, fail_update=False):
        self.doc = {"items": [dict(item)]}
        self.fail_update = fail_update

    def load(self):
        return {"items": [dict(item) for item in self.doc["items"]]}

    def update(self, mutator):
        if self.fail_update:
            raise OSError("SECRET persistence path=C:\\private")
        mutator(self.doc)
        return self.doc


def _hermes_item(media_type="movie", tmdb_id=42):
    return {
        "id": f"hermes-{media_type}-{tmdb_id}",
        "identity": f"{media_type}:{tmdb_id}",
        "source": "hermes",
        "type": media_type,
        "tmdb_id": tmdb_id,
        "active": True,
        "feedback": "liked",
        "request_state": None,
        "request_provider": None,
        "requested_at": None,
        "jellyseerr_request_id": None,
    }


class RequestValidationTests(unittest.TestCase):
    def test_valid_movie_and_tv_payloads_build_only_the_safe_jellyseerr_contract(self):
        movie = media_requests.validate_request_payload(
            {"mediaType": "movie", "mediaId": 42}
        )
        tv = media_requests.validate_request_payload(
            {
                "mediaType": "tv",
                "mediaId": 42,
                "seasons": [2, 0, 1],
                "is4k": False,
                "hermesId": "hermes-tv-42",
            }
        )

        self.assertIsNotNone(movie)
        self.assertIsNotNone(tv)
        self.assertEqual(
            movie.jellyseerr_payload(),
            {"mediaType": "movie", "mediaId": 42, "is4k": False},
        )
        self.assertEqual(
            tv.jellyseerr_payload(),
            {
                "mediaType": "tv",
                "mediaId": 42,
                "seasons": [0, 1, 2],
                "is4k": False,
            },
        )
        self.assertEqual(tv.hermes_id, "hermes-tv-42")

    def test_tv_all_is_preserved(self):
        command = media_requests.validate_request_payload(
            {"mediaType": "tv", "mediaId": 9, "seasons": "all"}
        )
        self.assertIsNotNone(command)
        self.assertEqual(command.jellyseerr_payload()["seasons"], "all")

    def test_invalid_contracts_are_rejected_before_any_writer_can_run(self):
        invalid = (
            {},
            {"mediaType": "series", "mediaId": 1, "seasons": [1]},
            {"mediaType": "movie", "mediaId": 0},
            {"mediaType": "movie", "mediaId": True},
            {"mediaType": "movie", "mediaId": "42"},
            {"mediaType": "movie", "mediaId": 1, "seasons": None},
            {"mediaType": "tv", "mediaId": 1},
            {"mediaType": "tv", "mediaId": 1, "seasons": []},
            {"mediaType": "tv", "mediaId": 1, "seasons": [1, 1]},
            {"mediaType": "tv", "mediaId": 1, "seasons": [-1]},
            {"mediaType": "tv", "mediaId": 1, "seasons": [True]},
            {"mediaType": "tv", "mediaId": 1, "seasons": "ALL"},
            {"mediaType": "movie", "mediaId": 1, "is4k": True},
            {"mediaType": "movie", "mediaId": 1, "is4k": None},
            {"mediaType": "movie", "mediaId": 1, "rootFolderPath": "/media"},
            {"mediaType": "movie", "mediaId": 1, "qualityProfileId": 7},
            {"mediaType": "movie", "mediaId": 1, "serverId": 3},
        )
        for payload in invalid:
            with self.subTest(payload=payload):
                with self.assertRaises(media_requests.MediaRequestValidationError):
                    media_requests.validate_request_payload(payload)


class MediaRequestServiceTests(unittest.TestCase):
    def service(
        self,
        *,
        states=None,
        post=None,
        invalidations=None,
        store=None,
        enqueue=None,
    ):
        states = states or [{"status": "missing"}]
        state_calls = []

        def state_reader(media_type, media_id, *, force=False):
            state_calls.append((media_type, media_id, force))
            index = min(len(state_calls) - 1, len(states) - 1)
            return dict(states[index])

        invalidations = invalidations if invalidations is not None else []
        service = media_requests.MediaRequestService(
            state_reader=state_reader,
            post_request=post
            or (lambda _path, _payload: {"id": 812, "status": 1}),
            invalidate_state=lambda media_type, media_id: invalidations.append(
                (media_type, media_id)
            ),
            store=store,
            enqueue_reconciliation=enqueue,
        )
        return service, state_calls, invalidations

    def test_missing_tv_posts_the_exact_safe_payload_and_invalidates_status_caches(self):
        posts = []
        service, state_calls, invalidations = self.service(
            post=lambda path, payload: posts.append((path, payload))
            or {"id": 812, "status": 2}
        )

        result = service.request(
            {"mediaType": "tv", "mediaId": 42, "seasons": [3, 1]}
        )

        self.assertEqual(
            posts,
            [
                (
                    "/api/v1/request",
                    {
                        "mediaType": "tv",
                        "mediaId": 42,
                        "seasons": [1, 3],
                        "is4k": False,
                    },
                )
            ],
        )
        self.assertEqual(state_calls, [("tv", 42, False)])
        self.assertEqual(invalidations, [("tv", 42)])
        self.assertEqual(
            result,
            {
                "ok": True,
                "partial_success": False,
                "jellyseerr_request_id": 812,
                "request_status": "processing",
                "already_requested": False,
                "dashboard_state_persisted": True,
                "reconciliation_queued": False,
                "message": "Request submitted to Jellyseerr.",
            },
        )

    def test_available_and_tracked_conflict_while_unknown_fails_closed(self):
        for state, error_type in (
            ({"status": "available"}, media_requests.MediaRequestConflict),
            ({"status": "tracked"}, media_requests.MediaRequestConflict),
            ({"status": "unknown"}, media_requests.MediaRequestUnavailable),
        ):
            with self.subTest(state=state):
                posts = []
                service, _, _ = self.service(
                    states=[state], post=lambda *args: posts.append(args)
                )
                with self.assertRaises(error_type):
                    service.request({"mediaType": "movie", "mediaId": 42})
                self.assertEqual(posts, [])

    def test_existing_active_request_is_idempotent_only_with_a_real_id(self):
        for status in ("requested", "processing"):
            with self.subTest(status=status):
                service, _, invalidations = self.service(
                    states=[{"status": status, "requestId": 700}]
                )
                result = service.request({"mediaType": "movie", "mediaId": 42})
                self.assertEqual(result["jellyseerr_request_id"], 700)
                self.assertEqual(result["request_status"], status)
                self.assertTrue(result["already_requested"])
                self.assertEqual(invalidations, [])

        service, _, _ = self.service(
            states=[{"status": "requested", "requestId": None}]
        )
        with self.assertRaises(media_requests.MediaRequestUnavailable):
            service.request({"mediaType": "movie", "mediaId": 42})

    def test_409_and_ambiguous_timeout_refetch_and_recover_only_a_real_request(self):
        for error in (
            JellyseerrUpstreamError(status=409),
            JellyseerrUpstreamError(status=None, ambiguous=True),
        ):
            with self.subTest(error=error):
                service, calls, invalidations = self.service(
                    states=[
                        {"status": "missing"},
                        {"status": "requested", "requestId": 901},
                    ],
                    post=lambda *_args, _error=error: (_ for _ in ()).throw(_error),
                )
                result = service.request({"mediaType": "movie", "mediaId": 42})
                self.assertEqual(
                    calls, [("movie", 42, False), ("movie", 42, True)]
                )
                self.assertEqual(invalidations, [("movie", 42), ("movie", 42)])
                self.assertEqual(result["jellyseerr_request_id"], 901)
                self.assertTrue(result["already_requested"])

    def test_recovery_without_a_matching_real_id_returns_only_a_safe_failure(self):
        secret = "SECRET upstream body path=C:\\private"
        for recovered in (
            {"status": "missing"},
            {"status": "requested", "requestId": None},
        ):
            with self.subTest(recovered=recovered):
                service, _, _ = self.service(
                    states=[{"status": "missing"}, recovered],
                    post=lambda *_args: (_ for _ in ()).throw(
                        JellyseerrUpstreamError(status=409, safe_detail=secret)
                    ),
                )
                with self.assertRaises(
                    media_requests.MediaRequestUpstreamFailure
                ) as raised:
                    service.request({"mediaType": "movie", "mediaId": 42})
                self.assertNotIn(secret, str(raised.exception))

    def test_non_ambiguous_upstream_failure_does_not_refetch(self):
        service, calls, _ = self.service(
            post=lambda *_args: (_ for _ in ()).throw(
                JellyseerrUpstreamError(status=500)
            )
        )
        with self.assertRaises(media_requests.MediaRequestUpstreamFailure):
            service.request({"mediaType": "movie", "mediaId": 42})
        self.assertEqual(calls, [("movie", 42, False)])

    def test_hermes_identity_is_validated_before_post_and_persists_jellyseerr(self):
        store = _Store(_hermes_item())
        posts = []
        service, _, _ = self.service(
            store=store,
            post=lambda path, payload: posts.append((path, payload))
            or {"id": 812, "status": 1},
        )
        result = service.request(
            {
                "mediaType": "movie",
                "mediaId": 42,
                "hermesId": "hermes-movie-42",
            }
        )
        item = store.doc["items"][0]
        self.assertEqual(result["jellyseerr_request_id"], 812)
        self.assertEqual(item["request_provider"], "jellyseerr")
        self.assertEqual(item["jellyseerr_request_id"], 812)
        self.assertEqual(item["request_state"], "requested")
        self.assertEqual(item["feedback"], "liked")

        mismatched = _Store(_hermes_item("movie", 42))
        mismatch_service, _, _ = self.service(store=mismatched, post=lambda *a: posts.append(a))
        with self.assertRaises(media_requests.HermesIdentityMismatch):
            mismatch_service.request(
                {
                    "mediaType": "tv",
                    "mediaId": 42,
                    "seasons": [1],
                    "hermesId": "hermes-movie-42",
                }
            )
        self.assertEqual(len(posts), 1)

    def test_jellyseerr_success_with_persistence_failure_queues_provider_aware_reconciliation(self):
        store = _Store(_hermes_item(), fail_update=True)
        queued = []
        service, _, _ = self.service(
            store=store,
            enqueue=lambda hermes_id, request_id, provider: queued.append(
                (hermes_id, request_id, provider)
            )
            or True,
        )
        result = service.request(
            {
                "mediaType": "movie",
                "mediaId": 42,
                "hermesId": "hermes-movie-42",
            }
        )

        self.assertEqual(queued, [("hermes-movie-42", 812, "jellyseerr")])
        self.assertTrue(result["partial_success"])
        self.assertFalse(result["dashboard_state_persisted"])
        self.assertTrue(result["reconciliation_queued"])
        self.assertEqual(
            result["message"],
            "Jellyseerr accepted the request; dashboard synchronization failed.",
        )


class RequestSerializationTests(unittest.TestCase):
    def test_same_typed_identity_serializes_and_second_request_is_idempotent(self):
        active = {}
        entered_post = threading.Event()
        release_post = threading.Event()
        post_count = 0
        guard = threading.Lock()

        def state_reader(media_type, media_id, *, force=False):
            return dict(active.get((media_type, media_id), {"status": "missing"}))

        def post(_path, payload):
            nonlocal post_count
            with guard:
                post_count += 1
            entered_post.set()
            release_post.wait(2)
            active[(payload["mediaType"], payload["mediaId"])] = {
                "status": "requested",
                "requestId": 812,
            }
            return {"id": 812, "status": 1}

        service = media_requests.MediaRequestService(
            state_reader=state_reader,
            post_request=post,
            invalidate_state=lambda *_args: None,
        )
        results = []
        threads = [
            threading.Thread(
                target=lambda: results.append(
                    service.request({"mediaType": "movie", "mediaId": 42})
                )
            )
            for _ in range(2)
        ]
        threads[0].start()
        self.assertTrue(entered_post.wait(1))
        threads[1].start()
        time.sleep(0.05)
        release_post.set()
        for thread in threads:
            thread.join(2)

        self.assertEqual(post_count, 1)
        self.assertEqual(sorted(result["already_requested"] for result in results), [False, True])
        self.assertEqual(len(service._locks._entries), 0)


class SingleWriterCutoverTests(unittest.TestCase):
    def test_direct_arr_request_writers_and_unsafe_defaults_are_removed(self):
        for owner, names in (
            (
                arr_client,
                (
                    "_add_to_arr_unmonitored",
                    "_add_radarr_movie_unmonitored",
                    "_add_sonarr_series_unmonitored",
                    "RADARR_ROOT_FOLDER",
                    "SONARR_ROOT_FOLDER",
                    "RADARR_QUALITY_PROFILE_ID",
                    "SONARR_QUALITY_PROFILE_ID",
                ),
            ),
            (discover_routes, ("_add_to_arr_unmonitored",)),
        ):
            with self.subTest(owner=owner.__name__):
                self.assertFalse(any(hasattr(owner, name) for name in names))

    def test_movie_and_tv_numeric_collision_do_not_share_a_lock(self):
        movie_entered = threading.Event()
        tv_entered = threading.Event()
        release_movie = threading.Event()

        def post(_path, payload):
            if payload["mediaType"] == "movie":
                movie_entered.set()
                release_movie.wait(2)
                return {"id": 100, "status": 1}
            tv_entered.set()
            return {"id": 200, "status": 1}

        service = media_requests.MediaRequestService(
            state_reader=lambda *_args, **_kwargs: {"status": "missing"},
            post_request=post,
            invalidate_state=lambda *_args: None,
        )
        movie = threading.Thread(
            target=lambda: service.request({"mediaType": "movie", "mediaId": 42})
        )
        tv = threading.Thread(
            target=lambda: service.request(
                {"mediaType": "tv", "mediaId": 42, "seasons": [1]}
            )
        )
        movie.start()
        self.assertTrue(movie_entered.wait(1))
        tv.start()
        self.assertTrue(tv_entered.wait(1))
        release_movie.set()
        movie.join(2)
        tv.join(2)
        self.assertEqual(len(service._locks._entries), 0)


if __name__ == "__main__":
    unittest.main()
