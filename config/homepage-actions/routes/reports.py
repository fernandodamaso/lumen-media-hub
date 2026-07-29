"""Cron log report route handlers."""
import json
import os
import urllib.parse
from datetime import datetime

import config as settings
from http_support import send_json


def _safe_tmp_log_path(filename):
    name = os.path.basename(str(filename or ""))
    if not name or name != filename:
        return None
    candidate = os.path.abspath(os.path.join(settings.TMP_DIR, name))
    if candidate != settings.TMP_DIR and not candidate.startswith(settings.TMP_DIR + os.sep):
        return None
    return candidate


def _tail_text_file(path, max_bytes=120_000, max_lines=200):
    if not os.path.isfile(path):
        return {"exists": False, "lines": [], "size": 0, "mtime": None}
    size = os.path.getsize(path)
    mtime = datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds")
    with open(path, "rb") as f:
        if size > max_bytes:
            f.seek(-max_bytes, os.SEEK_END)
            data = f.read()
            # Drop possibly partial first line after mid-file seek.
            data = data.split(b"\n", 1)[-1] if b"\n" in data else data
        else:
            data = f.read()
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return {"exists": True, "lines": lines, "size": size, "mtime": mtime}


def _short_title(value, limit=72):
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _watchdog_detail(row):
    summary = row.get("summary") or {}
    applied = int(summary.get("applied") or 0)
    skipped = int(summary.get("skipped") or 0)
    evaluated = int(summary.get("evaluated") or 0)
    fatal = row.get("fatal")
    if fatal:
        return str(fatal)
    if applied == 0 and skipped == 0 and evaluated == 0:
        return "Nothing to check"
    if applied == 0:
        return f"Checked {evaluated}, no repairs needed"
    entries = row.get("entries") or []
    highlights = []
    for item in entries:
        if item.get("status") not in ("applied", "repaired", "deleted", "blocklisted"):
            if not item.get("action") or item.get("action") == "none":
                continue
        title = _short_title(item.get("title") or item.get("hash") or "item")
        reason = item.get("reason") or item.get("action") or "repaired"
        highlights.append(f"{title} ({reason})")
        if len(highlights) >= 3:
            break
    if highlights:
        return f"Repaired {applied}: " + "; ".join(highlights)
    return f"Repaired {applied} of {evaluated}"


def _summarize_watchdog_lines(lines):
    """Parse NDJSON watchdog lines into compact run summaries."""
    runs = []
    for line in lines:
        line = line.strip().lstrip("\ufeff")
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            runs.append(
                {
                    "status": "unparsed",
                    "detail": "Could not parse log line",
                }
            )
            continue
        summary = row.get("summary") or {}
        applied = int(summary.get("applied") or 0)
        fatal = row.get("fatal")
        status = "fatal" if fatal else ("applied" if applied > 0 else "ok")
        runs.append(
            {
                "timestamp": row.get("timestamp"),
                "exitCode": row.get("exitCode"),
                "status": status,
                "applied": applied,
                "evaluated": summary.get("evaluated"),
                "skipped": summary.get("skipped"),
                "fatal": fatal,
                "detail": _watchdog_detail(row),
            }
        )
    return runs[-50:]


def _has_real_blockers(stdout):
    """Return True only if the Blockers: section has actual items (not '(none)')."""
    in_blockers = False
    for ln in stdout:
        stripped = ln.strip()
        if stripped.lower() == "blockers:":
            in_blockers = True
            continue
        if in_blockers:
            if not stripped or stripped.lower().startswith("manual steps"):
                break
            if stripped not in ("(none)", "- (none)"):
                return True
    return False


def _summarize_text_job_lines(lines):
    """Parse Hermes text job blocks into compact run summaries."""
    runs = []
    current = None

    def finish():
        nonlocal current
        if not current:
            return
        stdout = [ln.strip() for ln in current.pop("_stdout", []) if ln.strip()]
        rc = current.get("exitCode")
        dry = current.get("dryRun")
        detail = None
        status = "ok"
        if rc not in (None, 0):
            status = "fatal"
            detail = f"Failed (exit {rc})"
        elif _has_real_blockers(stdout):
            status = "warn"
        for ln in reversed(stdout):
            low = ln.lower()
            if low.startswith("summary:"):
                detail = ln
                break
            if "no stale" in low or "nothing to" in low:
                detail = ln
                break
            if low.startswith("homepage descriptions updated"):
                detail = "Homepage storage descriptions updated"
                break
            if "phase completed" in low:
                detail = ln
                break
            if ln.startswith("[DELETE]") or ln.startswith("[KEEP]"):
                detail = ln
                break
        if not detail and stdout:
            detail = stdout[-1]
        if not detail:
            detail = "Completed"
        if dry and status == "ok":
            detail = f"Dry-run - {detail}"
        current["status"] = status
        current["detail"] = detail
        current["highlights"] = stdout[-6:]
        runs.append(current)
        current = None

    for raw in lines:
        line = raw.rstrip("\n")
        if line.startswith("===="):
            finish()
            current = {"_stdout": [], "dryRun": False}
            continue
        if current is None:
            continue
        if line.startswith("timestamp="):
            # timestamp=... job=... returncode=...
            parts = {}
            for token in line.split():
                if "=" in token:
                    key, value = token.split("=", 1)
                    parts[key] = value
            current["timestamp"] = parts.get("timestamp")
            if "returncode" in parts:
                try:
                    current["exitCode"] = int(parts["returncode"])
                except ValueError:
                    current["exitCode"] = None
            continue
        if line.startswith("extra="):
            try:
                extra = json.loads(line[len("extra=") :])
                current["dryRun"] = bool(extra.get("dry_run"))
            except json.JSONDecodeError:
                pass
            continue
        if line.startswith("--- stdout ---") or line.startswith("command="):
            continue
        if line.startswith("--- stderr ---"):
            continue
        current.setdefault("_stdout", []).append(line)

    finish()
    return runs[-50:]


def handle_cron_logs(handler):
    """Return tails of Hermes repair-job logs under DATA_PATH/tmp."""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
    wanted = (query.get("id") or [None])[0]
    logs = []
    for spec in settings.CRON_LOG_FILES:
        if wanted and wanted != spec["id"]:
            continue
        path = _safe_tmp_log_path(spec["file"])
        if not path:
            continue
        tail = _tail_text_file(path)
        entry = {
            "id": spec["id"],
            "title": spec["title"],
            "file": spec["file"],
            "format": spec["format"],
            "schedule": spec["schedule"],
            "description": spec.get("description") or "",
            "actions": list(spec.get("actions") or []),
            "exists": tail["exists"],
            "size": tail["size"],
            "mtime": tail["mtime"],
            "runs": [],
        }
        if not tail["exists"]:
            entry["summary"] = "No log file yet"
        elif not tail["lines"]:
            entry["summary"] = "Log is empty"
        elif spec["format"] == "ndjson":
            entry["runs"] = _summarize_watchdog_lines(tail["lines"])
        else:
            entry["runs"] = _summarize_text_job_lines(tail["lines"])

        if entry["runs"]:
            last = entry["runs"][-1]
            entry["summary"] = last.get("detail") or status_label_for_run(last)
            entry["lastStatus"] = last.get("status") or "ok"
        elif entry.get("summary") is None:
            entry["summary"] = "No recent runs"
            entry["lastStatus"] = "missing"
        logs.append(entry)

    send_json(
        handler,
        200,
        {
            "ok": True,
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
            "logs": logs,
            "note": "Healthy ticks stay silent in Hermes chat. This page shows readable run history.",
        },
    )


def status_label_for_run(run):
    status = (run or {}).get("status") or "ok"
    if status == "fatal":
        return "Failed"
    if status == "applied":
        return "Repaired something"
    if status == "warn":
        return "Completed with warnings"
    if status == "missing":
        return "No log yet"
    return "All clear"
