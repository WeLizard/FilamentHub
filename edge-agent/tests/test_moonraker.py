from __future__ import annotations

import unittest
from typing import Any

from filamenthub_edge.errors import ProviderUnavailable
from filamenthub_edge.providers.moonraker import BYPASS_PROVIDER_INDEX, MoonrakerProvider


class FakeHttp:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response

    def request(self, method: str, path: str, **kwargs):  # noqa: ANN003, ANN201
        return 200, self.response, {}


class MoonrakerProviderTest(unittest.TestCase):
    def test_happy_hare_snapshot_reports_complete_topology_and_active_bypass(self) -> None:
        response = {
            "result": {
                "status": {
                    "print_stats": {"state": "printing", "filename": "part.gcode"},
                    "display_status": {"progress": 0.42},
                    "extruder": {"temperature": 218.5, "target": 220},
                    "heater_bed": {"temperature": 59.5, "target": 60},
                    "mmu": {
                        "num_gates": 2,
                        "gate_status": [2, 0],
                        "gate_material": ["PLA", ""],
                        "gate_color": ["ff6a13", "invalid"],
                        "gate_spool_id": [101, -1],
                        "has_bypass": True,
                        "tool": -2,
                        "filament_pos": 8.0,
                    },
                }
            }
        }
        provider = MoonrakerProvider(
            "http://moonraker.local:7125",
            api_key=None,
            material_provider="happy_hare",
            timeout=2,
            http_client=FakeHttp(response),
        )

        snapshot = provider.observe()

        self.assertEqual(snapshot.printer["state"], "printing")
        self.assertEqual(snapshot.printer["progress_percent"], 42)
        self.assertTrue(snapshot.slot_topology_complete)
        self.assertEqual(snapshot.capabilities, ["read", "presence"])
        self.assertEqual(snapshot.slots[0]["material"], "PLA")
        self.assertEqual(snapshot.slots[0]["color_hex"], "FF6A13")
        self.assertTrue(snapshot.slots[0]["present"])
        self.assertFalse(snapshot.slots[1]["present"])
        bypass = snapshot.slots[-1]
        self.assertEqual(bypass["provider_index"], BYPASS_PROVIDER_INDEX)
        self.assertTrue(bypass["active_feed"])
        self.assertTrue(bypass["present"])

    def test_disagreeing_happy_hare_arrays_are_rejected(self) -> None:
        response = {
            "result": {
                "status": {
                    "print_stats": {"state": "standby"},
                    "mmu": {
                        "num_gates": 2,
                        "gate_status": [1],
                        "gate_material": ["PLA", "PETG"],
                    },
                }
            }
        }
        provider = MoonrakerProvider(
            "http://moonraker.local:7125",
            api_key=None,
            material_provider="happy_hare",
            timeout=2,
            http_client=FakeHttp(response),
        )

        with self.assertRaises(ProviderUnavailable):
            provider.observe()


if __name__ == "__main__":
    unittest.main()
