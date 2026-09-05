"""Exercise adapter-lab services through the production adapter code paths."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import urllib.request
from pathlib import Path
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
ORCA_PLUGIN = ROOT / "orca-plugin" / "filamenthub_plugin.py"
OCTOPRINT_API_KEY = "FHLAB00000000000000000000000000000000001"
TARGETS = ("octoprint", "moonraker", "bambu")
COMPOSE_FILE = ROOT / "docker-compose.adapter-lab.yml"


def _load_orca_plugin():
    fake_orca = ModuleType("orca")
    fake_orca.base = object
    fake_orca.plugin = lambda cls: cls
    fake_orca.register_capability = lambda _capability: None
    fake_orca.script = SimpleNamespace(ScriptPluginCapabilityBase=object)
    fake_orca.host = SimpleNamespace(ui=SimpleNamespace())
    fake_orca.ExecutionResult = SimpleNamespace(success=lambda message: message)
    previous = sys.modules.get("orca")
    sys.modules["orca"] = fake_orca
    try:
        spec = importlib.util.spec_from_file_location(
            "adapter_lab_orca_plugin", ORCA_PLUGIN
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load Orca plugin")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            sys.modules.pop("orca", None)
        else:
            sys.modules["orca"] = previous


def smoke_octoprint() -> str:
    def get(path: str) -> dict:
        request = urllib.request.Request(
            "http://127.0.0.1:5010" + path,
            headers={"X-Api-Key": OCTOPRINT_API_KEY},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)

    version = get("/api/version")
    if "server" not in version or "api" not in version:
        raise RuntimeError("OctoPrint returned an incomplete version response")
    connection = get("/api/connection")
    if "VIRTUAL" not in connection.get("options", {}).get("ports", []):
        raise RuntimeError("OctoPrint Virtual Printer is unavailable")
    bridge = get("/api/plugin/filamenthub_bridge")
    if "paired" not in bridge or "outbox_size" not in bridge:
        raise RuntimeError("FilamentHub OctoPrint bridge API is unavailable")
    return (
        f"OctoPrint {version['server']} (API {version['api']}), "
        "Virtual Printer and FilamentHub bridge loaded"
    )


def smoke_moonraker(plugin) -> str:
    snapshot = plugin.read_happy_hare_snapshot(
        {
            "print_host": "127.0.0.1:7126",
            "api_key": "adapter-lab-hh-key",
        }
    )
    if snapshot["gate_count"] != 4 or snapshot["actual_spool_ids"] != [
        101,
        102,
        103,
        None,
    ]:
        raise RuntimeError(
            "Moonraker/Happy Hare topology does not match the lab fixture"
        )
    if snapshot.get("bypass") != {"selected": True, "present": True}:
        raise RuntimeError("Moonraker/Happy Hare bypass state was lost")
    return "Moonraker/Happy Hare: 4 gates, exact spool IDs, bypass selected"


def smoke_bambu(plugin) -> str:
    discovered, _complete = plugin.discover_lan_printers(duration=3.0)
    candidates = [
        item
        for item in discovered
        if item.get("provider") == "bambu"
        and item.get("serial") == "FH-BAMBU-LAB"
        and item.get("source") == "network"
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            f"expected one Bambu UDP discovery result, found {len(candidates)}"
        )
    host = candidates[0].get("host")
    config = {"host": host, "access_code": "adapterlab", "serial": ""}
    serial, report = plugin.read_bambu_lan_snapshot(config, timeout=5)
    if serial != "FH-BAMBU-LAB":
        raise RuntimeError(f"unexpected Bambu serial: {serial}")
    feed = plugin.parse_bambu_feed(report) or {}
    slots = {slot["index"]: slot for slot in feed.get("slots", [])}
    if set(slots) != {0, 1, 2, 3, 255} or slots[3]["present"]:
        raise RuntimeError("Bambu AMS/external-holder topology is incomplete")

    plugin._publish_bambu_json(
        config,
        serial,
        {
            "print": {
                "command": "ams_filament_setting",
                "sequence_id": "adapter-lab-smoke",
                "ams_id": 0,
                "slot_id": 1,
                "tray_id": 1,
                "tray_info_idx": "LAB-PETG",
                "setting_id": "LAB-PETG-SETTING",
                "tray_color": "00AABBFF",
                "nozzle_temp_min": 225,
                "nozzle_temp_max": 265,
                "tray_type": "PETG",
            }
        },
        timeout=5,
    )
    serial, report = plugin.read_bambu_lan_snapshot(
        {**config, "serial": serial}, timeout=5
    )
    slots = {
        slot["index"]: slot
        for slot in (plugin.parse_bambu_feed(report) or {}).get("slots", [])
    }
    if slots.get(1, {}).get("setting_id") != "LAB-PETG-SETTING":
        raise RuntimeError("Bambu material write was not visible on the next snapshot")
    return (
        f"Bambu LAN at {host}: UDP discovery, TLS/MQTT snapshot and "
        "verified material write"
    )


def smoke_bambu_in_lab() -> str:
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            "filamenthub-adapter-lab",
            "--file",
            str(COMPOSE_FILE),
            "exec",
            "--no-TTY",
            "bambu-lan",
            "python",
            "/source/adapter-lab/smoke.py",
            "bambu",
            "--inside-lab",
        ],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    output = completed.stdout.strip()
    if not output.startswith("ok: "):
        raise RuntimeError("Bambu in-network smoke returned an invalid result")
    return output.removeprefix("ok: ")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=(*TARGETS, "current"))
    parser.add_argument("--inside-lab", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside_lab and args.target != "bambu":
        parser.error("--inside-lab is only valid with bambu")
    targets = TARGETS if args.target == "current" else (args.target,)
    plugin = (
        _load_orca_plugin()
        if "moonraker" in targets or ("bambu" in targets and args.inside_lab)
        else None
    )
    checks = {
        "octoprint": lambda: smoke_octoprint(),
        "moonraker": lambda: smoke_moonraker(plugin),
        "bambu": lambda: (
            smoke_bambu(plugin) if args.inside_lab else smoke_bambu_in_lab()
        ),
    }
    for target in targets:
        print(f"ok: {checks[target]()}")


if __name__ == "__main__":
    main()
