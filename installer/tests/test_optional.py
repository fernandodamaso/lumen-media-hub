import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


INSTALLER_ROOT = Path(__file__).resolve().parents[1]
if str(INSTALLER_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALLER_ROOT))

from lumen_installer.services.optional import (  # noqa: E402
    configure_optional_profiles,
    validate_ai_config,
)


class OptionalProfileTests(unittest.TestCase):
    def test_request_profile_does_not_enable_when_integration_apply_is_partial(self):
        result = configure_optional_profiles(
            {"JELLYSEERR_ENABLED": "false"},
            requested_profiles=("requests",),
            tests={"requests": lambda: True},
            health={"requests": lambda: True},
            configure={"requests": lambda: SimpleNamespace(status="partial")},
        )

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.environment_update, {})
        self.assertEqual(result.enabled_profiles, ())

    def test_request_flag_is_enabled_only_after_service_test_and_health(self):
        environment = {
            "JELLYSEERR_ENABLED": "false",
            "JELLYSEERR_URL": "http://jellyseerr:5055",
            "JELLYSEERR_API_KEY": "preserve-existing-key",
        }
        events = []

        result = configure_optional_profiles(
            environment,
            requested_profiles=("requests",),
            tests={"requests": lambda: events.append("test") or True},
            health={"requests": lambda: events.append("health") or True},
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(events, ["test", "health"])
        self.assertEqual(result.environment_update["JELLYSEERR_ENABLED"], "true")
        self.assertEqual(environment["JELLYSEERR_ENABLED"], "false")
        self.assertEqual(environment["JELLYSEERR_API_KEY"], "preserve-existing-key")

    def test_failed_optional_test_does_not_enable_or_mutate_the_profile(self):
        environment = {"JELLYSEERR_ENABLED": "false"}

        result = configure_optional_profiles(
            environment,
            requested_profiles=("requests",),
            tests={"requests": lambda: False},
            health={"requests": lambda: True},
        )

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.environment_update, {})
        self.assertEqual(result.enabled_profiles, ())
        self.assertEqual(environment["JELLYSEERR_ENABLED"], "false")

    def test_failed_optional_health_check_does_not_enable_or_mutate_the_profile(self):
        environment = {"BAZARR_ENABLED": "false"}

        result = configure_optional_profiles(
            environment,
            requested_profiles=("subtitles",),
            tests={"subtitles": lambda: True},
            health={"subtitles": lambda: False},
        )

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.environment_update, {})
        self.assertEqual(result.enabled_profiles, ())
        self.assertEqual(environment["BAZARR_ENABLED"], "false")

    def test_bazarr_links_and_flaresolverr_proxy_are_only_returned_after_checks(self):
        result = configure_optional_profiles(
            {},
            requested_profiles=("subtitles", "indexer-tools"),
            tests={"subtitles": lambda: True, "indexer-tools": lambda: True},
            health={"subtitles": lambda: True, "indexer-tools": lambda: True},
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            result.environment_update,
            {
                "BAZARR_ENABLED": "true",
                "BAZARR_SONARR_URL": "http://sonarr:8989",
                "BAZARR_RADARR_URL": "http://radarr:7878",
                "BAZARR_JELLYFIN_URL": "http://jellyfin:8096",
                "FLARESOLVERR_URL": "http://flaresolverr:8191",
            },
        )

    def test_unsupported_bazarr_language_is_guided_and_disabled(self):
        result = configure_optional_profiles(
            {},
            requested_profiles=("subtitles",),
            bazarr_language="xx-unsupported",
            tests={"subtitles": lambda: True},
            health={"subtitles": lambda: True},
        )

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.environment_update, {})
        self.assertEqual(result.enabled_profiles, ())

    def test_ai_provider_validation_is_secret_safe_and_blocks_enablement(self):
        environment = {
            "AI_PROVIDER": "unsupported-provider",
            "AI_MODEL": "model-name",
            "OPENAI_API_KEY": "private-openai-key",
        }

        validation = validate_ai_config(environment)
        self.assertEqual(validation.status, "guided")
        self.assertFalse(validation.valid)
        self.assertNotIn("private-openai-key", repr(validation))

        result = configure_optional_profiles(
            environment,
            requested_profiles=("ai",),
            tests={"ai": lambda: self.fail("invalid AI config must not be tested")},
            health={"ai": lambda: self.fail("invalid AI config must not be health-checked")},
        )
        self.assertEqual(result.status, "guided")
        self.assertEqual(result.environment_update, {})

    def test_maintenance_is_a_non_destructive_guided_handoff(self):
        environment = {"MAINTENANCE_ENABLED": "false"}

        result = configure_optional_profiles(
            environment,
            requested_profiles=("maintenance",),
            tests={"maintenance": lambda: self.fail("maintenance is not automated")},
            health={"maintenance": lambda: self.fail("maintenance is not automated")},
        )

        self.assertEqual(result.status, "guided")
        self.assertEqual(result.environment_update, {})
        self.assertEqual(result.enabled_profiles, ())
        self.assertEqual(environment, {"MAINTENANCE_ENABLED": "false"})

    def test_dry_run_is_unverified_and_does_not_run_checks(self):
        calls = []
        result = configure_optional_profiles(
            {"AI_PROVIDER": "openai", "AI_MODEL": "gpt", "OPENAI_API_KEY": "private"},
            requested_profiles=("ai",),
            tests={"ai": lambda: calls.append("test") or True},
            health={"ai": lambda: calls.append("health") or True},
            dry_run=True,
        )

        self.assertEqual(result.status, "dry-run")
        self.assertEqual(calls, [])
        self.assertEqual(result.environment_update, {})


if __name__ == "__main__":
    unittest.main()
