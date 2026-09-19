"""The capability vocabulary and adapter ceilings have one server authority."""

from types import SimpleNamespace

import pytest

from app.core.printer_capabilities import (
    ADAPTER_CAPABILITY_MANIFESTS,
    CAPABILITY_NAMES,
    capability_ceiling,
    has_capability,
    normalize_capabilities,
)
from app.services.printer_bridge_service import require_printer_bridge_capability


def test_every_adapter_manifest_uses_only_canonical_capabilities() -> None:
    assert ADAPTER_CAPABILITY_MANIFESTS
    assert all(
        capabilities <= CAPABILITY_NAMES
        for capabilities in ADAPTER_CAPABILITY_MANIFESTS.values()
    )


def test_known_adapter_is_bounded_by_its_manifest() -> None:
    assert normalize_capabilities(
        ["presence", "consumption", "read", "future_capability"],
        provider="octoprint",
        transport="bridge_https",
    ) == ["consumption", "read"]


@pytest.mark.parametrize(
    ("provider", "transport", "expected"),
    [
        (
            "happy_hare",
            "orca_plugin_lan",
            ["presence", "read", "spool_identity", "tag_read"],
        ),
        (
            "happy_hare",
            "spoolman_compat",
            ["consumption", "presence", "read", "spool_identity", "write"],
        ),
        (
            "happy_hare",
            "legacy_adapter",
            ["consumption", "presence", "read", "spool_identity", "write"],
        ),
        ("legacy", "spoolman_compat", []),
        ("legacy", "legacy_adapter", []),
    ],
)
def test_legacy_adapter_manifest_is_explicit(
    provider: str,
    transport: str,
    expected: list[str],
) -> None:
    assert normalize_capabilities(
        [*CAPABILITY_NAMES, "future_capability"],
        provider=provider,
        transport=transport,
    ) == expected


def test_unknown_adapter_keeps_forward_compatible_known_vocabulary() -> None:
    assert capability_ceiling(provider="future", transport="edge_agent") == CAPABILITY_NAMES
    assert normalize_capabilities(
        ["read", "future_capability"],
        provider="future",
        transport="edge_agent",
    ) == ["read"]


def test_operation_guard_accepts_declared_bambu_orca_consumption() -> None:
    connector = SimpleNamespace(
        provider="bambu",
        transport="orca_plugin_lan",
        capabilities=["read", "consumption"],
    )

    require_printer_bridge_capability(connector, "consumption")


def test_route_proof_gate_accepts_declared_bambu_orca_consumption() -> None:
    assert has_capability(
        ["read", "consumption"],
        "consumption",
        provider="bambu",
        transport="orca_plugin_lan",
    )
