"""Canonical capability vocabulary and manifests for printer adapters."""

from __future__ import annotations

from typing import Literal

CapabilityName = Literal[
    "read",
    "write",
    "presence",
    "spool_identity",
    "consumption",
    "local_command",
    "tag_read",
    "tag_write",
]

CAPABILITY_NAMES: frozenset[str] = frozenset(
    {
        "read",
        "write",
        "presence",
        "spool_identity",
        "consumption",
        "local_command",
        "tag_read",
        "tag_write",
    }
)

# These are capability ceilings, not promises that every runtime instance has
# every capability. Dynamic adapters report the subset their current device and
# configuration can actually provide.
ADAPTER_CAPABILITY_MANIFESTS: dict[tuple[str, str], frozenset[str]] = {
    ("bambu", "orca_plugin_lan"): frozenset(
        {"read", "write", "presence", "tag_read", "consumption"}
    ),
    # Edge holds the printer's LAN MQTT link, reads what the plugin reads and
    # counts a job's filament by the plugin's rules. It does not set a slot's
    # material.
    ("bambu", "edge_agent"): frozenset({"read", "presence", "tag_read", "consumption"}),
    ("octoprint", "bridge_https"): frozenset(
        {"read", "write", "spool_identity", "consumption"}
    ),
    ("moonraker", "edge_agent"): frozenset(
        {"read", "presence", "consumption"}
    ),
    ("happy_hare", "edge_agent"): frozenset(
        {"read", "presence", "spool_identity", "consumption", "tag_read", "local_command"}
    ),
    # The plugin reads Klipper's own extruder counter while OrcaSlicer is open.
    # It reports "consumption" only when Moonraker has no Spoolman link of its
    # own, which would otherwise deduct the same print a second time.
    ("happy_hare", "orca_plugin_lan"): frozenset(
        {"read", "presence", "spool_identity", "tag_read", "consumption"}
    ),
    ("legacy", "orca_plugin_lan"): frozenset({"read", "presence", "consumption"}),
    ("happy_hare", "spoolman_compat"): frozenset(
        {"read", "write", "presence", "spool_identity", "consumption"}
    ),
    ("happy_hare", "legacy_adapter"): frozenset(
        {"read", "write", "presence", "spool_identity", "consumption"}
    ),
    # Flashforge's LAN API reports no spool identity and no measured usage,
    # only the slicer's estimate for the job. Whoever watches the print counts
    # that estimate by progress: Edge always, the plugin while OrcaSlicer is
    # open.
    ("flashforge", "edge_agent"): frozenset({"read", "presence", "consumption"}),
    # Only the plugin sets a station slot's material, and only a station has
    # slots to set: a single-spool printer does not report this capability.
    ("flashforge", "orca_plugin_lan"): frozenset(
        {"read", "presence", "consumption", "write"}
    ),
    # Creality's stock firmware reports its CFS slots and the length of filament
    # a job has used, and takes no spool identity. The plugin only reads it.
    ("creality", "orca_plugin_lan"): frozenset({"read", "presence", "consumption"}),
    # PrusaLink, the local HTTP API of Buddy firmware and of Prusa-Link, gives the
    # printer's state and, on a single-nozzle printer without an MMU, the material
    # loaded. It names no MMU slot or XL tool and counts no filament. The plugin
    # only reads it.
    ("prusalink", "orca_plugin_lan"): frozenset({"read", "presence"}),
    # SDCP (Chitu's open protocol; the Elegoo Centauri Carbon speaks it) and
    # Elegoo's MQTT API (the Centauri Carbon 2) report the print and the CANVAS
    # slots, and count no filament a job uses. The plugin and Edge only read them.
    ("sdcp", "orca_plugin_lan"): frozenset({"read", "presence"}),
    ("sdcp", "edge_agent"): frozenset({"read", "presence"}),
    ("elegoo_mqtt", "orca_plugin_lan"): frozenset({"read", "presence"}),
    ("elegoo_mqtt", "edge_agent"): frozenset({"read", "presence"}),
    ("legacy", "spoolman_compat"): frozenset(),
    ("legacy", "legacy_adapter"): frozenset(),
}


# The needs every connection is measured against. The remaining names
# (local_command, tag_write) are operations a few adapters offer, not something
# every printer owner expects, and stay outside this rule.
PARITY_CAPABILITIES: tuple[str, ...] = (
    "read",
    "presence",
    "spool_identity",
    "consumption",
    "write",
    "tag_read",
)

GapKind = Literal["device", "elsewhere", "planned"]
# Why a connection lacks a need. "device": the printer or its API cannot
# provide it. "elsewhere": the same printer gets it through another
# connection. "planned": it can be built and has not been yet. A connection
# may lack a need only for a reason written here; the "planned" entries are the
# list of what is left to do.
_NO_SPOOL_ON_BAMBU = (
    "device",
    "The printer identifies its own RFID tags, never a FilamentHub spool; tag_read carries "
    "what it knows.",
)
_BAMBU_EDGE_WRITE = (
    "planned",
    "Setting a slot's material needs the Bambu filament code the plugin takes from "
    "OrcaSlicer's presets; Edge has no source for it yet.",
)
_HAPPY_HARE_SPOOLMAN = (
    "elsewhere",
    "Happy Hare takes assignments and reports usage through its own Spoolman connection.",
)
_TAGS_NOT_ON_SPOOLMAN = (
    "elsewhere",
    "A tag seen in a slot is reported by Edge or the plugin; this connection carries "
    "spools and usage only.",
)
_FLASHFORGE_NO_SPOOL = (
    "device",
    "The printer knows the material set on it, never which spool is loaded.",
)
_FLASHFORGE_NO_READER = ("device", "The printer has no tag reader.")
_FLASHFORGE_EDGE_WRITE = (
    "planned",
    "The plugin sets a station slot when an assignment is saved inside OrcaSlicer. Edge "
    "sends a printer nothing unless its connection opts in, and that delivery is not built "
    "for Flashforge.",
)
_KLIPPER_ELSEWHERE = (
    "elsewhere",
    "A Klipper printer without an MMU reports through Moonraker's own Spoolman connection "
    "and through Edge; this connection grants nothing itself.",
)
_KLIPPER_NO_SLOT_TO_SET = (
    "device",
    "A Klipper printer without an MMU has no slot whose material could be set.",
)
_KLIPPER_NAMES_NO_SPOOL = (
    "device",
    "Klipper names no spool; the assignment made on the site is the only link.",
)
_KLIPPER_NO_READER = ("device", "A Klipper printer without an MMU has no tag reader.")
# What SDCP and Elegoo's MQTT API lack alike: both carry the same CANVAS slots.
_CANVAS_READ_ONLY: dict[str, tuple[GapKind, str]] = {
    "consumption": (
        "planned",
        "The printer reports no filament used; counting the slicer's estimate by "
        "progress, as for Flashforge, is not built yet.",
    ),
    "write": (
        "planned",
        "The plugin and Edge only read; setting a CANVAS slot's material is not built yet.",
    ),
    "spool_identity": (
        "device",
        "The printer knows the material in a slot, never which spool is loaded.",
    ),
    "tag_read": (
        "planned",
        "FilamentHub reads no spool tag from these printers yet.",
    ),
}

ADAPTER_CAPABILITY_GAPS: dict[tuple[str, str], dict[str, tuple[GapKind, str]]] = {
    ("bambu", "orca_plugin_lan"): {"spool_identity": _NO_SPOOL_ON_BAMBU},
    ("bambu", "edge_agent"): {
        "write": _BAMBU_EDGE_WRITE,
        "spool_identity": _NO_SPOOL_ON_BAMBU,
    },
    ("octoprint", "bridge_https"): {
        "presence": ("device", "OctoPrint does not know whether filament is loaded."),
        "tag_read": ("device", "No tag reader is reachable through OctoPrint."),
    },
    ("moonraker", "edge_agent"): {
        "write": _KLIPPER_NO_SLOT_TO_SET,
        "spool_identity": _KLIPPER_NAMES_NO_SPOOL,
        "tag_read": _KLIPPER_NO_READER,
    },
    ("happy_hare", "edge_agent"): {"write": _HAPPY_HARE_SPOOLMAN},
    ("happy_hare", "orca_plugin_lan"): {"write": _HAPPY_HARE_SPOOLMAN},
    ("legacy", "orca_plugin_lan"): {
        "write": _KLIPPER_NO_SLOT_TO_SET,
        "spool_identity": _KLIPPER_NAMES_NO_SPOOL,
        "tag_read": _KLIPPER_NO_READER,
    },
    ("happy_hare", "spoolman_compat"): {"tag_read": _TAGS_NOT_ON_SPOOLMAN},
    ("happy_hare", "legacy_adapter"): {"tag_read": _TAGS_NOT_ON_SPOOLMAN},
    ("flashforge", "edge_agent"): {
        "write": _FLASHFORGE_EDGE_WRITE,
        "spool_identity": _FLASHFORGE_NO_SPOOL,
        "tag_read": _FLASHFORGE_NO_READER,
    },
    ("flashforge", "orca_plugin_lan"): {
        "spool_identity": _FLASHFORGE_NO_SPOOL,
        "tag_read": _FLASHFORGE_NO_READER,
    },
    ("creality", "orca_plugin_lan"): {
        "write": (
            "planned",
            "The printer accepts a slot's material over its LAN channel; the plugin does not "
            "send it yet.",
        ),
        "spool_identity": (
            "device",
            "The printer knows the material in a slot, never which spool is loaded.",
        ),
        "tag_read": (
            "planned",
            "A CFS reads the tag of a Creality spool and reports only what it found on it; "
            "FilamentHub does not match that to a spool yet.",
        ),
    },
    ("prusalink", "orca_plugin_lan"): {
        "write": (
            "device",
            "PrusaLink has no request that sets the material of a slot or a tool.",
        ),
        "spool_identity": (
            "device",
            "The printer knows at most the material type loaded, never which spool.",
        ),
        "consumption": (
            "planned",
            "The printer reports no filament length. The slicer's estimate scaled by the "
            "job's progress could be counted, as for Flashforge; it is not built.",
        ),
        "tag_read": ("device", "The local API reports no spool tag."),
    },
    ("sdcp", "orca_plugin_lan"): _CANVAS_READ_ONLY,
    ("sdcp", "edge_agent"): _CANVAS_READ_ONLY,
    ("elegoo_mqtt", "orca_plugin_lan"): _CANVAS_READ_ONLY,
    ("elegoo_mqtt", "edge_agent"): _CANVAS_READ_ONLY,
    ("legacy", "spoolman_compat"): dict.fromkeys(PARITY_CAPABILITIES, _KLIPPER_ELSEWHERE),
    ("legacy", "legacy_adapter"): dict.fromkeys(PARITY_CAPABILITIES, _KLIPPER_ELSEWHERE),
}


def capability_ceiling(*, provider: str, transport: str) -> frozenset[str]:
    """Return the known ceiling, retaining vocabulary compatibility for new adapters."""
    return ADAPTER_CAPABILITY_MANIFESTS.get((provider, transport), CAPABILITY_NAMES)


def normalize_capabilities(
    values: list[str],
    *,
    provider: str | None = None,
    transport: str | None = None,
) -> list[str]:
    """Keep a deterministic supported subset without trusting adapter claims."""
    allowed = (
        capability_ceiling(provider=provider, transport=transport)
        if provider is not None and transport is not None
        else CAPABILITY_NAMES
    )
    return sorted(set(values).intersection(allowed))


def has_capability(
    values: list[str],
    capability: str,
    *,
    provider: str,
    transport: str,
) -> bool:
    """Check an operation against both the stored grant and its adapter ceiling."""
    return capability in normalize_capabilities(
        values,
        provider=provider,
        transport=transport,
    )
