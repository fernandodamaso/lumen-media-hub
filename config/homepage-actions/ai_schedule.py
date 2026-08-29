#!/usr/bin/env python3
"""Container-local daily scheduler for AI Picks top-ups."""

import threading
from datetime import datetime


class AiPicksSchedule:
    def __init__(self, *, load, queue, enabled, target, hour, count_effective=None):
        self.load = load
        self.queue = queue
        self.enabled = enabled
        self.target = target
        self.hour = hour
        self.count_effective = count_effective or self._count_active
        self._last_date = None

    @staticmethod
    def _count_active(doc):
        return sum(1 for item in doc.get("items", ()) if item.get("active"))

    def tick(self, now=None):
        now = now or datetime.now()
        if not self.enabled() or now.hour < self.hour or self._last_date == now.date():
            return False
        doc = self.load()
        active = self.count_effective(doc)
        missing = max(0, self.target - active)
        if missing == 0:
            self._last_date = now.date()
            return False
        self.queue("scheduled", missing)
        # Mark the day only after queueing succeeds so transient failures retry
        # on the next scheduler tick instead of suppressing the whole day.
        self._last_date = now.date()
        return True


class AiPicksScheduleRunner:
    def __init__(self, schedule, interval_seconds=30):
        self.schedule = schedule
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        if self.thread is not None and self.thread.is_alive():
            return False

        def run():
            while not self.stop_event.is_set():
                try:
                    self.schedule.tick()
                except Exception as error:
                    print(f"[ai-picks-schedule] tick failed code={type(error).__name__}", flush=True)
                self.stop_event.wait(self.interval_seconds)

        self.stop_event.clear()
        self.thread = threading.Thread(target=run, name="ai-picks-schedule", daemon=True)
        self.thread.start()
        return True

    def stop(self, timeout=2):
        self.stop_event.set()
        thread = self.thread
        self.thread = None
        if thread and thread.is_alive():
            thread.join(timeout)
