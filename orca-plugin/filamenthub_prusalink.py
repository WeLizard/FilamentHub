"""PrusaLink protocol for the FilamentHub OrcaSlicer plugin.

PrusaLink is the local HTTP API of Prusa printers: the Buddy firmware serves it
on the MK4/MK4S, MK3.5/3.9, XL, CORE One and MINI, and the Prusa-Link service
on a Raspberry Pi serves it for the MK3S and MK2.5S. OrcaSlicer keeps the
printer's address and login in its connection settings (host type
``prusalink``): either an API key sent as ``X-Api-Key`` or a user name and
password for HTTP Digest, chosen by ``printhost_authorization_type``. The plugin
reads them from there and asks for nothing.

Two generations of the API answer. Every printer has the OctoPrint-compatible
``/api/version``, ``/api/printer`` and ``/api/job``; Buddy 4.7.0 and later and
Prusa-Link add ``/api/v1/info``, ``/api/v1/status`` and ``/api/v1/job``. Only
the newer one names the printer's serial number, which is what a link is bound
to, so a printer that answers the old API alone is not linked. A profile of
type PrusaLink may also point at a real OctoPrint, which Orca accepts too; that
printer belongs to FilamentHub's OctoPrint bridge.

The local API names no MMU3 slot and no XL tool: Buddy says only whether an MMU
is on, and the material of the tool in use. One spool is shown for a Buddy
printer with one nozzle and no MMU; for the others no slot is claimed. The
printer reports no filament length.

Every field below is taken from the source (prusa3d/Prusa-Firmware-Buddy
b1043d68, prusa3d/Prusa-Link 601c81a6, PoorWSGI 2.7.0 for Prusa-Link's Digest,
OrcaSlicer a0663e6e ``src/slic3r/Utils/OctoPrint.cpp`` class ``PrusaLink``) and
is not confirmed on a printer.

This file holds definitions only: no I/O, no module state and no reference
to the plugin. ``build_package.py`` merges it into the single installable
plugin file, where every name below becomes a plugin global.
"""

import hashlib
import math
import re
import urllib.parse

PRUSALINK_PROVIDER = "prusalink"
PRUSALINK_HOST_TYPE = "prusalink"
PRUSALINK_IDENTITY_KIND = "prusalink_serial"
PRUSALINK_CAPABILITIES = ("read", "presence")
PRUSALINK_DEFAULT_PORT = 80
PRUSALINK_VERSION_PATH = "/api/version"
PRUSALINK_INFO_PATH = "/api/v1/info"
PRUSALINK_STATUS_PATH = "/api/v1/status"
PRUSALINK_JOB_PATH = "/api/v1/job"
# The OctoPrint-compatible reading: the only one that names the loaded material.
PRUSALINK_LEGACY_PRINTER_PATH = "/api/printer"
_PRUSALINK_SERIAL = re.compile(r"[A-Za-z0-9_-]{4,64}")
_PRUSALINK_SECRET = re.compile(r"[\x20-\x7e]{1,256}")
# Buddy model codes ("type.version.subversion" in /api/version) of printers
# with one nozzle; an MMU is reported separately. XL (3.x.x) and the INDX
# tool changers (x.10.x) have several, and an unknown code is not guessed.
_PRUSALINK_SINGLE_NOZZLE_MODELS = frozenset({
    "1.3.5", "1.3.6",  # MK3.5, MK3.5S
    "1.3.9", "1.3.10",  # MK3.9, MK3.9S
    "1.4.0", "1.4.1",  # MK4, MK4S
    "2.1.0",  # MINI
    "7.1.0", "7.2.0", "8.1.0",  # CORE One, CORE One (OAK), CORE One L
})
# What Buddy writes for "no material" (src/common/filament.cpp); Prusa-Link
# always writes " - " because it does not know.
_PRUSALINK_NO_MATERIAL = "---"
_PRUSALINK_STATES = {
    "IDLE": "idle",
    "READY": "idle",
    "PRINTING": "printing",
    "PAUSED": "paused",
    # The printer waits for the person in the middle of a job.
    "ATTENTION": "paused",
    "FINISHED": "finished",
    "STOPPED": "failed",
    "ERROR": "failed",
}
_PRUSALINK_DIGEST_ALGORITHMS = {"MD5": False, "MD5-SESS": True}
_PRUSALINK_AUTH_PARAM = re.compile(
    r'\s*([A-Za-z][A-Za-z0-9_-]*)\s*=\s*(?:"((?:[^"\\]|\\.)*)"|([^\s,"]*))\s*(?:,|$)'
)


def prusalink_endpoint(print_host):
    """Return ``(host, port)`` from Orca's print_host setting, or None.

    The printer serves plain HTTP; an https address is a proxy the plugin does
    not go through, and an address with a path or a login is not a printer.
    """
    raw = str(print_host or "").strip()
    if not raw or len(raw) > 500 or any(ch in raw for ch in "\\\r\n?#@"):
        return None
    try:
        parsed = urllib.parse.urlsplit(
            raw if "://" in raw else "http://" + raw, allow_fragments=False
        )
        host = parsed.hostname or ""
        port = parsed.port
    except (TypeError, ValueError):
        return None
    if parsed.scheme.lower() != "http" or parsed.path not in {"", "/"}:
        return None
    host = host.strip().rstrip(".")
    if not host or len(host) > 253 or any(ch in host for ch in "/\\?#@ "):
        return None
    return host, port or PRUSALINK_DEFAULT_PORT


def prusalink_url(address, port, path):
    """The URL of one API path at an already resolved LAN address."""
    host = "[%s]" % address if ":" in address else address
    return "http://%s:%d%s" % (host, port, path)


def prusalink_credentials(authorization_type, api_key, user, password):
    """How Orca logs in to this printer: a dict, or None when nothing usable is set.

    ``authorization_type`` is ``key`` (Orca's default) or ``user``, as Orca
    writes it; the host may also hand the enum over as 0 or 1.
    """
    kind = str(authorization_type if authorization_type is not None else "").strip().lower()
    if kind in {"", "0", "key"}:
        key = str(api_key or "").strip()
        return {"mode": "key", "key": key} if _PRUSALINK_SECRET.fullmatch(key) else None
    if kind in {"1", "user"}:
        name = str(user or "").strip()
        secret = str(password or "")
        if _PRUSALINK_SECRET.fullmatch(name) and _PRUSALINK_SECRET.fullmatch(secret):
            return {"mode": "digest", "user": name, "password": secret}
    return None


def prusalink_digest_challenge(headers):
    """The Digest challenge among ``WWW-Authenticate`` values, or None.

    Buddy asks for RFC 2069 Digest without ``qop``; Prusa-Link asks for
    ``MD5-sess`` with ``qop="auth"`` and an ``opaque`` value.
    """
    for header in headers or ():
        if not isinstance(header, str):
            continue
        scheme, _space, rest = header.strip().partition(" ")
        if scheme.lower() != "digest":
            continue
        params = {}
        position = 0
        while position < len(rest):
            match = _PRUSALINK_AUTH_PARAM.match(rest, position)
            if match is None or match.end() == position:
                break
            quoted = match.group(2)
            value = re.sub(r"\\(.)", r"\1", quoted) if quoted is not None else match.group(3)
            params[match.group(1).lower()] = value
            position = match.end()
        algorithm = (params.get("algorithm") or "MD5").upper()
        qop = params.get("qop")
        if qop is not None:
            if "auth" not in [item.strip().lower() for item in qop.split(",")]:
                continue
            qop = "auth"
        if (
            algorithm not in _PRUSALINK_DIGEST_ALGORITHMS
            or not params.get("nonce")
            or "realm" not in params
        ):
            continue
        return {
            "realm": params["realm"],
            "nonce": params["nonce"],
            "algorithm": params.get("algorithm"),
            "qop": qop,
            "opaque": params.get("opaque"),
            "stale": (params.get("stale") or "").lower() == "true",
        }
    return None


def _prusalink_md5(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _prusalink_quote(value):
    return '"%s"' % str(value).replace("\\", "\\\\").replace('"', '\\"')


def prusalink_digest_authorization(challenge, method, uri, user, password, cnonce, count):
    """The ``Authorization`` value answering ``challenge`` for one request."""
    algorithm = (challenge.get("algorithm") or "MD5").upper()
    secret = _prusalink_md5("%s:%s:%s" % (user, challenge["realm"], password))
    if _PRUSALINK_DIGEST_ALGORITHMS[algorithm]:
        secret = _prusalink_md5("%s:%s:%s" % (secret, challenge["nonce"], cnonce))
    target = _prusalink_md5("%s:%s" % (method, uri))
    nc = "%08x" % count
    if challenge.get("qop"):
        response = _prusalink_md5(":".join((
            secret, challenge["nonce"], nc, cnonce, challenge["qop"], target,
        )))
    else:
        response = _prusalink_md5("%s:%s:%s" % (secret, challenge["nonce"], target))
    parts = [
        "username=" + _prusalink_quote(user),
        "realm=" + _prusalink_quote(challenge["realm"]),
        "nonce=" + _prusalink_quote(challenge["nonce"]),
        "uri=" + _prusalink_quote(uri),
        "response=" + _prusalink_quote(response),
    ]
    if challenge.get("algorithm"):
        parts.append("algorithm=" + challenge["algorithm"])
    if challenge.get("opaque") is not None:
        parts.append("opaque=" + _prusalink_quote(challenge["opaque"]))
    if challenge.get("qop"):
        parts.extend(("qop=" + challenge["qop"], "nc=" + nc, "cnonce=" + _prusalink_quote(cnonce)))
    return "Digest " + ", ".join(parts)


def prusalink_version_kind(version):
    """Who answers ``/api/version``: ``"prusalink"``, ``"octoprint"`` or None.

    Orca accepts both names for this host type (``validate_version_text``).
    """
    if not isinstance(version, dict) or not version.get("api"):
        return None
    text = version.get("text")
    if not isinstance(text, str):
        return None
    if text.startswith("PrusaLink"):
        return "prusalink"
    if text.startswith("OctoPrint"):
        return "octoprint"
    return None


def prusalink_serial(info):
    """The serial number from ``/api/v1/info``, or ``""``."""
    value = info.get("serial") if isinstance(info, dict) else None
    serial = value.strip() if isinstance(value, str) else ""
    return serial if _PRUSALINK_SERIAL.fullmatch(serial) else ""


def prusalink_single_spool(version, info):
    """Whether one spool feeds this printer for certain.

    Only Buddy names its model; Prusa-Link knows of an MMU but does not say.
    """
    model = version.get("printer") if isinstance(version, dict) else None
    return (
        isinstance(info, dict)
        and info.get("mmu") is False
        and isinstance(model, str)
        and model.strip() in _PRUSALINK_SINGLE_NOZZLE_MODELS
    )


def _prusalink_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _prusalink_job_name(job):
    file = job.get("file") if isinstance(job, dict) else None
    if not isinstance(file, dict):
        return ""
    for key in ("display_name", "name"):
        name = file.get(key)
        if isinstance(name, str) and name.strip():
            return name.replace("\\", "/").rsplit("/", 1)[-1].strip()[:300]
    return ""


def prusalink_printer(status, job=None):
    """Normalize ``/api/v1/status`` (and ``/api/v1/job``) into the bridge contract."""
    printer_status = status.get("printer") if isinstance(status, dict) else None
    printer_status = printer_status if isinstance(printer_status, dict) else {}
    running = status.get("job") if isinstance(status, dict) else None
    running = running if isinstance(running, dict) else None
    code = str(printer_status.get("state") or "").strip().upper()
    if code == "BUSY":
        # Busy with a job is the start or the end of it; busy without one is a
        # command run from the printer's screen.
        state = "printing" if running else "unknown"
    else:
        state = _PRUSALINK_STATES.get(code, "unknown")
    printer = {"state": state}
    if running and state in {"printing", "paused", "preparing", "finished", "failed"}:
        name = _prusalink_job_name(job)
        if name:
            printer["job_name"] = name
        progress = _prusalink_number(running.get("progress"))
        if progress is not None and 0 <= progress <= 100:
            printer["progress_percent"] = round(progress)
        if state in {"printing", "paused", "preparing"}:
            remaining = _prusalink_number(running.get("time_remaining"))
            if remaining is not None and 0 <= remaining <= 2_592_000:
                printer["remaining_seconds"] = int(remaining)
    for key, source, low, high in (
        ("nozzle_temperature", "temp_nozzle", -50, 600),
        ("nozzle_target_temperature", "target_nozzle", 0, 600),
        ("bed_temperature", "temp_bed", -50, 250),
        ("bed_target_temperature", "target_bed", 0, 250),
    ):
        value = _prusalink_number(printer_status.get(source))
        if value is not None and low <= value <= high:
            printer[key] = round(value, 1)
    return printer


def prusalink_slots(version, info, legacy_printer):
    """The printer's feed and whether it is complete: ``(slots, complete)``.

    ``legacy_printer`` is the answer of ``/api/printer``, whose telemetry
    names the material of the tool in use.
    """
    if not prusalink_single_spool(version, info):
        return [], False
    spool = {
        "provider_index": 0,
        "label": "Spool",
        "kind": "external",
        "present": None,
        "spool_identity_known": False,
        # The only feed this printer has.
        "active_feed": True,
    }
    telemetry = legacy_printer.get("telemetry") if isinstance(legacy_printer, dict) else None
    material = telemetry.get("material") if isinstance(telemetry, dict) else None
    material = " ".join(material.split())[:80] if isinstance(material, str) else ""
    if material == _PRUSALINK_NO_MATERIAL:
        spool["present"] = False
    elif material and material.strip("- "):
        spool["present"] = True
        spool["material"] = material
    return [spool], True


def prusalink_capabilities(slots):
    """What this printer's connection can do; presence only where a spool is shown.

    The plugin charges a single-spool printer the slicer's estimate of a job;
    an MMU or an XL names no feeding slot, so nothing is charged there.
    """
    return list(PRUSALINK_CAPABILITIES) + ["consumption"] if slots else ["read"]
