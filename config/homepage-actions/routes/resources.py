"""System resources route handlers."""
import os
import shutil
import threading
import time

import config
import config as settings
from http_support import send_json


def _read_cpu_times():
    try:
        with open("/proc/stat", "r", encoding="utf-8") as f:
            line = f.readline()
        parts = line.split()
        if parts[0] != "cpu":
            return None
        values = [int(x) for x in parts[1:]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
        return idle, total
    except Exception:
        return None


def _cpu_percent():
    cur = _read_cpu_times()
    if not cur:
        return None
    with config._cpu_prev_lock:
        prev = config._cpu_prev
        config._cpu_prev = cur
    if not prev:
        return 0.0
    idle_d = cur[0] - prev[0]
    total_d = cur[1] - prev[1]
    if total_d <= 0:
        return 0.0
    used = 1.0 - (idle_d / total_d)
    return round(max(0.0, min(1.0, used)) * 100.0, 1)


def _mem_stats():
    try:
        info = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                key, _, rest = line.partition(":")
                info[key] = int(rest.strip().split()[0]) * 1024
        total = info.get("MemTotal", 0)
        available = info.get("MemAvailable", info.get("MemFree", 0))
        used = max(0, total - available)
        pct = round((used / total) * 100.0, 1) if total else 0.0
        return {"total": total, "used": used, "available": available, "percent": pct}
    except Exception:
        return None


def _disk_stats():
    path = settings.DATA_PATH if os.path.exists(settings.DATA_PATH) else "/"
    try:
        usage = shutil.disk_usage(path)
        pct = round((usage.used / usage.total) * 100.0, 1) if usage.total else 0.0
        return {
            "path": path,
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": pct,
        }
    except Exception:
        return None


def _build_system_resources():
    return {
        "ok": True,
        "cpu": {"percent": _cpu_percent()},
        "memory": _mem_stats(),
        "disk": _disk_stats(),
        "note": "CPU/RAM reflect the container/Docker VM view, same as Homepage widgets.",
    }


def _get_system_resources_cached():
    now = time.monotonic()
    cached = settings._arr_cache.get("resources")
    if cached and now - settings._arr_cache.get("resources_ts", 0) < settings.RESOURCES_CACHE_TTL:
        return cached
    with settings._arr_cache_lock:
        data = _build_system_resources()
        settings._arr_cache["resources"] = data
        settings._arr_cache["resources_ts"] = time.monotonic()
        return data


def handle_system_resources(handler):
    try:
        send_json(handler, 200, _get_system_resources_cached())
    except Exception as e:
        send_json(handler, 502, {"ok": False, "error": str(e)})
