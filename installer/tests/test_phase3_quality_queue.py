import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.http import HttpResponse  # noqa: E402
from lumen_installer.queue import (  # noqa: E402
    CLEANUP,
    PAUSED,
    PRESERVE_REVIEW,
    REPLACEMENT,
    classify_queue,
)
from lumen_installer.services.servarr import (  # noqa: E402
    QUALITY_PROFILE_1080P_NAME,
    QUALITY_PROFILE_4K_NAME,
    SonarrAdapter,
    ServarrSchemaError,
)


def response(payload, status=200):
    return HttpResponse(
        status,
        {"Content-Type": "application/json"},
        json.dumps(payload).encode("utf-8"),
    )


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        return self.responses.pop(0)


def definition(identifier, name, weight, maximum, minimum=10, preferred=50):
    return {
        "id": identifier,
        "quality": {"id": identifier, "name": name, "resolution": int(name.split("-")[-1][:-1])},
        "title": name,
        "weight": weight,
        "minSize": minimum,
        "maxSize": maximum,
        "preferredSize": preferred,
    }


def quality_item(identifier, name, allowed=False):
    return {
        "id": identifier,
        "quality": {"id": identifier, "name": name},
        "items": [],
        "allowed": allowed,
    }


class NativeQualityConfigurationTests(unittest.TestCase):
    def test_quality_profile_accepts_native_unknown_quality_id_zero(self):
        items = [
            {
                "quality": {
                    "id": 0,
                    "name": "Unknown",
                    "source": "unknown",
                    "resolution": 0,
                },
                "items": [],
                "allowed": False,
            }
        ]

        transformed = SonarrAdapter._profile_items(
            items,
            allowed_ids=set(),
            weights={0: 0},
        )

        self.assertEqual(transformed[0]["quality"]["id"], 0)
        self.assertFalse(transformed[0]["allowed"])

    def test_quality_configuration_uses_native_payloads_and_preserves_profile_metadata(self):
        definitions = [
            definition(1, "WEBRip-1080p", 100, 0, preferred=75),
            definition(2, "WEBDL-2160p", 200, 0, preferred=250),
            definition(3, "Bluray-1080p", 150, 0),
            definition(4, "Remux-2160p", 250, 0),
        ]
        template = {
            "id": 7,
            "name": "Any",
            "upgradeAllowed": False,
            "cutoff": 1,
            "items": [
                quality_item(4, "Remux-2160p", True),
                quality_item(2, "WEBDL-2160p"),
                quality_item(3, "Bluray-1080p"),
                quality_item(1, "WEBRip-1080p"),
            ],
            "language": {"id": 1, "name": "English"},
            "minFormatScore": 12,
        }
        custom_schema = {
            "implementation": "ReleaseTitleSpecification",
            "implementationName": "Release Title",
            "fields": [{"name": "value", "value": ""}],
        }
        transport = Transport(
            [
                response({"version": "4.0.0"}),
                response(definitions),
                response([template]),
                response([{"items": []}]),
                response([]),
                response([custom_schema]),
                response({}),
                response({}),
                response({"id": 11}),
                response({}),
                response({}),
            ]
        )
        result = SonarrAdapter(
            "http://sonarr.test:8989",
            transport,
            api_key="api-key",
            qbit_password="qbit-password",
        ).configure_quality_profiles()

        self.assertEqual(result.status, "ok")
        definition_updates = [request for request in transport.requests if request[0] == "PUT" and "qualitydefinition" in request[1]]
        self.assertEqual(len(definition_updates), 2)
        updated_by_id = {request[2]["json_body"]["id"]: request[2]["json_body"] for request in definition_updates}
        self.assertEqual(updated_by_id[1]["maxSize"], 100)
        self.assertEqual(updated_by_id[2]["maxSize"], 200)
        self.assertEqual(updated_by_id[2]["minSize"], 10)
        self.assertEqual(updated_by_id[2]["preferredSize"], 200)

        custom_payload = next(request[2]["json_body"] for request in transport.requests if request[0] == "POST" and "customformat" in request[1])
        expression = custom_payload["specifications"][0]["fields"][0]["value"]
        self.assertIn("remux", expression)
        self.assertIn("upscale", expression)
        profile_payloads = [request[2]["json_body"] for request in transport.requests if request[0] == "POST" and "qualityprofile" in request[1]]
        self.assertEqual({payload["name"] for payload in profile_payloads}, {QUALITY_PROFILE_4K_NAME, QUALITY_PROFILE_1080P_NAME})
        four_k = next(payload for payload in profile_payloads if payload["name"] == QUALITY_PROFILE_4K_NAME)
        self.assertTrue(four_k["upgradeAllowed"])
        self.assertEqual(four_k["cutoff"], 2)
        self.assertEqual(four_k["language"], template["language"])
        self.assertEqual(four_k["minFormatScore"], 12)
        self.assertEqual(four_k["formatItems"][0]["score"], -1000000)
        self.assertEqual(
            [(item["quality"]["id"], item["allowed"]) for item in four_k["items"]],
            [(1, True), (3, False), (2, True), (4, False)],
        )

    def test_quality_preview_is_read_only(self):
        definitions = [
            definition(1, "WEBRip-1080p", 100, 0),
            definition(2, "WEBDL-2160p", 200, 0),
        ]
        template = {
            "id": 7,
            "name": "Any",
            "items": [quality_item(2, "WEBDL-2160p"), quality_item(1, "WEBRip-1080p")],
        }
        custom_schema = {
            "implementation": "ReleaseTitleSpecification",
            "fields": [{"name": "value", "value": ""}],
        }
        transport = Transport(
            [
                response({"version": "4.0.0"}),
                response(definitions),
                response([template]),
                response([{"items": []}]),
                response([]),
                response([custom_schema]),
            ]
        )
        result = SonarrAdapter(
            "http://sonarr.test:8989",
            transport,
            api_key="api-key",
            qbit_password="qbit-password",
        ).configure_quality_profiles(dry_run=True)
        self.assertEqual(result.status, "dry-run")
        self.assertTrue(result.actions)
        self.assertTrue(all(request[0] == "GET" for request in transport.requests))

    def test_unsupported_custom_format_schema_prevents_all_mutation(self):
        definitions = [
            definition(1, "WEBRip-1080p", 100, 0),
            definition(2, "WEBDL-2160p", 200, 0),
        ]
        template = {
            "id": 7,
            "name": "Any",
            "items": [quality_item(2, "WEBDL-2160p"), quality_item(1, "WEBRip-1080p")],
        }
        transport = Transport(
            [
                response({"version": "4.0.0"}),
                response(definitions),
                response([template]),
                response([{"items": []}]),
                response([]),
                response([{"implementation": "Unsupported", "fields": []}]),
            ]
        )
        with self.assertRaises(ServarrSchemaError):
            SonarrAdapter(
                "http://sonarr.test:8989",
                transport,
                api_key="api-key",
                qbit_password="qbit-password",
            ).configure_quality_profiles()
        self.assertTrue(all(request[0] == "GET" for request in transport.requests))

    def test_grouped_quality_profiles_use_allowed_group_cutoffs_and_template_metadata(self):
        definitions = [
            definition(1, "WEBRip-1080p", 100, 100),
            definition(2, "WEBDL-1080p", 120, 100),
            definition(3, "WEBRip-2160p", 200, 200),
            definition(4, "WEBDL-2160p", 220, 200),
        ]
        template = {
            "id": 7,
            "name": "Any",
            "items": [
                {
                    "id": 100,
                    "quality": None,
                    "items": [quality_item(1, "WEBRip-1080p"), quality_item(2, "WEBDL-1080p")],
                },
                {
                    "id": 200,
                    "quality": None,
                    "items": [quality_item(3, "WEBRip-2160p"), quality_item(4, "WEBDL-2160p")],
                },
            ],
            "language": {"id": 2, "name": "Spanish"},
            "formatItems": [{"format": 9, "name": "Existing format", "score": 10}],
        }
        custom_schema = {
            "implementation": "ReleaseTitleSpecification",
            "fields": [{"name": "value", "value": ""}],
        }
        transport = Transport(
            [
                response({"version": "4.0.0"}),
                response(definitions),
                response([template]),
                response([{"items": [{"name": "profile schema"}]}]),
                response([]),
                response([custom_schema]),
                response({"id": 11}),
                response({}),
                response({}),
            ]
        )
        adapter = SonarrAdapter(
            "http://sonarr.test:8989",
            transport,
            api_key="api-key",
            qbit_password="qbit-password",
        )
        adapter.configure_quality_profiles()
        profiles = [
            request[2]["json_body"]
            for request in transport.requests
            if request[0] == "POST" and "qualityprofile" in request[1]
        ]
        four_k = next(profile for profile in profiles if profile["name"] == QUALITY_PROFILE_4K_NAME)
        fallback = next(profile for profile in profiles if profile["name"] == QUALITY_PROFILE_1080P_NAME)
        self.assertEqual(four_k["cutoff"], 200)
        self.assertEqual(fallback["cutoff"], 100)
        self.assertTrue(all(item["allowed"] for item in four_k["items"]))
        self.assertEqual([item["allowed"] for item in fallback["items"]], [True, False])
        self.assertEqual(four_k["language"], template["language"])
        self.assertEqual(four_k["formatItems"][0]["format"], 9)

    def test_quality_configuration_is_idempotent_after_native_resources_exist(self):
        definitions = [
            definition(1, "WEBRip-1080p", 100, 100),
            definition(2, "WEBDL-2160p", 200, 200),
        ]
        template = {
            "id": 7,
            "name": "Any",
            "upgradeAllowed": False,
            "cutoff": 1,
            "items": [
                quality_item(2, "WEBDL-2160p"),
                quality_item(1, "WEBRip-1080p"),
            ],
        }
        custom_schema = {
            "implementation": "ReleaseTitleSpecification",
            "implementationName": "Release Title",
            "fields": [{"name": "value", "value": ""}],
            "presets": [{"name": "native-preset", "fields": []}],
        }
        first = Transport(
            [
                response({"version": "4.0.0"}),
                response(definitions),
                response([template]),
                response([{"items": []}]),
                response([]),
                response([custom_schema]),
                response({"id": 11}),
                response({}),
                response({}),
            ]
        )
        adapter = SonarrAdapter("http://sonarr.test:8989", first, api_key="key", qbit_password="password")
        adapter.configure_quality_profiles()
        created_profiles = [
            copy.deepcopy(request[2]["json_body"])
            for request in first.requests
            if request[0] == "POST" and "qualityprofile" in request[1]
        ]
        release_filter = next(
            copy.deepcopy(request[2]["json_body"])
            for request in first.requests
            if request[0] == "POST" and "customformat" in request[1]
        )
        release_filter["id"] = 11
        release_filter["specifications"][0].pop("presets", None)
        for identifier, profile in enumerate(created_profiles, start=20):
            profile["id"] = identifier
        second = Transport(
            [
                response({"version": "4.0.0"}),
                response(definitions),
                response([template, *created_profiles]),
                response([{"items": []}]),
                response([release_filter]),
                response([custom_schema]),
            ]
        )
        result = SonarrAdapter("http://sonarr.test:8989", second, api_key="key", qbit_password="password").configure_quality_profiles()
        self.assertEqual(result.status, "ok")
        self.assertEqual([request[0] for request in second.requests], ["GET"] * 6)


class ConservativeQueueClassificationTests(unittest.TestCase):
    def base(self, **changes):
        record = {
            "id": "torrent-1",
            "runtime_minutes": 45,
            "media_type": "episode",
            "imported": False,
            "verified": False,
            "watched": False,
            "partial_pack": False,
            "incomplete": False,
            "source_registered": True,
            "missing_episodes": ["S01E01", "S01E02"],
            "disallowed": False,
            "acceptable": False,
            "fits_capacity": True,
        }
        record.update(changes)
        return record

    def test_imported_verified_becomes_cleanup_only(self):
        result = classify_queue([self.base(imported=True, verified=True)])
        self.assertEqual(result.counts[CLEANUP], 1)
        self.assertEqual(result.candidates[0].replacement_episodes, ())
        self.assertEqual(result.report["mutations"], ())

    def test_disallowed_incomplete_replaces_only_explicitly_unwatched_missing_episodes(self):
        result = classify_queue([self.base(disallowed=True, incomplete=True)])
        self.assertEqual(result.candidates[0].action, REPLACEMENT)
        self.assertEqual(result.candidates[0].replacement_episodes, ("S01E01", "S01E02"))

        watched = classify_queue([self.base(disallowed=True, incomplete=True, watched=True)])
        self.assertEqual(watched.candidates[0].action, PRESERVE_REVIEW)

    def test_completed_unimported_and_movie_records_never_receive_replacements(self):
        completed = classify_queue([self.base(disallowed=True, incomplete=False)])
        self.assertEqual(completed.candidates[0].action, PRESERVE_REVIEW)
        movie = classify_queue(
            [self.base(media_type="movie", disallowed=True, incomplete=True)]
        )
        self.assertEqual(movie.candidates[0].action, PRESERVE_REVIEW)

    def test_invalid_identifiers_media_runtime_and_registered_state_are_preserved(self):
        result = classify_queue(
            [
                self.base(id=None),
                self.base(media_type="podcast"),
                self.base(runtime_minutes=float("inf")),
                self.base(imported=True, verified=True, source_registered=None),
            ]
        )
        self.assertEqual(result.counts[PRESERVE_REVIEW], 4)

    def test_watch_state_is_only_required_for_episode_replacement(self):
        cleanup = classify_queue(
            [self.base(imported=True, verified=True, watched=None)]
        )
        self.assertEqual(cleanup.candidates[0].action, CLEANUP)
        paused = classify_queue(
            [self.base(acceptable=True, fits_capacity=False, watched=None)]
        )
        self.assertEqual(paused.candidates[0].action, PAUSED)
        replacement = classify_queue(
            [self.base(disallowed=True, incomplete=True, watched=None)]
        )
        self.assertEqual(replacement.candidates[0].action, PRESERVE_REVIEW)

    def test_acceptable_item_without_capacity_is_paused(self):
        result = classify_queue([self.base(acceptable=True, fits_capacity=False)])
        self.assertEqual(result.candidates[0].action, PAUSED)

    def test_unknown_runtime_partial_pack_and_unregistered_staging_are_preserved(self):
        result = classify_queue(
            [
                self.base(runtime_minutes=None),
                self.base(partial_pack=True),
                self.base(imported=True, verified=False),
                self.base(imported=True, verified=True, source_registered=False),
                self.base(imported=True, verified=True, watched=None),
            ]
        )
        self.assertEqual(result.counts[PRESERVE_REVIEW], 4)
        self.assertEqual(result.counts[CLEANUP], 1)
        self.assertEqual(
            [candidate.action for candidate in result.candidates],
            [PRESERVE_REVIEW, PRESERVE_REVIEW, PRESERVE_REVIEW, PRESERVE_REVIEW, CLEANUP],
        )


class ConfigureQualityGateTests(unittest.TestCase):
    def test_quality_profiles_are_not_selected_by_the_existing_configure_path(self):
        from lumen_installer.configure import run_configure

        selected: list[bool] = []

        class Adapter:
            def configure(self, **kwargs):
                selected.append(kwargs["quality_profiles"])
                return {"status": "ok"}

        with tempfile.TemporaryDirectory() as temporary:
            result = run_configure(
                Path(temporary),
                environment={"QBT_PASSWORD": "password"},
                adapter_factory=lambda *args, **kwargs: Adapter(),
                env_commit=lambda: None,
                restart=lambda: None,
                direct_health=lambda: True,
                proxy_health=lambda: True,
            )

        self.assertEqual(result.status, "ok")
        self.assertEqual(selected, [False] * 6)


if __name__ == "__main__":
    unittest.main()
