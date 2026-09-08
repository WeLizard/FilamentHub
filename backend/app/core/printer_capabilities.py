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
        {"read", "write", "presence", "tag_read"}
    ),
    # The current Edge runtime has no Bambu provider. Pairing can preserve an
    # existing connector identity, but it must not turn that placeholder into
    # read, identity or consumption authority.
    ("bambu", "edge_agent"): frozenset(),
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
    ("legacy", "spoolman_compat"): frozenset(),
    ("legacy", "legacy_adapter"): frozenset(),
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
