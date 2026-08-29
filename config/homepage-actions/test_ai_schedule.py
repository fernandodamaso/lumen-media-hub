#!/usr/bin/env python3
import unittest
from datetime import datetime

from ai_schedule import AiPicksSchedule


class AiPicksScheduleTests(unittest.TestCase):
    def test_scheduled_top_up_queues_once_when_effective_active_is_below_target(self):
        queued = []
        schedule = AiPicksSchedule(
            load=lambda: {"items": [{"active": True}, {"active": False}]},
            count_effective=lambda _doc: 1,
            queue=lambda trigger, count: queued.append((trigger, count)),
            enabled=lambda: True,
            target=20,
            hour=10,
        )

        self.assertTrue(schedule.tick(datetime(2026, 8, 29, 10, 0)))
        self.assertFalse(schedule.tick(datetime(2026, 8, 29, 10, 30)))
        self.assertEqual(queued, [("scheduled", 19)])

    def test_schedule_skips_disabled_or_full_active_slate(self):
        queued = []
        disabled = AiPicksSchedule(
            load=lambda: {"items": []}, queue=lambda *args: queued.append(args),
            enabled=lambda: False, target=20, hour=10,
        )
        full = AiPicksSchedule(
            load=lambda: {"items": [{"active": True}] * 20},
            count_effective=lambda _doc: 20,
            queue=lambda *args: queued.append(args), enabled=lambda: True,
            target=20, hour=10,
        )

        self.assertFalse(disabled.tick(datetime(2026, 8, 29, 10, 0)))
        self.assertFalse(full.tick(datetime(2026, 8, 29, 10, 0)))
        self.assertEqual(queued, [])

    def test_schedule_uses_authoritative_effective_count(self):
        queued = []
        schedule = AiPicksSchedule(
            load=lambda: {"items": [{"active": True}] * 20},
            count_effective=lambda _doc: 14,
            queue=lambda trigger, count: queued.append((trigger, count)),
            enabled=lambda: True,
            target=20,
            hour=10,
        )

        self.assertTrue(schedule.tick(datetime(2026, 8, 29, 10, 0)))
        self.assertEqual(queued, [("scheduled", 6)])

    def test_schedule_retries_same_day_after_queue_failure(self):
        attempts = []

        def queue(trigger, count):
            attempts.append((trigger, count))
            if len(attempts) == 1:
                raise RuntimeError("store unavailable")

        schedule = AiPicksSchedule(
            load=lambda: {"items": []},
            count_effective=lambda _doc: 0,
            queue=queue,
            enabled=lambda: True,
            target=20,
            hour=10,
        )

        with self.assertRaises(RuntimeError):
            schedule.tick(datetime(2026, 8, 29, 10, 0))
        self.assertTrue(schedule.tick(datetime(2026, 8, 29, 10, 1)))
        self.assertEqual(attempts, [("scheduled", 20), ("scheduled", 20)])


if __name__ == "__main__":
    unittest.main()
