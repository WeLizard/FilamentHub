from __future__ import annotations

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load(relative_path: str, name: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_adapter_lab_cli_never_starts_unrequested_protocols():
    cli = _load("scripts/adapter_lab.py", "adapter_lab_cli_test")

    assert cli.services_for("octoprint") == ("octoprint",)
    assert cli.services_for("moonraker") == ("moonraker-hh",)
    assert cli.services_for("bambu") == ("bambu-lan",)
    assert cli.services_for("current") == (
        "octoprint",
        "moonraker-hh",
        "bambu-lan",
    )


def test_moonraker_fixture_requires_key_and_returns_hh_bypass():
    moonraker = _load("adapter-lab/moonraker_hh.py", "moonraker_lab_test")
    server = ThreadingHTTPServer(("127.0.0.1", 0), moonraker.MoonrakerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(base_url + "/healthz", timeout=2) as response:
            assert response.status == 200
        request = urllib.request.Request(
            base_url + "/printer/objects/query",
            data=json.dumps(
                {"objects": {"mmu": ["num_gates"], "print_stats": ["state"]}}
            ).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": "adapter-lab-hh-key",
            },
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            body = json.load(response)
        mmu = body["result"]["status"]["mmu"]
        assert mmu["num_gates"] == 4
        assert mmu["gate_spool_id"] == [101, 102, 103, -1]
        assert mmu["has_bypass"] is True
        assert mmu["tool"] == -2
        assert mmu["filament_pos"] > 0

        unauthorized = urllib.request.Request(base_url + "/printer/info")
        try:
            urllib.request.urlopen(unauthorized, timeout=2)
        except urllib.error.HTTPError as error:
            assert error.code == 401
        else:
            raise AssertionError("Moonraker fixture accepted a missing API key")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_bambu_fixture_material_write_changes_only_target_slot():
    bambu = _load("adapter-lab/bambu_lan.py", "bambu_lab_test")
    before = bambu.snapshot()
    first_before = before["ams"]["ams"][0]["tray"][0].copy()

    assert bambu.apply_request(
        {
            "print": {
                "command": "ams_filament_setting",
                "ams_id": 0,
                "slot_id": 1,
                "tray_info_idx": "LAB-PETG",
                "setting_id": "LAB-PETG-SETTING",
                "tray_color": "00AABBFF",
                "nozzle_temp_min": 225,
                "nozzle_temp_max": 265,
                "tray_type": "PETG",
            }
        }
    )

    after = bambu.snapshot()
    trays = after["ams"]["ams"][0]["tray"]
    assert trays[0] == first_before
    assert trays[1]["tray_info_idx"] == "LAB-PETG"
    assert trays[1]["setting_id"] == "LAB-PETG-SETTING"
    assert trays[1]["tray_color"] == "00AABBFF"
    assert trays[3]["tray_type"] == ""


def test_compose_profiles_are_loopback_only_and_octoprint_is_persistent():
    compose = (ROOT / "docker-compose.adapter-lab.yml").read_text(encoding="utf-8")

    assert "profiles: [octoprint]" in compose
    assert "profiles: [moonraker]" in compose
    assert "profiles: [bambu]" in compose
    assert '"127.0.0.1:5010:80"' in compose
    assert '"127.0.0.1:7126:7125"' in compose
    assert '"127.0.0.1:8883:8883"' in compose
    assert '"0.0.0.0:' not in compose
    assert "filamenthub-adapter-lab-octoprint:local" in compose
    assert "octoprint_adapter_lab:/octoprint" in compose
    assert ".filamenthub-adapter-lab-config-v2" in compose
