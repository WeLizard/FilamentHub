"""Security boundary for opaque OrcaSlicer preset settings."""

from __future__ import annotations

from typing import Any, Literal

OrcaPresetScope = Literal["filament", "process", "machine"]

# These values identify or authenticate a physical print host. They belong to
# the dedicated printer connection/adapter flow, never to a reusable machine
# preset. Current plugins already omit them; the server repeats the boundary so
# old or hostile clients cannot persist them in opaque profile JSON.
ORCA_MACHINE_CONNECTION_KEYS = frozenset(
    {
        "preset_name",
        "preset_names",
        "host_type",
        "printer_agent",
        "print_host",
        "print_host_webui",
        "printhost_port",
        "printhost_apikey",
        "printhost_user",
        "printhost_password",
        "printhost_cafile",
        "printhost_ssl_ignore_revoke",
        "printhost_authorization_type",
        "flashforge_serial_number",
        "bbl_use_printhost",
        "bbl_use_print_host_webui",
    }
)


def sanitize_orca_settings_for_storage(
    settings: dict[str, Any] | None,
    scope: OrcaPresetScope,
) -> dict[str, Any]:
    """Copy settings while removing connection data from machine profiles."""

    if not settings:
        return {}
    if scope != "machine":
        return dict(settings)
    return {
        key: value
        for key, value in settings.items()
        if key not in ORCA_MACHINE_CONNECTION_KEYS
    }
