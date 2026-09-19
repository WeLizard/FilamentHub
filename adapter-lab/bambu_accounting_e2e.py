"""Live adapter-lab Bambu accounting scenario.

Run this only from the adapter-lab network namespace. It creates one isolated
FilamentHub printer/system/spool through the authenticated dev API and talks to
the real Bambu TLS/MQTT and implicit-FTPS lab services through the production
plugin code. It never prints the API token or bridge token.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import math
import os
import socket
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from smoke import _load_orca_plugin


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEV_URL = "http://host.docker.internal:8001/api/v1"
DEFAULT_STATE_URL = "http://127.0.0.1:8884/state"
BAMBU_SERIAL = "FH-BAMBU-LAB"
BAMBU_ACCESS_CODE = "adapterlab"
CAPABILITIES = ["read", "presence", "consumption", "tag_read"]


class DevApi:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, payload: object | None = None) -> object:
        url = self.base_url + path
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as exc:
            # Do not include request headers or token in diagnostics.
            detail = exc.read(512).decode("utf-8", "replace")
            raise RuntimeError(f"dev API {method} {path} returned HTTP {exc.code}: {detail}") from exc

    def get(self, path: str) -> object:
        return self.request("GET", path)

    def post(self, path: str, payload: object) -> object:
        return self.request("POST", path, payload)

    def patch(self, path: str, payload: object) -> object:
        return self.request("PATCH", path, payload)


def _api_base(value: str) -> str:
    from urllib.parse import urlsplit

    parsed = urlsplit(value.rstrip("/"))
    if parsed.scheme != "http" or parsed.hostname not in {
        "host.docker.internal", "localhost", "127.0.0.1",
    } or parsed.port != 8001 or parsed.username or parsed.password:
        raise RuntimeError(
            "--dev-url must be http on host.docker.internal, localhost or 127.0.0.1:8001"
        )
    path = parsed.path.rstrip("/")
    if path not in {"", "/api/v1"}:
        raise RuntimeError("--dev-url may only contain /api/v1 as its path")
    return f"http://{parsed.hostname}:8001/api/v1"


def _site_base(api_base: str) -> str:
    return api_base[: -len("/api/v1")]


def _post_state(url: str, payload: dict[str, object]) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read(512).decode("utf-8", "replace")
        raise RuntimeError(f"adapter-lab state returned HTTP {exc.code}: {detail}") from exc


def _private_bambu_host(value: str) -> str:
    host = value
    try:
        address = socket.gethostbyname(host)
    except OSError as exc:
        raise RuntimeError(f"cannot resolve Bambu lab host {host!r}") from exc
    parsed = ipaddress.ip_address(address)
    if parsed.is_loopback or parsed.is_unspecified or not (parsed.is_private or parsed.is_link_local):
        raise RuntimeError("Bambu host must be the lab container LAN address, not loopback")
    return address


def _observe(plugin, runtime, config: dict, expected_state: str, expected_percent: int) -> dict:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        serial, report = runtime._stream_observation(config)
        if serial != BAMBU_SERIAL:
            raise RuntimeError(f"unexpected Bambu serial: {serial}")
        if (
            str(report.get("gcode_state", "")).upper() == expected_state
            and int(report.get("mc_percent", -1)) == expected_percent
        ):
            return report
        time.sleep(0.25)
    raise RuntimeError(
        f"Bambu stream did not reach {expected_state}/{expected_percent}% before timeout"
    )


def _publish_and_record(plugin, runtime, config, report: dict, source_instance_id: str) -> str:
    snapshot = plugin.build_bambu_bridge_snapshot(config, source_instance_id, report)
    status, body, _retry_after = plugin.http_post_bridge_json(
        "/printer-bridge/snapshot",
        config["bridge_token"],
        snapshot,
    )
    if status != 200:
        raise RuntimeError(f"snapshot publication returned HTTP {status}: {body[:512].decode('utf-8', 'replace')}")
    runtime._record_stream_usage(
        config, source_instance_id, report, snapshot["observed_at"]
    )
    return snapshot["observed_at"]


def _spool_usage(api: DevApi, spool_id: int) -> list[dict]:
    value = api.get(f"/spools/{spool_id}/usage")
    if not isinstance(value, list):
        raise RuntimeError("spool usage response is not a list")
    if any(not isinstance(item, dict) for item in value):
        raise RuntimeError("spool usage response contains a non-object event")
    return value


def _print_job_with_estimate(api: DevApi, printer_id: int, spool_id: int) -> dict:
    value = api.get(f"/print-jobs?physical_printer_id={printer_id}&page=1&size=100")
    if not isinstance(value, dict) or not isinstance(value.get("total"), int):
        raise RuntimeError("print-jobs response is missing integer total")
    items = value.get("items")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise RuntimeError("print-jobs response is missing object items")
    matches = [
        item for item in items
        if item.get("estimated_consumption_g", 0) > 0
        and any(
            usage_item.get("spool_id") == spool_id
            for segment in item.get("usage_segments", [])
            for usage_item in segment.get("items", [])
        )
    ]
    if not matches:
        raise RuntimeError("print-jobs response has no estimated consumption")
    return matches[-1]


def run(args: argparse.Namespace) -> None:
    try:
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"cannot read token file {args.token_file}") from exc
    if not token:
        raise RuntimeError(f"token file {args.token_file} is empty")

    api_base = _api_base(args.dev_url)
    os.environ["FILAMENTHUB_SITE_URL"] = _site_base(api_base)
    plugin = _load_orca_plugin()
    api = DevApi(api_base, token)
    bambu_host = _private_bambu_host(args.bambu_host)

    printer = api.post("/physical-printers", {"name": "Adapter lab Bambu accounting"})
    printer_id = int(printer["id"])
    source_instance_id = f"bambu-accounting-lab-{printer_id:08d}"
    if printer.get("material_systems") != []:
        raise RuntimeError("new printer response unexpectedly contains material systems")
    system_response = api.post(
        f"/physical-printers/{printer_id}/material-systems",
        {"name": "Adapter lab AMS", "provider": "bambu", "slot_count": 2},
    )
    systems = system_response.get("material_systems")
    if not isinstance(systems, list):
        raise RuntimeError("material-system response is missing material_systems")
    system = next(item for item in systems if item["provider"] == "bambu")
    if len(system.get("slots", [])) != 2:
        raise RuntimeError("Bambu material system did not create two slots")
    system_id = int(system["id"])
    pairing = api.post(
        f"/printer-bridge/connections/{printer_id}/{system_id}/pairing-code"
        f"?transport=orca_plugin_lan",
        {},
    )
    paired = api.post(
        "/printer-bridge/pair",
        {
            "pairing_code": pairing["pairing_code"],
            "provider": "bambu",
            "transport": "orca_plugin_lan",
            "source_instance_id": source_instance_id,
            "plugin_version": "adapter-lab-live",
            "capabilities": CAPABILITIES,
        },
    )
    bridge_token = paired["bridge_token"]

    journal_root = tempfile.mkdtemp(prefix="fh-bambu-accounting-")
    plugin.BAMBU_CONFIG_FILE = str(Path(journal_root) / ".fh_bambu.json")
    config = {
        "host": bambu_host,
        "access_code": BAMBU_ACCESS_CODE,
        "serial": BAMBU_SERIAL,
        "physical_printer_id": printer_id,
        "material_system_id": system_id,
        "bridge_token": bridge_token,
    }
    runtime = plugin.BambuBridgeRuntime()
    try:
        _post_state(
            args.state_url,
            {
                "gcode_state": "RUNNING",
                "mc_percent": 40,
                "filename": "part.gcode",
                "task_id": "adapter-lab-bambu-accounting",
                "subtask_id": "adapter-lab-bambu-accounting",
                "ams_mapping": [0, 1],
            },
        )
        baseline = _observe(plugin, runtime, config, "RUNNING", 40)
        _publish_and_record(plugin, runtime, config, baseline, source_instance_id)

        created = api.post("/spools", {"initial_weight_g": 995})
        spool_id = int(created["id"])
        assert not _spool_usage(api, spool_id), "baseline created a debit before assignment"

        printer = api.get(f"/physical-printers/{printer_id}")
        current_system = next(item for item in printer["material_systems"] if item["id"] == system_id)
        slot = next(item for item in current_system["slots"] if item["provider_index"] == 0)
        assigned = api.patch(
            f"/physical-printers/{printer_id}/material-slots/{slot['id']}",
            {
                "expected_revision": slot["assignment_revision"],
                "expected_spool_id": None,
                "spool_id": spool_id,
            },
        )
        assigned_system = next(item for item in assigned["material_systems"] if item["id"] == system_id)
        assigned_slot = next(item for item in assigned_system["slots"] if item["provider_index"] == 0)
        assert assigned_slot["assignment"]["spool_id"] == spool_id
        assert assigned_slot["assignment_revision"] == slot["assignment_revision"] + 1

        _post_state(args.state_url, {"gcode_state": "RUNNING", "mc_percent": 40})
        assigned_baseline = _observe(plugin, runtime, config, "RUNNING", 40)
        _publish_and_record(plugin, runtime, config, assigned_baseline, source_instance_id)

        _post_state(args.state_url, {"gcode_state": "RUNNING", "mc_percent": 60})
        progression = _observe(plugin, runtime, config, "RUNNING", 60)
        _publish_and_record(plugin, runtime, config, progression, source_instance_id)

        _post_state(args.state_url, {"gcode_state": "FAILED", "mc_percent": 70})
        failed = _observe(plugin, runtime, config, "FAILED", 70)
        failed_observed_at = _publish_and_record(
            plugin, runtime, config, failed, source_instance_id
        )

        usage = _spool_usage(api, spool_id)
        estimated = [
            event for event in usage
            if (event.get("meta") or {}).get("consumption_kind") == "estimated"
        ]
        if not estimated:
            raise RuntimeError("assigned print produced no estimated printer_report debit")
        if not all((event.get("meta") or {}).get("estimate_source") in {
            "slicer_progress", "slicer_gcode"
        } for event in estimated):
            raise RuntimeError("estimated usage event has an unknown estimate source")
        job = _print_job_with_estimate(api, printer_id, spool_id)
        if job["confirmed_consumption_g"] != 0:
            raise RuntimeError("estimated Bambu debit was reported as confirmed consumption")
        if job["estimated_consumption_g"] <= 0:
            raise RuntimeError("print job has no estimated consumption")
        remaining = float(api.get(f"/spools/{spool_id}")["remaining_weight_g"])
        if not math.isclose(remaining, 991.25, abs_tol=0.001):
            raise RuntimeError(f"expected 3.75 g estimated debit, remaining={remaining}")
        if not any((event.get("meta") or {}).get("outcome") == "failed" for event in estimated):
            raise RuntimeError("estimated terminal usage event did not preserve failed outcome")

        runtime._record_stream_usage(config, source_instance_id, failed, failed_observed_at)
        recreated = plugin.BambuBridgeRuntime()
        try:
            recreated._record_stream_usage(config, source_instance_id, failed, failed_observed_at)
        finally:
            recreated.stop(wait_timeout=1)
        usage_after = _spool_usage(api, spool_id)
        remaining_after = float(api.get(f"/spools/{spool_id}")["remaining_weight_g"])
        assert len(usage_after) == len(usage), "repeated/recreated runtime duplicated usage"
        assert remaining_after == remaining, "repeated/recreated runtime changed spool balance"

        # Recovery: stop the first stream before changing the job identity, then
        # finish the next print through a fresh runtime against the same journal.
        runtime.stop(wait_timeout=3)
        second_created = api.post("/spools", {"initial_weight_g": 500})
        second_spool_id = int(second_created["id"])
        printer = api.get(f"/physical-printers/{printer_id}")
        current_system = next(item for item in printer["material_systems"] if item["id"] == system_id)
        second_slot = next(item for item in current_system["slots"] if item["provider_index"] == 1)
        assigned_second = api.patch(
            f"/physical-printers/{printer_id}/material-slots/{second_slot['id']}",
            {
                "expected_revision": second_slot["assignment_revision"],
                "expected_spool_id": None,
                "spool_id": second_spool_id,
            },
        )
        assigned_second_system = next(
            item for item in assigned_second["material_systems"] if item["id"] == system_id
        )
        assigned_second_slot = next(
            item for item in assigned_second_system["slots"] if item["provider_index"] == 1
        )
        assert assigned_second_slot["assignment"]["spool_id"] == second_spool_id
        assert assigned_second_slot["assignment_revision"] == second_slot["assignment_revision"] + 1

        second_runtime = plugin.BambuBridgeRuntime()
        second_job_id = "adapter-lab-bambu-accounting-recovery"
        try:
            _post_state(
                args.state_url,
                {
                    "gcode_state": "RUNNING",
                    "mc_percent": 0,
                    "filename": "part.gcode",
                    "task_id": second_job_id,
                    "subtask_id": second_job_id,
                    "ams_mapping": [0, 1],
                },
            )
            second_baseline = _observe(plugin, second_runtime, config, "RUNNING", 0)
            _publish_and_record(
                plugin, second_runtime, config, second_baseline, source_instance_id
            )
        finally:
            second_runtime.stop(wait_timeout=3)

        _post_state(args.state_url, {"gcode_state": "FINISH", "mc_percent": 100})
        finish_runtime = plugin.BambuBridgeRuntime()
        try:
            finished = _observe(plugin, finish_runtime, config, "FINISH", 100)
            finished_observed_at = _publish_and_record(
                plugin, finish_runtime, config, finished, source_instance_id
            )
        finally:
            finish_runtime.stop(wait_timeout=3)

        second_job = _print_job_with_estimate(api, printer_id, second_spool_id)
        if second_job["estimated_consumption_g"] != 20:
            raise RuntimeError(
                f"recovery job estimated consumption was {second_job['estimated_consumption_g']}, expected 20"
            )
        if second_job["confirmed_consumption_g"] != 0:
            raise RuntimeError("recovery estimated consumption was reported as measured")
        second_usage = _spool_usage(api, second_spool_id)
        if not any((event.get("meta") or {}).get("outcome") == "completed" for event in second_usage):
            raise RuntimeError("recovery terminal usage event did not preserve completed outcome")
        first_after_recovery = float(api.get(f"/spools/{spool_id}")["remaining_weight_g"])
        second_remaining = float(api.get(f"/spools/{second_spool_id}")["remaining_weight_g"])
        if not math.isclose(first_after_recovery, 978.75, abs_tol=0.001):
            raise RuntimeError(f"recovery did not debit 12.5 g from spool 0: {first_after_recovery}")
        if not math.isclose(second_remaining, 492.5, abs_tol=0.001):
            raise RuntimeError(f"recovery did not debit 7.5 g from spool 1: {second_remaining}")

        repeat_count = len(second_usage)
        repeat_runtime = plugin.BambuBridgeRuntime()
        try:
            repeat_runtime._record_stream_usage(
                config, source_instance_id, finished, finished_observed_at
            )
        finally:
            repeat_runtime.stop(wait_timeout=1)
        if len(_spool_usage(api, second_spool_id)) != repeat_count:
            raise RuntimeError("repeated recovery runtime duplicated usage")
        print(json.dumps({
            "ok": True,
            "printer_id": printer_id,
            "material_system_id": system_id,
            "spool_id": spool_id,
            "estimated_events": len(estimated),
            "estimated_consumption_g": job["estimated_consumption_g"],
            "remaining_weight_g": remaining_after,
            "journal_dir": journal_root,
            "recovery": {
                "spool_id": second_spool_id,
                "estimated_consumption_g": second_job["estimated_consumption_g"],
                "confirmed_consumption_g": second_job["confirmed_consumption_g"],
                "spool_0_remaining_weight_g": first_after_recovery,
                "spool_1_remaining_weight_g": second_remaining,
                "usage_events": len(second_usage),
            },
        }, sort_keys=True))
    finally:
        runtime.stop(wait_timeout=1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev-url", default=os.environ.get("FILAMENTHUB_DEV_URL", DEFAULT_DEV_URL))
    parser.add_argument("--token-file", default="/tmp/fh-bambu-lab-token")
    parser.add_argument("--state-url", default=DEFAULT_STATE_URL)
    parser.add_argument(
        "--bambu-host",
        default=os.environ.get("BAMBU_LAB_HOST", "bambu-lan"),
        help="Bambu lab container DNS name or private LAN IPv4 address",
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()

\n