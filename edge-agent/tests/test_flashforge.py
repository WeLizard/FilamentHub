"""Flashforge LAN reader (Adventurer 5M series, AD5X, Creator 5).

The fixture is synthetic: it follows the field list published by the community
API reference for Creator 5 firmware 1.7.8-1.9.8 and is not a device capture.
"""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from filamenthub_edge.config import NodeConfig
from filamenthub_edge.errors import ConfigurationError, HttpRequestError, ProviderUnavailable
from filamenthub_edge.node import build_connection
from filamenthub_edge.providers.flashforge import FlashforgeProvider

FIXTURE = Path(__file__).parent / "fixtures" / "flashforge" / "detail_printing.json"


class FlashforgeHttp:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response if response is not None else json.loads(FIXTURE.read_text())
        self.error = error
        self.calls: list[tuple[str, str, Any]] = []

    def request(self, method: str, path: str, **kwargs: Any):  # noqa: ANN201
        self.calls.append((method, path, kwargs.get("payload")))
        if self.error is not None:
            raise self.error
        return 200, self.response, {}


def provider(http: FlashforgeHttp) -> FlashforgeProvider:
    return FlashforgeProvider(
        "http://192.168.1.40:8898",
        serial_number="SNMQRB9400123",
        check_code="a1b2c3d4",
        timeout=2,
        http_client=http,  # type: ignore[arg-type]
    )


class FlashforgeProviderTest(unittest.TestCase):
    def test_reading_matches_the_fixture_shared_with_the_orca_plugin(self) -> None:
        # The OrcaSlicer plugin reads the same API with its own code; both are
        # held to this one expected result so the two readers cannot drift apart.
        expected = json.loads(FIXTURE.with_name("detail_printing.expected.json").read_text())
        snapshot = provider(FlashforgeHttp()).observe()

        self.assertEqual(
            {
                "printer": snapshot.printer,
                "slots": snapshot.slots,
                "slot_topology_complete": snapshot.slot_topology_complete,
            },
            expected,
        )

    def test_material_station_is_a_complete_four_slot_topology(self) -> None:
        http = FlashforgeHttp()
        snapshot = provider(http).observe()

        self.assertEqual(
            http.calls,
            [("POST", "/detail", {"serialNumber": "SNMQRB9400123", "checkCode": "a1b2c3d4"})],
        )
        self.assertTrue(snapshot.slot_topology_complete)
        slots = {slot["provider_index"]: slot for slot in snapshot.slots}
        self.assertEqual(sorted(slots), [0, 1, 2, 3])
        self.assertEqual(
            (slots[0]["present"], slots[0]["material"], slots[0]["color_hex"]),
            (True, "PLA", "4CAAF8"),
        )
        self.assertEqual(slots[1]["color_hex"], "FFFFFF")
        # An empty slot keeps the station's last material label; it is not a loaded spool.
        self.assertEqual(slots[2]["present"], False)
        self.assertNotIn("material", slots[2])
        self.assertNotIn("color_hex", slots[2])
        # Unknown material and an invalid colour stay unknown instead of guessed.
        self.assertTrue(slots[3]["present"])
        self.assertNotIn("material", slots[3])
        self.assertNotIn("color_hex", slots[3])
        self.assertTrue(all(slot["spool_identity_known"] is False for slot in slots.values()))
        # currentSlot is not a confirmed active-tool signal.
        self.assertTrue(all("active_feed" not in slot for slot in slots.values()))

    def test_feed_shape_follows_the_reported_model(self) -> None:
        base = json.loads(FIXTURE.read_text())

        # Adventurer 5M Pro: integer PID, no station, one spool with the set material.
        five_m = copy.deepcopy(base)
        five_m["detail"].update(pid=36, rightFilamentType="PETG")
        del five_m["detail"]["matlStationInfo"]
        snapshot = provider(FlashforgeHttp(five_m)).observe()
        self.assertTrue(snapshot.slot_topology_complete)
        self.assertEqual(
            [
                (s["provider_index"], s["kind"], s["present"], s.get("material"))
                for s in snapshot.slots
            ],
            [(0, "external", None, "PETG")],
        )

        # AD5X: hex PID "0026" and the same four-slot station as the Creator 5.
        ad5x = copy.deepcopy(base)
        ad5x["detail"].update(pid="0026", hasMatlStation=1)
        snapshot = provider(FlashforgeHttp(ad5x)).observe()
        self.assertTrue(snapshot.slot_topology_complete)
        self.assertEqual([slot["provider_index"] for slot in snapshot.slots], [0, 1, 2, 3])

        # Some firmware capitalizes station keys and sends 0/1 flags; read them like Orca does.
        variant = copy.deepcopy(ad5x)
        station = variant["detail"].pop("matlStationInfo")
        station["SlotInfos"] = station.pop("slotInfos")
        for entry in station["SlotInfos"]:
            entry["hasFilament"] = int(entry["hasFilament"])
        variant["detail"]["MatlStationInfo"] = station
        snapshot = provider(FlashforgeHttp(variant)).observe()
        self.assertTrue(snapshot.slot_topology_complete)
        self.assertEqual([slot["present"] for slot in snapshot.slots], [True, True, False, True])

        # A model outside the known families is not guessed into a topology.
        unknown = copy.deepcopy(base)
        unknown["detail"]["pid"] = "63"
        snapshot = provider(FlashforgeHttp(unknown)).observe()
        self.assertEqual((snapshot.slots, snapshot.slot_topology_complete), ([], False))

    def test_no_consumption_is_claimed_without_per_tool_usage(self) -> None:
        snapshot = provider(FlashforgeHttp()).observe()

        self.assertIsNone(snapshot.usage)
        self.assertEqual(snapshot.capabilities, ["read", "presence"])
        self.assertEqual(snapshot.device_identity, ("flashforge_serial", "SNMQRB9400123"))

    def test_printer_status_uses_only_unambiguous_readings(self) -> None:
        snapshot = provider(FlashforgeHttp()).observe()
        self.assertEqual(
            snapshot.printer,
            {
                "state": "printing",
                "job_name": "bracket.3mf",
                "progress_percent": 42,
                "remaining_seconds": 1820,
                "current_layer": 42,
                "total_layers": 120,
                "nozzle_temperature": 219.6,
                "nozzle_target_temperature": 220.0,
                "bed_temperature": 59.8,
                "bed_target_temperature": 60.0,
                "chamber_temperature": 38.2,
            },
        )

        response = json.loads(FIXTURE.read_text())
        detail = response["detail"]
        detail.update(
            status="ready",
            nozzleTargetTemps=[200, 200, 0, 0],
            chamberTemp=-108,
        )
        idle = provider(FlashforgeHttp(response)).observe().printer
        self.assertEqual(idle["state"], "idle")
        for absent in ("job_name", "nozzle_temperature", "chamber_temperature"):
            self.assertNotIn(absent, idle)

    def test_rejected_credentials_lan_mode_and_transport_errors_publish_nothing(self) -> None:
        cases = [
            FlashforgeHttp({"code": 1, "message": "Access code is different"}),
            FlashforgeHttp({"code": -2, "message": "Lan mode error"}),
            FlashforgeHttp({"code": 0, "message": "Success"}),
            FlashforgeHttp([]),
            FlashforgeHttp(error=HttpRequestError("HTTP peer is unreachable")),
        ]
        for http in cases:
            with self.subTest(response=http.response), self.assertRaises(ProviderUnavailable):
                provider(http).observe()

    def test_malformed_station_is_not_reported_as_a_topology(self) -> None:
        base = json.loads(FIXTURE.read_text())
        for mutate in (
            lambda station: station["slotInfos"].append(copy.deepcopy(station["slotInfos"][0])),
            lambda station: station.update(slotCnt=5),
            lambda station: station["slotInfos"][1].update(slotId=0),
        ):
            response = copy.deepcopy(base)
            mutate(response["detail"]["matlStationInfo"])
            with self.subTest(station=response["detail"]["matlStationInfo"]):
                snapshot = provider(FlashforgeHttp(response)).observe()
                self.assertFalse(snapshot.slot_topology_complete)


class FlashforgeConfigTest(unittest.TestCase):
    def load(self, entry: dict[str, Any]) -> NodeConfig:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "options.json"
            path.write_text(json.dumps({"connections": [entry]}), encoding="utf-8")
            with patch.dict("os.environ", {"FH_EDGE_OPTIONS_FILE": str(path)}, clear=True):
                return NodeConfig.load()

    def test_connection_defaults_to_the_lan_api_port_and_hides_the_check_code(self) -> None:
        config = self.load(
            {
                "id": "creator",
                "adapter": "flashforge",
                "printer_url": "http://192.168.1.40",
                "serial_number": "SNMQRB9400123",
                "check_code": "a1b2c3d4",
            }
        ).connections[0]

        self.assertEqual(config.material_provider, "flashforge")
        self.assertEqual(config.moonraker_url, "http://192.168.1.40:8898")
        self.assertNotIn("a1b2c3d4", repr(config))
        self.assertIsInstance(
            build_connection(config, store=None, state=None).provider,  # type: ignore[arg-type]
            FlashforgeProvider,
        )

    def test_incomplete_or_mixed_credentials_fail_closed(self) -> None:
        flashforge = {
            "id": "creator",
            "adapter": "flashforge",
            "printer_url": "http://192.168.1.40",
            "serial_number": "SNMQRB9400123",
            "check_code": "a1b2c3d4",
        }
        invalid = [
            {k: v for k, v in flashforge.items() if k != "check_code"},
            {k: v for k, v in flashforge.items() if k != "serial_number"},
            {**flashforge, "material_provider": "happy_hare"},
            {**flashforge, "moonraker_api_key": "secret"},
            {**flashforge, "moonraker_url": "http://192.168.1.41"},
            {"id": "voron", "moonraker_url": "http://voron.test", "check_code": "a1b2c3d4"},
        ]
        for entry in invalid:
            with self.subTest(entry=entry), self.assertRaises(ConfigurationError):
                self.load(entry)


if __name__ == "__main__":
    unittest.main()
