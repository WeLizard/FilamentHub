"""Anycubic's LAN protocol for the FilamentHub OrcaSlicer plugin.

The Kobra 3, Kobra S1, Kobra X and their Max / V2 variants are not Moonraker
printers. With "LAN mode" turned on at the printer's screen they answer a
signed handshake over HTTP on port 18910, hand out the login of their own MQTT
broker, and report over that broker (TLS, port 9883) on topics named after the
model and the device. No root and no other firmware is needed. OrcaSlicer has
no code of its own for them: their profiles send prints through the
OctoPrint-compatible service on port 80, which says nothing about state or
slots.

Sources. Every field this module reads is named in at least one of them; the
research note ``.docs/audits/research/ANYCUBIC_PROTOCOLS_2026_11_27.md`` keeps
the line references.

[ha]    chrisfore/anycubic_ha_local @ 65d5bd91, a Home Assistant integration
        whose protocol was captured from a Kobra S1 Max (fw 2.6.9.6) and
        confirmed by users on a Kobra 3, Kobra 4 and Kobra X:
        ``anycubic_local/handshake.py`` (the handshake), ``mqtt.py`` (TLS
        without certificate checks, login, subscription, ``getInfo``),
        ``const.py`` (topics, phases), ``models.py`` (``info``,
        ``multiColorBox`` and ``extfilbox`` fields),
        ``research/PROTOCOL-VALIDATED.md``.
[kc]    rvanderp3/kobra-connect @ 3edba246: ``kobra_connect/handshake.py``,
        the same handshake written independently;
        ``moonraker_bridge/state.py``: ``remain_time`` is in minutes.
[ian]   ianloic/anycubic-orca-plugin @ 458eee79: ``anycubic_lan.py``, ACE
        slots numbered box * 4 + slot, a slot loaded when its status is 4 or
        5 or it names a material.
[orca]  OrcaSlicer/OrcaSlicer @ a0663e6e: every Kobra 3 / S1 / X profile in
        ``resources/profiles/Anycubic/machine`` sets host type ``octoprint``.

Not confirmed on a printer of FilamentHub's own: the whole module. Not
confirmed by a source: the mapping of the printer's job phases to
FilamentHub's states (the plugin's reading of the phase names), and the slot
numbering of the Kobra X's built-in unit.

The plugin only reads: it asks for ``info``, the ACE units (``getInfo``) and
the spool holder (``reportInfo``), nothing else.

The handshake's answer is sealed with AES-128-CBC. OrcaSlicer's Python has no
cryptography package, so the block cipher (decryption only) is written here
from FIPS-197.

This file holds definitions only: no I/O, no module state and no reference
to the plugin. ``build_package.py`` merges it into the single installable
plugin file, where every name below becomes a plugin global.
"""

import codecs
import hashlib
import json
import math
import re
import urllib.parse

ANYCUBIC_PROVIDER = "anycubic"
ANYCUBIC_IDENTITY_KIND = "anycubic_serial"
ANYCUBIC_CAPABILITIES = ("read", "presence")
ANYCUBIC_INFO_PORT = 18910
ANYCUBIC_TOPIC_PREFIX = "anycubic/anycubicCloud/v1"
ANYCUBIC_SLOTS_PER_BOX = 4
ANYCUBIC_MAX_BOXES = 4
# The spool holder used without an ACE unit, numbered like the external
# holder of other printers on FilamentHub.
ANYCUBIC_EXTERNAL_INDEX = 255
ANYCUBIC_MAX_MESSAGE_BYTES = 1024 * 1024
# What the plugin asks the printer for: report type and the action it answers.
# The ACE units answer only "getInfo" and the spool holder only "reportInfo".
ANYCUBIC_QUERIES = (
    ("info", "query"),
    ("multiColorBox", "getInfo"),
    ("extfilbox", "reportInfo"),
)
# Model numbers of the generation that speaks this protocol, as /info gives
# them. Only shown to people; an unlisted number that completes the
# handshake is read all the same.
ANYCUBIC_MODELS = {
    "20024": "Anycubic Kobra 3",
    "20025": "Anycubic Kobra S1",
    "20026": "Anycubic Kobra 3 Max",
    "20027": "Anycubic Kobra 3 V2",
    "20028": "Anycubic Kobra 4",
    "20029": "Anycubic Kobra S1 Max",
    "20030": "Anycubic Kobra X",
}
# OrcaSlicer profiles of that generation, by printer_model. People choose
# Octo/Klipper, Moonraker or something else as the host type, so the model
# says more than the type does.
_ANYCUBIC_PROFILE_MODEL = re.compile(r"anycubic kobra (?:3|s1|x|4)(?: .*)?", re.IGNORECASE)
_ANYCUBIC_SERIAL = re.compile(r"[A-Za-z0-9_-]{4,64}")
_ANYCUBIC_DEVICE_ID = re.compile(r"[A-Za-z0-9_-]{4,128}")
_ANYCUBIC_MODEL_ID = re.compile(r"[0-9]{1,8}")
_ANYCUBIC_TOKEN = re.compile(r"[\x21-\x7e]{32,256}")
_ANYCUBIC_BROKER = re.compile(r"mqtts?://[^/:\s]+:([0-9]{1,5})/?")
_ANYCUBIC_BASE64 = re.compile(r"(?:[A-Za-z0-9+/]{4}){1,4096}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?")
_ANYCUBIC_PREPARING = frozenset({"preheating", "auto_leveling", "vibrating", "flow_calibrating"})
_ANYCUBIC_RUNNING = frozenset({"printing", "resuming", "resumed"})
_ANYCUBIC_PAUSED = frozenset({"pausing", "paused"})
# "stoped" is how the firmware spells it.
_ANYCUBIC_STOPPED = frozenset({"stopping", "stoped", "stopped"})


def anycubic_profile(printer_model):
    """Whether an OrcaSlicer printer_model belongs to the Kobra 3 / S1 / X generation."""
    return isinstance(printer_model, str) and bool(
        _ANYCUBIC_PROFILE_MODEL.fullmatch(printer_model.strip())
    )


def _anycubic_host_for_url(address):
    return "[%s]" % address if ":" in address else address


def anycubic_info_url(address):
    return "http://%s:%d/info" % (_anycubic_host_for_url(address), ANYCUBIC_INFO_PORT)


def anycubic_serial(value):
    return value if isinstance(value, str) and _ANYCUBIC_SERIAL.fullmatch(value) else ""


def anycubic_info(body):
    """Read the printer's ``/info`` answer: ``(info, failure)``.

    ``failure`` is ``"lan_mode"`` when LAN mode is off (``info`` then holds
    only the serial number), ``"unsupported"`` for a device that does not
    offer this handshake (the older Kobra 2 firmware) and ``"invalid"`` for an
    answer that is not a printer's. ``info`` keeps only what the handshake
    needs and what identifies the printer.
    """
    if not isinstance(body, dict):
        return None, "invalid"
    if body.get("ctrlType") == "cloud":
        # Still says which printer this is, so a linked one is told apart.
        return {"serial": anycubic_serial(body.get("cn"))}, "lan_mode"
    token = body.get("token")
    supplied = body.get("ctrlInfoUrl")
    model_id = body.get("modelId")
    if not token or not supplied or model_id in (None, ""):
        return None, "unsupported"
    if isinstance(model_id, int) and not isinstance(model_id, bool):
        model_id = str(model_id)
    serial = anycubic_serial(body.get("cn"))
    if not (
        isinstance(token, str) and _ANYCUBIC_TOKEN.fullmatch(token)
        and isinstance(model_id, str) and _ANYCUBIC_MODEL_ID.fullmatch(model_id)
        and isinstance(supplied, str) and len(supplied) <= 500
        and serial
    ):
        return None, "invalid"
    try:
        parts = urllib.parse.urlsplit(supplied)
        port = parts.port
    except ValueError:
        return None, "invalid"
    if parts.scheme not in ("http", "") or (port is not None and not 0 < port < 65536):
        return None, "invalid"
    path = parts.path if parts.path.startswith("/") else "/" + parts.path
    if any(ch in path for ch in "\\\r\n #"):
        return None, "invalid"
    name = body.get("modelName")
    return {
        "token": token,
        # Only where on the printer the next request goes: the host is always
        # the address the first request reached, so a device answering on
        # 18910 cannot send the plugin to another one.
        "ctrl_port": port or ANYCUBIC_INFO_PORT,
        "ctrl_path": path,
        "ctrl_query": parts.query,
        "model_id": model_id,
        "serial": serial,
        "model_name": (
            name.strip()[:120] if isinstance(name, str) and name.strip()
            else ANYCUBIC_MODELS.get(model_id, "Anycubic")
        ),
    }, None


def anycubic_sign(token, timestamp_ms, nonce):
    """``md5(md5(token[:16]) + timestamp + nonce)`` in hex, as the printer checks it."""
    first = hashlib.md5(token[:16].encode("utf-8")).hexdigest()
    return hashlib.md5((first + str(timestamp_ms) + nonce).encode("utf-8")).hexdigest()


def anycubic_ctrl_url(address, info, timestamp_ms, nonce, client_id):
    """The signed request that asks the printer for its broker login."""
    query = urllib.parse.urlencode({
        "ts": timestamp_ms,
        "nonce": nonce,
        "sign": anycubic_sign(info["token"], timestamp_ms, nonce),
        "did": client_id,
    })
    if info.get("ctrl_query"):
        query = info["ctrl_query"] + "&" + query
    return "http://%s:%d%s?%s" % (
        _anycubic_host_for_url(address), info["ctrl_port"], info["ctrl_path"], query
    )


# --------------------------------------------------------------------------- #
# AES-128 decryption (FIPS-197), for the handshake's sealed answer only
# --------------------------------------------------------------------------- #


def _anycubic_xtime(value):
    value <<= 1
    return (value ^ 0x11B) if value & 0x100 else value


def _anycubic_gmul(a, b):
    result = 0
    while b:
        if b & 1:
            result ^= a
        a = _anycubic_xtime(a)
        b >>= 1
    return result


def _anycubic_sbox():
    """The S-box: the multiplicative inverse in GF(2^8), then the affine map."""
    box = []
    for value in range(256):
        inverse = 0
        if value:
            inverse = next(c for c in range(1, 256) if _anycubic_gmul(value, c) == 1)
        out = inverse
        for shift in range(1, 5):
            out ^= ((inverse << shift) | (inverse >> (8 - shift))) & 0xFF
        box.append(out ^ 0x63)
    return bytes(box)


_ANYCUBIC_SBOX = _anycubic_sbox()
_ANYCUBIC_INV_SBOX = bytes(_ANYCUBIC_SBOX.index(value) for value in range(256))
_ANYCUBIC_MUL = {
    factor: bytes(_anycubic_gmul(value, factor) for value in range(256))
    for factor in (9, 11, 13, 14)
}


def _anycubic_round_keys(key):
    """The eleven round keys of AES-128, each as 16 bytes."""
    words = [list(key[index:index + 4]) for index in range(0, 16, 4)]
    rcon = 1
    for index in range(4, 44):
        word = list(words[index - 1])
        if index % 4 == 0:
            word = [_ANYCUBIC_SBOX[byte] for byte in word[1:] + word[:1]]
            word[0] ^= rcon
            rcon = _anycubic_xtime(rcon)
        words.append([a ^ b for a, b in zip(words[index - 4], word)])
    return [bytes(sum(words[round_ * 4:round_ * 4 + 4], [])) for round_ in range(11)]


def _anycubic_decrypt_block(block, round_keys):
    state = [a ^ b for a, b in zip(block, round_keys[10])]
    m9, m11, m13, m14 = (_ANYCUBIC_MUL[factor] for factor in (9, 11, 13, 14))
    for round_ in range(9, -1, -1):
        # InvShiftRows: row r of every column moves right by r columns.
        state = [state[(index + 4 * (index % 4) * 3) % 16] for index in range(16)]
        state = [_ANYCUBIC_INV_SBOX[byte] for byte in state]
        state = [a ^ b for a, b in zip(state, round_keys[round_])]
        if round_ == 0:
            break
        mixed = []
        for column in range(4):
            a0, a1, a2, a3 = state[column * 4:column * 4 + 4]
            mixed += [
                m14[a0] ^ m11[a1] ^ m13[a2] ^ m9[a3],
                m9[a0] ^ m14[a1] ^ m11[a2] ^ m13[a3],
                m13[a0] ^ m9[a1] ^ m14[a2] ^ m11[a3],
                m11[a0] ^ m13[a1] ^ m9[a2] ^ m14[a3],
            ]
        state = mixed
    return bytes(state)


def anycubic_aes_cbc_decrypt(key, iv, data):
    """Decrypt AES-128-CBC and strip PKCS#7 padding; ``None`` if it does not fit."""
    if len(key) != 16 or len(iv) != 16 or not data or len(data) % 16:
        return None
    round_keys = _anycubic_round_keys(key)
    previous = iv
    plain = bytearray()
    for offset in range(0, len(data), 16):
        block = data[offset:offset + 16]
        plain += bytes(
            a ^ b for a, b in zip(_anycubic_decrypt_block(block, round_keys), previous)
        )
        previous = block
    pad = plain[-1]
    if not 1 <= pad <= 16 or plain[-pad:] != bytes([pad]) * pad:
        return None
    return bytes(plain[:-pad])


def anycubic_session(body, info):
    """Open the printer's answer to the signed request: ``(session, failure)``.

    ``session`` holds the broker's port and login and the device id the
    topics are named after. The broker's host is not taken: it is the printer
    itself, reached at the address the handshake went to.
    """
    if not isinstance(body, dict):
        return None, "invalid"
    if body.get("code") != 200:
        return None, "refused"
    sealed = body.get("data")
    if not (
        isinstance(sealed, dict)
        and isinstance(sealed.get("info"), str)
        and isinstance(sealed.get("token"), str)
    ):
        return None, "invalid"
    if not _ANYCUBIC_BASE64.fullmatch(sealed["info"]):
        return None, "invalid"
    data = codecs.decode(sealed["info"].encode("ascii"), "base64")
    iv = sealed["token"].encode("utf-8")[:16].ljust(16, b"\0")
    plain = anycubic_aes_cbc_decrypt(info["token"][16:32].encode("utf-8"), iv, data)
    try:
        opened = json.loads(plain.decode("utf-8")) if plain is not None else None
    except (UnicodeDecodeError, ValueError):
        opened = None
    if not isinstance(opened, dict):
        return None, "invalid"
    broker = opened.get("broker")
    match = _ANYCUBIC_BROKER.fullmatch(broker) if isinstance(broker, str) else None
    username, password = opened.get("username"), opened.get("password")
    device_id = opened.get("deviceId")
    port = int(match.group(1)) if match else 0
    if not (
        0 < port < 65536
        and isinstance(username, str) and 0 < len(username) <= 256
        and isinstance(password, str) and 0 < len(password) <= 256
        and isinstance(device_id, str) and _ANYCUBIC_DEVICE_ID.fullmatch(device_id)
    ):
        return None, "invalid"
    return {
        "port": port, "username": username, "password": password, "device_id": device_id,
    }, None


# --------------------------------------------------------------------------- #
# MQTT topics and reports
# --------------------------------------------------------------------------- #


def anycubic_report_filter(model_id, device_id):
    """The subscription that receives every report of one printer."""
    return "%s/printer/public/%s/%s/#" % (ANYCUBIC_TOPIC_PREFIX, model_id, device_id)


def anycubic_query(model_id, device_id, report_type, action, message_id, timestamp_ms):
    """``(topic, payload)`` of one read-only request."""
    topic = "%s/web/printer/%s/%s/%s" % (ANYCUBIC_TOPIC_PREFIX, model_id, device_id, report_type)
    payload = json.dumps({
        "type": report_type, "action": action, "timestamp": timestamp_ms,
        "msgid": message_id, "data": None,
    }, separators=(",", ":"))
    return topic, payload


def anycubic_report(topic, payload, model_id, device_id):
    """``(report_type, data)`` of a report from this printer, or ``None``.

    The type is read from the topic and the message, never from ``action``,
    which varies from report to report. A message the plugin sent itself, or
    an answer that carries no data, is not a report.
    """
    prefix = "%s/printer/public/%s/%s/" % (ANYCUBIC_TOPIC_PREFIX, model_id, device_id)
    if not isinstance(topic, str) or not topic.startswith(prefix):
        return None
    parts = topic[len(prefix):].split("/")
    if len(parts) != 2 or parts[1] != "report" or len(payload) > ANYCUBIC_MAX_MESSAGE_BYTES:
        return None
    try:
        message = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(message, dict):
        return None
    report_type = message.get("type") if isinstance(message.get("type"), str) else parts[0]
    data = message.get("data")
    if report_type != parts[0] or not isinstance(data, dict):
        return None
    return report_type, data


def anycubic_merge_boxes(previous, data):
    """Fold one ``multiColorBox`` report into the ones before it.

    A report may carry one slot or all of them, so units are kept by id and
    slots by index; a later value replaces an earlier one, a missing value
    leaves it as it was.
    """
    units = {}
    for source in (previous, data):
        listed = source.get("multi_color_box") if isinstance(source, dict) else None
        for unit in listed if isinstance(listed, list) else []:
            unit_id = _anycubic_integer(unit.get("id")) if isinstance(unit, dict) else None
            if unit_id is None:
                continue
            kept = units.setdefault(unit_id, {"id": unit_id, "slots": {}})
            for key, value in unit.items():
                if key not in ("id", "slots") and value is not None:
                    kept[key] = value
            for slot in unit.get("slots") if isinstance(unit.get("slots"), list) else []:
                index = _anycubic_integer(slot.get("index")) if isinstance(slot, dict) else None
                if index is not None:
                    kept["slots"][index] = slot
    return {"multi_color_box": [
        dict(unit, slots=[unit["slots"][index] for index in sorted(unit["slots"])])
        for _unit_id, unit in sorted(units.items())
    ]}


def _anycubic_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _anycubic_integer(value):
    number = _anycubic_number(value)
    return int(number) if number is not None and number == int(number) else None


def _anycubic_text(value, maximum):
    return value.strip()[:maximum] if isinstance(value, str) else ""


def _anycubic_job_name(value):
    return _anycubic_text(value, 1000).replace("\\", "/").rsplit("/", 1)[-1].strip()[:300]


def _anycubic_state(raw_state, project):
    phase = _anycubic_text(project.get("state"), 40).lower()
    if raw_state == "free":
        return "finished" if phase == "finished" and project.get("_last") else "idle"
    if phase in _ANYCUBIC_PREPARING:
        return "preparing"
    if phase in _ANYCUBIC_RUNNING:
        return "paused" if _anycubic_integer(project.get("pause")) == 1 else "printing"
    if phase in _ANYCUBIC_PAUSED:
        return "paused"
    if phase in _ANYCUBIC_STOPPED:
        return "failed"
    if phase == "finished":
        return "finished"
    return "unknown"


def anycubic_printer(info):
    """Normalize an ``info`` report into the provider-neutral bridge contract."""
    if not isinstance(info, dict):
        return {"state": "unknown"}
    project = info.get("project")
    if isinstance(project, dict):
        project = dict(project)
    elif isinstance(info.get("last_project"), dict):
        project = dict(info["last_project"], _last=True)
    else:
        project = {}
    raw_state = _anycubic_text(info.get("state"), 20).lower()
    state = _anycubic_state(raw_state, project) if raw_state in ("free", "busy") else "unknown"
    printer: dict = {"state": state}
    job = _anycubic_job_name(project.get("filename"))
    if job and state in {"printing", "paused", "preparing", "finished", "failed"}:
        printer["job_name"] = job
        progress = _anycubic_number(project.get("progress"))
        if progress is not None and 0 <= progress <= 100:
            printer["progress_percent"] = round(progress)
        if state in {"printing", "paused", "preparing"}:
            # The printer counts the time left in minutes.
            remaining = _anycubic_number(project.get("remain_time"))
            if remaining is not None and 0 <= remaining * 60 <= 2_592_000:
                printer["remaining_seconds"] = int(remaining * 60)
        layer = _anycubic_integer(project.get("curr_layer"))
        total = _anycubic_integer(project.get("total_layers"))
        if layer is not None and 0 <= layer <= 10_000_000:
            printer["current_layer"] = layer
        if total is not None and 0 < total <= 10_000_000:
            printer["total_layers"] = total
    temperatures = info.get("temp")
    temperatures = temperatures if isinstance(temperatures, dict) else {}
    for key, source, low, high in (
        ("nozzle_temperature", "curr_nozzle_temp", -50, 600),
        ("nozzle_target_temperature", "target_nozzle_temp", 0, 600),
        ("bed_temperature", "curr_hotbed_temp", -50, 250),
        ("bed_target_temperature", "target_hotbed_temp", 0, 250),
        ("chamber_temperature", "curr_chamber_temp", -50, 150),
    ):
        value = _anycubic_number(temperatures.get(source))
        if value is not None and low <= value <= high:
            printer[key] = round(value, 1)
    return printer


def _anycubic_color(value):
    if not isinstance(value, list) or len(value) < 3:
        return None
    channels = [_anycubic_integer(item) for item in value[:3]]
    if any(channel is None or not 0 <= channel <= 255 for channel in channels):
        return None
    return "%02X%02X%02X" % tuple(channels)


def _anycubic_filled(slot, index, label, kind, present):
    slot_out: dict = {
        "provider_index": index,
        "label": label,
        "kind": kind,
        "present": present,
        "spool_identity_known": False,
    }
    if present:
        material = _anycubic_text(slot.get("type"), 80)
        if material:
            slot_out["material"] = material
        color = _anycubic_color(slot.get("color"))
        if color:
            slot_out["color_hex"] = color
    return slot_out


def _anycubic_box_slot(slot, index, label, loaded_slot):
    if not isinstance(slot, dict):
        return {
            "provider_index": index, "label": label, "kind": "slot",
            "present": None, "spool_identity_known": False,
        }
    status = _anycubic_integer(slot.get("status"))
    present = bool(_anycubic_text(slot.get("type"), 80)) or status in (4, 5)
    slot_out = _anycubic_filled(slot, index, label, "slot", present)
    if loaded_slot is not None:
        slot_out["active_feed"] = present and loaded_slot == _anycubic_integer(slot.get("index"))
    percent = _anycubic_integer(slot.get("consumables_percent"))
    if present and percent is not None and 0 <= percent <= 100:
        slot_out["remaining_percent"] = percent
    return slot_out


def anycubic_slots(boxes, holder=None):
    """Turn the ACE units and the spool holder into slots: ``(slots, complete)``.

    ``boxes`` is the data of a ``multiColorBox`` answer, ``holder`` that of an
    ``extfilbox`` one. An ACE unit has four slots, numbered unit * 4 + slot.
    ``complete`` says the answer named every slot of every unit it listed; a
    report that carries only the slots that changed is not complete.

    The holder's answer to a request is partial: it says ``loaded`` 0 with -1
    in both status fields even when a spool is in place. Then its presence is
    left unknown and only its material and colour are kept.
    """
    units = boxes.get("multi_color_box") if isinstance(boxes, dict) else None
    slots = []
    complete = isinstance(units, list) and bool(units)
    seen = set()
    for unit in (units if isinstance(units, list) else []):
        unit_id = _anycubic_integer(unit.get("id")) if isinstance(unit, dict) else None
        if unit_id is None or not 0 <= unit_id < ANYCUBIC_MAX_BOXES or unit_id in seen:
            complete = False
            continue
        seen.add(unit_id)
        loaded = _anycubic_integer(unit.get("loaded_slot"))
        listed = unit.get("slots") if isinstance(unit.get("slots"), list) else []
        by_index = {}
        for slot in listed:
            index = _anycubic_integer(slot.get("index")) if isinstance(slot, dict) else None
            if index is not None and 0 <= index < ANYCUBIC_SLOTS_PER_BOX:
                by_index.setdefault(index, slot)
        for index in range(ANYCUBIC_SLOTS_PER_BOX):
            if index not in by_index:
                complete = False
            slots.append(_anycubic_box_slot(
                by_index.get(index),
                unit_id * ANYCUBIC_SLOTS_PER_BOX + index,
                "ACE %d slot %d" % (unit_id + 1, index + 1),
                loaded if loaded is not None and loaded >= -1 else None,
            ))
    if isinstance(holder, dict):
        status_type = _anycubic_integer(holder.get("status_type"))
        current = _anycubic_integer(holder.get("current_status"))
        loaded = _anycubic_integer(holder.get("loaded"))
        partial = status_type == -1 and current == -1
        present = None if partial or loaded not in (0, 1) else loaded == 1
        slot = _anycubic_filled(
            holder, ANYCUBIC_EXTERNAL_INDEX, "External spool", "external",
            present is not False,
        )
        slot["present"] = present
        slots.append(slot)
    slots.sort(key=lambda slot: slot["provider_index"])
    return slots, complete and bool(slots)
