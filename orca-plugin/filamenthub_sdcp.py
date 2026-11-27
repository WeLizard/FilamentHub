"""SDCP printers for the FilamentHub OrcaSlicer plugin.

SDCP (Smart Device Control Protocol) is Chitu Systems' open LAN protocol.
This module knows the protocol, not a brand: any FDM printer that speaks it is
read the same way. The known devices are Elegoo's Centauri and Centauri Carbon;
the Centauri Carbon 2 speaks another protocol and has its own adapter
(``filamenthub_elegoo_mqtt.py``).

Sources. Every field this module reads is named in at least one of them; an
item marked "not confirmed" is not.

[spec]  cbd-tech/SDCP-Smart-Device-Control-Protocol-V3.0.0 @ f9772157,
        "SDCP(Smart Device Control Protocol)_V3.0.0_EN.md": the WebSocket at
        ``ws://<printer>:3030/websocket`` (l. 13, 34), the topics
        ``sdcp/{request,response,status,attributes}/<MainboardID>`` (l. 41-47),
        the status object (l. 136-158), command 0 status and 1 attributes
        (l. 302, 341), ``Ack`` 0 for success (l. 252).
[link]  elegooofficial/elegoo-link @ ec2d2269 (Elegoo's own LAN library),
        ``src/lan/adapters/elegoo_fdm_cc/elegoo_fdm_cc_message_adapter.cpp``:
        machine and print status codes of FDM firmware (l. 19-61), the request
        envelope (l. 85-106), status parsing with a file transfer giving way
        to the second machine status (l. 564-600), ``PrintInfo`` fields
        (l. 742-752), temperatures ``TempOf*`` / ``TempTarget*`` (l. 821-828),
        attributes ``MainboardID`` and ``FirmwareVersion``, multi-colour
        support from firmware 1.2 (l. 835-898), the CANVAS answer (l. 902-947)
        and the command table 0, 1 and 324 (l. 975-1001); the reply of a
        command sits in ``Data.Data`` with ``Ack`` (l. 353-410).
[orca]  OrcaSlicer/OrcaSlicer @ 7cdc829a, ``src/slic3r/Utils/ElegooLink.cpp``:
        ``classify_printer_model`` (l. 136-146) and the connection test that
        tries Moonraker first and SDCP after it for a profile of unknown model
        (l. 465-484); the request envelope with ``From`` 1 (l. 1121-1137).
[ha]    danielcherubini/elegoo-homeassistant @ ce9c1559,
        ``custom_components/elegoo_printer/sdcp/models/status.py`` l. 185-194:
        FDM firmware counts ``CurrentTicks`` / ``TotalTicks`` in seconds; the
        resin-era spec says milliseconds.
[tiger] TigerTag-Project/TigerTag-Studio-Manager issue #41 (2026-10-08): a
        status and attributes capture of a Centauri Carbon on V1.4.49, kept as
        ``edge-agent/tests/fixtures/sdcp/status_idle.json`` and ``attributes.json``.

Not confirmed on a printer of FilamentHub's own: the whole module. Not
confirmed by any source: the meaning of print status codes 23-26, which [link]
names for another device family and which are read here as a running job.

The plugin sends a printer only read commands: 1 (attributes), 0 (status) and,
on firmware that supports a multi-colour unit, 324 (the CANVAS slots). A
command the firmware does not know may stop its daemon, so nothing else is
sent.

This file holds definitions only: no I/O, no module state and no reference
to the plugin. ``build_package.py`` merges it into the single installable
plugin file, where every name below becomes a plugin global.
"""

import json
import re

SDCP_PROVIDER = "sdcp"
SDCP_PORT = 3030
SDCP_PATH = "/websocket"
SDCP_CMD_STATUS = 0
SDCP_CMD_ATTRIBUTES = 1
SDCP_CMD_CANVAS = 324
SDCP_IDENTITY_KIND = "sdcp_mainboard"
SDCP_CAPABILITIES = ("read", "presence")
# OrcaSlicer host types under which SDCP printers are found. ElegooLink is the
# right one; production profiles also show Centauri Carbon printers set up as
# Moonraker or OctoPrint.
SDCP_HOST_TYPES = ("elegoolink", "moonraker", "octoprint")
SDCP_ROUTE_KNOWN = "known"
SDCP_ROUTE_PROBE = "probe"
_SDCP_MAINBOARD_ID = re.compile(r"[0-9a-f]{8,64}")
_SDCP_FIRMWARE = re.compile(r"[vV]?(\d+)\.(\d+)")
_SDCP_JOB_STATES = {"printing", "paused", "preparing", "finished", "failed"}
_SDCP_RUNNING_STATES = {"printing", "paused", "preparing"}
# Machine status ([link] l. 19-30): 0 idle, 1 printing, 2 file transfer; the
# rest is calibration, homing or filament handling outside a job.
_SDCP_MACHINE_IDLE = 0
_SDCP_MACHINE_PRINTING = 1
_SDCP_MACHINE_FILE_TRANSFER = 2
# PrintInfo.Status of FDM firmware while the machine prints ([link] l. 35-61).
_SDCP_PRINT_STATES = {
    0: "printing", 1: "preparing", 5: "paused", 6: "paused", 7: "failed", 8: "failed",
    9: "finished", 10: "preparing", 11: "preparing", 12: "printing", 13: "printing",
    14: "failed", 15: "preparing", 16: "preparing", 17: "preparing", 18: "printing",
    19: "preparing", 20: "preparing", 21: "printing", 22: "printing",
}


def sdcp_profile_route(host_type, printer_model):
    """How an OrcaSlicer profile reaches SDCP: ``"known"``, ``"probe"`` or ``""``.

    A Centauri Carbon set up as ElegooLink speaks SDCP, as OrcaSlicer assumes
    ([orca] l. 136-146, 465-484). The same model under another host type, and
    an ElegooLink profile of unknown model, may speak SDCP or run Moonraker:
    the printer's answer decides. A model ending in "2" is the Carbon 2.
    """
    host_type = str(host_type or "").strip().lower()
    model = str(printer_model or "")
    if host_type not in SDCP_HOST_TYPES:
        return ""
    centauri = model.startswith("Elegoo Centauri")
    if centauri and model.rstrip().endswith("2"):
        return ""
    if centauri and host_type == "elegoolink":
        return SDCP_ROUTE_KNOWN
    if centauri or host_type == "elegoolink":
        return SDCP_ROUTE_PROBE
    return ""


def sdcp_mainboard_id(value):
    """A printer's ``MainboardID`` in lower case, or ``""``."""
    text = value.strip().lower() if isinstance(value, str) else ""
    return text if _SDCP_MAINBOARD_ID.fullmatch(text) and text.strip("0") else ""


def sdcp_request(command, request_id, timestamp_ms, mainboard_id=""):
    """One SDCP request in OrcaSlicer's envelope ([orca] l. 1121-1137).

    OrcaSlicer leaves ``MainboardID`` empty; Elegoo's library fills it in
    ([link] l. 88), as this plugin does once the attributes have named it.
    """
    return json.dumps({
        "Id": "",
        "Data": {
            "Cmd": command,
            "Data": {},
            "RequestID": request_id,
            "MainboardID": mainboard_id,
            "TimeStamp": timestamp_ms,
            "From": 1,
        },
    }, separators=(",", ":"))


def sdcp_message(payload):
    """One received JSON object, or None for anything else."""
    try:
        message = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
    except (AttributeError, UnicodeDecodeError, ValueError):
        return None
    return message if isinstance(message, dict) else None


def sdcp_topic(message):
    """The topic kind of a message: ``"status"``, ``"attributes"``, ``"response"`` or ``""``."""
    topic = str(message.get("Topic") or "") if isinstance(message, dict) else ""
    kind = topic.split("/", 2)[1] if topic.startswith("sdcp/") and topic.count("/") >= 2 else ""
    return kind if kind in ("status", "attributes", "response") else ""


def sdcp_status(message):
    """The ``Status`` object of a status message, or None."""
    status = message.get("Status") if isinstance(message, dict) else None
    return status if isinstance(status, dict) else None


def sdcp_attributes(message):
    """The ``Attributes`` object of an attributes message, or None."""
    attributes = message.get("Attributes") if isinstance(message, dict) else None
    return attributes if isinstance(attributes, dict) else None


def sdcp_response(message, request_id):
    """The answer to one request, if it succeeded: the ``Data.Data`` object, else None."""
    data = message.get("Data") if isinstance(message, dict) else None
    if not isinstance(data, dict) or data.get("RequestID") != request_id:
        return None
    result = data.get("Data")
    return result if isinstance(result, dict) and result.get("Ack") == 0 else None


def sdcp_canvas_supported(attributes):
    """Whether the firmware answers command 324: version 1.2 or later ([link] l. 877-895)."""
    version = attributes.get("FirmwareVersion") if isinstance(attributes, dict) else None
    match = _SDCP_FIRMWARE.match(version.strip()) if isinstance(version, str) else None
    if not match:
        return False
    major, minor = int(match.group(1)), int(match.group(2))
    return major > 1 or (major == 1 and minor > 1)


def _sdcp_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number == number and abs(number) != float("inf") else None


def _sdcp_integer(value):
    number = _sdcp_number(value)
    return int(number) if number is not None and number == int(number) else None


def _sdcp_machine_status(status):
    """The machine status that matters: a file transfer gives way to the next one."""
    codes = status.get("CurrentStatus")
    if not isinstance(codes, list):
        return None
    codes = [code for code in map(_sdcp_integer, codes) if code is not None]
    if not codes:
        return _SDCP_MACHINE_IDLE
    if codes[0] == _SDCP_MACHINE_FILE_TRANSFER and len(codes) > 1:
        return codes[1]
    return codes[0]


def sdcp_printer(status):
    """Normalize an SDCP status into the provider-neutral bridge contract."""
    machine = _sdcp_machine_status(status)
    info = status.get("PrintInfo") if isinstance(status.get("PrintInfo"), dict) else {}
    filename = info.get("Filename") if isinstance(info.get("Filename"), str) else ""
    job = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()[:300]
    if machine is None:
        state = "unknown"
    elif machine == _SDCP_MACHINE_IDLE:
        state = "idle"
    elif machine == _SDCP_MACHINE_PRINTING:
        state = _SDCP_PRINT_STATES.get(_sdcp_integer(info.get("Status")), "printing")
    else:
        # Calibrating, homing or handling filament: part of a job only if one is named.
        state = "preparing" if job else "unknown"
    if not job and state in _SDCP_JOB_STATES:
        # An idle printer keeps the last job's totals without its file name.
        state = "unknown"
    printer = {"state": state}
    if job and state in _SDCP_JOB_STATES:
        printer["job_name"] = job
        progress = _sdcp_number(info.get("Progress"))
        if progress is not None and 0 <= progress <= 100:
            printer["progress_percent"] = round(progress)
        total, ticks = _sdcp_number(info.get("TotalTicks")), _sdcp_number(info.get("CurrentTicks"))
        if state in _SDCP_RUNNING_STATES and total is not None and ticks is not None and total > 0:
            # FDM firmware counts seconds ([ha]).
            remaining = max(0.0, total - ticks)
            if remaining <= 2_592_000:
                printer["remaining_seconds"] = int(remaining)
        layer, layers = _sdcp_integer(info.get("CurrentLayer")), _sdcp_integer(info.get("TotalLayer"))
        if layer is not None and 0 <= layer <= 10_000_000:
            printer["current_layer"] = layer
        if layers is not None and 0 < layers <= 10_000_000:
            printer["total_layers"] = layers
    for key, field, low, high in (
        ("nozzle_temperature", "TempOfNozzle", -50, 600),
        ("nozzle_target_temperature", "TempTargetNozzle", 0, 600),
        ("bed_temperature", "TempOfHotbed", -50, 250),
        ("bed_target_temperature", "TempTargetHotbed", 0, 250),
        ("chamber_temperature", "TempOfBox", -50, 150),
    ):
        number = _sdcp_number(status.get(field))
        if number is not None and low <= number <= high:
            printer[key] = round(number, 1)
    return printer

