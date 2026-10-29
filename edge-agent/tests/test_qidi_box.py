"""QIDI Box reader. Fixtures follow the shapes read by OrcaSlicer's
QidiPrinterAgent (a65ae5fe); they are reconstructed from that implementation,
not captured from a device, and still need hardware confirmation."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from filamenthub_edge.errors import HttpRequestError
from filamenthub_edge.providers import qidi_box
from filamenthub_edge.providers.moonraker import MoonrakerProvider

FIXTURES = Path(__file__).parent / "fixtures" / "qidi_box"


def fixture(name: str) -> Any:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return text if name.endswith(".cfg") else json.loads(text)


class QidiHttp:
    def __init__(self, *, objects: Any = None, config: Any = None, dictionary: bool = True) -> None:
        self.objects = objects if objects is not None else fixture("objects_list.json")
        self.config = config if config is not None else {}
        self.dictionary = dictionary
        self.paths: list[str] = []

    def request(self, method: str, path: str, **kwargs: Any):  # noqa: ANN201
        self.paths.append(path)
        if path == "/printer/objects/list":
            return 200, self.objects, {}
        if path == qidi_box.DICT_PATH:
            if not self.dictionary:
                raise HttpRequestError("HTTP peer returned 404", status_code=404)
            return 200, fixture("officiall_filas_list.cfg"), {}
        if path == "/server/config":
            return 200, {"result": {"config": self.config}}, {}
        if path == "/printer/objects/query":
            return 200, fixture("query.json"), {}
        raise HttpRequestError("unexpected path " + path)


def provider(http: QidiHttp, material: str = "legacy") -> MoonrakerProvider:
    return MoonrakerProvider(
        "http://qidi.local:7125",
        api_key=None,
        material_provider=material,
        timeout=2,
        http_client=http,
    )


class QidiBoxTest(unittest.TestCase):
    def test_slots_follow_orca_reader_rules(self) -> None:
        snapshot = provider(QidiHttp()).observe()
        slots = {slot["provider_index"]: slot for slot in snapshot.slots}
        self.assertEqual(sorted(slots), [0, 1, 2, 3])
        self.assertEqual(
            (slots[0]["present"], slots[0]["material"], slots[0]["color_hex"]),
            (True, "PLA", "060606"),
        )
        self.assertEqual((slots[1]["material"], slots[1]["color_hex"]), ("PETG", "0A2989"))
        # runout_button == 1: empty slot carries no material or colour
        self.assertFalse(slots[2]["present"])
        self.assertNotIn("material", slots[2])
        # missing sensor value is unknown, not empty
        self.assertIsNone(slots[3]["present"])
        self.assertTrue(snapshot.slot_topology_complete)
        self.assertTrue(all(slot["spool_identity_known"] is False for slot in slots.values()))

    def test_plain_klipper_without_box_steppers_has_no_slots_and_no_extra_requests(self) -> None:
        http = QidiHttp(objects={"result": {"objects": ["print_stats", "extruder"]}})
        snapshot = provider(http).observe()
        self.assertEqual(snapshot.slots, [])
        self.assertNotIn(qidi_box.DICT_PATH, http.paths)

    def test_missing_dictionary_keeps_presence_and_leaves_material_unknown(self) -> None:
        snapshot = provider(QidiHttp(dictionary=False)).observe()
        self.assertTrue(snapshot.slots[0]["present"])
        self.assertNotIn("material", snapshot.slots[0])
        self.assertNotIn("color_hex", snapshot.slots[0])

    def test_native_spoolman_remains_the_only_consumption_source(self) -> None:
        for config, usage in (({"spoolman": {}}, False), ({}, True)):
            with self.subTest(config=config):
                snapshot = provider(QidiHttp(config=config)).observe()
                self.assertEqual("consumption" in snapshot.capabilities, usage)
                self.assertEqual(snapshot.usage is not None, usage)
                self.assertNotIn("spool_identity", snapshot.capabilities)

    def test_unknown_slot_count_is_capped(self) -> None:
        status = fixture("query.json")["result"]["status"]
        status["save_variables"]["variables"]["box_count"] = 40
        self.assertEqual(len(qidi_box.build_slots(status, {}, {})), qidi_box.MAX_SLOTS)

    def test_dictionary_parser_ignores_comments_and_other_sections(self) -> None:
        colors, filaments = qidi_box.parse_dictionary(
            "[other]\n1=x\n# c\n[colordict]\n3 = #112233\n"
            "[fila0]\nfilament=X\n[fila2]\nfilament = ABS\n"
        )
        self.assertEqual((colors, filaments), ({3: "#112233"}, {2: "ABS"}))

    def test_material_normalisation_matches_orca(self) -> None:
        self.assertEqual(qidi_box.normalize_material("PA12-CF"), "PA")
        self.assertEqual(qidi_box.normalize_material("PETG Tough"), "PETG")
        self.assertEqual(qidi_box.normalize_material("pc blend"), "PC")


if __name__ == "__main__":
    unittest.main()
