from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one block, found {count}")
    write(path, text.replace(old, new, 1))


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    text = read(path)
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    write(path, text[:start_index] + replacement + text[end_index:])


# Do not prompt at the CLI boundary before setup has inspected the existing
# environment. Foundation owns the fresh-local default and legacy migration
# checkpoint; CLI only supplies the secure prompt implementation.
replace_once(
    "installer/lumen_installer/cli.py",
    '''    selected_network_mode = getattr(args, "network_mode", None)\n    selected_public_host = getattr(args, "public_host", None)\n    if prompt is not None and selected_network_mode is None:\n        selected_network_mode = str(prompt("NETWORK_MODE", "local") or "local").strip().lower()\n        if selected_network_mode not in {"local", "lan", "preserve-lan"}:\n            raise InvalidInputError("network mode must be local or lan")\n    if prompt is not None and selected_network_mode in {"lan", "preserve-lan"} and selected_public_host is None:\n        selected_public_host = prompt("PUBLIC_HOST", None)\n''',
    '''    selected_network_mode = getattr(args, "network_mode", None)\n    selected_public_host = getattr(args, "public_host", None)\n''',
)

# Track the verified qBittorrent password reset as transient transaction state.
# It is never persisted, but dependent adapters can use it to decide whether an
# opaque stored credential needs a live verification/reconciliation pass.
replace_once(
    "installer/lumen_installer/configure.py",
    '''        "QBT_CURRENT_PASSWORD",\n    }\n)\n''',
    '''        "QBT_CURRENT_PASSWORD",\n        "_LUMEN_QBT_CREDENTIAL_REFRESH",\n    }\n)\n''',
)
replace_once(
    "installer/lumen_installer/configure.py",
    '''        result = _invoke_reconcile(\n            reconcile,\n            service,\n            environment=working_environment,\n            dry_run=dry_run,\n        )\n        update = _environment_update(result)\n''',
    '''        result = _invoke_reconcile(\n            reconcile,\n            service,\n            environment=working_environment,\n            dry_run=dry_run,\n        )\n        if service == "qbittorrent" and not dry_run:\n            result_actions = (\n                result.get("actions", ())\n                if isinstance(result, Mapping)\n                else getattr(result, "actions", ())\n            )\n            if "set-password" in result_actions and "verify-password" in result_actions:\n                working_environment["_LUMEN_QBT_CREDENTIAL_REFRESH"] = "true"\n        update = _environment_update(result)\n''',
)
replace_once(
    "installer/lumen_installer/configure.py",
    '''                qbit_password=password,\n                qbit_port=_service_port(current_environment, "qbittorrent"),\n                sonarr_api_key=_configured_value(current_environment, "SONARR_API_KEY"),\n''',
    '''                qbit_password=password,\n                qbit_port=_service_port(current_environment, "qbittorrent"),\n                verify_qbit_client=(\n                    _configured_value(current_environment, "_LUMEN_QBT_CREDENTIAL_REFRESH")\n                    == "true"\n                ),\n                sonarr_api_key=_configured_value(current_environment, "SONARR_API_KEY"),\n''',
)
replace_once(
    "installer/lumen_installer/configure.py",
    '''                api_key=api_key,\n                qbit_password=password or "",\n                qbit_port=_service_port(environment, "qbittorrent"),\n            )\n''',
    '''                api_key=api_key,\n                qbit_password=password or "",\n                qbit_port=_service_port(environment, "qbittorrent"),\n                verify_qbit_client=(\n                    _configured_value(environment, "_LUMEN_QBT_CREDENTIAL_REFRESH")\n                    == "true"\n                ),\n            )\n''',
)

# Servarr keeps normal masked-password noops unchanged. Only after this
# configure transaction has actually reset qBittorrent do we test the stored
# client. If that stored client fails, test the selected credential and update
# the managed client without requiring confirmation for the secret rotation.
replace_once(
    "installer/lumen_installer/services/servarr.py",
    '''        qbit_password: str,\n        qbit_port: int = 8081,\n    ) -> None:\n''',
    '''        qbit_password: str,\n        qbit_port: int = 8081,\n        verify_qbit_client: bool = False,\n    ) -> None:\n''',
)
replace_once(
    "installer/lumen_installer/services/servarr.py",
    '''        self._qbit_port = qbit_port\n''',
    '''        self._qbit_port = qbit_port\n        self._verify_qbit_client = bool(verify_qbit_client)\n''',
)
replace_between(
    "installer/lumen_installer/services/servarr.py",
    "    def _configure_from_state(\n",
    "    def configure(",
    '''    def _configure_from_state(\n        self,\n        roots: list[Mapping[str, Any]],\n        schema: Mapping[str, Any],\n        clients: list[Mapping[str, Any]],\n        *,\n        confirm: bool,\n    ) -> ServarrResult:\n        root_exists = any(root.get("path") == self.root_path for root in roots)\n        actions: list[str] = ["reuse-root-folder" if root_exists else "create-root-folder"]\n        existing = next((client for client in clients if self._is_qbit_client(client)), None)\n        if existing is None:\n            client_payload = self._client_payload(schema)\n            drift: tuple[ServiceDrift, ...] = ()\n        else:\n            existing_values = self._field_values(existing.get("fields"))\n            desired = {\n                "host": "qbittorrent",\n                "port": self._qbit_port,\n                "username": "admin",\n                self.category_field: self.service,\n            }\n            drift = tuple(\n                ServiceDrift(\n                    resource="download-client",\n                    field=name,\n                    reason="managed field differs",\n                )\n                for name, value in desired.items()\n                if existing_values.get(name, object()) != value\n            )\n            client_payload = self._updated_client_payload(existing, schema)\n            if drift and not confirm:\n                return ServarrResult(\n                    service=self.service,\n                    status="drift",\n                    actions=tuple(actions),\n                    drift=drift,\n                    error=ServarrConflictError(),\n                )\n\n        def test_client(payload: Mapping[str, Any]) -> bool:\n            try:\n                self._request(\n                    "POST",\n                    f"{self.api_prefix}/downloadclient/test",\n                    body=payload,\n                )\n            except (HttpStatusError, HttpTransportError, ServarrError):\n                return False\n            return True\n\n        def guided_test_failure() -> ServarrResult:\n            checkpoint = ServiceCheckpoint(\n                code="servarr-download-client-test",\n                reason="The qBittorrent download client test failed; review the service and retry.",\n                action="retry",\n                severity="error",\n            )\n            return ServarrResult(\n                service=self.service,\n                status="guided",\n                actions=tuple(actions),\n                checkpoints=(checkpoint,),\n                error=ServarrError(code="servarr-download-client-test"),\n            )\n\n        if existing is not None and not drift:\n            if self._verify_qbit_client:\n                # Test the stored resource first. Servarr can keep secrets\n                # masked/omitted in GET responses while still resolving them\n                # by resource id during the test call.\n                if not test_client(dict(existing)):\n                    if not test_client(client_payload):\n                        return guided_test_failure()\n                    client_id = existing.get("id")\n                    if client_id is None:\n                        raise ServarrSchemaError() from None\n                    if not root_exists:\n                        self._request(\n                            "POST",\n                            f"{self.api_prefix}/rootfolder",\n                            body={"path": self.root_path},\n                        )\n                    self._request(\n                        "PUT",\n                        f"{self.api_prefix}/downloadclient/{client_id}",\n                        body=client_payload,\n                    )\n                    actions[0] = "reuse-root-folder" if root_exists else "create-root-folder"\n                    actions.append("update-download-client")\n                    return ServarrResult(\n                        service=self.service, status="ok", actions=tuple(actions)\n                    )\n            if not root_exists:\n                self._request(\n                    "POST",\n                    f"{self.api_prefix}/rootfolder",\n                    body={"path": self.root_path},\n                )\n                actions[0] = "create-root-folder"\n            actions.append("reuse-download-client")\n            return ServarrResult(service=self.service, status="ok", actions=tuple(actions))\n\n        if not test_client(client_payload):\n            return guided_test_failure()\n\n        if not root_exists:\n            self._request(\n                "POST",\n                f"{self.api_prefix}/rootfolder",\n                body={"path": self.root_path},\n            )\n        actions[0] = "reuse-root-folder" if root_exists else "create-root-folder"\n        if existing is None:\n            self._request(\n                "POST", f"{self.api_prefix}/downloadclient", body=client_payload\n            )\n            actions.append("create-download-client")\n        else:\n            client_id = existing.get("id")\n            if client_id is None:\n                raise ServarrSchemaError() from None\n            self._request(\n                "PUT",\n                f"{self.api_prefix}/downloadclient/{client_id}",\n                body=client_payload,\n            )\n            actions.append("update-download-client")\n        return ServarrResult(service=self.service, status="ok", actions=tuple(actions))\n\n\n''',
)

# Prowlarr follows the same transaction-specific verification policy.
replace_once(
    "installer/lumen_installer/services/prowlarr.py",
    '''        qbit_port: int = DEFAULT_QBIT_PORT,\n        sonarr_api_key: str | None = None,\n''',
    '''        qbit_port: int = DEFAULT_QBIT_PORT,\n        verify_qbit_client: bool = False,\n        sonarr_api_key: str | None = None,\n''',
)
replace_once(
    "installer/lumen_installer/services/prowlarr.py",
    '''        self._qbit_port = qbit_port\n\n        key_sources = [application_api_keys, app_api_keys]\n''',
    '''        self._qbit_port = qbit_port\n        self._verify_qbit_client = bool(verify_qbit_client)\n\n        key_sources = [application_api_keys, app_api_keys]\n''',
)
replace_between(
    "installer/lumen_installer/services/prowlarr.py",
    "@dataclass(frozen=True)\nclass _ResourcePlan:",
    "\n\nclass ProwlarrAdapter:",
    '''@dataclass(frozen=True)\nclass _ResourcePlan:\n    resource: str\n    create_path: str\n    test_path: str\n    update_path: str | None\n    payload: dict[str, Any]\n    action: str\n    drift: tuple[ServiceDrift, ...] = ()\n    existing_id: Any = None\n    verify_existing: bool = False\n    verification_payload: dict[str, Any] | None = None\n\n    @property\n    def mutating(self) -> bool:\n        return self.action.startswith(("create-", "update-"))\n''',
)
replace_between(
    "installer/lumen_installer/services/prowlarr.py",
    "    def _qbit_plan(",
    "    def _application_plan(",
    '''    def _qbit_plan(\n        self,\n        schema: Mapping[str, Any],\n        existing: Mapping[str, Any] | None,\n    ) -> _ResourcePlan:\n        desired = {\n            ("host", "hostname", "server"): DEFAULT_QBIT_HOST,\n            ("port",): self._qbit_port,\n            ("username", "user"): DEFAULT_QBIT_USERNAME,\n            ("password", "pass"): self._qbit_password,\n        }\n        if existing is None:\n            payload = self._payload_from_schema(\n                schema,\n                desired,\n                default_name="qBittorrent",\n                defaults={\n                    "implementation": "QBittorrent",\n                    "configContract": "QBittorrentSettings",\n                    "enable": True,\n                },\n            )\n            return _ResourcePlan(\n                resource="download-client",\n                create_path=f"{self.api_prefix}/downloadclient",\n                test_path=f"{self.api_prefix}/downloadclient/test",\n                update_path=None,\n                payload=payload,\n                action="create-download-client",\n            )\n\n        fields = existing.get("fields")\n        if self._verify_qbit_client:\n            non_secret_desired = {\n                aliases: value\n                for aliases, value in desired.items()\n                if not {"password", "pass"}.intersection(\n                    {_normalized_name(alias) for alias in aliases}\n                )\n            }\n            drift = self._resource_drift(\n                "download-client", fields, non_secret_desired\n            )\n        else:\n            # GET responses commonly mask or omit the stored password. Keep the\n            # established no-op behavior unless this configure transaction has\n            # actually reset qBittorrent and requested a live credential check.\n            drift = self._resource_drift(\n                "download-client",\n                fields,\n                desired,\n                ignore_unknown=("password", "pass"),\n            )\n        payload = self._payload_from_existing(existing, schema, desired)\n        action = "reuse-download-client" if not drift else "update-download-client"\n        return _ResourcePlan(\n            resource="download-client",\n            create_path=f"{self.api_prefix}/downloadclient",\n            test_path=f"{self.api_prefix}/downloadclient/test",\n            update_path=(\n                f"{self.api_prefix}/downloadclient/{existing.get('id')}"\n                if existing.get("id") is not None\n                else None\n            ),\n            payload=payload,\n            action=action,\n            drift=drift,\n            existing_id=existing.get("id"),\n            verify_existing=self._verify_qbit_client and not drift,\n            verification_payload=dict(existing) if self._verify_qbit_client and not drift else None,\n        )\n\n\n''',
)
replace_between(
    "installer/lumen_installer/services/prowlarr.py",
    "    def _apply_plans(\n",
    "    def configure(\n",
    '''    def _apply_plans(\n        self,\n        plans: tuple[_ResourcePlan, ...],\n        *,\n        confirm: bool,\n    ) -> ProwlarrResult:\n        drift = tuple(record for resource_plan in plans for record in resource_plan.drift)\n        actions = tuple(resource_plan.action for resource_plan in plans)\n        if drift and not confirm:\n            return ProwlarrResult(\n                service=SERVICE_NAME,\n                status="drift",\n                actions=actions,\n                drift=drift,\n                error=ProwlarrConflictError(),\n                api_key=self._api_key,\n            )\n\n        completed: list[str] = []\n        for resource_plan in plans:\n            if resource_plan.verify_existing:\n                try:\n                    self._request(\n                        "POST",\n                        resource_plan.test_path,\n                        body=resource_plan.verification_payload,\n                    )\n                except (HttpStatusError, HttpTransportError, ProwlarrError):\n                    try:\n                        self._request(\n                            "POST",\n                            resource_plan.test_path,\n                            body=resource_plan.payload,\n                        )\n                    except (HttpStatusError, HttpTransportError, ProwlarrError):\n                        return self._guided(\n                            code=f"prowlarr-{resource_plan.resource}-test",\n                            reason="The Prowlarr resource test failed; review the service and retry.",\n                            action="retry",\n                            error=ProwlarrTestError(\n                                code=f"prowlarr-{resource_plan.resource}-test"\n                            ),\n                            actions=tuple(completed),\n                        )\n                    if resource_plan.update_path is None:\n                        raise ProwlarrSchemaError() from None\n                    self._request(\n                        "PUT",\n                        resource_plan.update_path,\n                        body=resource_plan.payload,\n                    )\n                    completed.append("update-download-client")\n                else:\n                    completed.append("reuse-download-client")\n                continue\n            if not resource_plan.mutating:\n                completed.append(resource_plan.action)\n                continue\n            try:\n                self._apply_plan(resource_plan)\n            except ProwlarrTestError as error:\n                checkpoint_code = error.code\n                return self._guided(\n                    code=checkpoint_code,\n                    reason="The Prowlarr resource test failed; review the service and retry.",\n                    action="retry",\n                    error=ProwlarrTestError(code=checkpoint_code),\n                    actions=tuple(completed),\n                )\n            completed.append(resource_plan.action)\n        return ProwlarrResult(\n            service=SERVICE_NAME,\n            status="ok",\n            actions=tuple(completed),\n            api_key=self._api_key,\n        )\n\n\n''',
)

# Correct the regression fixtures to model the actual review scenario: the
# credential refresh path is active, the stored client test fails, the selected
# password test succeeds, and only then is the managed client updated.
text = read("installer/tests/test_pr59_regressions.py")
text = text.replace(
    '''        transport = _Transport()\n        adapter = SonarrAdapter(\n            "http://127.0.0.1:8989",\n            transport,\n            api_key="sonarr-key",\n            qbit_password="new-password",\n        )\n''',
    '''        class CredentialTransport(_Transport):\n            def __init__(self):\n                super().__init__()\n                self.tests = 0\n\n            def request(self, method, url, **kwargs):\n                self.calls.append((method, url, kwargs))\n                if method == "POST" and url.endswith("/downloadclient/test"):\n                    self.tests += 1\n                    if self.tests == 1:\n                        return {"status": 400, "body": {}}\n                return {"status": 200, "body": {}}\n\n        transport = CredentialTransport()\n        adapter = SonarrAdapter(\n            "http://127.0.0.1:8989",\n            transport,\n            api_key="sonarr-key",\n            qbit_password="new-password",\n            verify_qbit_client=True,\n        )\n''',
    1,
)
text = text.replace(
    '''        adapter = ProwlarrAdapter(\n            "http://127.0.0.1:9696",\n            _Transport(),\n            api_key="prowlarr-key",\n            qbit_password="new-password",\n        )\n''',
    '''        class CredentialTransport(_Transport):\n            def __init__(self):\n                super().__init__()\n                self.tests = 0\n\n            def request(self, method, url, **kwargs):\n                self.calls.append((method, url, kwargs))\n                if method == "POST" and url.endswith("/downloadclient/test"):\n                    self.tests += 1\n                    if self.tests == 1:\n                        return {"status": 400, "body": {}}\n                return {"status": 200, "body": {}}\n\n        transport = CredentialTransport()\n        adapter = ProwlarrAdapter(\n            "http://127.0.0.1:9696",\n            transport,\n            api_key="prowlarr-key",\n            qbit_password="new-password",\n            verify_qbit_client=True,\n        )\n''',
    1,
)
text = text.replace(
    '''        plan = adapter._qbit_plan({"fields": fields}, {"id": 9, "fields": fields})\n        self.assertEqual(plan.action, "update-download-client")\n''',
    '''        plan = adapter._qbit_plan({"fields": fields}, {"id": 9, "fields": fields})\n        result = adapter._apply_plans((plan,), confirm=False)\n        self.assertIn("update-download-client", result.actions)\n        self.assertEqual(\n            [call[0] for call in transport.calls], ["POST", "POST", "PUT"]\n        )\n''',
    1,
)
write("installer/tests/test_pr59_regressions.py", text)

text = read("installer/tests/test_pr59_prowlarr_credential.py")
text = text.replace(
    '''class _Transport:\n    def request(self, method, url, **kwargs):\n        return {"status": 200, "body": {}}\n''',
    '''class _Transport:\n    def __init__(self):\n        self.calls = []\n        self.tests = 0\n\n    def request(self, method, url, **kwargs):\n        self.calls.append((method, url, kwargs))\n        if method == "POST" and url.endswith("/downloadclient/test"):\n            self.tests += 1\n            if self.tests == 1:\n                return {"status": 400, "body": {}}\n        return {"status": 200, "body": {}}\n''',
)
text = text.replace(
    '''        adapter = ProwlarrAdapter(\n            "http://127.0.0.1:9696",\n            _Transport(),\n            api_key="prowlarr-key",\n            qbit_password="new-password",\n        )\n''',
    '''        transport = _Transport()\n        adapter = ProwlarrAdapter(\n            "http://127.0.0.1:9696",\n            transport,\n            api_key="prowlarr-key",\n            qbit_password="new-password",\n            verify_qbit_client=True,\n        )\n''',
)
text = text.replace(
    '''        plan = adapter._qbit_plan({"fields": fields}, {"id": 9, "fields": fields})\n\n        self.assertEqual(plan.action, "update-download-client")\n''',
    '''        plan = adapter._qbit_plan({"fields": fields}, {"id": 9, "fields": fields})\n        result = adapter._apply_plans((plan,), confirm=False)\n\n        self.assertIn("update-download-client", result.actions)\n        self.assertEqual([call[0] for call in transport.calls], ["POST", "POST", "PUT"])\n''',
)
write("installer/tests/test_pr59_prowlarr_credential.py", text)

# The rollback dry-run now validates an existing durable record; creating that
# record is setup for the test, not a dry-run side effect.
replace_between(
    "installer/tests/test_update.py",
    "    def test_rollback_dry_run_is_read_only_even_without_confirmation(self):\n",
    "    def test_rollback_rejects_every_symlinked_state_boundary_without_callbacks(self):\n",
    '''    def test_rollback_dry_run_is_read_only_even_without_confirmation(self):\n        with tempfile.TemporaryDirectory() as temp_dir:\n            root = Path(temp_dir)\n            manifest, _ = self._manifest(root)\n            updated = self._update(root, manifest)\n            calls = []\n            result = run_rollback(\n                root,\n                updated["run_id"],\n                False,\n                lambda: calls.append("stop"),\n                lambda: calls.append("start"),\n                dry_run=True,\n            )\n            self.assertEqual(\n                {\n                    "action": "rollback",\n                    "dry_run": True,\n                    "run_id": updated["run_id"],\n                },\n                result,\n            )\n            self.assertEqual([], calls)\n            self.assertFalse(\n                (root / ".state" / "installer" / "failed-runs").exists()\n            )\n\n''',
)

print("PR 59 follow-up fixes applied")
