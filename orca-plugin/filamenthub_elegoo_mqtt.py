"""Elegoo's MQTT printer API for the FilamentHub OrcaSlicer plugin.

The Centauri Carbon 2 does not speak SDCP. It runs an MQTT broker and answers
a JSON API on topics named after its serial number. Elegoo's own LAN library
keeps it as a separate adapter from SDCP, and so does this plugin.

Sources. Every field this module reads is named in at least one of them; an
item marked "not confirmed" is not.

[link]  elegooofficial/elegoo-link @ ec2d2269 (Elegoo's own LAN library):
        ``src/lan/adapters/elegoo_fdm_cc2/elegoo_fdm_cc2_protocol.cpp``: client
        id ``1_PC_<4 digits>`` and request id ``<client>_req`` (l. 15-17), the
        broker on TCP 1883 (l. 25), the serial number from
        ``GET /system/info`` with the access code as ``X-Token`` header and
        query, default "123456" (l. 68-101), user ``elegoo`` with the access
        code as password (l. 150-186), the topics ``api_response``,
        ``api_status``, ``register_response``, ``api_request`` and
        ``api_register`` (l. 198-232), and the register answer with
        ``client_id`` and ``error`` "ok" or "too many clients" (l. 248-290);
        ``src/lan/adapters/elegoo_fdm_cc2/elegoo_fdm_cc2_message_adapter.cpp``:
        ``machine_status.status`` / ``sub_status`` (l. 639-960),
        ``print_status`` with ``filename``, ``total_layer``, ``current_layer``
        and ``remaining_time_sec`` (l. 973-985), ``extruder``, ``heater_bed``
        and ``ztemperature_sensor`` with ``temperature`` / ``target``
        (l. 1004-1029), and the methods 1002 status and 2005 CANVAS
        (l. 1391-1423).
[orca]  OrcaSlicer/OrcaSlicer @ 7cdc829a: ``src/slic3r/Utils/ElegooLink.cpp``
        ``classify_printer_model`` (l. 136-146) and the default access code
        (l. 82); ``resources/web/elegoolink/lan_service_web/index.html``
        (Elegoo's bundled panel): requests ``{"method", "id"}`` and the method
        ``GetMonoFilamentInfo`` = 1061 answered by ``mono_filament_info``.
[tiger] TigerTag-Project/TigerTag-Studio-Manager issue #41 (2026-10-08): the
        broker on 1883 reached from another client.

Not confirmed on a printer of FilamentHub's own: the whole module. Not
confirmed by a source: reading power-loss recovery (machine status 15) as a
paused job; it is the plugin's interpretation of a job waiting to resume.

The plugin only reads: it registers as a client and asks for methods 1002,
2005 and 1061, nothing else.

This file holds definitions only: no I/O, no module state and no reference
to the plugin. ``build_package.py`` merges it into the single installable
plugin file, where every name below becomes a plugin global.
"""

import json
import re

ELEGOO_MQTT_PROVIDER = "elegoo_mqtt"
ELEGOO_MQTT_HTTP_PORT = 80
ELEGOO_MQTT_PORT = 1883
ELEGOO_MQTT_USERNAME = "elegoo"
ELEGOO_MQTT_DEFAULT_ACCESS_CODE = "123456"
ELEGOO_MQTT_STATUS = 1002
ELEGOO_MQTT_CANVAS = 2005
ELEGOO_MQTT_MONO_FILAMENT = 1061
ELEGOO_MQTT_IDENTITY_KIND = "elegoo_serial"
ELEGOO_MQTT_CAPABILITIES = ("read", "presence")
# Host types a Carbon 2 profile is found under; ElegooLink is the right one.
ELEGOO_MQTT_HOST_TYPES = ("elegoolink", "moonraker", "octoprint")
_ELEGOO_MQTT_SERIAL = re.compile(r"[A-Za-z0-9_-]{4,64}")
_ELEGOO_MQTT_JOB_STATES = {"printing", "paused", "preparing", "finished", "failed"}
_ELEGOO_MQTT_RUNNING_STATES = {"printing", "paused", "preparing"}
# machine_status.sub_status while the status is 2, printing ([link] l. 653-760).
_ELEGOO_MQTT_PRINT_SUBSTATES = {
    1081: "preparing", 1082: "preparing", 1086: "preparing",
    1045: "preparing", 1096: "preparing", 1405: "preparing", 1906: "preparing",
    2801: "preparing", 2802: "preparing", 2901: "preparing", 2902: "preparing",
    2501: "paused", 2502: "paused", 2505: "paused",
    2503: "failed", 2504: "failed", 2077: "finished",
}


def elegoo_mqtt_profile(host_type, printer_model):
    """Whether an OrcaSlicer profile is a Centauri Carbon 2 ([orca] l. 136-146)."""
    model = str(printer_model or "")
    return (
        str(host_type or "").strip().lower() in ELEGOO_MQTT_HOST_TYPES
        and model.startswith("Elegoo Centauri")
        and model.rstrip().endswith("2")
    )


def elegoo_mqtt_access_code(api_key):
    """The access code from the connection's API key, or ``""`` if it cannot be one."""
    code = str(api_key or "").strip()
    if not code:
        return ELEGOO_MQTT_DEFAULT_ACCESS_CODE
    if len(code) > 64 or any(ord(ch) < 33 or ord(ch) > 126 for ch in code):
        return ""
    return code


def elegoo_mqtt_serial(value):
    """A serial number, or ``""``; it is a topic segment, so strictly checked."""
    text = value.strip() if isinstance(value, str) else ""
    return text if _ELEGOO_MQTT_SERIAL.fullmatch(text) and text.strip("0") else ""


def elegoo_mqtt_system_info(body):
    """The serial number in a ``/system/info`` answer: ``(serial, failure)``."""
    try:
        answer = json.loads(body.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, ValueError):
        return "", "invalid"
    if not isinstance(answer, dict):
        return "", "invalid"
    code = answer.get("error_code")
    if code == 1000:
        # The printer refused the access code.
        return "", "auth"
    if code != 0:
        return "", "invalid"
    info = answer.get("system_info")
    serial = elegoo_mqtt_serial(info.get("sn")) if isinstance(info, dict) else ""
    return (serial, None) if serial else ("", "identity")


def elegoo_mqtt_topics(serial, client_id):
    base = "elegoo/%s/" % serial
    request_id = client_id + "_req"
    return {
        "register": base + "api_register",
        "register_response": base + request_id + "/register_response",
        "request": base + client_id + "/api_request",
        "response": base + client_id + "/api_response",
    }


def elegoo_mqtt_register_payload(client_id):
    return json.dumps(
        {"client_id": client_id, "request_id": client_id + "_req"}, separators=(",", ":")
    )


def elegoo_mqtt_register_result(message, client_id):
    """``"ok"``, ``"busy"`` or ``"refused"`` for a register answer to this client, else None."""
    if not isinstance(message, dict) or message.get("client_id") != client_id:
        return None
    error = message.get("error")
    if error == "ok":
        return "ok"
    return "busy" if isinstance(error, str) and "too many clients" in error else "refused"


def elegoo_mqtt_request(request_id, method):
    """A read request the way Elegoo's panel sends one: no parameters."""
    return json.dumps({"method": method, "id": request_id}, separators=(",", ":"))


def elegoo_mqtt_message(payload):
    """One received JSON object, or None for anything else."""
    try:
        message = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
    except (AttributeError, UnicodeDecodeError, ValueError):
        return None
    return message if isinstance(message, dict) else None


def _elegoo_mqtt_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number == number and abs(number) != float("inf") else None


def _elegoo_mqtt_integer(value):
    number = _elegoo_mqtt_number(value)
    return int(number) if number is not None and number == int(number) else None


def _elegoo_mqtt_object(result, key):
    value = result.get(key) if isinstance(result, dict) else None
    return value if isinstance(value, dict) else {}


def elegoo_mqtt_printer(result):
    """Normalize a status answer (method 1002) into the bridge contract."""
    machine = _elegoo_mqtt_object(result, "machine_status")
    job_status = _elegoo_mqtt_object(result, "print_status")
    code = _elegoo_mqtt_integer(machine.get("status"))
    filename = job_status.get("filename") if isinstance(job_status.get("filename"), str) else ""
    job = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()[:300]
    if code == 1:
        state = "idle"
    elif code == 2:
        state = _ELEGOO_MQTT_PRINT_SUBSTATES.get(
            _elegoo_mqtt_integer(machine.get("sub_status")), "printing"
        )
    elif code == 15:
        # Power-loss recovery: the job waits to be resumed.
        state = "paused"
    elif code == 14:
        # Emergency stop.
        state = "failed"
    else:
        state = "unknown"
    if not job and state in _ELEGOO_MQTT_JOB_STATES:
        state = "unknown"
    printer = {"state": state}
    if job and state in _ELEGOO_MQTT_JOB_STATES:
        printer["job_name"] = job
        progress = _elegoo_mqtt_number(machine.get("progress"))
        if progress is not None and 0 <= progress <= 100:
            printer["progress_percent"] = round(progress)
        remaining = _elegoo_mqtt_number(job_status.get("remaining_time_sec"))
        if state in _ELEGOO_MQTT_RUNNING_STATES and remaining is not None and 0 <= remaining <= 2_592_000:
            printer["remaining_seconds"] = int(remaining)
        layer = _elegoo_mqtt_integer(job_status.get("current_layer"))
        layers = _elegoo_mqtt_integer(job_status.get("total_layer"))
        if layer is not None and 0 <= layer <= 10_000_000:
            printer["current_layer"] = layer
        if layers is not None and 0 < layers <= 10_000_000:
            printer["total_layers"] = layers
    for key, source, field, low, high in (
        ("nozzle_temperature", "extruder", "temperature", -50, 600),
        ("nozzle_target_temperature", "extruder", "target", 0, 600),
        ("bed_temperature", "heater_bed", "temperature", -50, 250),
        ("bed_target_temperature", "heater_bed", "target", 0, 250),
        ("chamber_temperature", "ztemperature_sensor", "temperature", -50, 150),
    ):
        number = _elegoo_mqtt_number(_elegoo_mqtt_object(result, source).get(field))
        if number is not None and low <= number <= high:
            printer[key] = round(number, 1)
    return printer


def elegoo_mqtt_canvas_info(result):
    """The ``canvas_info`` object of a CANVAS answer (method 2005), or None."""
    info = result.get("canvas_info") if isinstance(result, dict) else None
    return info if isinstance(info, dict) else None


def elegoo_mqtt_mono_filament(result):
    """The ``mono_filament_info`` object of a single-spool answer (method 1061), or None."""
    info = result.get("mono_filament_info") if isinstance(result, dict) else None
    return info if isinstance(info, dict) else None
