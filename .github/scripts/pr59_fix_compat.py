from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "installer/tests/test_cli.py"
text = path.read_text(encoding="utf-8")
old = '''        def configure_boundary(*, options, interactive, dry_run):\n            configured_options.append(options)\n            with tempfile.TemporaryDirectory() as temporary:\n                return configure_module.run_configure(\n                    Path(temporary),\n                    options=options,\n                    reconcile=lambda service: {"service": service, "status": "ok"},\n                    env_commit=lambda: None,\n                    restart=lambda: None,\n                    direct_health=lambda: True,\n                    proxy_health=lambda: True,\n                    interactive=interactive,\n                    dry_run=dry_run,\n                )\n'''
new = '''        def configure_boundary(*, options, interactive, dry_run, prompt=None):\n            configured_options.append(options)\n            with tempfile.TemporaryDirectory() as temporary:\n                return configure_module.run_configure(\n                    Path(temporary),\n                    options=options,\n                    reconcile=lambda service: {"service": service, "status": "ok"},\n                    env_commit=lambda: None,\n                    restart=lambda: None,\n                    direct_health=lambda: True,\n                    proxy_health=lambda: True,\n                    interactive=interactive,\n                    prompt=prompt,\n                    dry_run=dry_run,\n                )\n'''
if text.count(old) != 1:
    raise SystemExit("test_cli.py: expected configure boundary block once")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("PR 59 compatibility test updated")
