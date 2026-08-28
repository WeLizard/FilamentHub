from __future__ import annotations

import unittest

from filamenthub_edge.providers.base import ProviderSnapshot
from filamenthub_edge.state import EdgeState
from filamenthub_edge.usage import capture_usage_events


def snapshot(
    *,
    state: str,
    filament_used: float,
    print_duration: float,
    active_slot: int | None,
) -> ProviderSnapshot:
    slots = []
    if active_slot is not None:
        slots = [
            {"provider_index": index, "active_feed": index == active_slot}
            for index in range(2)
        ]
    return ProviderSnapshot(
        printer={"state": state},
        slots=slots,
        slot_topology_complete=bool(slots),
        capabilities=["read", "presence", "consumption"],
        usage={
            "state": state,
            "file_name": "part.gcode",
            "filament_used_mm": filament_used,
            "print_duration_s": print_duration,
            "total_duration_s": print_duration + 10,
        },
    )


class UsageTrackerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = EdgeState(
            desired_snapshot={
                "slots": [
                    {"index": 0, "spool": {"id": 99}},
                    {"index": 1, "spool": {"id": 100}},
                ]
            }
        )

    def test_periodic_and_terminal_events_use_one_stable_route(self) -> None:
        self.assertEqual(
            capture_usage_events(
                self.state,
                snapshot(state="printing", filament_used=0, print_duration=0, active_slot=0),
                observed_at="2026-01-01T00:00:00+00:00",
            ),
            [],
        )
        self.assertEqual(
            capture_usage_events(
                self.state,
                snapshot(state="printing", filament_used=100, print_duration=299, active_slot=0),
                observed_at="2026-01-01T00:04:59+00:00",
            ),
            [],
        )
        periodic = capture_usage_events(
            self.state,
            snapshot(state="printing", filament_used=120, print_duration=300, active_slot=0),
            observed_at="2026-01-01T00:05:00+00:00",
        )
        self.assertEqual(len(periodic), 1)
        self.assertEqual(periodic[0]["event_type"], "checkpoint")
        self.assertEqual(periodic[0]["items"][0]["spool_id"], 99)
        self.assertEqual(periodic[0]["items"][0]["used_length_mm"], 120)

        terminal = capture_usage_events(
            self.state,
            snapshot(state="complete", filament_used=150, print_duration=330, active_slot=0),
            observed_at="2026-01-01T00:05:30+00:00",
        )
        self.assertEqual(len(terminal), 1)
        self.assertEqual(terminal[0]["outcome"], "completed")
        self.assertEqual(terminal[0]["items"][0]["used_length_mm"], 30)
        self.assertEqual(
            capture_usage_events(
                self.state,
                snapshot(state="complete", filament_used=150, print_duration=330, active_slot=0),
                observed_at="2026-01-01T00:06:00+00:00",
            ),
            [],
        )

    def test_route_change_drops_only_the_ambiguous_polling_interval(self) -> None:
        capture_usage_events(
            self.state,
            snapshot(state="printing", filament_used=0, print_duration=0, active_slot=0),
            observed_at="2026-01-01T00:00:00+00:00",
        )
        capture_usage_events(
            self.state,
            snapshot(state="printing", filament_used=100, print_duration=100, active_slot=0),
            observed_at="2026-01-01T00:01:40+00:00",
        )
        changed = capture_usage_events(
            self.state,
            snapshot(state="printing", filament_used=120, print_duration=120, active_slot=1),
            observed_at="2026-01-01T00:02:00+00:00",
        )
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0]["reasons"], ["tool_change"])
        self.assertEqual(changed[0]["items"][0]["spool_id"], 99)
        self.assertEqual(changed[0]["items"][0]["used_length_mm"], 100)

        terminal = capture_usage_events(
            self.state,
            snapshot(state="cancelled", filament_used=150, print_duration=150, active_slot=1),
            observed_at="2026-01-01T00:02:30+00:00",
        )
        self.assertEqual(terminal[0]["outcome"], "cancelled")
        self.assertEqual(terminal[0]["items"][0]["spool_id"], 100)
        self.assertEqual(terminal[0]["items"][0]["used_length_mm"], 30)

    def test_single_desired_feed_supports_provider_without_slot_topology(self) -> None:
        state = EdgeState(desired_snapshot={"slots": [{"index": 7, "spool": {"id": 55}}]})
        capture_usage_events(
            state,
            snapshot(state="printing", filament_used=0, print_duration=0, active_slot=None),
            observed_at="2026-01-01T00:00:00+00:00",
        )
        event = capture_usage_events(
            state,
            snapshot(state="printing", filament_used=50, print_duration=300, active_slot=None),
            observed_at="2026-01-01T00:05:00+00:00",
        )[0]
        self.assertEqual(
            event["items"][0],
            {"slot_index": 7, "spool_id": 55, "used_length_mm": 50.0},
        )


if __name__ == "__main__":
    unittest.main()
