from __future__ import annotations

import hashlib
import unittest
from typing import Any

from filamenthub_edge.errors import ProviderUnavailable
from filamenthub_edge.providers.moonraker import BYPASS_PROVIDER_INDEX, MoonrakerProvider


class FakeHttp:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response

    def request(self, method: str, path: str, **kwargs):  # noqa: ANN003, ANN201
        if path == "/server/config":
            return 200, {"result": {"config": {}}}, {}
        return 200, self.response, {}


class MoonrakerProviderTest(unittest.TestCase):
    def test_direct_feed_does_not_duplicate_native_or_unknown_spoolman_usage(self) -> None:
        for config, allowed in (({}, True), ({"spoolman": {}}, False), (None, False)):

            class ConfigHttp(FakeHttp):
                def request(self, method, path, config=config, **kwargs):
                    if path == "/server/config":
                        return 200, {"result": {"config": config}}, {}
                    return super().request(method, path, **kwargs)

            with self.subTest(config=config):
                provider = MoonrakerProvider(
                    "http://printer.test",
                    api_key=None,
                    material_provider="legacy",
                    timeout=2,
                    http_client=ConfigHttp(
                        {
                            "result": {
                                "status": {
                                    "print_stats": {
                                        "state": "printing",
                                        "filament_used": 100,
                                    }
                                }
                            }
                        }
                    ),
                )
                snapshot = provider.observe()
                self.assertEqual(snapshot.usage is not None, allowed)
                self.assertEqual("consumption" in snapshot.capabilities, allowed)

    def test_happy_hare_snapshot_reports_complete_topology_and_active_bypass(self) -> None:
        response = {
            "result": {
                "status": {
                    "print_stats": {
                        "state": "printing",
                        "filename": "part.gcode",
                        "filament_used": 123.5,
                        "total_duration": 400.0,
                        "print_duration": 360.0,
                    },
                    "display_status": {"progress": 0.42},
                    "extruder": {"temperature": 218.5, "target": 220},
                    "heater_bed": {"temperature": 59.5, "target": 60},
                    "mmu": {
                        "num_gates": 2,
                        "spoolman_support": "off",
                        "gate_status": [2, 0],
                        "gate_material": ["PLA", ""],
                        "gate_color": ["ff6a13", "invalid"],
                        "gate_spool_id": [101, -1],
                        "gate_spool_rfid": ["04:a1-b2:c3", ""],
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
        self.assertEqual(
            snapshot.capabilities,
            ["read", "presence", "spool_identity", "consumption", "tag_read"],
        )
        self.assertEqual(snapshot.usage["filament_used_mm"], 123.5)
        self.assertEqual(snapshot.usage["print_duration_s"], 360.0)
        self.assertEqual(snapshot.slots[0]["material"], "PLA")
        self.assertEqual(snapshot.slots[0]["color_hex"], "FF6A13")
        self.assertEqual(snapshot.slots[0]["tag_uid"], "04A1B2C3")
        self.assertEqual(snapshot.slots[0]["tag_technology"], "unknown")
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

    def test_invalid_happy_hare_tag_is_ignored_without_hiding_the_gate(self) -> None:
        response = {
            "result": {
                "status": {
                    "print_stats": {"state": "standby"},
                    "mmu": {
                        "num_gates": 1,
                        "gate_status": [1],
                        "gate_spool_rfid": ["not-a-tag"],
                        "spoolman_support": "off",
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

        self.assertEqual(len(snapshot.slots), 1)
        self.assertTrue(snapshot.slots[0]["present"])
        self.assertNotIn("tag_uid", snapshot.slots[0])
        # Array presence advertises reader support even when one individual
        # value is malformed and must not be trusted as identity.
        self.assertIn("tag_read", snapshot.capabilities)

    def test_native_spoolman_owns_usage_and_tool_mapping_is_not_a_gate(self) -> None:
        class NativeHttp:
            def request(self, method, path, **kwargs):
                if path == "/server/config":
                    return (
                        200,
                        {
                            "result": {
                                "config": {
                                    "spoolman": {
                                        "server": "https://filamenthub.ru/api/v1/spool_compat/test-device-key",
                                    }
                                }
                            }
                        },
                        {},
                    )
                return (
                    200,
                    {
                        "result": {
                            "status": {
                                "mmu": {
                                    "num_gates": 2,
                                    "gate_status": [1, 1],
                                    "gate_spool_id": [42, -1],
                                    "gate": 1,
                                    "tool": 0,
                                    "filament_pos": 10,
                                    "spoolman_support": "pull",
                                },
                                "print_stats": {"state": "printing", "filament_used": 100},
                            }
                        }
                    },
                    {},
                )

        provider = MoonrakerProvider(
            "http://printer:7125",
            api_key=None,
            material_provider="happy_hare",
            timeout=2,
            http_client=NativeHttp(),
        )
        snapshot = provider.observe()
        self.assertIsNone(snapshot.usage)
        self.assertNotIn("consumption", snapshot.capabilities)
        self.assertEqual(
            snapshot.inventory_key_digest, hashlib.sha256(b"test-device-key").hexdigest()
        )
        self.assertFalse(snapshot.slots[0]["active_feed"])
        self.assertTrue(snapshot.slots[1]["active_feed"])
        self.assertEqual(snapshot.slots[0]["spool_id"], 42)
        self.assertIsNone(snapshot.slots[1]["spool_id"])
        self.assertTrue(snapshot.slots[1]["present"])
        provider.filamenthub_url = "https://another-site.example"
        snapshot = provider.observe()
        self.assertIsNone(snapshot.inventory_key_digest)
        self.assertIsNone(snapshot.usage)


if __name__ == "__main__":
    unittest.main()
