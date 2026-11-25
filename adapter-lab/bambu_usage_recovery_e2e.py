"""Live adapter-lab check of what a Bambu print leaves behind when things go wrong.

Run from the adapter-lab network namespace, like ``bambu_accounting_e2e.py``.
It drives the production plugin code against the lab printer and the dev API
through three prints:

* the connection to the printer is lost in mid-print: the grams printed
  meanwhile are still charged, and the slot that printed without a spool is
  named in the job;
* nothing is assigned at all: the job says so instead of ending at zero grams;
* a spool smaller than the job: it keeps its slot at a recorded zero, the
  owner is told once, and the next print is still written to its history;
* a job whose file is not on the printer, sent from this OrcaSlicer: it is
  counted from the slice the plugin kept.

Every run creates its own printers and spools and never prints a token.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from pathlib import Path

from bambu_accounting_e2e import (
    BAMBU_ACCESS_CODE,
    BAMBU_SERIAL,
    CAPABILITIES,
    DEFAULT_DEV_URL,
    DEFAULT_STATE_URL,
    DevApi,
    _api_base,
    _observe,
    _post_state,
    _private_bambu_host,
    _publish_and_record,
    _site_base,
    _spool_usage,
)
from smoke import _load_orca_plugin

# What the lab's part.gcode weighs per filament; see bambu_lan.py.
SLOT_0_G = 12.5
SLOT_1_G = 7.5


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


class Lab:
    def __init__(self, args: argparse.Namespace):
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
        _expect(bool(token), f"token file {args.token_file} is empty")
        api_base = _api_base(args.dev_url)
        os.environ["FILAMENTHUB_SITE_URL"] = _site_base(api_base)
        self.plugin = _load_orca_plugin()
        self.api = DevApi(api_base, token)
        self.host = _private_bambu_host(args.bambu_host)
        self.state_url = args.state_url
        self.root = Path(tempfile.mkdtemp(prefix="fh-bambu-recovery-"))
        self.plugin.BAMBU_CONFIG_FILE = str(self.root / ".fh_bambu.json")
        self.plugin._SLICE_INDEX_FILE = str(self.root / ".fh_slices.json")
        self.plugin._SLICE_CACHE_DIR = str(self.root / "slices")

    def printer(self, name: str) -> dict:
        printer = self.api.post("/physical-printers", {"name": name})
        printer_id = int(printer["id"])
        systems = self.api.post(
            f"/physical-printers/{printer_id}/material-systems",
            {"name": "Adapter lab AMS", "provider": "bambu", "slot_count": 2},
        )["material_systems"]
        system = next(item for item in systems if item["provider"] == "bambu")
        source = f"bambu-recovery-lab-{printer_id:08d}"
        pairing = self.api.post(
            f"/printer-bridge/connections/{printer_id}/{system['id']}/pairing-code"
            "?transport=orca_plugin_lan",
            {},
        )
        paired = self.api.post(
            "/printer-bridge/pair",
            {
                "pairing_code": pairing["pairing_code"],
                "provider": "bambu",
                "transport": "orca_plugin_lan",
                "source_instance_id": source,
                "plugin_version": self.plugin.PLUGIN_VERSION,
                "capabilities": CAPABILITIES,
            },
        )
        return {
            "id": printer_id,
            "system_id": int(system["id"]),
            "source": source,
            "config": {
                "host": self.host,
                "access_code": BAMBU_ACCESS_CODE,
                "serial": BAMBU_SERIAL,
                "physical_printer_id": printer_id,
                "material_system_id": int(system["id"]),
                "bridge_token": paired["bridge_token"],
            },
        }

    def slot(self, printer: dict, index: int) -> dict:
        current = self.api.get(f"/physical-printers/{printer['id']}")
        system = next(
            item for item in current["material_systems"] if item["id"] == printer["system_id"]
        )
        return next(item for item in system["slots"] if item["provider_index"] == index)

    def assign(self, printer: dict, index: int, initial_weight_g: float) -> int:
        spool_id = int(self.api.post("/spools", {"initial_weight_g": initial_weight_g})["id"])
        slot = self.slot(printer, index)
        self.api.patch(
            f"/physical-printers/{printer['id']}/material-slots/{slot['id']}",
            {
                "expected_revision": slot["assignment_revision"],
                "expected_spool_id": None,
                "spool_id": spool_id,
            },
        )
        return spool_id

    def stage(self, runtime, printer: dict, state: str, percent: int, **job) -> None:
        _post_state(self.state_url, {"gcode_state": state, "mc_percent": percent, **job})
        report = _observe(self.plugin, runtime, printer["config"], state, percent)
        _publish_and_record(self.plugin, runtime, printer["config"], report, printer["source"])

    def start(self, runtime, printer: dict, job: str, percent: int = 0) -> None:
        self.stage(
            runtime, printer, "RUNNING", percent,
            filename="part.gcode", task_id=job, subtask_id=job, ams_mapping=[0, 1],
        )

    def lose_connection(self, runtime, printer: dict) -> None:
        """Mark the interval as unwatched, exactly as a dropped MQTT link does."""
        stream = runtime._streams[self.plugin._bambu_stream_key(printer["config"])]
        with stream["lock"]:
            stream["usage_gap_pending"] = True
            stream.pop("usage_signature", None)

    def jobs(self, printer: dict) -> list[dict]:
        return self.api.get(
            f"/print-jobs?physical_printer_id={printer['id']}&page=1&size=100"
        )["items"]

    def remaining(self, spool_id: int) -> float:
        return float(self.api.get(f"/spools/{spool_id}")["remaining_weight_g"])


def lost_connection(lab: Lab) -> dict:
    printer = lab.printer("Adapter lab: lost connection")
    spool_id = lab.assign(printer, 0, 1000)
    runtime = lab.plugin.BambuBridgeRuntime()
    try:
        lab.start(runtime, printer, "adapter-lab-recovery-gap", percent=10)
        lab.lose_connection(runtime, printer)
        lab.stage(runtime, printer, "RUNNING", 60)
        lab.stage(runtime, printer, "FINISH", 100)
    finally:
        runtime.stop(wait_timeout=3)
    charged = 1000 - lab.remaining(spool_id)
    _expect(
        math.isclose(charged, SLOT_0_G * 0.9, abs_tol=0.001),
        f"a lost connection dropped usage: charged {charged} g, expected {SLOT_0_G * 0.9}",
    )
    (job,) = lab.jobs(printer)
    _expect(job["status"] == "completed", f"job ended as {job['status']}")
    _expect(
        job["usage_issues"] == [{"reason": "slot_without_spool", "slot_index": 1}],
        f"the slot printed without a spool is not named: {job['usage_issues']}",
    )
    return {"printer_id": printer["id"], "charged_g": round(charged, 4), "issues": job["usage_issues"]}


def nothing_assigned(lab: Lab) -> dict:
    printer = lab.printer("Adapter lab: nothing assigned")
    runtime = lab.plugin.BambuBridgeRuntime()
    try:
        lab.start(runtime, printer, "adapter-lab-recovery-empty")
        lab.stage(runtime, printer, "FINISH", 100)
    finally:
        runtime.stop(wait_timeout=3)
    (job,) = lab.jobs(printer)
    _expect(
        job["estimated_consumption_g"] == 0 and job["confirmed_consumption_g"] == 0,
        "a print without spools was charged to something",
    )
    _expect(
        job["usage_issues"] == [{"reason": "no_spool_assigned", "slot_index": None}],
        f"an uncounted print does not say why: {job['usage_issues']}",
    )
    return {"printer_id": printer["id"], "issues": job["usage_issues"]}


def spool_runs_out(lab: Lab) -> dict:
    printer = lab.printer("Adapter lab: spool runs out")
    spool_id = lab.assign(printer, 0, 5)
    for job in ("adapter-lab-recovery-out-1", "adapter-lab-recovery-out-2"):
        runtime = lab.plugin.BambuBridgeRuntime()
        try:
            lab.start(runtime, printer, job)
            lab.stage(runtime, printer, "FINISH", 100)
        finally:
            runtime.stop(wait_timeout=3)
    spool = lab.api.get(f"/spools/{spool_id}")
    _expect(float(spool["remaining_weight_g"]) == 0, "the spool did not reach a recorded zero")
    _expect(spool["state"] != "empty", "a printer estimate marked the spool empty")
    assignment = lab.slot(printer, 0)["assignment"]
    _expect(
        assignment is not None and assignment["spool_id"] == spool_id,
        "the spool lost its slot at a recorded zero",
    )
    reports = [
        event for event in _spool_usage(lab.api, spool_id)
        if (event.get("meta") or {}).get("event_type") == "terminal"
    ]
    _expect(len(reports) == 2, f"the print after zero left no trace: {len(reports)} reports")
    notices = [
        item for item in lab.api.get("/notifications/?page=1&size=50")["items"]
        if item["title"] == "spool_out_by_estimate"
        and (item.get("extra_data") or {}).get("spool_id") == spool_id
    ]
    _expect(len(notices) == 1, f"expected one notice about the spool, found {len(notices)}")
    return {"printer_id": printer["id"], "spool_id": spool_id, "reports": len(reports)}


def sent_from_orca(lab: Lab) -> dict:
    printer = lab.printer("Adapter lab: sent from Orca")
    spool_id = lab.assign(printer, 0, 1000)
    # What the plugin holds after a slice and the host's "print sent" event.
    sliced = lab.root / "plate_1.gcode"
    lines = ["M83"]
    for layer in range(3):
        lines += ["; CHANGE_LAYER", f"G1 X{layer + 1} E1"]
    sliced.write_text("\n".join([*lines, "; filament used [g] = 9.00", ""]), encoding="utf-8")
    lab.plugin._remember_slice_path(str(sliced))
    job = "adapter-lab-sent-from-orca"
    _expect(lab.plugin.remember_sent_print(job, BAMBU_SERIAL), "the sent print was not noted")
    runtime = lab.plugin.BambuBridgeRuntime()
    try:
        # The printer names a file it does not hold any more.
        lab.stage(
            runtime, printer, "RUNNING", 0,
            filename=job + ".gcode", task_id=job, subtask_id=job, ams_mapping=[0],
            total_layer_num=3, layer_num=0,
        )
        lab.stage(runtime, printer, "FINISH", 100, layer_num=3)
    finally:
        runtime.stop(wait_timeout=3)
    charged = 1000 - lab.remaining(spool_id)
    _expect(math.isclose(charged, 9.0, abs_tol=0.001), f"charged {charged} g, expected 9")
    (shown,) = lab.jobs(printer)
    _expect(shown["usage_issues"] == [], f"a counted job reports issues: {shown['usage_issues']}")
    return {"printer_id": printer["id"], "charged_g": round(charged, 4)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev-url", default=os.environ.get("FILAMENTHUB_DEV_URL", DEFAULT_DEV_URL))
    parser.add_argument("--token-file", default="/tmp/fh-bambu-lab-token")
    parser.add_argument("--state-url", default=DEFAULT_STATE_URL)
    parser.add_argument("--bambu-host", default=os.environ.get("BAMBU_LAB_HOST", "bambu-lan"))
    lab = Lab(parser.parse_args())
    print(json.dumps({
        "ok": True,
        "plugin_version": lab.plugin.PLUGIN_VERSION,
        "lost_connection": lost_connection(lab),
        "nothing_assigned": nothing_assigned(lab),
        "spool_runs_out": spool_runs_out(lab),
        "sent_from_orca": sent_from_orca(lab),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
