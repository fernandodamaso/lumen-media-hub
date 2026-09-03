"""Focused orchestration tests for the Linux core configure command."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from lumen_installer.services.base import ServiceDrift, ServiceResult


class ConfigureFlowTests(unittest.TestCase):
    def test_apply_orders_core_reconciliation_before_single_env_commit_and_health(self):
        try:
            configure = importlib.import_module("lumen_installer.configure")
        except ModuleNotFoundError:
            configure = None
        self.assertIsNotNone(configure, "configure orchestration module is required")

        events: list[str] = []

        def reconcile(service: str):
            events.append(service)
            return {"service": service, "status": "ok"}

        def commit_environment():
            events.append("env-commit")

        def restart_stack():
            events.append("restart")

        def direct_health():
            events.append("direct-health")
            return True

        def proxy_health():
            events.append("proxy-health")
            return True

        with tempfile.TemporaryDirectory() as temporary:
            result = configure.run_configure(
                Path(temporary),
                dry_run=False,
                reconcile=reconcile,
                env_commit=commit_environment,
                restart=restart_stack,
                direct_health=direct_health,
                proxy_health=proxy_health,
            )

        self.assertEqual(
            events,
            [
                "jellyfin",
                "qbittorrent",
                "sonarr",
                "radarr",
                "prowlarr",
                "torznab",
                "env-commit",
                "restart",
                "direct-health",
                "proxy-health",
            ],
        )
        self.assertEqual(result.status, "ok")

    def test_dry_run_is_read_only_and_does_not_mutate_caller_environment(self):
        configure = importlib.import_module("lumen_installer.configure")
        environment = {"QBT_PASSWORD": "original-secret"}
        events: list[tuple[str, bool]] = []

        def reconcile(service: str, *, environment, dry_run):
            events.append((service, dry_run))
            if service == "qbittorrent":
                return SimpleNamespace(
                    status="dry-run",
                    environment_update={"QBT_PASSWORD": "would-be-updated"},
                )
            return SimpleNamespace(status="dry-run")

        with tempfile.TemporaryDirectory() as temporary:
            journal = configure.ConfigureJournal(Path(temporary))
            result = configure.run_configure(
                Path(temporary),
                environment=environment,
                reconcile=reconcile,
                dry_run=True,
                env_commit=lambda: self.fail("dry-run must not commit .env"),
                restart=lambda: self.fail("dry-run must not restart services"),
                direct_health=lambda: True,
                proxy_health=lambda: True,
                journal=journal,
            )

            self.assertFalse((Path(temporary) / ".env").exists())
            self.assertFalse(journal.completed)

        self.assertEqual(result.status, "dry-run")
        self.assertEqual(environment, {"QBT_PASSWORD": "original-secret"})
        self.assertEqual(events, [(service, True) for service in configure.CORE_ORDER])

    def test_environment_commit_is_one_mode_six_hundred_atomic_write(self):
        configure = importlib.import_module("lumen_installer.configure")
        commit_environment = getattr(configure, "commit_environment", None)
        self.assertIsNotNone(commit_environment, "configure must expose its env commit boundary")

        with tempfile.TemporaryDirectory() as temporary:
            env_path = Path(temporary) / ".env"
            env_path.write_text("QBT_PASSWORD=old-secret\n", encoding="utf-8")
            document = configure.DotEnvDocument.parse(env_path)
            document.set("QBT_PASSWORD", "verified-secret")
            writes: list[tuple[Path, str, int]] = []

            def writer(path: Path, content: str, *, mode: int):
                writes.append((path, content, mode))
                path.write_text(content, encoding="utf-8")

            changed = commit_environment(env_path, document, writer=writer)

        self.assertTrue(changed)
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][0], env_path)
        self.assertEqual(writes[0][2], 0o600)
        self.assertNotIn("old-secret", writes[0][1])

    def test_environment_commit_repairs_special_bits_even_when_read_bits_are_six_hundred(self):
        configure = importlib.import_module("lumen_installer.configure")
        with tempfile.TemporaryDirectory() as temporary:
            env_path = Path(temporary) / ".env"
            env_path.write_text("SAFE=value\n", encoding="utf-8")
            os.chmod(env_path, 0o1600)
            writes: list[int] = []

            def writer(path: Path, content: str, *, mode: int):
                writes.append(mode)

            changed = configure.commit_environment(
                env_path,
                configure.DotEnvDocument.parse(env_path),
                writer=writer,
            )

        self.assertTrue(changed)
        self.assertEqual(writes, [0o600])

    def test_verified_qbittorrent_environment_update_reaches_dependent_adapters_before_commit(self):
        configure = importlib.import_module("lumen_installer.configure")
        events: list[str] = []
        working_environment = {"QBT_PASSWORD": "old-secret"}

        def reconcile(service: str, *, environment, dry_run):
            self.assertFalse(dry_run)
            events.append(service)
            if service == "qbittorrent":
                return SimpleNamespace(
                    status="ok",
                    environment_update={
                        "QBT_PASSWORD": "verified-secret",
                        "STACK_PASSWORD": "verified-secret",
                    },
                )
            if service in {"sonarr", "radarr", "prowlarr", "torznab"}:
                self.assertEqual(environment["QBT_PASSWORD"], "verified-secret")
            return SimpleNamespace(status="ok")

        def commit_environment():
            events.append("env-commit")
            self.assertEqual(working_environment["QBT_PASSWORD"], "verified-secret")

        with tempfile.TemporaryDirectory() as temporary:
            result = configure.run_configure(
                Path(temporary),
                environment=working_environment,
                reconcile=reconcile,
                env_commit=commit_environment,
                restart=lambda: None,
                direct_health=lambda: True,
                proxy_health=lambda: True,
            )

        self.assertEqual(result.status, "ok")
        self.assertEqual(working_environment["QBT_PASSWORD"], "verified-secret")
        self.assertEqual(events[-1], "env-commit")

    def test_adapter_factory_is_the_default_reconciliation_boundary(self):
        configure = importlib.import_module("lumen_installer.configure")
        constructed: list[str] = []

        class Adapter:
            def __init__(self, service: str):
                self.service = service

            def configure(self, *, dry_run: bool, confirm: bool):
                return {"service": self.service, "status": "dry-run" if dry_run else "ok"}

        def factory(service: str, *, environment, dry_run: bool, confirm: bool):
            constructed.append(service)
            return Adapter(service)

        with tempfile.TemporaryDirectory() as temporary:
            result = configure.run_configure(
                Path(temporary),
                environment={"QBT_PASSWORD": "verified-secret"},
                adapter_factory=factory,
                confirm=True,
                restart=lambda: None,
                direct_health=lambda: True,
                proxy_health=lambda: True,
            )

        self.assertEqual(result.status, "ok")
        self.assertEqual(constructed, list(configure.CORE_ORDER))

    def test_default_factory_is_available_for_real_core_adapter_wiring(self):
        configure = importlib.import_module("lumen_installer.configure")
        self.assertTrue(
            callable(getattr(configure, "build_adapter_factory", None)),
            "configure must wire the Task 9-12 adapters",
        )

    def test_factory_level_confirmation_is_preserved_for_jellyfin_reconciliation(self):
        configure = importlib.import_module("lumen_installer.configure")

        class Adapter:
            def __init__(self, *args, **kwargs):
                pass

        with mock.patch.object(configure, "JellyfinAdapter", Adapter):
            with tempfile.TemporaryDirectory() as temporary:
                environment = {
                    "JELLYFIN_ADMIN_NAME": "admin",
                    "JELLYFIN_ADMIN_PASSWORD": "secret",
                }
                factory = configure.build_adapter_factory(
                    Path(temporary),
                    environment=environment,
                    confirm=True,
                )
                reconciler = factory("jellyfin", environment=environment, confirm=False)

        self.assertTrue(reconciler.confirm)

    def test_real_qbittorrent_factory_forwards_adoption_credentials_and_bounded_logs(self):
        configure = importlib.import_module("lumen_installer.configure")
        current_password = "current-password-must-stay-private"
        logs = "bounded qBittorrent logs"
        captured = {}

        class Adapter:
            def __init__(self, *args, **kwargs):
                captured.update(kwargs)

        with mock.patch.object(configure, "QbittorrentAdapter", Adapter):
            with tempfile.TemporaryDirectory() as temporary:
                environment = {
                    "QBT_PASSWORD": "configured-password",
                    "QBT_CURRENT_PASSWORD": current_password,
                }
                factory = configure.build_adapter_factory(
                    Path(temporary),
                    environment=environment,
                    qbt_logs=logs,
                    qbt_log_max_bytes=128,
                    qbt_log_max_lines=4,
                )
                factory("qbittorrent", environment=environment)

        self.assertEqual(captured["current_password"], current_password)
        self.assertIs(captured["logs"], logs)
        self.assertEqual(captured["log_max_bytes"], 128)
        self.assertEqual(captured["log_max_lines"], 4)

    def test_lumen_qbittorrent_current_password_is_in_memory_only_at_configure_boundary(self):
        configure = importlib.import_module("lumen_installer.configure")
        current_password = "lumen-current-password-must-stay-private"
        captured = []

        class Adapter:
            def configure(self, **kwargs):
                return {"status": "ok"}

        def factory_builder(root, *, environment, **kwargs):
            captured.append(dict(environment))
            return lambda service, **factory_kwargs: Adapter()

        writes = []
        with mock.patch.dict(
            os.environ,
            {"LUMEN_QBT_CURRENT_PASSWORD": current_password},
            clear=False,
        ), mock.patch.object(configure, "build_adapter_factory", factory_builder):
            with tempfile.TemporaryDirectory() as temporary:
                result = configure.run_configure(
                    Path(temporary),
                    env_writer=lambda path, content, *, mode: writes.append(content),
                    restart=lambda: None,
                    direct_health=lambda: True,
                    proxy_health=lambda: True,
                )

        self.assertEqual(result.status, "ok")
        self.assertEqual(captured[0]["QBT_CURRENT_PASSWORD"], current_password)
        self.assertTrue(writes)
        self.assertNotIn(current_password, writes[0])
        self.assertNotIn("QBT_CURRENT_PASSWORD", writes[0])

    def test_configure_public_api_is_exported_from_installer_package(self):
        package = importlib.import_module("lumen_installer")
        self.assertIs(package.run_configure, importlib.import_module("lumen_installer.configure").run_configure)

    def test_default_restart_targets_homepage_actions_and_dashboard_only(self):
        configure = importlib.import_module("lumen_installer.configure")
        calls: list[tuple[str, ...]] = []

        class Runner:
            def run(self, argv, **kwargs):
                calls.append(tuple(argv))
                return None

        class Adapter:
            def configure(self, **kwargs):
                return {"status": "ok"}

        def factory(service: str, **kwargs):
            return Adapter()

        with tempfile.TemporaryDirectory() as temporary:
            result = configure.run_configure(
                Path(temporary),
                adapter_factory=factory,
                runner=Runner(),
                direct_health=lambda: True,
                proxy_health=lambda: True,
            )

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][-3:], ("restart", "homepage-actions", "dashboard"))
        self.assertNotIn("--remove-orphans", calls[0])

    def test_invalid_adapter_result_stops_before_environment_commit_with_exit_two(self):
        configure = importlib.import_module("lumen_installer.configure")
        commits: list[str] = []

        def reconcile(service: str):
            if service == "jellyfin":
                return {"service": service, "status": "unsupported"}
            return {"service": service, "status": "ok"}

        with tempfile.TemporaryDirectory() as temporary:
            result = configure.run_configure(
                Path(temporary),
                reconcile=reconcile,
                env_commit=lambda: commits.append("commit"),
                restart=lambda: None,
            )

        self.assertEqual(result.status, "invalid")
        self.assertEqual(result.exit_code, 2)
        self.assertEqual(commits, [])

    def test_noninteractive_drift_is_exit_three_and_guided_checkpoint_is_exit_four(self):
        configure = importlib.import_module("lumen_installer.configure")

        for status, expected_code, expected_status in (
            ("drift", 3, "drift"),
            ("guided", 4, "guided"),
        ):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                commits: list[str] = []

                def reconcile(service: str):
                    if service == "jellyfin":
                        return {
                            "service": service,
                            "status": status,
                            "password": "must-not-escape",
                            "api_key": "must-not-escape",
                        }
                    return {"service": service, "status": "ok"}

                result = configure.run_configure(
                    Path(temporary),
                    reconcile=reconcile,
                    interactive=False,
                    env_commit=lambda: commits.append("commit"),
                    restart=lambda: None,
                )

                self.assertEqual(result.status, expected_status)
                self.assertEqual(result.exit_code, expected_code)
                self.assertEqual(commits, [])
                self.assertNotIn("must-not-escape", repr(result.report))

    def test_noninteractive_guided_result_with_real_drift_records_is_exit_three(self):
        configure = importlib.import_module("lumen_installer.configure")

        def reconcile(service: str):
            if service == "jellyfin":
                return ServiceResult(
                    service=service,
                    status="guided",
                    drift=(
                        ServiceDrift(
                            resource="library",
                            field="path",
                            reason="managed path differs",
                        ),
                    ),
                )
            return ServiceResult(service=service, status="ok")

        with tempfile.TemporaryDirectory() as temporary:
            result = configure.run_configure(
                Path(temporary),
                reconcile=reconcile,
                interactive=False,
                env_commit=lambda: self.fail("drift must stop before env commit"),
                restart=lambda: self.fail("drift must stop before restart"),
            )

        self.assertEqual(result.status, "drift")
        self.assertEqual(result.exit_code, 3)
        self.assertEqual(
            result.report["services"]["jellyfin"]["drift"][0]["field"],
            "path",
        )

    def test_successful_rerun_uses_the_completed_journal_without_mutations(self):
        configure = importlib.import_module("lumen_installer.configure")
        events: list[str] = []

        def reconcile(service: str):
            events.append(service)
            return {"service": service, "status": "ok"}

        with tempfile.TemporaryDirectory() as temporary:
            first = configure.run_configure(
                Path(temporary),
                reconcile=reconcile,
                env_commit=lambda: events.append("env-commit"),
                restart=lambda: events.append("restart"),
                direct_health=lambda: events.append("direct-health") or True,
                proxy_health=lambda: events.append("proxy-health") or True,
            )
            events.clear()
            second = configure.run_configure(
                Path(temporary),
                reconcile=reconcile,
                env_commit=lambda: events.append("env-commit"),
                restart=lambda: events.append("restart"),
                direct_health=lambda: events.append("direct-health") or True,
                proxy_health=lambda: events.append("proxy-health") or True,
            )

        self.assertEqual(first.status, "ok")
        self.assertEqual(second.status, "ok")
        self.assertEqual(events, [])

    def test_default_health_gate_checks_direct_then_lumen_proxy(self):
        configure = importlib.import_module("lumen_installer.configure")
        requested: list[str] = []

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def opener(request, *, timeout):
            requested.append(request.full_url)
            return Response()

        class Adapter:
            def configure(self, **kwargs):
                return {"status": "ok"}

        with tempfile.TemporaryDirectory() as temporary:
            result = configure.run_configure(
                Path(temporary),
                adapter_factory=lambda service, **kwargs: Adapter(),
                restart=lambda: None,
                health_opener=opener,
            )

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            requested,
            [configure.DEFAULT_DIRECT_HEALTH_URL, configure.DEFAULT_PROXY_HEALTH_URL],
        )

    def test_direct_health_failure_is_partial_and_does_not_probe_proxy(self):
        configure = importlib.import_module("lumen_installer.configure")
        events: list[str] = []

        def reconcile(service: str):
            events.append(service)
            return {"status": "ok"}

        with tempfile.TemporaryDirectory() as temporary:
            result = configure.run_configure(
                Path(temporary),
                reconcile=reconcile,
                env_commit=lambda: events.append("env-commit"),
                restart=lambda: events.append("restart"),
                direct_health=lambda: events.append("direct-health") or False,
                proxy_health=lambda: self.fail("proxy health must follow direct health"),
                health_timeout=0,
            )

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.exit_code, 4)
        self.assertEqual(events[-3:], ["env-commit", "restart", "direct-health"])

    def test_default_repository_root_is_the_installer_checkout_not_caller_cwd(self):
        configure = importlib.import_module("lumen_installer.configure")
        roots: list[Path] = []

        class Journal:
            completed = configure.CONFIGURE_ORDER

            def is_complete(self, stage):
                return True

        def journal_factory(root):
            roots.append(root)
            return Journal()

        with tempfile.TemporaryDirectory() as temporary:
            original_cwd = os.getcwd()
            os.chdir(temporary)
            try:
                with mock.patch.object(configure, "ConfigureJournal", side_effect=journal_factory):
                    configure.run_configure()
            finally:
                os.chdir(original_cwd)

        self.assertEqual(roots, [Path(configure.__file__).resolve().parents[2]])

    def test_lumen_configure_environment_overrides_are_in_memory_and_redacted(self):
        configure = importlib.import_module("lumen_installer.configure")
        seen: list[str] = []

        def reconcile(service: str, *, environment, dry_run):
            if service == "jellyfin":
                seen.append(environment["JELLYFIN_ADMIN_PASSWORD"])
            return {"service": service, "status": "ok"}

        with mock.patch.dict(
            os.environ,
            {"LUMEN_JELLYFIN_ADMIN_PASSWORD": "secret-from-environment"},
            clear=False,
        ):
            with tempfile.TemporaryDirectory() as temporary:
                result = configure.run_configure(
                    Path(temporary),
                    reconcile=reconcile,
                    restart=lambda: None,
                    direct_health=lambda: True,
                    proxy_health=lambda: True,
                )

        self.assertEqual(result.status, "ok")
        self.assertEqual(seen, ["secret-from-environment"])
        self.assertNotIn("secret-from-environment", repr(result.report))

    def test_transient_jellyfin_admin_password_is_not_written_to_env(self):
        configure = importlib.import_module("lumen_installer.configure")
        writes: list[str] = []

        def writer(path: Path, content: str, *, mode: int):
            writes.append(content)
            path.write_text(content, encoding="utf-8")

        with mock.patch.dict(
            os.environ,
            {"LUMEN_JELLYFIN_ADMIN_PASSWORD": "transient-admin-secret"},
            clear=False,
        ):
            with tempfile.TemporaryDirectory() as temporary:
                result = configure.run_configure(
                    Path(temporary),
                    adapter_factory=lambda service, **kwargs: type(
                        "Adapter", (), {"configure": lambda self, **kwargs: {"status": "ok"}}
                    )(),
                    env_writer=writer,
                    restart=lambda: None,
                    direct_health=lambda: True,
                    proxy_health=lambda: True,
                )

        self.assertEqual(result.status, "ok")
        self.assertTrue(writes)
        self.assertNotIn("transient-admin-secret", writes[0])
        self.assertNotIn("JELLYFIN_ADMIN_PASSWORD", writes[0])

    def test_interrupted_run_resumes_at_first_incomplete_service(self):
        configure = importlib.import_module("lumen_installer.configure")
        journal_type = getattr(configure, "ConfigureJournal", None)
        self.assertIsNotNone(journal_type, "configure runs require a resumable journal")

        events: list[str] = []
        should_interrupt = True

        def reconcile(service: str):
            nonlocal should_interrupt
            events.append(service)
            if service == "sonarr" and should_interrupt:
                should_interrupt = False
                raise KeyboardInterrupt()
            return {"service": service, "status": "ok"}

        with tempfile.TemporaryDirectory() as temporary:
            journal = journal_type(Path(temporary))
            with self.assertRaises(KeyboardInterrupt):
                configure.run_configure(
                    Path(temporary),
                    reconcile=reconcile,
                    journal=journal,
                    restart=lambda: None,
                )
            self.assertEqual(journal.completed, ("jellyfin", "qbittorrent"))

            events.clear()
            result = configure.run_configure(
                Path(temporary),
                reconcile=reconcile,
                journal=journal,
                restart=lambda: None,
                direct_health=lambda: True,
                proxy_health=lambda: True,
            )

        self.assertEqual(
            events,
            ["sonarr", "radarr", "prowlarr", "torznab"],
        )
        self.assertEqual(result.status, "ok")

    def test_resume_replays_completed_service_with_uncommitted_environment_update(self):
        configure = importlib.import_module("lumen_installer.configure")
        environment = {"QBT_PASSWORD": "old-secret"}
        resumed_environment = {"QBT_PASSWORD": "old-secret"}
        events: list[str] = []
        should_interrupt = True

        def reconcile(service: str, *, environment, dry_run):
            nonlocal should_interrupt
            events.append(service)
            if service == "qbittorrent":
                return SimpleNamespace(
                    status="ok",
                    environment_update={
                        "QBT_PASSWORD": "verified-secret",
                        "STACK_PASSWORD": "verified-secret",
                    },
                )
            if service == "sonarr":
                self.assertEqual(environment["QBT_PASSWORD"], "verified-secret")
                if should_interrupt:
                    should_interrupt = False
                    raise KeyboardInterrupt()
            return SimpleNamespace(status="ok")

        with tempfile.TemporaryDirectory() as temporary:
            journal = configure.ConfigureJournal(Path(temporary))
            with self.assertRaises(KeyboardInterrupt):
                configure.run_configure(
                    Path(temporary),
                    environment=environment,
                    reconcile=reconcile,
                    journal=journal,
                    restart=lambda: None,
                    direct_health=lambda: True,
                    proxy_health=lambda: True,
                )
            self.assertEqual(journal.pending_environment, ("qbittorrent",))

            events.clear()
            result = configure.run_configure(
                Path(temporary),
                environment=resumed_environment,
                reconcile=reconcile,
                journal=journal,
                restart=lambda: None,
                direct_health=lambda: True,
                proxy_health=lambda: True,
            )

        self.assertEqual(result.status, "ok")
        self.assertEqual(events[:2], ["qbittorrent", "sonarr"])
        self.assertEqual(resumed_environment["QBT_PASSWORD"], "verified-secret")

    def test_resume_runs_torznab_after_a_completed_prowlarr_checkpoint(self):
        configure = importlib.import_module("lumen_installer.configure")
        environment = {
            "TORZNAB_URL": "http://indexer.test/api",
            "TORZNAB_API_KEY": "torznab-secret",
        }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = configure.ConfigureJournal(root)
            for stage in configure.CORE_ORDER[:5]:
                journal.complete(stage)
            factory = configure.build_adapter_factory(root, environment=environment)
            result = configure.run_configure(
                root,
                environment=environment,
                adapter_factory=factory,
                journal=journal,
                env_commit=lambda: None,
                restart=lambda: None,
                direct_health=lambda: True,
                proxy_health=lambda: True,
            )

        self.assertEqual(result.status, "ok")

    def test_resume_keeps_completed_direct_health_checkpoint_in_order_once(self):
        configure = importlib.import_module("lumen_installer.configure")

        with tempfile.TemporaryDirectory() as temporary:
            journal = configure.ConfigureJournal(Path(temporary))
            for stage in configure.CONFIGURE_ORDER[:-1]:
                journal.complete(stage)

            result = configure.run_configure(
                Path(temporary),
                journal=journal,
                adapter_factory=lambda service, **kwargs: SimpleNamespace(
                    configure=lambda **configure_kwargs: {"status": "ok"}
                ),
                restart=lambda: None,
                direct_health=lambda: True,
                proxy_health=lambda: True,
            )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.stages_completed, configure.CONFIGURE_ORDER)
        self.assertEqual(result.stages_completed.count("direct-health"), 1)


if __name__ == "__main__":
    unittest.main()
