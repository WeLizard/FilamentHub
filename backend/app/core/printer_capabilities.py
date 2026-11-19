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
        {"read", "presence", "spool_identity", "consumption", "tag_read"}
    ),
    ("happy_hare", "orca_plugin_lan"): frozenset(
        {"read", "presence", "spool_identity", "tag_read"}
    ),
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
        "write": (
            "device",
            "A Klipper printer without an MMU has no slot whose material could be set.",
        ),
        "spool_identity": (
            "device",
            "Klipper names no spool; the assignment made on the site is the only link.",
        ),
        "tag_read": ("device", "A Klipper printer without an MMU has no tag reader."),
    },
    ("happy_hare", "edge_agent"): {"write": _HAPPY_HARE_SPOOLMAN},
    ("happy_hare", "orca_plugin_lan"): {
        "write": _HAPPY_HARE_SPOOLMAN,
        "consumption": _HAPPY_HARE_SPOOLMAN,
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
